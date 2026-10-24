"""本地存储：候选人、JD、投递记录。用标准库 sqlite，零依赖。"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_DB = Path(os.getenv("CAREER_LOOP_DB", Path.home() / ".career_loop" / "loop.db"))

POSITIVE_STATUSES = {"replied", "interview", "offer"}


def get_db() -> Path:
    return DEFAULT_DB


def _connect(db: Optional[str] = None) -> sqlite3.Connection:
    path = Path(db) if db else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(db: Optional[str] = None) -> None:
    conn = _connect(db)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS jds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            requirements TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jd_id INTEGER NOT NULL,
            profile_id INTEGER NOT NULL,
            fit_score REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'applied',
            note TEXT DEFAULT '',
            applied_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (jd_id) REFERENCES jds(id),
            FOREIGN KEY (profile_id) REFERENCES profiles(id)
        );
        """
    )
    conn.commit()
    conn.close()


def add_profile(name: str, text: str, db: Optional[str] = None) -> int:
    conn = _connect(db)
    cur = conn.execute("INSERT INTO profiles(name, text) VALUES (?, ?)", (name, text))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def add_jd(title: str, text: str, requirements: list, db: Optional[str] = None) -> int:
    conn = _connect(db)
    cur = conn.execute(
        "INSERT INTO jds(title, text, requirements) VALUES (?, ?, ?)",
        (title, text, json.dumps([r.__dict__ for r in requirements], ensure_ascii=False)),
    )
    jid = cur.lastrowid
    conn.commit()
    conn.close()
    return jid


def get_profile(pid: int, db: Optional[str] = None) -> Optional[dict]:
    conn = _connect(db)
    row = conn.execute("SELECT * FROM profiles WHERE id = ?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_jd(jid: int, db: Optional[str] = None) -> Optional[dict]:
    conn = _connect(db)
    row = conn.execute("SELECT * FROM jds WHERE id = ?", (jid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_jds(db: Optional[str] = None) -> list[dict]:
    conn = _connect(db)
    rows = conn.execute("SELECT * FROM jds ORDER BY id").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["requirements"] = json.loads(d["requirements"])
        except (json.JSONDecodeError, TypeError):
            d["requirements"] = []
        out.append(d)
    return out


def record_application(
    jd_id: int, profile_id: int, fit_score: float, db: Optional[str] = None
) -> int:
    conn = _connect(db)
    cur = conn.execute(
        "INSERT INTO applications(jd_id, profile_id, fit_score, status) VALUES (?, ?, ?, 'applied')",
        (jd_id, profile_id, fit_score),
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid


def set_status(app_id: int, status: str, note: str = "", db: Optional[str] = None) -> None:
    conn = _connect(db)
    conn.execute(
        "UPDATE applications SET status = ?, note = ? WHERE id = ?", (status, note, app_id)
    )
    conn.commit()
    conn.close()


def list_applications(db: Optional[str] = None) -> list[dict]:
    conn = _connect(db)
    rows = conn.execute(
        """
        SELECT a.id, a.fit_score, a.status, a.applied_at,
               j.title AS jd_title, p.name AS profile_name
        FROM applications a
        JOIN jds j ON j.id = a.jd_id
        JOIN profiles p ON p.id = a.profile_id
        ORDER BY a.applied_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@dataclass
class CalibrationRow:
    app_id: int
    fit_score: float
    positive: bool
    status: str


def calibration_rows(db: Optional[str] = None) -> list[CalibrationRow]:
    conn = _connect(db)
    rows = conn.execute(
        "SELECT id, fit_score, status FROM applications ORDER BY id"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append(
            CalibrationRow(
                app_id=r["id"],
                fit_score=float(r["fit_score"]),
                positive=r["status"] in POSITIVE_STATUSES,
                status=r["status"],
            )
        )
    return out
