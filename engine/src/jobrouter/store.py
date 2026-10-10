"""Public evidence storage, separate from private search briefs."""
import json
import sqlite3
from .models import now


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs(identity TEXT PRIMARY KEY, data TEXT NOT NULL, observed_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources(url TEXT PRIMARY KEY, parent TEXT, kind TEXT NOT NULL, state TEXT NOT NULL, detail TEXT, checked_at TEXT);
                CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY, data TEXT NOT NULL);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def job(self, job):
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?) ON CONFLICT(identity) DO UPDATE SET data=excluded.data,observed_at=excluded.observed_at",
                       (job.identity, json.dumps(job.to_dict()), job.observed_at))

    def jobs(self):
        with self.connect() as db:
            return [json.loads(x[0]) for x in db.execute("SELECT data FROM jobs ORDER BY identity")]

    def source(self, url, parent, kind, state, detail=""):
        with self.connect() as db:
            db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET state=excluded.state,detail=excluded.detail,checked_at=excluded.checked_at",
                       (url, parent, kind, state, detail, now()))

    def receipts(self, rows):
        with self.connect() as db:
            db.executemany("INSERT INTO receipts(data) VALUES(?)", [(json.dumps(x),) for x in rows])
