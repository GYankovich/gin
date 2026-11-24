"""Шифрование брокерских секретов в api_tokens.

Один ключ на token и token_secret. Ключ выводится из SECRET_KEY.
Уже зашифрованное значение не шифруется повторно. Открытый текст
старых строк читается как есть, пока миграция его не запечатает.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_sealed(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def seal(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    if text == "" or is_sealed(text):
        return text
    token = _fernet().encrypt(text.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def open_secret(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not is_sealed(text):
        return text
    try:
        raw = _fernet().decrypt(text[len(_PREFIX):].encode("ascii"))
    except (InvalidToken, ValueError):
        return text
    return raw.decode("utf-8")


def open_broker_material(
    token: str | None,
    secret: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Открывает ключ и секрет. В словарь для брокера секрет попадает уже открытым."""
    data = dict(extra) if isinstance(extra, dict) else {}
    stored = secret
    if not stored:
        stored = data.get("token_secret") or data.get("api_secret")
    plain_secret = open_secret(str(stored)) if stored else None
    data.pop("token_secret", None)
    data.pop("api_secret", None)
    if plain_secret:
        data["token_secret"] = plain_secret
    return open_secret(token) or "", data
