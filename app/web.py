import asyncio
from contextlib import asynccontextmanager
import fcntl
import hmac
import json
import logging
from pathlib import Path
import sqlite3
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from telegram import Bot
from telegram.request import HTTPXRequest

from .config import Settings
from .db import Database
from .service import Service
from .transport import Transport

log = logging.getLogger(__name__)
MAX_BODY = 32768


def create_app(settings=None, telegram_enabled=True):
    settings = settings or Settings.load()
    db = Database(settings.db_path)
    service = Service(db, settings)

    @asynccontextmanager
    async def lifespan(app):
        # Linux flock guards against accidental multiple uvicorn workers on the same DB.
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        lock = open(settings.db_path + '.lock', 'a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise RuntimeError('Only one application instance may use this database') from None
        tasks = []
        try:
            await asyncio.to_thread(db.initialize)
            app.state.tasks = tasks
            if not telegram_enabled:
                yield
            else:
                request = HTTPXRequest(connection_pool_size=8, connect_timeout=10, read_timeout=30)
                polling = HTTPXRequest(connection_pool_size=1, connect_timeout=10, read_timeout=35)
                async with Bot(settings.bot_token, request=request, get_updates_request=polling) as bot:
                    service.bot_username = bot.username
                    await bot.delete_webhook(drop_pending_updates=False)
                    transport = Transport(bot, db, service)
                    app.state.transport = transport
                    tasks.extend([asyncio.create_task(transport.poll(), name='telegram-poll'),
                                  asyncio.create_task(transport.process(), name='inbox'),
                                  asyncio.create_task(transport.send(), name='outbox')])
                    try:
                        yield
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    app = FastAPI(title='3D Print Order Service', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db, app.state.service = db, service

    @app.get('/healthz')
    async def health():
        try:
            await asyncio.to_thread(db.read, 'SELECT 1')
            tasks = getattr(app.state, 'tasks', [])
            if any(t.done() for t in tasks):
                raise RuntimeError('Worker stopped')
            transport = getattr(app.state, 'transport', None)
            if transport and transport.last_poll_at and time.time() - transport.last_poll_at > 120:
                raise RuntimeError('Polling stale')
        except Exception:
            return JSONResponse({'ok': False}, status_code=503)
        return {'ok': True}

    @app.post('/webhooks/google-form')
    async def form_webhook(request: Request):
        secrets = request.headers.getlist('x-webhook-secret')
        if (len(secrets) != 1 or not hmac.compare_digest(secrets[0].encode('utf-8'), settings.webhook_secret.encode('utf-8'))):
            raise HTTPException(401, 'Unauthorized')
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            raise HTTPException(415, 'JSON required')
        body = bytearray()
        try:
            async with asyncio.timeout(15):
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > MAX_BODY:
                        raise HTTPException(413, 'Request too large')
        except TimeoutError:
            raise HTTPException(408, 'Body read timed out') from None
        try:
            payload = json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid JSON number')))
            return await asyncio.to_thread(service.accept_form, payload)
        except (ValueError, UnicodeDecodeError, RecursionError):
            log.warning('invalid_webhook_envelope')
            raise HTTPException(400, 'Invalid event envelope') from None
        except sqlite3.Error as exc:
            log.error('webhook_database_failure error_type=%s', type(exc).__name__)
            raise HTTPException(503, 'Storage unavailable; retry later') from None
        except Exception as exc:
            log.error('webhook_failure error_type=%s', type(exc).__name__)
            raise HTTPException(500, 'Internal error; retry later') from None

    return app
