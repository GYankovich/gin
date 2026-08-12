"""Config validation for robots v2."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.modules.robots_v2.config.v4_schema import (
    PortfolioUpdaterConfigV4,
    TradingRobotConfigV4,
)


class ValidationIssue(BaseModel):
    field: str
    message: str
    severity: Literal["error", "warning"] = "error"


def _issues_from_validation_error(exc: ValidationError, prefix: str = "") -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", ()))
        field = f"{prefix}.{loc}" if prefix else loc
        issues.append(ValidationIssue(field=field, message=err["msg"]))
    return issues


def validate_trading_config(raw: dict[str, Any]) -> tuple[TradingRobotConfigV4 | None, list[ValidationIssue]]:
    try:
        return TradingRobotConfigV4.model_validate(raw), []
    except ValidationError as exc:
        return None, _issues_from_validation_error(exc)


def validate_portfolio_config(raw: dict[str, Any]) -> tuple[PortfolioUpdaterConfigV4 | None, list[ValidationIssue]]:
    try:
        return PortfolioUpdaterConfigV4.model_validate(raw), []
    except ValidationError as exc:
        return None, _issues_from_validation_error(exc)
