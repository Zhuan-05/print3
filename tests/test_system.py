import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
import secrets
import sqlite3
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import pytest
from telegram.error import Forbidden, NetworkError

from app.config import Settings
from app.db import Database, enqueue
from app.service import Service, price_sen
from app.transport import Transport
from app.web import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings('123456:TEST_TOKEN', -100123456, frozenset({999}), 'a' * 64,
                    'FORM_ID', 'https://docs.google.com/forms/d/e/PUBLIC/viewform',
                    'entry.111', 'entry.222', str(tmp_path / 'orders.db'))


@pytest.fixture
def system(settings):
    db = Database(settings.db_path)
    db.initialize()
    return db, Service(db, settings)


def incoming(db, service, n, uid=101, text=None, photo=False, group=False, reply=None):
    m = {'message_id': n, 'from': {'id': uid, 'is_bot': False},
         'chat': {'id': service.s.admin_chat_id if group else uid, 'type': 'supergroup' if group else 'private'}}
    if text is not None:
        m['text'] = text
    if photo:
        m['photo'] = [{'file_id': 'photo_file_id', 'file_size': 512}]
    if reply:
        m['reply_to_message'] = {'message_id': reply}
    db.ingest([{'update_id': n, 'message': m}])
    while service.process_one():
        pass


def callback(db, service, n, uid, data, group=False):
    q = {'id': f'cb{n}', 'from': {'id': uid}, 'data': data,
         'message': {'message_id': 2000, 'chat': {'id': service.s.admin_chat_id if group else uid}}}
    db.ingest([{'update_id': n, 'callback_query': q}])
    while service.process_one():
        pass


def form_payload(db, service, uid=101, response='response1', issued_offset=-10, expires_offset=86400):
    token = secrets.token_urlsafe(32)
    now = time.time()
    with db.transaction() as c:
        c.execute('INSERT OR IGNORE INTO user_sessions(user_id,chat_id,created_at) VALUES (?,?,?)', (uid, uid, now))
        c.execute('INSERT INTO binding_tokens(token_hash,user_id,issued_at,expires_at) VALUES (?,?,?,?)',
                  (sha256(token.encode()).hexdigest(), uid, now + issued_offset, now + expires_offset))
    return {'schema_version': 1, 'source': 'google_forms', 'form_id': 'FORM_ID',
            'response_id': response, 'event_id': 'FORM_ID:' + response,
            'submitted_at': datetime.now(timezone.utc).isoformat(), 'telegram_id': str(uid),
            'binding_token': token, 'requirements': {'layer_height_mm': '0.20', 'infill_percent': '20', 'material': 'PLA'},
            'files': [{'file_id': 'file123', 'name': 'part.stl', 'size_bytes': 100,
                       'view_url': 'https://drive.google.com/file/d/file123/view',
                       'download_url': 'https://drive.google.com/uc?id=file123&export=download'}], 'validation_errors': []}


def status(db, oid=1):
    return db.read('SELECT status FROM orders WHERE id=?', (oid,))[0]['status']


def messages(db):
    return [json.loads(r['payload_json']) for r in db.read("SELECT payload_json FROM notification_outbox ORDER BY id")]


def test_webhook_auth_and_ack(settings):
    app = create_app(settings, telegram_enabled=False)
    with TestClient(app) as client:
        db, svc = app.state.db, app.state.service
        p = form_payload(db, svc)
        assert client.post('/webhooks/google-form', json=p).status_code == 401
        assert client.post('/webhooks/google-form', json=p, headers={'X-Webhook-Secret': 'wrong'}).status_code == 401
        assert not db.read('SELECT * FROM orders')
        headers = {'X-Webhook-Secret': settings.webhook_secret}
        first = client.post('/webhooks/google-form', json=p, headers=headers)
        assert first.status_code == 200 and first.json()['disposition'] == 'created'
        assert client.post('/webhooks/google-form', json=p, headers=headers).json()['disposition'] == 'duplicate'
        assert client.get('/healthz').json() == {'ok': True}


