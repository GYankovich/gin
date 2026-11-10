"""Resolve user package → tab features for /me-info and API guards."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import (
    DEFAULT_PACKAGE_ID,
    PACKAGE_TAB_CODES,
    STATUS_ON,
    TAB_BACKTEST,
    TAB_DASHBOARD,
    TAB_PORTFOLIO,
    TAB_ROBOTS,
    User,
)


def _empty_features() -> dict[str, bool]:
    return {code: False for code in PACKAGE_TAB_CODES}


def features_for_package(db: Session, package_id: int | None) -> dict[str, bool]:
    """Map package_feature rows. Disabled package or missing id → all false.

    robots and backtest stay independent (separate feature rows).
    """
    features = _empty_features()
    pid = int(package_id) if package_id is not None else 0
    if pid <= 0:
        return features

    pkg = db.execute(
        text(
            """
            SELECT id
              FROM package
             WHERE id = :package_id
               AND status = :status_on
            """
        ),
        {"package_id": pid, "status_on": STATUS_ON},
    ).fetchone()
    if not pkg:
        return features

    rows = db.execute(
        text(
            """
            SELECT feature, status
              FROM package_feature
             WHERE package_id = :package_id
            """
        ),
        {"package_id": pid},
    ).fetchall()
    for row in rows:
        feature = str(row[0] or "").strip()
        if feature in features:
            features[feature] = int(row[1] or 0) == STATUS_ON
    return features


def package_id_for_user(db: Session, user_id: int) -> int:
    row = db.execute(
        text('SELECT package_code FROM "user" WHERE id = :user_id'),
        {"user_id": user_id},
    ).fetchone()
    if not row or row[0] is None:
        return DEFAULT_PACKAGE_ID
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return DEFAULT_PACKAGE_ID


def features_for_user(db: Session, user_id: int) -> dict[str, bool]:
    return features_for_package(db, package_id_for_user(db, user_id))


def user_has_tab(db: Session, user_id: int, tab_code: str) -> bool:
    return bool(features_for_user(db, user_id).get(tab_code))


def require_package_tab(tab_code: str):
    """FastAPI dependency: 403 when the user's package disables this tab."""

    def _dep(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not user_has_tab(db, int(current_user.id), tab_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Package does not include tab '{tab_code}'",
            )
        return current_user

    return _dep


require_dashboard_tab = require_package_tab(TAB_DASHBOARD)
require_portfolio_tab = require_package_tab(TAB_PORTFOLIO)
require_robots_tab = require_package_tab(TAB_ROBOTS)
require_backtest_tab = require_package_tab(TAB_BACKTEST)
