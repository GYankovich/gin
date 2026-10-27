"""Шаблон письма с кодом верификации. Робот подставляет код и пояснение из очереди."""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

_LOGO_PATH = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "assets"
    / "ginity-logo-infinity-g.png"
)
LOGO_CID = "ginity-logo"
_CODE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_LINK = re.compile(r"https?://\S+")

_COPYRIGHT = "© 2026 Ginity"


def confirmation_subject(purpose: str) -> str:
    if purpose == "register":
        return "Регистрация GINITY"
    return "Авторизация GINITY"


def confirmation_heading(purpose: str) -> str:
    if purpose == "register":
        return "Код для завершения регистрации"
    return "Код для входа"


def logo_bytes() -> bytes:
    return _LOGO_PATH.read_bytes()


def letter_fields(subject: str, body: str, purpose: str) -> dict[str, str]:
    """Код и ссылка берутся из текста строки очереди, остальное остаётся пояснением."""
    code_match = _CODE.search(body or "")
    link_match = _LINK.search(body or "")
    code = code_match.group(1) if code_match else ""
    link = link_match.group(0).rstrip(".,)") if link_match else ""
    notes: list[str] = []
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if code and code in line:
            continue
        if link and link in line:
            continue
        notes.append(line)
    return {
        "subject": (subject or "").strip(),
        "purpose": purpose or "",
        "code": code,
        "link": link,
        "notes": "\n".join(notes),
    }


def render_html(subject: str, body: str, purpose: str) -> str:
    fields = letter_fields(subject, body, purpose)
    title = escape(confirmation_heading(fields["purpose"]) if fields["code"] else (fields["subject"] or "GIN"))
    notes_html = "<br>".join(escape(line) for line in fields["notes"].splitlines() if line)
    if fields["code"]:
        main = (
            '<div style="margin:0;background:#f4f5f7;border-radius:12px;text-align:center;'
            'padding:18px 8px 18px 18px;font-family:Consolas,Courier New,monospace;'
            f'font-size:32px;line-height:1.2;letter-spacing:0.28em;color:#13161a;">{escape(fields["code"])}</div>'
        )
    elif fields["link"]:
        href = escape(fields["link"], quote=True)
        main = (
            f'<a href="{href}" style="display:inline-block;background:#13161a;color:#ffffff;'
            'text-decoration:none;padding:12px 22px;border-radius:10px;'
            'font-family:Segoe UI,Arial,sans-serif;font-size:15px;font-weight:600;">Открыть ссылку</a>'
            f'<p style="margin:14px 0 0;font-family:Segoe UI,Arial,sans-serif;font-size:12px;'
            f'line-height:1.5;color:#6b7280;word-break:break-all;">{href}</p>'
        )
    else:
        main = ""
    notes_block = ""
    if notes_html:
        notes_block = (
            '<p style="margin:18px 0 0;font-family:Segoe UI,Arial,sans-serif;font-size:14px;'
            f'line-height:1.55;color:#4b5563;">{notes_html}</p>'
        )
    return f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="width:480px;max-width:480px;background:#ffffff;border-radius:16px;">
          <tr>
            <td align="center" style="background:#13161a;padding:28px 24px;border-radius:16px 16px 0 0;">
              <img src="cid:{LOGO_CID}" width="168" alt="Ginity" style="display:block;border:0;width:168px;height:auto;">
            </td>
          </tr>
          <tr>
            <td style="padding:28px 32px 8px;">
              <h1 style="margin:0;font-family:Segoe UI,Arial,sans-serif;font-size:22px;line-height:1.35;font-weight:600;color:#13161a;">{title}</h1>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 28px;">
              {main}
              {notes_block}
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:14px 32px 20px;border-top:1px solid #eceef1;font-family:Segoe UI,Arial,sans-serif;font-size:12px;color:#9aa1a9;text-align:center;">
              {_COPYRIGHT}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
