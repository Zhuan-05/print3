from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_sessions(
 user_id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL,
 mode TEXT NOT NULL DEFAULT 'BOT_MODE' CHECK(mode IN ('BOT_MODE','HUMAN_SUPPORT')),
 support_session_id TEXT, payment_order_id INTEGER, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS binding_tokens(
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES user_sessions(user_id),
 issued_at REAL NOT NULL, expires_at REAL NOT NULL, used_event_id TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS webhook_events(
 event_id TEXT PRIMARY KEY, form_id TEXT NOT NULL, response_id TEXT NOT NULL,
 disposition TEXT NOT NULL, reasons_json TEXT NOT NULL, received_at REAL NOT NULL,
 UNIQUE(form_id,response_id)
);
CREATE TABLE IF NOT EXISTS orders(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 event_id TEXT UNIQUE NOT NULL REFERENCES webhook_events(event_id),
 user_id INTEGER NOT NULL REFERENCES user_sessions(user_id),
 status TEXT NOT NULL CHECK(status IN ('PENDING_QUOTE','AWAITING_PAYMENT','PAYMENT_REVIEW','PROCESSING','COMPLETED')),
 requirements_json TEXT NOT NULL, files_json TEXT NOT NULL,
 price_sen INTEGER CHECK(price_sen IS NULL OR price_sen>0),
 current_proof_id INTEGER, quoted_by INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_proofs(
 id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES orders(id),
 user_id INTEGER NOT NULL REFERENCES user_sessions(user_id),
 source_message_id INTEGER NOT NULL, file_id TEXT NOT NULL, media_type TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED')),
 reviewed_by INTEGER, created_at REAL NOT NULL, reviewed_at REAL,
 UNIQUE(user_id, source_message_id)
);
CREATE TABLE IF NOT EXISTS support_routes(
 route_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES user_sessions(user_id),
 support_session_id TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notification_outbox(
 id INTEGER PRIMARY KEY AUTOINCREMENT, payload_json TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SENT','DEAD')),
 attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
 last_error TEXT, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS outbox_due ON notification_outbox(status,next_at,id);
CREATE TABLE IF NOT EXISTS message_mappings(
 admin_chat_id INTEGER NOT NULL, admin_message_id INTEGER NOT NULL,
 user_id INTEGER NOT NULL REFERENCES user_sessions(user_id),
 user_chat_id INTEGER NOT NULL, support_session_id TEXT NOT NULL,
 route_id TEXT NOT NULL REFERENCES support_routes(route_id),
 outbox_id INTEGER NOT NULL REFERENCES notification_outbox(id), created_at REAL NOT NULL,
 PRIMARY KEY(admin_chat_id,admin_message_id)
);
CREATE TABLE IF NOT EXISTS telegram_inbox(
 update_id INTEGER PRIMARY KEY, payload_json TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','DONE','DEAD')),
 attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
 last_error TEXT, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS inbox_due ON telegram_inbox(status,next_at,update_id);
CREATE TABLE IF NOT EXISTS audit_log(
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER, action TEXT NOT NULL,
 order_id INTEGER REFERENCES orders(id), detail TEXT NOT NULL, created_at REAL NOT NULL
);
"""


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def enqueue(c, method, **kwargs):
    return c.execute(
        "INSERT INTO notification_outbox(payload_json,created_at) VALUES (?,?)",
        (dumps({"method": method, **kwargs}), time.time()),
    ).lastrowid


class Database:
    def __init__(self, path):
        self.path = str(path)

    def connect(self):
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=10000")
        c.execute("PRAGMA synchronous=FULL")
        return c

    def initialize(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        c = self.connect()
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            c.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version','1')")
            if c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] != '1':
                raise RuntimeError("Unsupported database schema version")
        finally:
            c.close()

    @contextmanager
    def transaction(self):
        c = self.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def read(self, sql, parameters=()):
        c = self.connect()
        try:
            return [dict(r) for r in c.execute(sql, parameters).fetchall()]
        finally:
            c.close()

    def offset(self):
        rows = self.read("SELECT value FROM meta WHERE key='telegram_offset'")
        return int(rows[0]['value']) if rows else 0

    def ingest(self, updates):
        if not updates:
            return
        with self.transaction() as c:
            for u in updates:
                c.execute("INSERT OR IGNORE INTO telegram_inbox(update_id,payload_json,created_at) VALUES (?,?,?)",
                          (u['update_id'], dumps(u), time.time()))
            offset = max(u['update_id'] for u in updates) + 1
            c.execute("INSERT INTO meta VALUES ('telegram_offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (str(offset),))
