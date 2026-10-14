"""Local operator tools; never expose these commands as public HTTP routes."""
import argparse
import json
from pathlib import Path
import sqlite3
import time

from app.config import Settings
from app.db import Database


def main():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('status')
    subs.add_parser('quarantined')
    backup = subs.add_parser('backup')
    backup.add_argument('destination')
    retry = subs.add_parser('retry')
    retry.add_argument('queue', choices=['inbox', 'outbox'])
    retry.add_argument('id', type=int)
    args = parser.parse_args()
    settings = Settings.load()
    db = Database(settings.db_path)
    if not Path(db.path).exists():
        parser.error('Database does not exist; start the service first')
    if args.command == 'status':
        result = {}
        for table in ('orders', 'telegram_inbox', 'notification_outbox'):
            result[table] = db.read(f'SELECT status,COUNT(*) count FROM {table} GROUP BY status')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == 'quarantined':
        print(json.dumps(db.read("SELECT event_id,reasons_json,received_at FROM webhook_events WHERE disposition='quarantined' ORDER BY received_at DESC LIMIT 50"), ensure_ascii=False, indent=2))
    elif args.command == 'backup':
        target = Path(args.destination).resolve()
        if target.exists():
            parser.error('Backup destination already exists; choose a new filename')
        target.parent.mkdir(parents=True, exist_ok=True)
        src = db.connect()
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed')
        finally:
            src.close()
            dst.close()
        target.chmod(0o600)
        print(str(target))
    else:
        table, column = ('telegram_inbox', 'update_id') if args.queue == 'inbox' else ('notification_outbox', 'id')
        with db.transaction() as c:
            result = c.execute(f"UPDATE {table} SET status='PENDING',attempts=0,next_at=?,last_error=NULL WHERE {column}=? AND status='DEAD'",
                               (time.time(), args.id))
            if result.rowcount != 1:
                parser.error('No matching DEAD item; nothing changed')
        print('Queued for retry. Delivery may duplicate a previously accepted Telegram message.')


if __name__ == '__main__':
    main()
