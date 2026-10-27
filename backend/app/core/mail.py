"""Исходящая почта. Код подтверждения уходит через SMTP, если он задан в окружении."""

from __future__ import annotations

import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from app.core.config import settings
from app.core.mail_template import (
    LOGO_CID,
    confirmation_heading,
    confirmation_subject,
    logo_bytes,
    render_html,
)
from app.modules.auth.confirmation import CODE_TTL

logger = logging.getLogger(__name__)


class MailDeliveryError(Exception):
    """SMTP ответил ошибкой или соединение оборвалось."""


def _codes_mailbox() -> dict[str, object] | None:
    host = settings.SMTP_CODES_HOST.strip()
    sender = settings.SMTP_CODES_FROM.strip()
    if not host or not sender:
        return None
    return {
        "host": host,
        "port": int(settings.SMTP_CODES_PORT),
        "user": settings.SMTP_CODES_USER.strip(),
        "password": settings.SMTP_CODES_PASSWORD,
        "sender": sender,
        "ssl": bool(settings.SMTP_CODES_SSL),
        "tls": bool(settings.SMTP_CODES_TLS),
    }


def _legacy_mailbox() -> dict[str, object] | None:
    host = settings.SMTP_HOST.strip()
    sender = settings.SMTP_FROM.strip()
    if not host or not sender:
        return None
    return {
        "host": host,
        "port": int(settings.SMTP_PORT),
        "user": settings.SMTP_USER.strip(),
        "password": settings.SMTP_PASSWORD,
        "sender": sender,
        "ssl": bool(settings.SMTP_SSL),
        "tls": bool(settings.SMTP_TLS),
    }


def mailbox():
    """Ящик кодов, если он задан. Иначе прежний общий SMTP_*."""
    return _codes_mailbox() or _legacy_mailbox()


def smtp_configured() -> bool:
    return mailbox() is not None


def _ru_minutes(count: int) -> str:
    """15 минут, 2 минуты, 1 минуту."""
    n = abs(count) % 100
    n1 = n % 10
    if 11 <= n <= 14 or n1 == 0 or n1 >= 5:
        word = "минут"
    elif n1 == 1:
        word = "минуту"
    else:
        word = "минуты"
    return f"{count} {word}"


def confirmation_note(ttl: timedelta | None = None) -> str:
    span = CODE_TTL if ttl is None else ttl
    minutes = max(1, int(span.total_seconds() // 60))
    return (
        f"Код действует {_ru_minutes(minutes)}. "
        "Если вы не запрашивали его — проигнорируйте это письмо."
    )


def build_confirmation_message(to: str, code: str, purpose: str = "register") -> EmailMessage:
    """Шаблон письма с кодом верификации. Вход и регистрация отличаются темой и заголовком."""
    message = EmailMessage()
    message["Subject"] = confirmation_subject(purpose)
    message["From"] = settings.SMTP_FROM.strip() or "GIN <noreply@localhost>"
    message["To"] = to
    message.set_content("\n".join([f"{confirmation_heading(purpose)}: {code}", "", confirmation_note()]))
    return message


def confirmation_letter(code: str, purpose: str = "register") -> tuple[str, str]:
    """Тема и текст письма с кодом. Адрес получателя в текст не входит."""
    message = build_confirmation_message("unused@localhost", code, purpose)
    return str(message["Subject"]), message.get_content().strip()


def reset_letter(link: str) -> tuple[str, str]:
    message = build_reset_message("unused@localhost", link)
    return str(message["Subject"]), message.get_content().strip()


def build_reset_message(to: str, link: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "Восстановление пароля GIN"
    message["From"] = settings.SMTP_FROM.strip() or "GIN <noreply@localhost>"
    message["To"] = to
    message.set_content(
        "\n".join(
            [
                "Чтобы задать новый пароль, откройте ссылку:",
                link,
                "",
                "Ссылка действует 30 минут.",
                "Если вы не запрашивали восстановление, проигнорируйте это письмо.",
            ]
        )
    )
    return message


def send_queued_message(to: str, subject: str, body: str, purpose: str) -> None:
    """Собирает письмо из строки очереди: текст остаётся как есть, HTML — из шаблона."""
    account = mailbox()
    if account is None:
        raise MailDeliveryError("SMTP is not configured")
    message = EmailMessage()
    message["Subject"] = subject or ""
    message["From"] = str(account["sender"])
    message["To"] = to
    message.set_content(body or "")
    html = render_html(subject, body, purpose)
    message.add_alternative(html, subtype="html")
    html_part = message.get_payload()[1]
    html_part.add_related(
        logo_bytes(),
        maintype="image",
        subtype="png",
        cid=f"<{LOGO_CID}>",
    )
    _deliver(account, message, to)


def send_prepared_message(to: str, subject: str, body: str) -> None:
    """Отправляет уже собранное письмо. Робот берёт тему и текст из очереди."""
    account = mailbox()
    if account is None:
        raise MailDeliveryError("SMTP is not configured")
    message = EmailMessage()
    message["Subject"] = subject or ""
    message["From"] = str(account["sender"])
    message["To"] = to
    message.set_content(body)
    _deliver(account, message, to)


def deliver_confirmation_code(to: str, code: str, purpose: str = "register") -> str | None:
    """Отправляет код. В разработке без SMTP возвращает код, чтобы регистрацию можно было пройти.

    В production без SMTP поднимает MailDeliveryError.
    """
    if not smtp_configured():
        if settings.is_production:
            raise MailDeliveryError("SMTP is not configured")
        logger.warning("SMTP не настроен, код подтверждения для %s: %s", to, code)
        return code

    message = build_confirmation_message(to, code, purpose)
    account = mailbox()
    if account is None:
        raise MailDeliveryError("SMTP is not configured")
    message.replace_header("From", str(account["sender"]))
    _deliver(account, message, to)
    return None


def deliver_reset_link(to: str, link: str) -> str | None:
    """Отправляет ссылку. В разработке без SMTP возвращает ссылку."""
    if not smtp_configured():
        if settings.is_production:
            raise MailDeliveryError("SMTP is not configured")
        logger.warning("SMTP не настроен, ссылка восстановления для %s: %s", to, link)
        return link

    message = build_reset_message(to, link)
    account = mailbox()
    if account is None:
        raise MailDeliveryError("SMTP is not configured")
    message.replace_header("From", str(account["sender"]))
    _deliver(account, message, to)
    return None


def _deliver(account: dict[str, object], message: EmailMessage, to: str) -> None:
    host = str(account["host"])
    port = int(account["port"])
    try:
        if account["ssl"]:
            with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
                _login_and_send(smtp, message, account)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                if account["tls"]:
                    smtp.starttls()
                _login_and_send(smtp, message, account)
    except MailDeliveryError:
        raise
    except Exception as exc:
        logger.exception("Не удалось отправить письмо на %s", to)
        raise MailDeliveryError(str(exc)) from exc


def _login_and_send(smtp: smtplib.SMTP, message: EmailMessage, account: dict[str, object]) -> None:
    user = str(account["user"] or "").strip()
    if user:
        smtp.login(user, str(account["password"] or ""))
    smtp.send_message(message)