@pytest.mark.parametrize('bad', ['', 'abc', '1.5', '-1', '9007199254740992', None, 101, True])
def test_invalid_id_quarantine(system, bad):
    db, svc = system
    p = form_payload(db, svc)
    p['telegram_id'] = bad
    assert svc.accept_form(p)['disposition'] == 'quarantined'
    assert not db.read('SELECT * FROM orders')
    event = db.read('SELECT * FROM webhook_events')[0]
    assert 'INVALID_TELEGRAM_ID' in event['reasons_json']
    assert any(m.get('chat_id') == svc.s.admin_chat_id and '隔离' in m.get('text', '') for m in messages(db))
    assert p['binding_token'] not in event['reasons_json']


def test_tamper_replay_and_expiry(system):
    db, svc = system
    p = form_payload(db, svc)
    p['telegram_id'] = '202'
    assert svc.accept_form(p)['disposition'] == 'quarantined'
    p = form_payload(db, svc, response='valid')
    assert svc.accept_form(p)['disposition'] == 'created'
    p['response_id'], p['event_id'] = 'replay', 'FORM_ID:replay'
    assert svc.accept_form(p)['disposition'] == 'quarantined'
    p = form_payload(db, svc, response='expired', issued_offset=-90000, expires_offset=-1)
    assert svc.accept_form(p)['disposition'] == 'quarantined'
    assert len(db.read('SELECT * FROM orders')) == 1


def test_delayed_delivery_uses_submit_time(system):
    db, svc = system
    p = form_payload(db, svc, issued_offset=-90000, expires_offset=-100)
    p['submitted_at'] = datetime.fromtimestamp(time.time() - 200, timezone.utc).isoformat()
    assert svc.accept_form(p)['disposition'] == 'created'


def test_concurrent_idempotency(system):
    db, svc = system
    p = form_payload(db, svc)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: svc.accept_form(p), range(12)))
    assert sum(r['disposition'] == 'created' for r in results) == 1
    assert len(db.read('SELECT * FROM orders')) == 1
    assert len(db.read('SELECT * FROM notification_outbox')) == 3


def test_start_link_matches_hash_and_user(system):
    db, svc = system
    incoming(db, svc, 1, text='/start')
    link = next(m['reply_markup']['inline_keyboard'][0][0]['url'] for m in messages(db)
                if m.get('reply_markup', {}).get('inline_keyboard'))
    query = parse_qs(urlsplit(link).query)
    token = query['entry.222'][0]
    assert query['entry.111'] == ['101']
    assert db.read('SELECT token_hash FROM binding_tokens')[0]['token_hash'] == sha256(token.encode()).hexdigest()
    # Duplicated Telegram updates do not issue another link.
    incoming(db, svc, 1, text='/start')
    assert len(db.read('SELECT * FROM binding_tokens')) == 1


def test_payment_permissions_versions_and_completion(system):
    db, svc = system
    svc.accept_form(form_payload(db, svc))
    incoming(db, svc, 1, photo=True)
    assert status(db) == 'PENDING_QUOTE' and not db.read('SELECT * FROM payment_proofs')
    incoming(db, svc, 2, uid=888, group=True, text='/quote 1 35.50')
    assert status(db) == 'PENDING_QUOTE'
    incoming(db, svc, 3, uid=999, group=True, text='/quote 1 35.50')
    assert status(db) == 'AWAITING_PAYMENT'
    callback(db, svc, 4, 202, 'pay:1')
    incoming(db, svc, 5, uid=202, photo=True)
    assert not db.read('SELECT * FROM payment_proofs')
    callback(db, svc, 6, 101, 'pay:1')
    incoming(db, svc, 7, photo=True)
    assert status(db) == 'PAYMENT_REVIEW'
    callback(db, svc, 8, 888, 'approve:1:1', group=True)
    assert status(db) == 'PAYMENT_REVIEW'
    callback(db, svc, 9, 999, 'reject:1:1', group=True)
    assert status(db) == 'AWAITING_PAYMENT'
    callback(db, svc, 10, 101, 'pay:1')
    incoming(db, svc, 11, photo=True)
    callback(db, svc, 12, 999, 'approve:1:1', group=True)
    assert status(db) == 'PAYMENT_REVIEW'
    callback(db, svc, 13, 999, 'approve:1:2', group=True)
    callback(db, svc, 14, 999, 'approve:1:2', group=True)
    assert status(db) == 'PROCESSING'
    assert len(db.read("SELECT * FROM audit_log WHERE action='APPROVE_PAYMENT'")) == 1
    incoming(db, svc, 15, uid=999, group=True, text='/complete 1')
    assert status(db) == 'COMPLETED'


