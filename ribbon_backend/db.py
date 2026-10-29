import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,owner_id TEXT REFERENCES users(id),name TEXT NOT NULL,kind TEXT NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL,source TEXT NOT NULL,is_demo INTEGER NOT NULL,shared INTEGER NOT NULL,derived_from TEXT,enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS templates(id TEXT NOT NULL,version INTEGER NOT NULL,name TEXT NOT NULL,mode TEXT NOT NULL,rules_json TEXT NOT NULL,enabled INTEGER NOT NULL,thumbnail_path TEXT NOT NULL,PRIMARY KEY(id,version));
CREATE TABLE IF NOT EXISTS output_profiles(id TEXT PRIMARY KEY,version INTEGER UNIQUE NOT NULL,name TEXT NOT NULL,profile_json TEXT NOT NULL,active INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS designs(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,current_version_id TEXT,successful_refinement_count INTEGER NOT NULL DEFAULT 0 CHECK(successful_refinement_count BETWEEN 0 AND 2),active_job_id TEXT,revision INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id),design_id TEXT REFERENCES designs(id),kind TEXT NOT NULL,idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,payload_json TEXT NOT NULL,base_version_id TEXT,status TEXT NOT NULL,phase TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,lease_until REAL,provider TEXT NOT NULL,error TEXT,needs_clarification INTEGER NOT NULL DEFAULT 0,result_version_id TEXT,result_asset_id TEXT,artifact_json TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(owner_id,idempotency_key));
CREATE INDEX IF NOT EXISTS jobs_claim ON jobs(status,lease_until,created_at);
CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY,design_id TEXT NOT NULL REFERENCES designs(id),parent_version_id TEXT REFERENCES versions(id),sequence INTEGER NOT NULL,snapshot_json TEXT NOT NULL,preview_path TEXT NOT NULL,master_path TEXT NOT NULL,master_sha256 TEXT NOT NULL,prompt TEXT NOT NULL,render_kind TEXT NOT NULL,provider TEXT NOT NULL,job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),created_at TEXT NOT NULL,UNIQUE(design_id,sequence));
CREATE TABLE IF NOT EXISTS quota_events(job_id TEXT PRIMARY KEY REFERENCES jobs(id),design_id TEXT NOT NULL REFERENCES designs(id),created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox_events(job_id TEXT PRIMARY KEY REFERENCES jobs(id),created_at TEXT NOT NULL,delivered_at TEXT);
CREATE TABLE IF NOT EXISTS provider_calls(id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),attempt INTEGER NOT NULL,operation TEXT NOT NULL,provider TEXT NOT NULL,model TEXT,request_id TEXT,usage_json TEXT,elapsed_ms INTEGER NOT NULL,status TEXT NOT NULL,error TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS expired_requests(owner_id TEXT NOT NULL REFERENCES users(id),idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,PRIMARY KEY(owner_id,idempotency_key));
CREATE TABLE IF NOT EXISTS cleanup_paths(path TEXT PRIMARY KEY,is_directory INTEGER NOT NULL);
'''


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
        with self.transaction() as conn:
            # Unknown legacy timestamps remain NULL: do not expire old work by guesswork.
            for table, columns in {
                'designs': {'retained_at': 'REAL'},
                'assets': {'retained_at': 'REAL'},
                'jobs': {'settled_at': 'REAL'},
                'versions': {'preview_sha256': 'TEXT'},
                'templates': {'thumbnail_sha256': 'TEXT'},
            }.items():
                existing = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
                for name, kind in columns.items():
                    if name not in existing:
                        conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
