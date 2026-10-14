"""Durable Telegram ingress and egress using python-telegram-bot's async Bot API."""
import asyncio
import json
import logging
import random
import time
from datetime import timedelta

from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.error import BadRequest, Conflict, Forbidden, NetworkError, RetryAfter, TelegramError

from .db import enqueue

log = logging.getLogger(__name__)
ALLOWED_METHODS = {'send_message', 'copy_message', 'send_photo', 'send_document', 'answer_callback_query'}


class Transport:
    def __init__(self, bot, db, service):
        self.bot, self.db, self.service = bot, db, service
        self.next_chat = {}
        self.next_global = 0.0
        self.last_poll_at = time.time()

    async def poll(self):
        while True:
            try:
                offset = await asyncio.to_thread(self.db.offset)
                updates = await self.bot.get_updates(offset=offset, timeout=25,
                                                     allowed_updates=['message', 'callback_query'],
                                                     read_timeout=35)
                # Commit the batch and next offset before acknowledging it on the next request.
                await asyncio.to_thread(self.db.ingest, [json.loads(u.to_json()) for u in updates])
                self.last_poll_at = time.time()
            except Conflict:
                log.critical('Another Telegram poller or webhook is using this token; stopping poller')
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning('poll_retry error_type=%s', type(exc).__name__)
                await asyncio.sleep(5)

    async def process(self):
        while True:
            try:
                worked = await asyncio.to_thread(self.service.process_one)
                if not worked:
                    await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error('inbox_worker_retry error_type=%s', type(exc).__name__)
                await asyncio.sleep(2)

    def candidates(self):
        # Prioritize callback acknowledgements. Preserve FIFO for messages to each chat.
        return self.db.read('''SELECT o.* FROM notification_outbox o
          WHERE o.status='PENDING' AND o.next_at<=? AND NOT EXISTS (
            SELECT 1 FROM notification_outbox p WHERE p.status='PENDING' AND p.id<o.id
            AND json_extract(p.payload_json,'$.chat_id')=json_extract(o.payload_json,'$.chat_id')
          ) ORDER BY CASE WHEN json_extract(o.payload_json,'$.method')='answer_callback_query' THEN 0 ELSE 1 END,o.id LIMIT 100''', (time.time(),))

    def mark_sent(self, row, payload, result):
        with self.db.transaction() as c:
            mapping = payload.get('_mapping')
            if mapping:
                c.execute('''INSERT OR IGNORE INTO message_mappings
                    (admin_chat_id,admin_message_id,user_id,user_chat_id,support_session_id,route_id,outbox_id,created_at)
                    VALUES (?,?,?,?,?,?,?,?)''',
                          (payload['chat_id'], result.message_id, mapping['user_id'], mapping['user_chat_id'],
                           mapping['support_session_id'], mapping['route_id'], row['id'], time.time()))
            # Do not retain sent prefilled bearer tokens or copies of message content.
            c.execute("UPDATE notification_outbox SET status='SENT',payload_json='{}',attempts=attempts+1,last_error=NULL WHERE id=?",
                      (row['id'],))

    def mark_failed(self, row, payload, error, delay, permanent=False):
        attempt = row['attempts'] + 1
        with self.db.transaction() as c:
            c.execute('UPDATE notification_outbox SET status=?,attempts=?,next_at=?,last_error=? WHERE id=?',
                      ('DEAD' if permanent else 'PENDING', attempt, time.time() + delay, error, row['id']))
            if permanent and payload['method'] != 'answer_callback_query':
                log.error('outbox_dead id=%s target=%s error_type=%s', row['id'], payload.get('chat_id'), error)
                if payload.get('chat_id') != self.service.s.admin_chat_id:
                    enqueue(c, 'send_message', chat_id=self.service.s.admin_chat_id,
                            text=f"⚠️ 通知发送失败，任务 #{row['id']}，客户 {payload.get('chat_id')}，错误类型 {error}。请人工跟进。")
            elif attempt in (5, 20):
                log.error('outbox_backlog id=%s attempt=%s error_type=%s', row['id'], attempt, error)

    async def deliver(self, row):
        payload = json.loads(row['payload_json'])
        kwargs = {k: v for k, v in payload.items() if k != 'method' and not k.startswith('_')}
        method = payload['method']
        try:
            if method not in ALLOWED_METHODS:
                raise ValueError('Invalid outbox method')
            if 'reply_markup' in kwargs:
                markup = kwargs['reply_markup']
                cls = InlineKeyboardMarkup if 'inline_keyboard' in markup else ReplyKeyboardMarkup
                kwargs['reply_markup'] = cls.de_json(markup, self.bot)
            result = await getattr(self.bot, method)(**kwargs)
            await asyncio.to_thread(self.mark_sent, row, payload, result)
        except asyncio.CancelledError:
            raise
        except RetryAfter as exc:
            seconds = exc.retry_after.total_seconds() if isinstance(exc.retry_after, timedelta) else float(exc.retry_after)
            self.next_global = time.time() + seconds + 1
            await asyncio.to_thread(self.mark_failed, row, payload, 'RetryAfter', seconds + 1)
        except (Forbidden, BadRequest) as exc:
            # Stale callback-query IDs must not block the queue or undo successful business work.
            await asyncio.to_thread(self.mark_failed, row, payload, type(exc).__name__, 0, True)
        except (NetworkError, TelegramError) as exc:
            delay = min(3600, 2 ** min(row['attempts'] + 1, 11)) + random.random()
            await asyncio.to_thread(self.mark_failed, row, payload, type(exc).__name__, delay)
        except Exception as exc:
            # A SQLite write can fail after Telegram accepted the message. Retry may duplicate it.
            await asyncio.to_thread(self.mark_failed, row, payload, type(exc).__name__, 30)

    async def send(self):
        while True:
            try:
                if self.next_global > time.time():
                    await asyncio.sleep(0.2)
                    continue
                rows = await asyncio.to_thread(self.candidates)
                chosen = None
                for row in rows:
                    p = json.loads(row['payload_json'])
                    cid = p.get('chat_id')
                    if cid is None or self.next_chat.get(cid, 0) <= time.time():
                        chosen = row
                        break
                if chosen:
                    p = json.loads(chosen['payload_json'])
                    cid = p.get('chat_id')
                    await self.deliver(chosen)
                    if cid is not None:
                        self.next_chat[cid] = time.time() + (3.1 if cid < 0 else 1.05)
                    self.next_global = max(self.next_global, time.time() + 0.05)
                else:
                    await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error('outbox_worker_retry error_type=%s', type(exc).__name__)
                await asyncio.sleep(2)