def test_payment_support_independent(system):
    db, svc = system
    svc.accept_form(form_payload(db, svc))
    incoming(db, svc, 1, uid=999, group=True, text='/quote 1 20')
    incoming(db, svc, 2, text='联系人工')
    incoming(db, svc, 3, photo=True)
    assert status(db) == 'AWAITING_PAYMENT'
    callback(db, svc, 4, 101, 'pay:1')
    incoming(db, svc, 5, photo=True)
    assert status(db) == 'PAYMENT_REVIEW'
    assert db.read('SELECT mode FROM user_sessions WHERE user_id=101')[0]['mode'] == 'HUMAN_SUPPORT'


def test_mapping_survives_restart_and_ended_sessions(system):
    db, svc = system
    incoming(db, svc, 1, text='联系人工')
    incoming(db, svc, 2, text='这个模型能打印吗？')
    row = next(r for r in db.read('SELECT * FROM notification_outbox')
               if json.loads(r['payload_json'])['method'] == 'copy_message')
    payload = json.loads(row['payload_json'])
    Transport(None, db, svc).mark_sent(row, payload, SimpleNamespace(message_id=777))
    db2 = Database(db.path)
    svc2 = Service(db2, svc.s)
    incoming(db2, svc2, 3, uid=999, group=True, text='可以，请提供尺寸', reply=777)
    assert any(m.get('method') == 'copy_message' and m.get('chat_id') == 101 and m.get('message_id') == 3 for m in messages(db2))
    incoming(db2, svc2, 4, text='/end')
    count = len([m for m in messages(db2) if m.get('method') == 'copy_message'])
    incoming(db2, svc2, 5, uid=999, group=True, text='旧会话回复', reply=777)
    assert len([m for m in messages(db2) if m.get('method') == 'copy_message']) == count


def test_mapping_chat_scope_and_manual_recovery(system):
    db, svc = system
    incoming(db, svc, 1, text='联系人工')
    rid = db.read('SELECT route_id FROM support_routes')[0]['route_id']
    incoming(db, svc, 2, uid=999, group=True, text='/reply ' + rid + ' 收到')
    assert any(m.get('chat_id') == 101 and m.get('text') == '收到' for m in messages(db))
    incoming(db, svc, 3, uid=999, group=True, text='未知消息回复', reply=999999)
    assert any('找不到有效客服映射' in m.get('text', '') for m in messages(db))


def test_outbox_recovers_retries_and_scrubs(system):
    db, svc = system
    with db.transaction() as c:
        enqueue(c, 'send_message', chat_id=101, text='persisted message')
    class FakeBot:
        fail = True
        async def send_message(self, **kwargs):
            if self.fail:
                raise NetworkError('network unavailable')
            return SimpleNamespace(message_id=123)
    bot = FakeBot()
    transport = Transport(bot, db, svc)
    row = db.read('SELECT * FROM notification_outbox')[0]
    asyncio.run(transport.deliver(row))
    assert db.read('SELECT status,attempts FROM notification_outbox')[0] == {'status': 'PENDING', 'attempts': 1}
    bot.fail = False
    restarted = Transport(bot, Database(db.path), svc)
    asyncio.run(restarted.deliver(db.read('SELECT * FROM notification_outbox')[0]))
    assert db.read('SELECT status,payload_json FROM notification_outbox')[0] == {'status': 'SENT', 'payload_json': '{}'}


def test_inbox_business_rollback(system, monkeypatch):
    db, svc = system
    def broken(c, update):
        enqueue(c, 'send_message', chat_id=101, text='must rollback')
        raise RuntimeError('failure')
    monkeypatch.setattr(svc, 'handle', broken)
    db.ingest([{'update_id': 1, 'message': {}}])
    assert svc.process_one()
    assert not db.read('SELECT * FROM notification_outbox')
    assert db.read('SELECT attempts FROM telegram_inbox')[0]['attempts'] == 1


