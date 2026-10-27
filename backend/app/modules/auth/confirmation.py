"""Код подтверждения почты: срок, повторная отправка, сверка без хранения открытого кода."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings

CODE_TTL = timedelta(minutes=15)
RESET_TTL = timedelta(minutes=30)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5
PURPOSE_REGISTER = "register"
PURPOSE_LOGIN = "login"
PURPOSE_RESET = "reset"


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def new_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode()).hexdigest()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_code(email: str, code: str) -> str:
    message = f"{email.strip().lower()}:{code.strip()}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def codes_match(email: str, code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(email, code), code_hash)


def resend_allowed(last_sent_at: datetime, now: datetime, cooldown: timedelta = RESEND_COOLDOWN) -> bool:
    return as_utc(now) - as_utc(last_sent_at) >= cooldown
