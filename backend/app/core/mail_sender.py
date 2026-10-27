"""Робот исходящей почты: забирает pending-строки и отправляет их через SMTP."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.mail import MailDeliveryError, send_queued_message, smtp_configured
from app.modules.auth.confirmation import CODE_TTL, PURPOSE_RESET, RESET_TTL

logger = logging.getLogger(__name__)

MAIL_SENDER = "mail_sender"
MAX_ATTEMPTS = 5
STALE_SENDING_SECONDS = 120

_stop = threading.Event()
_thread: threading.Thread | None = None
_warned_unconfigured = False

_CLAIM = """
UPDATE outbound_message
SET status = 'sending',
    attempts = attempts + 1,
    updated_at = :now,
    updated_source = 'robot',
    updated_by = :actor
WHERE id = (
    SELECT id
    FROM outbound_message
    WHERE status = 'pending'
      AND (next_attempt_at IS NULL OR next_attempt_at <= :now)
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id, channel, email_id, to_email, subject, body, purpose, attempts
"""

_RECLAIM_STALE = """
UPDATE outbound_message
SET status = 'pending',
    updated_at = :now,
    updated_source = 'robot',
    updated_by = :actor
WHERE status = 'sending'
  AND updated_at < :stale_before
"""

_EMAIL_BY_ID = """
SELECT email
FROM user_email
WHERE id = :email_id
"""

_EXTEND_EXPIRY = """
UPDATE email_confirmation
SET expires_at = :expires_at
WHERE lower(email) = :email
  AND purpose = :purpose
"""

_FINISH = """
UPDATE outbound_message
SET status = :status,
    error_code = :error_code,
    error_message = :error_message,
    sent_at = :sent_at,
    next_attempt_at = :next_attempt_at,
    updated_at = :now,
    updated_source = 'robot',
    updated_by = :actor
WHERE id = :id
"""


def retry_delay_seconds(attempts: int) -> int:
    """30, 60, 120… секунд, не дольше 15 минут."""
    shift = max(int(attempts) - 1, 0)
    return min(30 * (2 ** shift), 900)


def failure_status(attempts: int) -> str:
    return "failed" if int(attempts) >= MAX_ATTEMPTS else "pending"


def expires_after_send(sent_at: datetime, purpose: str) -> datetime:
    """15 минут на код и 30 на ссылку сброса, от момента успешной отправки."""
    ttl = RESET_TTL if purpose == PURPOSE_RESET else CODE_TTL
    return sent_at + ttl


def start_mail_sender() -> None:
    global _thread
    if not settings.MAIL_SENDER_ENABLED:
        logger.info("Робот почты выключен (MAIL_SENDER_ENABLED=false)")
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="mail-sender", daemon=True)
    _thread.start()
    logger.info("Робот почты запущен")


def stop_mail_sender() -> None:
    _stop.set()


def run_mail_sender_forever() -> None:
    """Блокирующий цикл для отдельного процесса."""
    _stop.clear()
    logger.info("Робот почты запущен отдельным процессом")
    _loop()


def deliver_pending_once() -> bool:
    """Забирает одно письмо. True, если строка была."""
    global _warned_unconfigured
    if not smtp_configured():
        if not _warned_unconfigured:
            logger.warning("Робот почты ждёт: в конфиге нет ящика SMTP_CODES_* или SMTP_*")
            _warned_unconfigured = True
        return False
    _warned_unconfigured = False
    now = datetime.now(timezone.utc)
    row = _claim(now)
    if row is None:
        return False
    mail_id = int(row[0])
    channel = str(row[1])
    try:
        if channel != "mail":
            _finish(
                mail_id,
                status_name="failed",
                now=now,
                error_code="channel_unsupported",
                error_message=f"Канал {channel} робот почты не отправляет",
            )
            return True
        address = _recipient(row[2], row[3])
        if not address:
            _finish(
                mail_id,
                status_name="failed",
                now=now,
                error_code="no_recipient",
                error_message="Нет адреса: карточка почты пуста и to_email не заполнен",
            )
            return True
        send_queued_message(address, str(row[4] or ""), str(row[5] or ""), str(row[6] or ""))
        sent_at = datetime.now(timezone.utc)
        _extend_expiry(address, str(row[6] or ""), sent_at)
        _finish(mail_id, status_name="sent", now=sent_at)
        logger.info("Письмо id=%s отправлено, purpose=%s", mail_id, row[6])
        return True
    except MailDeliveryError as exc:
        attempts = int(row[7] or 1)
        status_name = failure_status(attempts)
        delay = retry_delay_seconds(attempts)
        _finish(
            mail_id,
            status_name=status_name,
            now=datetime.now(timezone.utc),
            error_code="smtp",
            error_message=str(exc),
            next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=delay) if status_name == "pending" else None,
        )
        logger.warning("Письмо id=%s не ушло, статус %s", mail_id, status_name)
        return True


def _loop() -> None:
    while not _stop.is_set():
        worked = False
        try:
            worked = deliver_pending_once()
        except Exception:
            logger.exception("Цикл робота почты оборвался")
        if not worked:
            _stop.wait(float(settings.MAIL_SENDER_POLL_SECONDS))


def _claim(now: datetime):
    db = SessionLocal()
    try:
        db.execute(
            text(_RECLAIM_STALE),
            {
                "now": now,
                "actor": MAIL_SENDER,
                "stale_before": now - timedelta(seconds=STALE_SENDING_SECONDS),
            },
        )
        row = db.execute(text(_CLAIM), {"now": now, "actor": MAIL_SENDER}).first()
        db.commit()
        return row
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _extend_expiry(address: str, purpose: str, sent_at: datetime) -> None:
    if purpose not in {"login", "register", PURPOSE_RESET}:
        return
    db = SessionLocal()
    try:
        db.execute(
            text(_EXTEND_EXPIRY),
            {
                "email": address.strip().lower(),
                "purpose": purpose,
                "expires_at": expires_after_send(sent_at, purpose),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Не удалось сдвинуть срок кода после отправки")
    finally:
        db.close()


def _recipient(email_id, to_email) -> str:
    direct = str(to_email or "").strip()
    if direct:
        return direct
    if email_id is None:
        return ""
    db = SessionLocal()
    try:
        row = db.execute(text(_EMAIL_BY_ID), {"email_id": email_id}).first()
        return str(row[0]).strip() if row and row[0] else ""
    finally:
        db.close()


def _finish(
    mail_id: int,
    *,
    status_name: str,
    now: datetime,
    error_code: str | None = None,
    error_message: str | None = None,
    next_attempt_at: datetime | None = None,
) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(_FINISH),
            {
                "id": mail_id,
                "status": status_name,
                "error_code": error_code,
                "error_message": (error_message or "")[:2000] or None,
                "sent_at": now if status_name == "sent" else None,
                "next_attempt_at": next_attempt_at,
                "now": now,
                "actor": MAIL_SENDER,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
