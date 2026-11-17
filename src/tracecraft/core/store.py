"""One SQLite schema. WAL and transactions, not external exactly-once promises."""
import hashlib
import json
import sqlite3
import subprocess
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import RunManifest, TraceSpan

ROOT = Path(__file__).resolve().parents[3]

def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value: Any) -> str:
    return hashlib.sha256((value if isinstance(value, bytes) else canonical(value).encode())).hexdigest()

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

def source_fingerprint():
    files = sorted([p for p in (ROOT/'src').rglob('*.py') if '__pycache__' not in p.parts] +
                   list((ROOT/'configs').glob('*.json')) + list(ROOT.glob('requirements*.txt')) + list(ROOT.glob('requirements*.lock')))
    return digest({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})

class Store:
    def __init__(self, path: str | Path = ROOT / 'runtime' / 'tracecraft.sqlite'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records(namespace TEXT,key TEXT,value TEXT,updated REAL,PRIMARY KEY(namespace,key))')
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)')
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('schema', '1'))

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, namespace: str, key: str, default=None):
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT value FROM records WHERE namespace=? AND key=?', (namespace, key)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, namespace: str, key: str, value: Any):
        with self.transaction() as db:
            db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?)', (namespace, key, canonical(value), time.time()))
        return value

    def list(self, namespace: str) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute('SELECT value FROM records WHERE namespace=? ORDER BY updated,key', (namespace,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def delete(self, namespace: str, key: str):
        with self.transaction() as db:
            db.execute('DELETE FROM records WHERE namespace=? AND key=?', (namespace, key))

    def trace(self, run_id, stage, inputs, outputs, status='ok', error=None, parent_id=None):
        span = TraceSpan(id=uuid.uuid4().hex, run_id=run_id, timestamp=utcnow(), stage=stage,
                         inputs=inputs, outputs=outputs, status=status, error=error, parent_id=parent_id).model_dump()
        return self.put('spans', span['id'], span)

    def spans(self, run_id):
        return [s for s in self.list('spans') if s['run_id'] == run_id]

    def new_run(self, module, mode, config):
        revision = None
        dirty = None
        try:
            revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
            dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True))
        except (OSError, subprocess.CalledProcessError):
            pass
        try:
            dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, stderr=subprocess.DEVNULL,text=True))
        except (OSError, subprocess.CalledProcessError):
            pass
        manifest = RunManifest(id=uuid.uuid4().hex, module=module, mode=mode, config=config,
                               config_hash=digest(config), code_revision=revision, dirty_tree=dirty,
                               started_at=utcnow(), code_source_hash=source_fingerprint()).model_dump()
        return self.put('runs', manifest['id'], manifest)

    def finish_run(self, run_id, status, **fields):
        run = self.get('runs', run_id)
        if run is None:
            raise KeyError(run_id)
        run.update(status=status, measurement_status='measured', finished_at=utcnow(), **fields)
        return self.put('runs', run_id, run)
