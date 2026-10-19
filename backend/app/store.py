import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

def db_path():
    return os.getenv("DATABASE_PATH", "./docupilot.db")

@contextmanager
def connect():
    con = sqlite3.connect(db_path(), timeout=10)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, language TEXT NOT NULL,
            status TEXT NOT NULL, original_code TEXT NOT NULL, proposed_code TEXT NOT NULL,
            final_code TEXT, analysis_json TEXT NOT NULL, verification_json TEXT,
            mode TEXT NOT NULL
        )""")

def save_run(language, original, proposed, analysis, mode):
    run_id = str(uuid.uuid4())
    created = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute("INSERT INTO runs (id, created_at, language, status, original_code, proposed_code, analysis_json, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, created, language, "pending_review", original, proposed, json.dumps(analysis), mode))
    return run_id

def approve_run(run_id, final_code, verification):
    with connect() as con:
        cur = con.execute("UPDATE runs SET status=?, final_code=?, verification_json=? WHERE id=?",
            ("approved_verified" if verification.get("passed") else "approved_checks_failed", final_code, json.dumps(verification), run_id))
        return cur.rowcount > 0

def get_run(run_id):
    with connect() as con:
        row = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    for key in ("analysis_json", "verification_json"):
        result[key.replace("_json", "")] = json.loads(result.pop(key)) if result.get(key) else None
    return result

def list_runs(limit=25):
    with connect() as con:
        rows = con.execute("SELECT id, created_at, language, status, mode FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
