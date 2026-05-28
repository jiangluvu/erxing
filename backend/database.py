"""
SQLite persistent storage for 播刻 (Boke) backend.

Replaces JSON file-based storage with proper SQLite tables.
Supports concurrent access via WAL mode and threading lock.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "boke.db"
RECORDINGS_DIR = BASE_DIR / "recordings"

_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'generating_opening',
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()


# ── Session operations ──


def session_create(session_id: str, request_id: str, duration: str, title: str) -> dict:
    session = {
        "status": "generating_opening",
        "progress": 0,
        "error": None,
        "opening_audio_path": None,
        "full_audio_path": None,
        "opening_script": None,
        "full_script": None,
        "title": title,
        "duration": duration,
        "request_id": request_id,
        "created_at": time.time(),
        "parse_time_ms": None,
        "llm_time_ms": None,
        "tts_time_ms": None,
        "eval_scores": None,
    }
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, data, status, created_at) VALUES (?, ?, ?, ?)",
                (session_id, json.dumps(session, ensure_ascii=False), session["status"], session["created_at"]),
            )
            conn.commit()
        finally:
            conn.close()
    return session


def session_get(session_id: str) -> dict | None:
    with _lock:
        conn = get_conn()
        try:
            row = conn.execute("SELECT data FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            return json.loads(row["data"])
        finally:
            conn.close()


def session_set(session_id: str, key: str, value):
    with _lock:
        conn = get_conn()
        try:
            row = conn.execute("SELECT data FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return
            data = json.loads(row["data"])
            data[key] = value
            # Keep status column in sync for filtering
            status = data.get("status", "generating_opening")
            conn.execute(
                "UPDATE sessions SET data = ?, status = ? WHERE id = ?",
                (json.dumps(data, ensure_ascii=False), status, session_id),
            )
            conn.commit()
        finally:
            conn.close()


def session_delete(session_id: str):
    with _lock:
        conn = get_conn()
        try:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()


def session_list(status_filter: tuple[str, ...] | None = None) -> list[dict]:
    """Return all sessions, optionally filtered by status."""
    with _lock:
        conn = get_conn()
        try:
            if status_filter:
                placeholders = ",".join("?" for _ in status_filter)
                rows = conn.execute(
                    f"SELECT data FROM sessions WHERE status IN ({placeholders}) ORDER BY created_at DESC",
                    status_filter,
                ).fetchall()
            else:
                rows = conn.execute("SELECT data FROM sessions ORDER BY created_at DESC").fetchall()
            return [json.loads(r["data"]) for r in rows]
        finally:
            conn.close()


def session_count(status: str | None = None) -> int:
    with _lock:
        conn = get_conn()
        try:
            if status:
                row = conn.execute("SELECT COUNT(*) AS cnt FROM sessions WHERE status = ?", (status,)).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS cnt FROM sessions").fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()


# ── Settings operations ──


def settings_load() -> dict:
    with _lock:
        conn = get_conn()
        try:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            result = {}
            for r in rows:
                try:
                    result[r["key"]] = json.loads(r["value"])
                except (json.JSONDecodeError, TypeError):
                    result[r["key"]] = r["value"]
            return result
        finally:
            conn.close()


def settings_save(updates: dict):
    """Merge updates into settings. `updates` is a flat dict of key→value pairs."""
    with _lock:
        conn = get_conn()
        try:
            for key, value in updates.items():
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, json.dumps(value, ensure_ascii=False)),
                )
            conn.commit()
        finally:
            conn.close()


def settings_replace_all(data: dict):
    """Replace all settings with a flat dict (flatten nested keys)."""
    with _lock:
        conn = get_conn()
        try:
            conn.execute("DELETE FROM settings")
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    conn.execute(
                        "INSERT INTO settings (key, value) VALUES (?, ?)",
                        (key, json.dumps(value, ensure_ascii=False)),
                    )
                else:
                    conn.execute(
                        "INSERT INTO settings (key, value) VALUES (?, ?)",
                        (key, str(value)),
                    )
            conn.commit()
        finally:
            conn.close()


# ── Audio file helpers ──


def save_audio_file(source_path: str, session_id: str) -> str:
    """Copy audio file to recordings/ directory and return the stable path."""
    from pathlib import Path as _Path
    src = _Path(source_path)
    if not src.exists():
        return source_path
    dest = RECORDINGS_DIR / f"final_{session_id[:8]}.mp3"
    import shutil
    shutil.copy2(str(src), str(dest))
    return str(dest)


def get_audio_path(session_id: str) -> str | None:
    """Get full_audio_path for a session, checking recordings/ as fallback."""
    session = session_get(session_id)
    if not session:
        return None
    path = session.get("full_audio_path")
    if path and _Path(path).exists():
        return path
    # Check recordings/ directory
    fallback = RECORDINGS_DIR / f"final_{session_id[:8]}.mp3"
    if fallback.exists():
        return str(fallback)
    return None


# ── Migration from JSON files ──


def migrate_from_json():
    """Import existing sessions.json and settings.json into SQLite."""
    sessions_path = BASE_DIR / "sessions.json"
    if sessions_path.exists():
        try:
            with open(sessions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for sid, s in data.items():
                    status = s.get("status", "generating_opening")
                    created_at = s.get("created_at", time.time())
                    with _lock:
                        conn = get_conn()
                        try:
                            conn.execute(
                                "INSERT OR IGNORE INTO sessions (id, data, status, created_at) VALUES (?, ?, ?, ?)",
                                (sid, json.dumps(s, ensure_ascii=False), status, created_at),
                            )
                            conn.commit()
                        finally:
                            conn.close()
                # Rename migrated file
                sessions_path.rename(sessions_path.with_suffix(".json.migrated"))
        except Exception as e:
            print(f"Session migration warning: {e}")

    settings_path = BASE_DIR / "settings.json"
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                settings_replace_all(data)
                settings_path.rename(settings_path.with_suffix(".json.migrated"))
        except Exception as e:
            print(f"Settings migration warning: {e}")