"""
RiskManager — единый риск-менеджмент для backtest и live.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §7.

Логика, перенесённая в этот модуль:
- проверка лимитов до открытия позиции (max_position_pct/rub, max_concurrent,
  free_funds reserve);
- расчёт размера позиции (по %, по рублям, по дистанции до стопа);
- стопы fixed и trailing (через high/low бара или close);
- дневной P&L и halt при превышении лимита;
- серия убыточных дней (cooling);
- force-close по времени МСК.

В этой версии реализация **по умолчанию использует те же формулы**, что и
`backtest/engine.py` и `grain_seed_orchestrator.py`, чтобы parity-тест проходил
без изменения торгового поведения.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingRiskManager [1]
#/// Исходный модуль `backend/app/modules/robots/trading/risk/manager.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Dict, List, Optional

from app.modules.robots.trading.contracts import Candle, Position, Signal
from app.modules.robots.trading.costs import (
    TradingCosts,
    calculate_position_size,
)
from app.modules.robots.trading.risk.params import RiskParams


# ---------------------------------------------------------------------------
# Утилиты (бывшие в grain_seed_orchestrator.py)
# ---------------------------------------------------------------------------

def parse_force_close_time(value: Optional[str]) -> time:
    """Парсит строку вида '18:45' / '18:45 MSK' / '18:45:00' в time."""
    raw = (value or "").strip()
    head = raw.split()[0] if raw else ""
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(head, fmt).time()
        except ValueError:
            continue
    return time(18, 45)


def compute_effective_free_funds(raw_free: float, reserve_pct: float) -> float:
    """Применяет резерв свободных средств."""
    r = max(0.0, min(100.0, float(reserve_pct or 0.0)))
    return max(0.0, float(raw_free or 0.0) * (1.0 - r / 100.0))


def risk_budget_max_quantity(
    *,
    portfolio_value: float,
    entry_price: float,
    risk_per_trade_pct: float,
    stop_loss_pct: float,
) -> Optional[int]:
    """Сколько лотов укладывается в риск-бюджет на сделку (дистанция до стопа)."""
    if portfolio_value <= 0 or entry_price <= 0 or risk_per_trade_pct <= 0 or stop_loss_pct <= 0:
        return None
    max_loss_rub = portfolio_value * (risk_per_trade_pct / 100.0)
    loss_per_unit = entry_price * (stop_loss_pct / 100.0)
    if loss_per_unit <= 0:
        return None
    q = int(max_loss_rub // loss_per_unit)
    return q if q > 0 else None


# ---------------------------------------------------------------------------
# RiskDecision — результат pre_trade_check
# ---------------------------------------------------------------------------

@dataclass
class RiskDecision:
    allow: bool
    reason: str = ""
    quantity: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# RiskManager
# ---------------------------------------------------------------------------

class RiskManager:
    """Единый риск-менеджмент.

    Сохраняет внутреннее состояние:
    - `today_pnl` — накопленный реализованный + нереализованный P&L за день;
    - `loss_streak` — серия убыточных дней;
    - `cooling_no_new_entries` — флаг паузы на следующий день после превышения streak;
    - `day_start_equity` — equity на старте торгового дня (для max_daily_loss).
    """

    def __init__(
        self,
        params: RiskParams,
        *,
        commission_rate: Optional[float] = None,
        ndfl_rate: Optional[float] = None,
    ):
        self.params = params.normalize() if isinstance(params, RiskParams) else RiskParams.from_legacy_dict(params)
        self.commission_rate = float(commission_rate) if commission_rate is not None else float(self.params.commission_pct) / 100.0
        self.ndfl_rate = float(ndfl_rate) if ndfl_rate is not None else 0.13
        # внутреннее состояние
        self.day_start_equity: Optional[float] = None
        self.today_realized_pnl: float = 0.0
        self.loss_streak: int = 0
        self.cooling_no_new_entries: bool = False
        self._pause_entries_today: bool = False
        self._daily_loss_hit: bool = False

    # ------- жизненный цикл дня -------

    def begin_day(self, equity_at_open: float, *, external_loss_streak: int = 0) -> None:
        """Вызывать в начале каждого торгового дня."""
        self.day_start_equity = float(equity_at_open)
        self.today_realized_pnl = 0.0
        self._daily_loss_hit = False
        # cooling -> один день без новых входов
        if self.cooling_no_new_entries:
            self.cooling_no_new_entries = False
            self._pause_entries_today = True
        else:
            self._pause_entries_today = False
        if external_loss_streak:
            self.loss_streak = max(self.loss_streak, int(external_loss_streak))

    def end_day(self, equity_at_close: float, *, had_trades_today: bool) -> None:
        """Вызывать в конце каждого торгового дня. Обновляет streak/cooling."""
        if self.day_start_equity is None or not had_trades_today:
            return
        if equity_at_close < self.day_start_equity:
            self.loss_streak += 1
        else:
            self.loss_streak = 0
        limit = int(self.params.day_loss_streak_limit or 0)
        if limit > 0 and self.loss_streak >= limit:
            self.cooling_no_new_entries = True
            self.loss_streak = 0

    # ------- проверка ДО открытия позиции -------

    def pre_trade_check(
        self,
        signal: Signal,
        *,
        cash: float,
        equity: float,
        positions: Dict[str, Position],
        today_unrealized_pnl: float = 0.0,
    ) -> RiskDecision:
        """Проверяет, можно ли открыть позицию по сигналу.

        Возвращает RiskDecision(allow=True, quantity=...) или allow=False с reason.
        """
        if signal.side == "SELL":
            key = signal.figi or signal.secid or ""
            has_position = bool((key and key in positions) or (signal.secid and signal.secid in positions))
            if not has_position and not bool(self.params.allow_short):
                return RiskDecision(allow=False, reason="short_not_allowed", quantity=0)
            return RiskDecision(allow=True, reason="sell_signal", quantity=signal.quantity_hint or 0)
        if signal.side != "BUY":
            # CLOSE/REBALANCE — проверки на лимит концентрации/free_funds не нужны
            return RiskDecision(allow=True, reason="exit_signal", quantity=signal.quantity_hint or 0)

        if self._pause_entries_today:
            return RiskDecision(allow=False, reason="blocked_pause_after_loss_streak")

        if self._daily_loss_hit:
            return RiskDecision(allow=False, reason="blocked_daily_loss_cap")

        # дневной лимит убытка (по equity на старте дня + текущему unrealized)
        if self.day_start_equity is not None:
            current_loss = self.day_start_equity - equity - today_unrealized_pnl
            max_rub = float(self.params.effective_max_daily_loss_rub or 0.0)
            max_pct = float(self.params.max_daily_loss_pct or 0.0)
            max_pct_rub = self.day_start_equity * (max_pct / 100.0) if max_pct > 0 else 0.0
            cap = max(max_rub, max_pct_rub) if max_pct_rub > 0 or max_rub > 0 else 0.0
            if cap > 0 and current_loss >= cap:
                self._daily_loss_hit = True
                return RiskDecision(allow=False, reason="blocked_daily_loss_cap")

        # серия убыточных дней
        limit = int(self.params.day_loss_streak_limit or 0)
        if limit > 0 and self.loss_streak >= limit:
            return RiskDecision(allow=False, reason=f"loss_streak>={limit}")

        # концентрация
        max_pos = int(self.params.max_concurrent_positions or 0)
        if max_pos > 0 and len(positions) >= max_pos:
            # допускаем добавление, только если у нас уже есть позиция по этому secid (усреднение)
            key = signal.figi or signal.secid or ""
            if key and key not in positions and signal.secid not in positions:
                return RiskDecision(allow=False, reason="max_concurrent_positions")

        # цена для расчёта объёма
        price = float(signal.target_price or signal.price_at_signal or 0.0)
        if price <= 0:
            return RiskDecision(allow=False, reason="no_execution_price")

        qty = self.compute_quantity(signal, cash=cash, equity=equity, entry_price=price)
        if qty <= 0:
            return RiskDecision(allow=False, reason="rejected_position_size")

        return RiskDecision(allow=True, reason="ok", quantity=qty)

    # ------- расчёт размера позиции -------

    def compute_quantity(
        self,
        signal: Signal,
        *,
        cash: float,
        equity: float,
        entry_price: float,
    ) -> int:
        """Расчёт лотов с учётом всех лимитов риска."""
        if entry_price <= 0:
            return 0

        eff_cash = compute_effective_free_funds(cash, float(self.params.free_funds_reserve_pct or 0.0))

        # cap по дистанции до стопа
        rb_cap = risk_budget_max_quantity(
            portfolio_value=equity,
            entry_price=entry_price,
            risk_per_trade_pct=float(self.params.risk_per_trade_pct or 0.0),
            stop_loss_pct=float(self.params.effective_stop_loss_pct or 0.0),
        )

        max_pos_pct = float(self.params.effective_max_position_pct or 0.0)
        max_pos_rub = float(self.params.max_position_rub or 0.0) if self.params.max_position_rub else None

        # тот же calculate_position_size, что использует Stage5Signals
        qty = calculate_position_size(
            portfolio_value=equity,
            current_price=entry_price,
            max_position_percent=max_pos_pct,
            max_position_rub=max_pos_rub,
            free_funds=eff_cash,
        )

        if rb_cap is not None:
            qty = min(qty, rb_cap)

        # leverage cap: максимум notional = equity * max_leverage.
        max_lev = float(self.params.max_leverage or 0.0)
        if max_lev > 0:
            lev_cap = int((equity * max_lev) // entry_price)
            qty = min(qty, max(0, lev_cap))

        # явная учётная проверка кэша (с комиссией)
        if qty > 0:
            comm = entry_price * qty * self.commission_rate
            if entry_price * qty + comm > cash:
                # сужаем до того, что влезает
                qty = max(0, int((cash - comm) / entry_price))

        return max(0, int(qty))

    # ------- выход по стопу/тейку/трейлингу -------

    def evaluate_exits(
        self,
        position: Position,
        candle: Candle,
    ) -> Optional[Signal]:
        """Проверяет SL/TP/трейлинг по текущему бару.

        Возвращает Signal(side="CLOSE") если сработал выход.
        Цена выхода кладётся в `target_price` сигнала.
        """
        if position.quantity <= 0:
            return None

        entry = float(position.avg_entry_price or 0.0)
        if entry <= 0:
            return None

        stop_pct = float(self.params.effective_stop_loss_pct or 0.0)
        tp_pct = float(self.params.effective_take_profit_pct or 0.0)
        mode = self.params.stop_loss_mode

        if mode == "trailing":
            return self._evaluate_trailing(position, candle, stop_pct, tp_pct)

        # fixed: SL/TP по high/low бара
        if stop_pct > 0 or tp_pct > 0:
            lo = float(candle.low)
            hi = float(candle.high)
            sl_px = entry * (1.0 - stop_pct / 100.0) if stop_pct > 0 else None
            tp_px = entry * (1.0 + tp_pct / 100.0) if tp_pct > 0 else None
            if position.side == "LONG":
                if sl_px is not None and lo <= sl_px:
                    return self._make_close_signal(position, sl_px, "stop_loss", candle)
                if tp_px is not None and hi >= tp_px:
                    return self._make_close_signal(position, tp_px, "take_profit", candle)
            else:  # SHORT
                if tp_px is not None and lo <= entry * (1.0 - tp_pct / 100.0):
                    return self._make_close_signal(position, entry * (1.0 - tp_pct / 100.0), "take_profit", candle)
                if sl_px is not None and hi >= entry * (1.0 + stop_pct / 100.0):
                    return self._make_close_signal(position, entry * (1.0 + stop_pct / 100.0), "stop_loss", candle)
        return None

    def _evaluate_trailing(
        self,
        position: Position,
        candle: Candle,
        stop_pct: float,
        tp_pct: float,
    ) -> Optional[Signal]:
        """Trailing-stop: после активации стоп подтягивается за пиком.

        Формулы согласованы с поведением `engine.py`:
            peak = max(peak, close);
            stop_px = peak * (1 - trailing_step_pct/100), но не выше entry*(1 - stop_pct/100).
            Активируется, только если close >= entry * (1 + trailing_activation_pct/100).
        """
        close = float(candle.close)
        if close <= 0:
            return None

        entry = float(position.avg_entry_price or 0.0)
        activation_pct = float(self.params.trailing_activation_pct or 0.0)
        step_pct = float(self.params.trailing_step_pct or 0.0)

        # обновляем peak
        if position.peak_price <= 0:
            position.peak_price = max(entry, close)
        else:
            position.peak_price = max(position.peak_price, close)

        # фиксированный TP (если активирован)
        if tp_pct > 0:
            tp_px = entry * (1.0 + tp_pct / 100.0)
            if float(candle.high) >= tp_px:
                return self._make_close_signal(position, tp_px, "take_profit", candle)

        # активирован ли трейлинг?
        activated = activation_pct <= 0 or position.peak_price >= entry * (1.0 + activation_pct / 100.0)
        if not activated:
            # до активации работает обычный фикс-стоп
            if stop_pct > 0 and float(candle.low) <= entry * (1.0 - stop_pct / 100.0):
                return self._make_close_signal(position, entry * (1.0 - stop_pct / 100.0), "stop_loss", candle)
            return None

        # трейлинг активирован
        if step_pct <= 0:
            step_pct = stop_pct
        stop_px = position.peak_price * (1.0 - step_pct / 100.0)
        # но не ниже обычного стопа
        if stop_pct > 0:
            stop_px = max(stop_px, entry * (1.0 - stop_pct / 100.0))
        if close <= stop_px:
            return self._make_close_signal(position, close, "trailing_stop", candle)
        return None

    def _make_close_signal(
        self,
        position: Position,
        price: float,
        reason: str,
        candle: Candle,
    ) -> Signal:
        bar_time_str = candle.time.isoformat() if hasattr(candle.time, "isoformat") else str(candle.time)
        return Signal(
            secid=position.secid,
            figi=position.figi,
            side="CLOSE",
            target_price=float(price),
            reason=reason,
            bar_time=bar_time_str,
            quantity_hint=int(position.quantity),
            meta={"trigger": reason},
        )

    # ------- force-close по времени МСК -------

    def force_close_signals(
        self,
        now_msk: datetime,
        positions: Dict[str, Position],
    ) -> List[Signal]:
        """Если now_msk >= force_close_time — генерим CLOSE на все позиции."""
        if not positions:
            return []
        ft = parse_force_close_time(self.params.force_close_time)
        if now_msk.time() < ft:
            return []
        out: List[Signal] = []
        for key, pos in positions.items():
            if pos.quantity <= 0:
                continue
            px = float(pos.current_price or pos.avg_entry_price or 0.0)
            out.append(Signal(
                secid=pos.secid,
                figi=pos.figi,
                side="CLOSE",
                target_price=px if px > 0 else None,
                reason="force_market_flatten_eod",
                quantity_hint=int(pos.quantity),
                meta={"trigger": "force_close_time"},
            ))
        return out

    # ------- состояние / трейс -------

    def record_realized_pnl(self, pnl: float) -> None:
        self.today_realized_pnl += float(pnl)

    def is_trading_halted(self, equity: float) -> tuple[bool, str]:
        """Является ли торговля заблокированной (без открытия новых)."""
        limit = int(self.params.day_loss_streak_limit or 0)
        if limit > 0 and self.loss_streak >= limit:
            return True, f"loss_streak>={limit}"
        if self._pause_entries_today:
            return True, "cooling_after_loss_streak"
        if self._daily_loss_hit:
            return True, "daily_loss_cap"
        return False, ""


__all__ = [
    "RiskManager",
    "RiskDecision",
    "parse_force_close_time",
    "compute_effective_free_funds",
    "risk_budget_max_quantity",
]
