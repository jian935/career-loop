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


def _fetchall(db: Optional[str], sql: str) -> list[dict]:
    """查多行，**并保证连接一定被关掉**。

    为什么必须包一层：早先的写法是先 `_connect` 再 `execute`，
    一旦 SQL 报错（比如库是空的、表还没建），连接就没人 close——
    在 Windows 上这个文件句柄不释放，库文件会被锁住删不掉
    （WinError 32，测试里删临时库时抓到过），CLI 侧则是 `loop.db` 被占。
    """
    conn = _connect(db)
    try:
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def _fetchone(db: Optional[str], sql: str, params: tuple = ()) -> Optional[dict]:
    """查一行，同样保证连接一定关闭。"""
    conn = _connect(db)
    try:
        row = conn.execute(sql, params).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


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
    return _fetchone(db, "SELECT * FROM profiles WHERE id = ?", (pid,))


def get_jd(jid: int, db: Optional[str] = None) -> Optional[dict]:
    return _fetchone(db, "SELECT * FROM jds WHERE id = ?", (jid,))


def list_jds(db: Optional[str] = None) -> list[dict]:
    out = []
    for d in _fetchall(db, "SELECT * FROM jds ORDER BY id"):
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
    return _fetchall(
        db,
        """
        SELECT a.id, a.fit_score, a.status, a.applied_at,
               j.title AS jd_title, p.name AS profile_name
        FROM applications a
        JOIN jds j ON j.id = a.jd_id
        JOIN profiles p ON p.id = a.profile_id
        ORDER BY a.applied_at DESC
        """,
    )


@dataclass
class CalibrationRow:
    app_id: int
    fit_score: float
    positive: bool
    status: str


def list_applications_detail(db: Optional[str] = None) -> list[dict]:
    """投递明细，附带 JD 原文与所属经历原文。

    为什么要单开一个函数而不是给 `list_applications` 加字段：
    后者是 CLI `status` 的输出契约，加字段会让日常排查的输出变长；
    看板要同时做「算缺口排行」（需要 JD 原文）和「按经历重新对齐」（需要经历原文），
    信息比 CLI 多，所以单独取。
    """
    conn = _connect(db)
    try:
        rows = conn.execute(
            """
        SELECT a.id, a.fit_score, a.status, a.note, a.applied_at,
               j.title AS jd_title, j.text AS jd_text,
               p.name AS profile_name, p.text AS profile_text
        FROM applications a
        JOIN jds j ON j.id = a.jd_id
        JOIN profiles p ON p.id = a.profile_id
        ORDER BY a.id
        """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def calibration_rows(db: Optional[str] = None) -> list[CalibrationRow]:
    # 库还没初始化时 _fetchall 会抛 OperationalError：看板负责把它降级成提示，
    # 这里刻意往外抛，而不是吞掉伪装成"零条记录"——没有数据和读不到数据是两回事。
    rows = _fetchall(db, "SELECT id, fit_score, status FROM applications ORDER BY id")
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
