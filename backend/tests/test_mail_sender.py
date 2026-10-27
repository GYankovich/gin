"""Робот почты: повтор не бесконечный, чужая строка не забирается без блокировки."""

from datetime import datetime, timedelta, timezone

from app.core.mail_sender import _CLAIM, _EXTEND_EXPIRY, expires_after_send, failure_status, retry_delay_seconds


def test_retry_waits_longer_then_stops():
    assert retry_delay_seconds(1) == 30
    assert retry_delay_seconds(2) == 60
    assert retry_delay_seconds(3) == 120
    assert failure_status(4) == "pending"
    assert failure_status(5) == "failed"


def test_expiry_starts_when_the_letter_is_sent():
    sent = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    assert expires_after_send(sent, "login") == sent + timedelta(minutes=15)
    assert expires_after_send(sent, "register") == sent + timedelta(minutes=15)
    assert expires_after_send(sent, "reset") == sent + timedelta(minutes=30)
    assert "expires_at = :expires_at" in _EXTEND_EXPIRY


def test_claim_locks_one_pending_row():
    assert "FOR UPDATE SKIP LOCKED" in _CLAIM
    assert "status = 'pending'" in _CLAIM
    assert "mail_sender" not in _CLAIM
