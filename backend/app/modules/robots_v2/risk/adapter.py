"""Map v4 RiskConfig → v1 RiskParams."""

from __future__ import annotations

from app.modules.robots.trading.risk.params import RiskParams
from app.modules.robots_v2.config.v4_schema import RiskConfig


def risk_params_from_v4(cfg: RiskConfig, *, allow_short: bool = False) -> RiskParams:
    return RiskParams(
        max_position_pct=cfg.max_position_share_pct,
        max_position_rub=cfg.capital * (cfg.max_position_share_pct / 100.0),
        max_daily_loss_rub=cfg.max_daily_loss,
        max_daily_loss_pct=0.0,
        max_drawdown_percent=cfg.max_drawdown_pct,
        max_concurrent_positions=cfg.max_concurrent_positions,
        allow_short=allow_short,
        max_leverage=1.0,
        stop_loss_pct=cfg.stop_loss_pct,
        take_profit_pct=cfg.take_profit_pct,
        commission_pct=cfg.broker_commission_pct,
        free_funds_reserve_pct=5.0,
        min_hold_seconds=0.0,
        min_tp_move_bps=0.0,
    )


def risk_params_dict_from_v4(cfg: RiskConfig) -> dict:
    p = risk_params_from_v4(cfg)
    return {
        "stop_loss_percent": p.stop_loss_pct,
        "take_profit_percent": p.take_profit_pct,
        "stop_loss_pct": p.stop_loss_pct,
        "take_profit_pct": p.take_profit_pct,
        "min_hold_seconds": p.min_hold_seconds,
        "min_tp_move_bps": p.min_tp_move_bps,
    }
