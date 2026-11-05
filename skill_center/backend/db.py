import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(os.getenv('SC_STORAGE', Path(__file__).resolve().parents[1] / 'storage')).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
DB = ROOT / 'database' / 'center.sqlite'
DB.parent.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
LOCAL = threading.local()
TABLES = {'skills','revisions','drafts','sources','imports','sessions','algorithms','algorithm_versions','datasets','runs'}


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid4().hex


@contextmanager
def transaction():
    with LOCK:
        existing = getattr(LOCAL, 'connection', None)
        if existing is not None:
            yield existing
            return
        conn = sqlite3.connect(DB, timeout=30)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
        LOCAL.connection = conn
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            LOCAL.connection = None
            conn.close()


def migrate():
    with transaction() as conn:
        for table in TABLES:
            conn.execute(f'CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        conn.execute("CREATE INDEX IF NOT EXISTS skills_category ON skills(json_extract(body,'$.category'))")
        conn.execute("CREATE INDEX IF NOT EXISTS skills_updated ON skills(json_extract(body,'$.updated_at'))")
        conn.execute("UPDATE skills SET body=json_set(body,'$.applicable_modules',json('[]')) WHERE json_type(body,'$.applicable_modules') IS NULL")
        conn.execute('PRAGMA user_version=3')


def put(table, value, conn=None):
    assert table in TABLES
    if conn is None:
        with transaction() as own:
            return put(table,value,own)
    conn.execute(f'INSERT INTO {table} VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body', (value['id'], json.dumps(value, ensure_ascii=False)))
    return value


def get(table, key, conn=None):
    assert table in TABLES
    if conn is None:
        with transaction() as own:
            return get(table,key,own)
    row = conn.execute(f'SELECT body FROM {table} WHERE id=?', (key,)).fetchone()
    return json.loads(row[0]) if row else None


def all_rows(table, conn=None):
    assert table in TABLES
    if conn is None:
        with transaction() as own:
            return all_rows(table,own)
    return [json.loads(r[0]) for r in conn.execute(f'SELECT body FROM {table}')]


def revision_root(rev):
    return ROOT / 'skills' / rev['skill_id'] / 'revisions' / rev['id'] / 'bundle'


def draft_root(draft):
    return ROOT / 'drafts' / draft['id'] / 'bundle'


migrate()
