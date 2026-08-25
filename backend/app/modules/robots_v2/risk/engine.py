"""Risk Engine facade for robots v2 (greenfield Part V)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.modules.robots.trading.contracts import OrderIntent, Position, Signal
from app.modules.robots.trading.risk.manager import RiskDecision, RiskManager
from app.modules.robots_v2.config.v4_schema import RiskConfig
from app.modules.robots_v2.risk.adapter import risk_params_dict_from_v4, risk_params_from_v4


@dataclass
class Decision:
    code: str
    message: str
    ticker: str | None = None
    allow: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionRiskState:
    accept_new_entries: bool = True
    halt_session: bool = False
    halt_reason: str | None = None
    peak_equity: float = 0.0


class RiskEngine:
    def __init__(self, risk_config: RiskConfig, *, allow_short: bool = False) -> None:
        self.config = risk_config
        # Hard budget for live micro-accounts (allocatedCapital, else wizard capital).
        self._budget_cap = float(risk_config.allocated_capital or risk_config.capital or 0)
        self.manager = RiskManager(
            risk_params_from_v4(risk_config, allow_short=allow_short),
            commission_rate=risk_config.broker_commission_pct / 100.0,
        )
        self.session_state = SessionRiskState()
        self._risk_dict = risk_params_dict_from_v4(risk_config)

    def _capped_equity(self, equity: float) -> float:
        eq = float(equity or 0)
        if eq <= 0:
            return 0.0
        if self._budget_cap > 0:
            return min(eq, self._budget_cap)
        return eq

    def begin_session(self, equity: float) -> None:
        eq = self._capped_equity(equity) or float(equity or 0)
        self.manager.begin_day(eq)
        self.session_state.peak_equity = eq

    def begin_trading_day(self, equity: float) -> None:
        """Reset daily PnL/loss counters without touching session peak (drawdown)."""
        eq = self._capped_equity(equity) or float(equity or 0)
        self.manager.begin_day(eq)

    def rebind_capital(self, equity: float) -> None:
        """Live: size from account equity, capped by allocatedCapital/wizard capital."""
        eq = self._capped_equity(equity)
        if eq <= 0:
            return
        self.config.capital = eq
        share = float(self.config.max_position_share_pct or 0) / 100.0
        self.manager.params.max_position_rub = eq * share

    def evaluate_exits(
        self,
        open_positions: list[dict[str, Any]],
        prices: dict[str, float],
    ) -> list[OrderIntent]:
        return self.manager.plan_sl_tp_exit_intents(
            open_positions,
            prices,
            self._risk_dict,
            cost_kw={
                "broker_commission_rate": self.config.broker_commission_pct / 100.0,
                "ndfl_rate": self.config.tax_pct / 100.0,
            },
        )

    def pre_trade(
        self,
        signal: Signal,
        *,
        cash: float,
        equity: float,
        positions: dict[str, Position],
    ) -> tuple[RiskDecision, Decision]:
        if not self.session_state.accept_new_entries and signal.side == "BUY":
            d = Decision(code="ENTRIES_PAUSED", message="New entries paused", ticker=signal.secid, allow=False)
            return RiskDecision(allow=False, reason=d.code), d
        if not self.session_state.accept_new_entries and signal.side == "SELL":
            # Short entry (no long to close) is blocked; closing long is allowed by RiskManager path.
            has_long = any(
                str(getattr(p, "secid", "") or "").upper() == str(signal.secid or "").upper()
                and str(getattr(p, "side", "")).upper() in ("LONG", "BUY")
                for p in (positions or {}).values()
            )
            if not has_long:
                d = Decision(code="ENTRIES_PAUSED", message="New entries paused", ticker=signal.secid, allow=False)
                return RiskDecision(allow=False, reason=d.code), d

        if self.session_state.halt_session:
            d = Decision(code="SESSION_HALTED", message=self.session_state.halt_reason or "halt", allow=False)
            return RiskDecision(allow=False, reason=d.code), d

        eq = self._capped_equity(equity)
        if eq > self.session_state.peak_equity:
            self.session_state.peak_equity = eq
        dd_limit = self.config.max_drawdown_pct
        if dd_limit > 0 and self.session_state.peak_equity > 0:
            dd = (self.session_state.peak_equity - eq) / self.session_state.peak_equity * 100.0
            if dd >= dd_limit:
                self.session_state.halt_session = True
                self.session_state.halt_reason = "MAX_DRAWDOWN"
                d = Decision(code="MAX_DRAWDOWN", message=f"Drawdown {dd:.1f}% >= {dd_limit}%", allow=False)
                return RiskDecision(allow=False, reason=d.code), d

        decision = self.manager.pre_trade_check(signal, cash=cash, equity=eq, positions=positions)
        code = decision.reason if not decision.allow else "ALLOW"
        audit = Decision(
            code=code,
            message=decision.reason,
            ticker=signal.secid,
            allow=decision.allow,
            meta={"quantity": decision.quantity},
        )
        return decision, audit

    def build_entry_intent(self, signal: Signal, quantity: int, price: float) -> OrderIntent:
        side = "BUY" if signal.side == "BUY" else "SELL"
        ticker = str(signal.secid or signal.figi or "")
        return OrderIntent(
            kind="entry",
            figi=ticker,
            side=side,
            quantity=float(quantity),
            price=price,
            reason=signal.reason or "entry",
            signal_id=signal.signal_id,
            meta={"strategy": signal.strategy or ""},
        )

    def build_exit_intent(self, intent: OrderIntent) -> OrderIntent:
        return intent

    def record_realized_pnl(self, pnl: float) -> None:
        self.manager.today_realized_pnl += pnl

    def pause_entries(self) -> None:
        self.session_state.accept_new_entries = False

    def resume_entries(self) -> None:
        if not self.session_state.halt_session:
            self.session_state.accept_new_entries = True

    def halt(self, reason: str) -> None:
        self.session_state.accept_new_entries = False
        self.session_state.halt_session = True
        self.session_state.halt_reason = reason