def test_http_limits_and_storage_rollback(settings, monkeypatch):
    app = create_app(settings, telegram_enabled=False)
    with TestClient(app) as client:
        headers = {'X-Webhook-Secret': settings.webhook_secret, 'Content-Type': 'application/json'}
        assert client.post('/webhooks/google-form', content='x' * 32769, headers=headers).status_code == 413
        assert client.post('/webhooks/google-form', content='{', headers=headers).status_code == 400
        p = form_payload(app.state.db, app.state.service)
        import app.service as module
        def fail(*args, **kwargs):
            raise sqlite3.OperationalError('simulated storage error')
        monkeypatch.setattr(module, 'notify', fail)
        assert client.post('/webhooks/google-form', json=p, headers=headers).status_code == 503
        assert not app.state.db.read('SELECT * FROM orders')
        assert not app.state.db.read('SELECT * FROM webhook_events')


@pytest.mark.parametrize('raw', ['NaN', '1e3', '-1', '0', '1.001', '100000.01', 'inf'])
def test_money_rejects_invalid(raw):
    with pytest.raises(ValueError):
        price_sen(raw)


def test_environment_loading(monkeypatch, tmp_path):
    env = {'BOT_TOKEN': '123456:TEST_TOKEN', 'ADMIN_CHAT_ID': '-100123456', 'ADMIN_USER_IDS': '999,888',
           'WEBHOOK_SECRET': 'b' * 64, 'GOOGLE_FORM_ID': 'FORM_ID',
           'GOOGLE_FORM_URL': 'https://docs.google.com/forms/d/e/PUBLIC/viewform',
           'FORM_TELEGRAM_ENTRY': 'entry.111', 'FORM_BINDING_ENTRY': 'entry.222',
           'DATABASE_PATH': str(tmp_path / 'db.sqlite3')}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert Settings.load().admin_user_ids == frozenset({999, 888})
    monkeypatch.setenv('FORM_BINDING_ENTRY', 'entry.111')
    with pytest.raises(ValueError):
        Settings.load()


def test_telegram_markup_delivery_and_permanent_failure(system):
    db, svc = system
    incoming(db, svc, 1, text='/start')
    class FakeBot:
        forbidden = False
        async def send_message(self, **kwargs):
            if self.forbidden:
                raise Forbidden('blocked')
            assert not isinstance(kwargs.get('reply_markup'), dict)
            return SimpleNamespace(message_id=88)
    bot = FakeBot()
    transport = Transport(bot, db, svc)
    rows = db.read('SELECT * FROM notification_outbox')
    asyncio.run(transport.deliver(rows[0]))
    asyncio.run(transport.deliver(rows[1]))
    assert all(r['status'] == 'SENT' for r in db.read('SELECT status FROM notification_outbox'))
    with db.transaction() as c:
        mid = enqueue(c, 'send_message', chat_id=101, text='blocked message')
    bot.forbidden = True
    asyncio.run(transport.deliver(db.read('SELECT * FROM notification_outbox WHERE id=?', (mid,))[0]))
    assert db.read('SELECT status FROM notification_outbox WHERE id=?', (mid,))[0]['status'] == 'DEAD'
    assert any('通知发送失败' in m.get('text', '') for m in messages(db))


def test_callback_ack_prioritized_and_chat_fifo(system):
    db, svc = system
    with db.transaction() as c:
        first = enqueue(c, 'send_message', chat_id=101, text='first')
        enqueue(c, 'send_message', chat_id=101, text='second')
        other = enqueue(c, 'send_message', chat_id=202, text='other')
        callback_id = enqueue(c, 'answer_callback_query', callback_query_id='a', text='ok')
        c.execute('UPDATE notification_outbox SET next_at=? WHERE id=?', (time.time() + 100, first))
    ids = [r['id'] for r in Transport(None, db, svc).candidates()]
    assert ids == [callback_id, other]
