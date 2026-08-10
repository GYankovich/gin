"""Record external broker API usage against api_tokens."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging_config import get_logger

logger = get_logger(__name__)

_ERROR_MAX_LEN = 2000


def record_api_token_call(
    token_id: Optional[int],
    *,
    ok: bool,
    error: Optional[str] = None,
    db: Optional[Session] = None,
) -> None:
    """
    Update last_used_at on any external call.
    On success clear last_error; on failure persist error text in last_error.
    """
    if token_id is None:
        return
    try:
        tid = int(token_id)
    except (TypeError, ValueError):
        return
    if tid <= 0:
        return

    own_session = db is None
    session = db if db is not None else SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        if ok:
            session.execute(
                text(
                    """
                    UPDATE api_tokens
                    SET last_used_at = :now,
                        last_error = NULL,
                        last_error_at = NULL,
                        updated_at = :now
                    WHERE id = :token_id
                    """
                ),
                {"now": now, "token_id": tid},
            )
        else:
            err = (error or "External API error").strip()[:_ERROR_MAX_LEN] or "External API error"
            session.execute(
                text(
                    """
                    UPDATE api_tokens
                    SET last_used_at = :now,
                        last_error = :error,
                        last_error_at = :now,
                        updated_at = :now
                    WHERE id = :token_id
                    """
                ),
                {"now": now, "token_id": tid, "error": err},
            )
        if own_session:
            session.commit()
    except Exception:
        if own_session:
            try:
                session.rollback()
            except Exception:
                pass
        logger.exception("Failed to record api_token call for token_id=%s", tid)
    finally:
        if own_session:
            session.close()
