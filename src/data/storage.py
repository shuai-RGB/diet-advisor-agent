"""SQLite 持久化：对话历史 / 用户画像 / 饮食记录。"""
from __future__ import annotations

import sqlite3
import time
import uuid

from .. import config

DB_PATH = config.DATA_DIR / "health.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS chat_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, ts REAL
    );
    CREATE TABLE IF NOT EXISTS users(
        id TEXT PRIMARY KEY, profile TEXT, ts REAL
    );
    CREATE TABLE IF NOT EXISTS diet_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, date TEXT, items TEXT, totals TEXT, ts REAL
    );
    CREATE TABLE IF NOT EXISTS latest(
        key TEXT PRIMARY KEY, value TEXT, ts REAL
    );
    CREATE TABLE IF NOT EXISTS traces(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trace_id TEXT, task_type TEXT, ts REAL, duration_ms REAL,
        prompt_tokens INTEGER, completion_tokens INTEGER, layers TEXT
    );
    CREATE TABLE IF NOT EXISTS memories(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, content TEXT, ts REAL
    );
    """)
    conn.commit()
    conn.close()


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def save_message(session_id: str, role: str, content: str) -> None:
    conn = _conn()
    conn.execute("INSERT INTO chat_history(session_id, role, content, ts) VALUES(?,?,?,?)",
                 (session_id, role, content, time.time()))
    conn.commit()
    conn.close()


def get_history(session_id: str, limit: int = 10) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT role, content FROM chat_history WHERE session_id=? ORDER BY id DESC LIMIT ?",
        (session_id, limit)).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def save_diet_log(user_id: str, date: str, items: list, totals: dict) -> None:
    import json
    conn = _conn()
    conn.execute("INSERT INTO diet_logs(user_id, date, items, totals, ts) VALUES(?,?,?,?,?)",
                 (user_id, date, json.dumps(items, ensure_ascii=False),
                  json.dumps(totals, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def get_diet_logs(user_id: str, limit: int = 30) -> list[dict]:
    import json
    conn = _conn()
    rows = conn.execute(
        "SELECT date, items, totals, ts FROM diet_logs WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit)).fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({"date": r["date"], "items": json.loads(r["items"]),
                    "totals": json.loads(r["totals"]), "ts": r["ts"]})
    return out


def get_today_intake(user_id: str) -> dict:
    import json
    from datetime import date
    today = date.today().isoformat()
    conn = _conn()
    rows = conn.execute("SELECT totals FROM diet_logs WHERE user_id=? AND date=?", (user_id, today)).fetchall()
    conn.close()
    total = {"energy_kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0, "fiber_g": 0, "sodium_mg": 0}
    for r in rows:
        t = json.loads(r["totals"])
        for k in total:
            total[k] += t.get(k, 0)
    return total


def save_trace(trace_id: str, task_type: str, duration_ms: float,
               prompt_tokens: int, completion_tokens: int, layers: list) -> None:
    import json
    init_db()
    conn = _conn()
    conn.execute("INSERT INTO traces(trace_id, task_type, ts, duration_ms, prompt_tokens, completion_tokens, layers) "
                 "VALUES(?,?,?,?,?,?,?)",
                 (trace_id, task_type, time.time(), round(duration_ms, 1),
                  prompt_tokens, completion_tokens, json.dumps(layers, ensure_ascii=False)))
    conn.commit()
    conn.close()


def get_traces(limit: int = 30) -> list[dict]:
    import json
    init_db()
    conn = _conn()
    rows = conn.execute("SELECT trace_id, task_type, ts, duration_ms, prompt_tokens, completion_tokens, layers "
                        "FROM traces ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({"trace_id": r["trace_id"], "task_type": r["task_type"], "ts": r["ts"],
                    "duration_ms": r["duration_ms"], "prompt_tokens": r["prompt_tokens"],
                    "completion_tokens": r["completion_tokens"], "layers": json.loads(r["layers"])})
    return out


def save_memory(user_id: str, content: str) -> None:
    conn = _conn()
    conn.execute("INSERT INTO memories(user_id, content, ts) VALUES(?,?,?)",
                 (user_id, content, time.time()))
    conn.commit()
    conn.close()


def get_memories(user_id: str, limit: int = 20) -> list[dict]:
    conn = _conn()
    rows = conn.execute("SELECT content, ts FROM memories WHERE user_id=? ORDER BY id DESC LIMIT ?",
                        (user_id, limit)).fetchall()
    conn.close()
    return [{"content": r["content"], "ts": r["ts"]} for r in rows]


def get_preferences(user_id: str, top_n: int = 5) -> list[dict]:
    """从饮食记录统计最常吃的食物（偏好学习）。"""
    from collections import Counter
    logs = get_diet_logs(user_id, 30)
    counter = Counter()
    for log in logs:
        for it in log["items"]:
            name = (it.get("name") or "").strip()
            if name and "未识别" not in name:
                counter[name] += 1
    return [{"food": name, "count": c} for name, c in counter.most_common(top_n)]


def save_latest(key: str, value) -> None:
    import json
    conn = _conn()
    conn.execute("INSERT OR REPLACE INTO latest(key, value, ts) VALUES(?,?,?)",
                 (key, json.dumps(value, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def get_latest(key: str):
    import json
    conn = _conn()
    row = conn.execute("SELECT value FROM latest WHERE key=?", (key,)).fetchone()
    conn.close()
    return json.loads(row["value"]) if row else None


def save_profile(user_id: str, profile: dict) -> None:
    import json
    conn = _conn()
    conn.execute("INSERT OR REPLACE INTO users(id, profile, ts) VALUES(?,?,?)",
                 (user_id, json.dumps(profile, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def get_profile(user_id: str) -> dict:
    import json
    conn = _conn()
    row = conn.execute("SELECT profile FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return json.loads(row["profile"]) if row else {}
