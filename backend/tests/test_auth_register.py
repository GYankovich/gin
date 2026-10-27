"""Саморегистрация: почта нормализуется, пароль короче 8 символов не проходит."""
import pytest
from pydantic import ValidationError

from app.modules.auth.queries import (
    build_get_email_confirmation_query,
    build_get_user_by_email_query,
)
from app.modules.auth.schemas import CONFIRMATION_CODE_REQUIRED, RegisterPendingResponse, RegisterRequest


def test_pending_status_asks_the_ui_for_a_code():
    body = RegisterPendingResponse(email="ada@example.com")
    assert body.status == CONFIRMATION_CODE_REQUIRED


def test_register_email_is_lowercased():
    body = RegisterRequest(login="ada", email="Ada@Example.COM", password="longpassword")
    assert str(body.email) == "ada@example.com"
    assert body.login == "ada"


def test_register_rejects_short_password():
    with pytest.raises(ValidationError):
        RegisterRequest(login="ada", email="ada@example.com", password="short")


def test_register_rejects_login_with_spaces():
    with pytest.raises(ValidationError):
        RegisterRequest(login="bad login", email="ada@example.com", password="longpassword")


def test_confirmation_query_is_scoped_by_purpose():
    sql = build_get_email_confirmation_query()
    assert "purpose = :purpose" in sql


def test_email_login_query_is_case_insensitive():
    sql = build_get_user_by_email_query()
    assert "lower(e.email)" in sql
    assert "valid_to IS NULL" in sql
