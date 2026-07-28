"""
History backtest через полный TradingSession (Stage5/6, grain_seed, stop-loss).

Live: WebSocket + брокер. Backtest: replay свечей в price_queue + SimBacktestBrokerFacade.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.modules.robots.trading.backtest.types import (
    BacktestResult,
    bar_in_trading_session as _bar_in_trading_session,
    candle_time_iso as _candle_time_iso,
    session_time_from_risk as _session_time_from_risk,
)
from app.modules.robots.trading.brokers.sim_backtest import (
    SimBacktestBrokerFacade,
    _close_price,
)
from app.modules.robots.trading.indicators.service import indicator_service
from app.modules.robots.trading.contracts import ExecutionMode
from app.modules.robots.trading.session import TradingSession

logger = logging.getLogger(__name__)


def _iso_to_dt(iso: str) -> datetime:
    s = str(iso or "").replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _funding_events_in_window(
    prev_bar_time: Optional[str],
    bar_time: str,
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    bar_dt = _iso_to_dt(bar_time)
    if prev_bar_time:
        prev_dt = _iso_to_dt(prev_bar_time)
    else:
        prev_dt = datetime.min.replace(tzinfo=timezone.utc)
    out: List[Dict[str, Any]] = []
    for ev in events or []:
        ft = ev.get("funding_time")
        if ft is None:
            continue
        if isinstance(ft, str):
            fdt = _iso_to_dt(ft)
        elif isinstance(ft, datetime):
            fdt = ft if ft.tzinfo else ft.replace(tzinfo=timezone.utc)
        else:
            continue
        if prev_dt < fdt <= bar_dt:
            out.append(ev)
    return out


class BacktestTradingSession(TradingSession):
    """TradingSession на исторических данных без записи в robot_trades/signals."""

    def __init__(
        self,
        *,
        sim_broker: SimBacktestBrokerFacade,
        allowed_figis_by_date: Dict[str, List[str]],
        **kwargs,
    ):
        super().__init__(**kwargs, mode=ExecutionMode.BACKTEST)
        self._broker = sim_broker
        self._sim_broker = sim_broker
        self.allowed_figis_by_date = {
            str(k): [str(x).upper() for x in (v or []) if x]
            for k, v in (allowed_figis_by_date or {}).items()
        }
        self._current_bar_time: str = ""
        self._sim_now = datetime.now(timezone.utc)
        self._clock_override = lambda: self._sim_now
        self._skip_cycle_sleep = True
        self._bt_signals: List[Dict[str, Any]] = []
        self._bt_equity_curve: List[Dict[str, Any]] = []
        self._signal_seq = 0
        self._bt_daily_pnl: Dict[str, float] = {}
        self.account_id = "BACKTEST"
        self._prev_bar_time: str = ""
        self._applied_funding_keys: Set[Tuple[str, str]] = set()
        self._funding_by_symbol: Dict[str, List[Dict[str, Any]]] = {}

    def _backtest_trading_hours(self) -> Optional[Tuple[time, time]]:
        if str(self.broker_type or "").lower() == "bybit":
            return None
        return (
            _session_time_from_risk(self.risk_params.get("trading_hours_start"), "10:00"),
            _session_time_from_risk(self.risk_params.get("trading_hours_end"), "18:45"),
        )

    def _bar_allowed_in_session(self, bar_iso: str) -> bool:
        hours = self._backtest_trading_hours()
        if hours is None:
            return True
        session_start, session_end = hours
        return _bar_in_trading_session(bar_iso, session_start, session_end)

    def _funding_mode(self) -> str:
        costs = self.config.get("costs") if isinstance(self.config.get("costs"), dict) else {}
        mode = str(costs.get("funding_mode") or "").strip().lower()
        if mode in {"off", "historical", "forecast", "average"}:
            return mode
        if not bool(costs.get("funding_rate_enabled", True)):
            return "off"
        return "historical"

    def _crypto_funding_enabled(self) -> bool:
        if str(self.broker_type or "").lower() != "bybit":
            return False
        if self._funding_mode() == "off":
            return False
        bybit_cfg = self.config.get("bybit") if isinstance(self.config.get("bybit"), dict) else {}
        category = str(bybit_cfg.get("instrument_category") or "linear").strip().lower()
        return category != "spot"

    def _resolve_funding_rate(
        self,
        events: List[Dict[str, Any]],
        ev: Dict[str, Any],
        *,
        bar_time: str,
    ) -> float:
        mode = self._funding_mode()
        if mode == "historical":
            return float(ev.get("funding_rate") or 0)
        if mode == "average":
            rates = [float(e.get("funding_rate") or 0) for e in (events or [])]
            return (sum(rates) / len(rates)) if rates else 0.0
        if mode == "forecast":
            ft = ev.get("funding_time")
            if isinstance(ft, str):
                fdt = _iso_to_dt(ft)
            elif isinstance(ft, datetime):
                fdt = ft if ft.tzinfo else ft.replace(tzinfo=timezone.utc)
            else:
                fdt = None
            if fdt is not None:
                for candidate in events or []:
                    cft = candidate.get("funding_time")
                    if isinstance(cft, str):
                        cdt = _iso_to_dt(cft)
                    elif isinstance(cft, datetime):
                        cdt = cft if cft.tzinfo else cft.replace(tzinfo=timezone.utc)
                    else:
                        continue
                    if cdt > fdt:
                        return float(candidate.get("funding_rate") or ev.get("funding_rate") or 0)
            return float(ev.get("funding_rate") or 0)
        return float(ev.get("funding_rate") or 0)

    def _load_funding_schedule(self, symbols: List[str]) -> None:
        if not self._crypto_funding_enabled() or not symbols:
            self._funding_by_symbol = {}
            return
        from datetime import time as time_cls, timedelta
        from app.modules.robots.trading.data.providers.bybit_market import load_funding_history_from_cache

        bybit_cfg = self.config.get("bybit") if isinstance(self.config.get("bybit"), dict) else {}
        category = str(bybit_cfg.get("instrument_category") or "linear").strip().lower()
        all_times: List[datetime] = []
        for sym in symbols:
            for c in self._sim_broker.candles_by_figi.get(sym, []):
                iso = _candle_time_iso(c)
                if iso:
                    all_times.append(_iso_to_dt(iso))
        if not all_times:
            self._funding_by_symbol = {}
            return
        from_dt = min(all_times).replace(hour=0, minute=0, second=0, microsecond=0)
        to_dt_exclusive = max(all_times) + timedelta(days=1)
        to_dt_exclusive = datetime.combine(
            to_dt_exclusive.date(),
            time_cls.min,
            tzinfo=timezone.utc,
        )
        self._funding_by_symbol = load_funding_history_from_cache(
            self.db,
            symbols=symbols,
            instrument_category=category,
            from_dt=from_dt,
            to_dt_exclusive=to_dt_exclusive,
        )

    def _apply_funding_charges_for_bar(self, bar_time: str) -> None:
        if not self._funding_by_symbol:
            return
        day_key = bar_time[:10] if bar_time else self._sim_now.strftime("%Y-%m-%d")
        for symbol, events in self._funding_by_symbol.items():
            due = _funding_events_in_window(self._prev_bar_time or None, bar_time, events)
            for ev in due:
                ft = ev.get("funding_time")
                if isinstance(ft, datetime):
                    ft_key = ft.astimezone(timezone.utc).isoformat()
                else:
                    ft_key = str(ft)
                dedupe = (symbol.upper(), ft_key)
                if dedupe in self._applied_funding_keys:
                    continue
                rate = self._resolve_funding_rate(events, ev, bar_time=bar_time)
                adjustment = self._sim_broker.apply_funding_charge(
                    symbol,
                    rate,
                    bar_time=bar_time,
                )
                if adjustment != 0.0:
                    self._applied_funding_keys.add(dedupe)
                    self._bt_daily_pnl[day_key] = float(self._bt_daily_pnl.get(day_key, 0) or 0) + adjustment

    @property
    def broker(self):
        return self._sim_broker

    async def _publish_live_event(self, payload: Dict[str, Any]) -> None:
        return None

    async def _sync_portfolio_updater_snapshot(self) -> None:
        return None

    async def _create_execution_log(self) -> Optional[int]:
        return None

    async def _complete_execution_log(self, **kwargs) -> None:
        return None

    async def create_run_cycle(self, *args, **kwargs) -> Optional[int]:
        return None

    async def complete_run_cycle(self, *args, **kwargs) -> None:
        return None

    async def save_decision(self, *args, **kwargs) -> Optional[int]:
        return None

    async def save_order_event(self, *args, **kwargs) -> None:
        return None

    async def mark_signals_executed(self, *args, **kwargs) -> int:
        return 0

    async def update_trade_status(self, *args, **kwargs) -> bool:
        return True

    async def _ensure_account_id(self) -> Optional[str]:
        self.account_id = "BACKTEST"
        return self.account_id

    async def refresh_config(self) -> None:
        """Backtest: конфиг frozen из snapshot — не дергаем БД на каждом баре."""
        return

    async def _update_positions(self) -> None:
        self.positions = self._sim_broker.open_positions_for_session()
        self.cached_positions = self.positions

    async def _is_daily_loss_limit_breached(self) -> bool:
        max_daily_loss = float(self.risk_params.get("max_daily_loss", 0) or 0)
        if max_daily_loss <= 0:
            return False
        total_value = float((self.portfolio or {}).get("total_value", 0) or 0)
        if total_value <= 0:
            return False
        day_key = self._sim_now.strftime("%Y-%m-%d")
        daily_pnl = float(self._bt_daily_pnl.get(day_key, 0) or 0)
        daily_loss_pct = (-daily_pnl / total_value) * 100.0 if daily_pnl < 0 else 0.0
        return daily_loss_pct >= max_daily_loss

    async def save_signals(self, db, schema, robot_id, signals: List[Dict]) -> List[int]:
        ids: List[int] = []
        for s in signals:
            self._signal_seq += 1
            sid = self._signal_seq
            s["_signal_id"] = sid
            ids.append(sid)
            self._bt_signals.append(
                {
                    "id": sid,
                    "figi": s.get("figi"),
                    "signal_type": str(s.get("signal", "")).lower(),
                    "bar_time": self._current_bar_time,
                    "price": s.get("price"),
                    "was_executed": 0,
                    "reason": s.get("reason"),
                }
            )
        return ids

    async def save_trades(self, db, schema, robot_id, trades: List[Dict]) -> List[int]:
        ids: List[int] = []
        for i, t in enumerate(trades):
            if t.get("status") in {"skipped", "failed"}:
                continue
            tid = len(self._sim_broker.trade_log) + i + 1
            ids.append(tid)
            pnl = t.get("profit")
            if pnl is not None:
                day_key = self._current_bar_time[:10] if self._current_bar_time else self._sim_now.strftime("%Y-%m-%d")
                self._bt_daily_pnl[day_key] = float(self._bt_daily_pnl.get(day_key, 0) or 0) + float(pnl)
        executed_sids = {
            int(t["signal_id"])
            for t in trades
            if t.get("signal_id") and t.get("status") not in {"failed", "skipped"}
        }
        for sig in self._bt_signals:
            if int(sig.get("id") or 0) in executed_sids:
                sig["was_executed"] = 1
        return ids

    async def _feed_bar(self, bar_time: str, candles_at_bar: Dict[str, Dict[str, Any]]) -> None:
        self._current_bar_time = bar_time
        self._sim_now = _iso_to_dt(bar_time)
        self._sim_broker.current_bar_time = bar_time
        day = bar_time[:10]
        allowed = self.allowed_figis_by_date.get(day)
        if allowed is not None:
            self.allowed_figis = list(allowed)

        prices: Dict[str, float] = {}
        for figi, candle in candles_at_bar.items():
            px = _close_price(candle)
            if px <= 0:
                continue
            prices[figi] = px
            self._sim_broker.set_last_price(figi, px)
            await indicator_service.on_closed_candle(
                self.robot_id,
                self.broker,
                figi,
                candle,
                self.strategy_params,
                persist_to_db=False,
            )
            await self._put_to_queue_with_limit(
                self.price_queue,
                {
                    "type": "candle_closed",
                    "figi": figi,
                    "candle": candle,
                    "price": px,
                    "timestamp": self._sim_now.isoformat(),
                },
            )
            self.stats["prices_received"] += 1

        self.cached_prices.update(prices)

    def _record_equity(self) -> None:
        eq = float(self._sim_broker._equity())
        self._bt_equity_curve.append({"time": self._current_bar_time, "equity": eq})

    async def run_history_replay(
        self,
        *,
        candles_by_figi: Dict[str, List[Dict[str, Any]]],
        cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
        cancel_check_sync: Optional[Callable[[], bool]] = None,
        progress_callback_sync: Optional[Callable[[int, int], None]] = None,
    ) -> BacktestResult:
        initial_capital = float(self._sim_broker.cash)
        br, ndfl = self._sim_broker.commission_rate, self._sim_broker.ndfl_rate

        figis = list(candles_by_figi.keys())
        if not figis:
            raise ValueError("Нет свечей")

        self._sim_broker.candles_by_figi = candles_by_figi
        self.strategy_params["figis"] = figis
        all_figis = sorted(set(figis))
        self.allowed_figis = all_figis

        self._load_funding_schedule(all_figis)

        session_hours = self._backtest_trading_hours()

        candles_by_day: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for f in figis:
            for c in sorted(candles_by_figi.get(f, []), key=_candle_time_iso):
                t = _candle_time_iso(c)
                if not t or len(t) < 10:
                    continue
                candles_by_day.setdefault(t[:10], {}).setdefault(f, []).append(c)

        bars_total = 0
        for day in sorted(candles_by_day.keys()):
            dm = candles_by_day[day] or {}
            times = sorted({(_candle_time_iso(c) or "") for ff in dm for c in dm.get(ff, []) if _candle_time_iso(c)})
            if session_hours:
                session_start, session_end = session_hours
                times = [bt for bt in times if _bar_in_trading_session(bt, session_start, session_end)]
            else:
                times = [bt for bt in times if self._bar_allowed_in_session(bt)]
            bars_total += len(times)

        await indicator_service.register_robot(self.robot_id, self.broker, all_figis, self.strategy_params)
        await indicator_service.bootstrap_candles_at_startup(
            self.robot_id,
            self.broker,
            all_figis,
            self.strategy_params,
            log_func=self._write_log,
        )

        await self._update_portfolio()
        cycle_count = 0
        bars_processed = 0
        peak_equity = initial_capital
        max_dd_pct: Optional[float] = None
        max_dd_limit = float(self.risk_params.get("max_drawdown_percent") or 0)
        stop_replay = False

        if progress_callback_sync and bars_total > 0:
            try:
                progress_callback_sync(0, bars_total)
            except Exception:
                pass

        for day in sorted(candles_by_day.keys()):
            if stop_replay:
                break
            if cancel_check_sync and cancel_check_sync():
                return _build_result(
                    initial_capital, self._sim_broker, self._bt_equity_curve,
                    self._bt_signals, peak_equity, max_dd_pct, cancelled=True,
                )
            if cancel_check:
                try:
                    if await cancel_check():
                        return _build_result(
                            initial_capital, self._sim_broker, self._bt_equity_curve,
                            self._bt_signals, peak_equity, max_dd_pct, cancelled=True,
                        )
                except Exception:
                    pass

            day_map = candles_by_day.get(day) or {}
            allowed_today = set(self.allowed_figis_by_date.get(day, []))
            day_figis = sorted(f for f in day_map.keys() if not allowed_today or f.upper() in allowed_today)
            if not day_figis:
                continue

            day_times = sorted({(_candle_time_iso(c) or "") for ff in day_figis for c in day_map.get(ff, []) if _candle_time_iso(c)})
            if session_hours:
                session_start, session_end = session_hours
                day_times = [bt for bt in day_times if _bar_in_trading_session(bt, session_start, session_end)]
            else:
                day_times = [bt for bt in day_times if self._bar_allowed_in_session(bt)]
            if not day_times:
                continue

            for bar_time in day_times:
                if stop_replay:
                    break
                bars_processed += 1
                if progress_callback_sync and bars_total > 0:
                    if bars_processed % 48 == 0 or bars_processed == bars_total:
                        try:
                            progress_callback_sync(bars_processed, bars_total)
                        except Exception:
                            pass

                at_bar: Dict[str, Dict[str, Any]] = {}
                for ff in day_figis:
                    for c in day_map.get(ff, []):
                        if _candle_time_iso(c) == bar_time:
                            at_bar[ff] = c
                            break
                if not at_bar:
                    continue

                await self._feed_bar(bar_time, at_bar)
                liq_events = self._sim_broker.check_liquidations()
                if liq_events:
                    self._write_log(f"   ⚠️ Margin liquidation: {len(liq_events)} position(s)")
                cycle_count += 1
                try:
                    await self._run_single_trading_cycle(cycle_count)
                except Exception as exc:
                    logger.exception("backtest trading cycle failed bar=%s: %s", bar_time, exc)
                    self.stats["errors"] += 1

                self._apply_funding_charges_for_bar(bar_time)
                self._prev_bar_time = bar_time

                self._record_equity()
                eq = float(self._bt_equity_curve[-1]["equity"]) if self._bt_equity_curve else initial_capital
                if eq > peak_equity:
                    peak_equity = eq
                if peak_equity > 0:
                    dd = (peak_equity - eq) / peak_equity * 100.0
                    if max_dd_pct is None or dd > max_dd_pct:
                        max_dd_pct = dd
                if max_dd_limit > 0 and max_dd_pct is not None and max_dd_pct >= max_dd_limit:
                    self._write_log(
                        f"🛑 Достигнута макс. просадка {max_dd_limit:.2f}% "
                        f"(текущая {max_dd_pct:.2f}%), бэктест остановлен"
                    )
                    stop_replay = True
                    break

        await indicator_service.unregister_robot(self.robot_id)
        return _build_result(
            initial_capital, self._sim_broker, self._bt_equity_curve,
            self._bt_signals, peak_equity, max_dd_pct, cancelled=False,
        )


def _build_result(
    initial_capital: float,
    broker: SimBacktestBrokerFacade,
    equity_curve: List[Dict[str, Any]],
    signals: List[Dict[str, Any]],
    peak_equity: float,
    max_dd_pct: Optional[float],
    *,
    cancelled: bool,
) -> BacktestResult:
    final_equity = float(broker._equity())
    ret_pct = ((final_equity - initial_capital) / initial_capital * 100.0) if initial_capital > 0 else 0.0
    fee_summary = broker.fee_totals()
    trades: List[Dict[str, Any]] = []
    for i, t in enumerate(broker.trade_log):
        trades.append(
            {
                "id": i + 1,
                "figi": t.get("figi"),
                "side": t.get("side"),
                "bar_time": t.get("bar_time") or "",
                "price": round(float(t.get("price") or 0), 6),
                "quantity": int(t.get("quantity") or 0),
                "commission": round(float(t.get("commission") or 0), 4),
                "fee_kind": t.get("fee_kind"),
                "order_type": t.get("order_type"),
                "liquidation": bool(t.get("liquidation")),
                "pnl_net": round(float(t.get("pnl_net") or 0), 4) if t.get("pnl_net") is not None else None,
            }
        )
    for i, ev in enumerate(broker.liquidation_log):
        trades.append(
            {
                "id": len(trades) + 1,
                "figi": ev.get("figi"),
                "side": "sell",
                "bar_time": ev.get("bar_time") or "",
                "price": round(float(ev.get("mark_price") or 0), 6),
                "quantity": int(ev.get("qty") or 0),
                "commission": 0.0,
                "fee_kind": "taker",
                "order_type": "liquidation",
                "liquidation": True,
                "pnl_net": None,
            }
        )
    return BacktestResult(
        initial_capital=initial_capital,
        final_equity=final_equity,
        total_return_percent=ret_pct,
        max_drawdown_percent=max_dd_pct,
        trades=trades,
        equity_curve=equity_curve,
        signals=signals,
        cancelled=cancelled,
        fee_summary=fee_summary,
        margin_summary=broker.margin_summary(),
    )


async def run_session_history_backtest(
    *,
    db: Session,
    schema: str,
    robot_id: int,
    user_id: int,
    token_id: int,
    token: str,
    config: Dict[str, Any],
    candles_by_figi: Dict[str, List[Dict[str, Any]]],
    allowed_figis_by_date: Dict[str, List[str]],
    initial_capital: float,
    log_func=None,
    cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
    cancel_check_sync: Optional[Callable[[], bool]] = None,
    progress_callback_sync: Optional[Callable[[int, int], None]] = None,
) -> BacktestResult:
    """Запуск полного TradingSession на исторических свечах (deprecated alias → orchestrator)."""
    from app.modules.robots.trading.runtime import get_trading_orchestrator

    return await get_trading_orchestrator().run_backtest_replay(
        db=db,
        schema=schema,
        robot_id=robot_id,
        user_id=user_id,
        token_id=token_id,
        token=token,
        config=config,
        candles_by_figi=candles_by_figi,
        allowed_figis_by_date=allowed_figis_by_date,
        initial_capital=initial_capital,
        log_func=log_func,
        cancel_check=cancel_check,
        cancel_check_sync=cancel_check_sync,
        progress_callback_sync=progress_callback_sync,
    )


__all__ = ["BacktestTradingSession", "run_session_history_backtest"]
