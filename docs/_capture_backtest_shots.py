# -*- coding: utf-8 -*-
"""Capture Robots V2 chrome tab screenshots for the backtest PDF."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from sqlalchemy import text

from app.core.database import get_db_context
from app.modules.auth import service as auth_service

OUT_DIR = Path(__file__).resolve().parent / "backtest-shots"
BASE = "http://localhost:5173"
ROBOT_ID = 13


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with get_db_context() as db:
        row = db.execute(
            text('SELECT id, login, created_at FROM "user" WHERE id = 1')
        ).fetchone()
        if not row:
            raise SystemExit("user id=1 not found")
        user = {
            "id": int(row[0]),
            "login": row[1],
            "email": None,
            "phone": None,
            "created_at": row[2].isoformat() if row[2] else None,
        }
        token_resp = auth_service.auth_service.create_user_token(db, user)
        access = token_resp.access_token

    pages = [
        ("01-fleet", f"{BASE}/robots", "Флот"),
        ("02-live", f"{BASE}/robots/{ROBOT_ID}/monitor", "Лайв"),
        ("03-edit", f"{BASE}/robots/edit/{ROBOT_ID}", "Правка"),
        ("04-logs", f"{BASE}/robots/{ROBOT_ID}/logs", "Логи"),
        ("05-backtest", f"{BASE}/robots/{ROBOT_ID}/backtest", "Бэктест"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1.25,
        )
        page = context.new_page()
        page.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=60000)
        page.evaluate(
            """([token, user]) => {
                localStorage.setItem('gin-token', token);
                localStorage.setItem('gin-user', JSON.stringify(user));
                localStorage.setItem('gin-login-at', new Date().toISOString());
            }""",
            [access, user],
        )

        manifest = []
        for slug, url, title in pages:
            page.goto(url, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1500)
            # Prefer chrome/header area + main content
            path = OUT_DIR / f"{slug}.png"
            page.screenshot(path=str(path), full_page=False)
            # Also full-page for backtest (results may be long)
            if slug.endswith("backtest"):
                full = OUT_DIR / f"{slug}-full.png"
                page.screenshot(path=str(full), full_page=True)
                manifest.append({"slug": f"{slug}-full", "title": f"{title} (full)", "file": str(full.name)})
            manifest.append({"slug": slug, "title": title, "file": path.name, "url": url})
            print("saved", path)

        (OUT_DIR / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        browser.close()
    print("done", OUT_DIR)


if __name__ == "__main__":
    main()
