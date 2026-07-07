"""인증 — 비밀번호 해시(pbkdf2, stdlib) + 세션 토큰.

외부 의존성 없음. bcrypt 대신 hashlib.pbkdf2_hmac 사용.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from . import config, db

_ITER = 200_000
_ALGO = "sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode(), salt, _ITER)
    return f"pbkdf2${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(_ALGO, password.encode(),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def _valid_email(email: str) -> bool:
    email = email.strip()
    return "@" in email and "." in email.split("@")[-1] and len(email) <= 200


class AuthError(ValueError):
    pass


def signup(email: str, password: str):
    email = email.strip().lower()
    if not _valid_email(email):
        raise AuthError("올바른 이메일을 입력하세요.")
    if len(password) < 6:
        raise AuthError("비밀번호는 6자 이상이어야 합니다.")
    if db.get_user_by_email(email):
        raise AuthError("이미 가입된 이메일입니다.")
    is_admin = email == config.ADMIN_EMAIL
    uid = db.create_user(email, hash_password(password),
                         config.SIGNUP_FREE_CREDITS, is_admin)
    return db.get_user(uid)


def login(email: str, password: str):
    email = email.strip().lower()
    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        raise AuthError("이메일 또는 비밀번호가 올바르지 않습니다.")
    return user


def start_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.create_session(token, user_id)
    return token


def current_user(token: Optional[str]):
    return db.user_for_session(token) if token else None
