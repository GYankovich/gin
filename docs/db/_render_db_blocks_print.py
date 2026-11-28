"""Render a printable PNG of DB blocks for GIN."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("gin-db-blocks-print.png")

# A4 landscape @ 150 dpi
W, H = 1754, 1240
MARGIN = 48
GAP = 18
COLS = 2
ROWS = 2

BLOCKS = [
    {
        "title": "1. Пользователь и права",
        "purpose": "Кто вошёл, что ему можно, как подтверждена почта",
        "tables": [
            "user — учётка, package_code, status",
            "package / package_feature — тариф и вкладки",
            "user_email / user_phone — контакты (status 1/0)",
            "user_token — сессии входа",
            "email_confirmation — код до создания user",
            "outbound_message — очередь писем",
            "app_config — TTL сессии и прочее",
        ],
        "links": "→ ключи, роботы, счета через user.id",
    },
    {
        "title": "2. API-ключи и роботы",
        "purpose": "Секреты брокера и торговый/бэктест контур",
        "tables": [
            "api_tokens — token + token_secret (шифр)",
            "robots — live/paper робот",
            "robot_config_history — версии конфига",
            "robot_sessions → cycles",
            "robot_signals / decisions",
            "robot_orders → fills",
            "robot_day_stats — дневные W/L",
            "backtest_runs + backtest_*",
        ],
        "links": "ключ → robot.token_id; user владеет обоими",
    },
    {
        "title": "3. Счета и прогресс",
        "purpose": "Что видит дашборд: деньги, позиции, заявки",
        "tables": [
            "portfolio_accounts — брокерские счета",
            "token_portfolio_accounts — какие счета видит ключ",
            "portfolio_snapshots / positions",
            "portfolio_operations / portfolio_orders",
            "portfolio_snapshot_daily — EOD mart",
            "portfolio_account_stats — KPI mart",
        ],
        "links": "user → accounts; token ↔ accounts через TPA",
    },
    {
        "title": "4. Прочие блоки",
        "purpose": "Топливо рынка и служебные очереди",
        "tables": [
            "Рынок: candles_cache, market_*, snapshot*",
            "Bybit: funding / oi / lsr history",
            "Служебные: background_jobs, cron, dictionary",
        ],
        "links": "рынок → роботы и бэктест; jobs → прогоны",
    },
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = (
        ("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    )
    for path in names:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def main() -> None:
    img = Image.new("RGB", (W, H), "#F7F5F1")
    draw = ImageDraw.Draw(img)

    title_f = font(36, bold=True)
    sub_f = font(18)
    card_title = font(24, bold=True)
    body = font(17)
    small = font(15)
    foot = font(14)

    draw.text((MARGIN, 28), "GIN — база данных по блокам", font=title_f, fill="#1A1A1A")
    draw.text(
        (MARGIN, 78),
        "Распечатка для обзора. Стрелки «→» — зависимости между блоками, не полный ER.",
        font=sub_f,
        fill="#4A4A4A",
    )

    top = 118
    bottom = H - 56
    usable_h = bottom - top
    usable_w = W - 2 * MARGIN
    card_w = (usable_w - GAP) // COLS
    card_h = (usable_h - GAP) // ROWS

    colors = [
        ("#E8F1FF", "#1E4E8C"),
        ("#EAF7EE", "#1F6B3A"),
        ("#FFF4E5", "#8A4B12"),
        ("#F1EEF8", "#4A3A7A"),
    ]

    for i, block in enumerate(BLOCKS):
        col = i % COLS
        row = i // COLS
        x0 = MARGIN + col * (card_w + GAP)
        y0 = top + row * (card_h + GAP)
        x1 = x0 + card_w
        y1 = y0 + card_h
        bg, accent = colors[i]

        draw.rounded_rectangle((x0, y0, x1, y1), radius=16, fill=bg, outline=accent, width=3)
        draw.rectangle((x0, y0, x1, y0 + 8), fill=accent)

        pad = 22
        y = y0 + 24
        draw.text((x0 + pad, y), block["title"], font=card_title, fill=accent)
        y += 38
        for line in wrap(draw, block["purpose"], body, card_w - 2 * pad):
            draw.text((x0 + pad, y), line, font=body, fill="#333333")
            y += 24
        y += 8
        draw.line((x0 + pad, y, x1 - pad, y), fill=accent, width=1)
        y += 14

        for item in block["tables"]:
            for line in wrap(draw, "• " + item, small, card_w - 2 * pad):
                draw.text((x0 + pad, y), line, font=small, fill="#222222")
                y += 22
            if y > y1 - 70:
                break

        y = y1 - 48
        draw.line((x0 + pad, y, x1 - pad, y), fill="#CCCCCC", width=1)
        y += 10
        for line in wrap(draw, block["links"], small, card_w - 2 * pad):
            draw.text((x0 + pad, y), line, font=small, fill="#555555")
            y += 20

    draw.text(
        (MARGIN, H - 40),
        "Связи: Пользователь → Ключи/Роботы → Счета; Рынок → Роботы и бэктест.  ·  public, Alembic 0089",
        font=foot,
        fill="#666666",
    )

    img.save(OUT, "PNG", dpi=(150, 150))
    print(OUT)


if __name__ == "__main__":
    main()
