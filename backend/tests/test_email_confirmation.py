"""Код подтверждения: хеш не совпадает с чужим кодом, повторная отправка ждёт минуту."""
from datetime import datetime, timedelta, timezone

from app.core.mail import build_confirmation_message, build_reset_message, confirmation_letter, confirmation_note
from app.core.mail_template import LOGO_CID, letter_fields, logo_bytes, render_html
from app.modules.auth.confirmation import codes_match, hash_code, hash_token, resend_allowed
from app.modules.auth.queries import build_insert_outbound_message_query
from app.modules.auth.service import mail_contact


def test_code_hash_rejects_other_code_and_other_email():
    digest = hash_code("Ada@Example.com", "123456")
    assert codes_match("ada@example.com", "123456", digest)
    assert not codes_match("ada@example.com", "000000", digest)
    assert not codes_match("other@example.com", "123456", digest)


def test_resend_waits_one_minute():
    sent = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    assert not resend_allowed(sent, sent + timedelta(seconds=30))
    assert resend_allowed(sent, sent + timedelta(seconds=60))


def test_confirmation_message_contains_the_code():
    message = build_confirmation_message("ada@example.com", "654321")
    assert message["To"] == "ada@example.com"
    assert message["Subject"] == "Регистрация GINITY"
    assert "654321" in message.get_content()
    assert "Код для завершения регистрации" in message.get_content()


def test_reset_message_contains_the_link():
    message = build_reset_message("ada@example.com", "https://ginity.ru/reset?token=abc")
    assert message["Subject"] == "Восстановление пароля GIN"
    assert "https://ginity.ru/reset?token=abc" in message.get_content()


def test_reset_token_hash_hides_the_token():
    assert hash_token("secret-token-value") != "secret-token-value"
    assert hash_token("secret-token-value") == hash_token("secret-token-value")


def test_queued_letter_keeps_the_code_and_not_the_placeholder():
    subject, body = confirmation_letter("654321")
    assert subject == "Регистрация GINITY"
    assert "654321" in body
    assert "unused@localhost" not in body


def test_known_account_uses_email_card_and_registration_keeps_the_address():
    assert mail_contact("ada@example.com", (7, 3)) == {
        "user_id": 3,
        "email_id": 7,
        "to_email": None,
    }
    assert mail_contact("ada@example.com", None) == {
        "user_id": None,
        "email_id": None,
        "to_email": "ada@example.com",
    }


def test_outbound_insert_records_the_rest_actor():
    sql = build_insert_outbound_message_query()
    assert "INSERT INTO outbound_message" in sql
    assert "'rest', :actor, 'rest', :actor" in sql


def test_code_letter_puts_the_queue_text_into_the_template():
    subject, body = confirmation_letter("654321", purpose="login")
    fields = letter_fields(subject, body, "login")
    html = render_html(subject, body, "login")
    assert fields["code"] == "654321"
    assert "654321" not in fields["notes"]
    assert fields["notes"] == confirmation_note()
    assert "Код действует 15 минут. Если вы не запрашивали его — проигнорируйте это письмо." in fields["notes"]
    assert f"cid:{LOGO_CID}" in html
    assert "Копировать" not in html
    assert "654321" in html
    assert "Код для входа" in html
    assert "Код для завершения регистрации" not in html
    assert "Вход" not in html
    register_subject, register_body = confirmation_letter("654321", purpose="register")
    register_html = render_html(register_subject, register_body, "register")
    assert register_subject == "Регистрация GINITY"
    assert "Код для завершения регистрации" in register_html
    assert "Код для входа" not in register_html
    assert 'align="center"' in html
    assert "© 2026 Ginity" in html
    assert logo_bytes().startswith(b"\x89PNG")


def test_confirmation_note_follows_code_ttl(monkeypatch):
    monkeypatch.setattr("app.core.mail.CODE_TTL", timedelta(minutes=1))
    assert confirmation_note() == "Код действует 1 минуту. Если вы не запрашивали его — проигнорируйте это письмо."
    _, body = confirmation_letter("654321")
    assert "1 минуту" in body
    monkeypatch.setattr("app.core.mail.CODE_TTL", timedelta(minutes=2))
    assert "2 минуты" in confirmation_note()


def test_login_message_is_an_entry_code():
    message = build_confirmation_message("ada@example.com", "111222", purpose="login")
    assert message["Subject"] == "Авторизация GINITY"
    assert "111222" in message.get_content()
    assert "входа" in message.get_content()
