"""SQLite 데이터 계층 — 회원·크레딧·갤러리.

stdlib sqlite3 만 사용. 스레드 안전을 위해 매 호출마다 커넥션을 연다
(백그라운드 파이프라인 스레드에서도 안전하게 쓰기 위함).

⚠️ Render 무료 인스턴스는 디스크가 임시라 재배포 시 이 DB 가 초기화된다.
실제 서비스는 퍼시스턴트 디스크나 외부 DB 로 GROK_STUDIO_DB 를 지정할 것.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from . import config

_DB = Path(config.DB_PATH)


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                credits       INTEGER NOT NULL DEFAULT 0,
                is_admin      INTEGER NOT NULL DEFAULT 0,
                created_at    REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS generations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                model_id   TEXT,
                garment    TEXT,
                tryon_url  TEXT,
                video_url  TEXT,
                status     TEXT,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS credit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                amount     INTEGER NOT NULL,
                reason     TEXT,
                created_at REAL NOT NULL
            );
            """
        )


# ── 유저 ──────────────────────────────────────────────────────
def create_user(email: str, password_hash: str, credits: int, is_admin: bool) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO users(email,password_hash,credits,is_admin,created_at) "
            "VALUES(?,?,?,?,?)",
            (email.lower(), password_hash, credits, 1 if is_admin else 0, time.time()),
        )
        uid = cur.lastrowid
        if credits:
            c.execute(
                "INSERT INTO credit_log(user_id,amount,reason,created_at) VALUES(?,?,?,?)",
                (uid, credits, "signup_bonus", time.time()),
            )
        return uid


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()


def get_user(user_id: int) -> Optional[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def list_users() -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()


# ── 크레딧 ────────────────────────────────────────────────────
def try_spend_credit(user_id: int, amount: int, reason: str = "video") -> bool:
    """크레딧을 원자적으로 차감. 잔액 부족이면 False."""
    with _conn() as c:
        cur = c.execute(
            "UPDATE users SET credits=credits-? WHERE id=? AND credits>=?",
            (amount, user_id, amount),
        )
        if cur.rowcount == 0:
            return False
        c.execute(
            "INSERT INTO credit_log(user_id,amount,reason,created_at) VALUES(?,?,?,?)",
            (user_id, -amount, reason, time.time()),
        )
        return True


def grant_credit(user_id: int, amount: int, reason: str = "topup") -> None:
    with _conn() as c:
        c.execute("UPDATE users SET credits=credits+? WHERE id=?", (amount, user_id))
        c.execute(
            "INSERT INTO credit_log(user_id,amount,reason,created_at) VALUES(?,?,?,?)",
            (user_id, amount, reason, time.time()),
        )


# ── 세션 ──────────────────────────────────────────────────────
def create_session(token: str, user_id: int) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO sessions(token,user_id,created_at) VALUES(?,?,?)",
            (token, user_id, time.time()),
        )


def user_for_session(token: str) -> Optional[sqlite3.Row]:
    if not token:
        return None
    with _conn() as c:
        row = c.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?",
            (token,),
        ).fetchone()
        return row


def delete_session(token: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))


# ── 갤러리(생성 이력) ─────────────────────────────────────────
def add_generation(user_id: int, model_id: str, garment: str,
                   tryon_url: str, video_url: str, status: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO generations(user_id,model_id,garment,tryon_url,video_url,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (user_id, model_id, garment, tryon_url, video_url, status, time.time()),
        )


def list_generations(user_id: int, limit: int = 60) -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM generations WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
