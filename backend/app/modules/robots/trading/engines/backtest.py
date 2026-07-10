"""
BacktestEngine — тонкий оркестратор бэктеста на единых контрактах.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §9.

Этот движок **не подменяет** существующий `trading/backtest/engine.py`
(монолитная функция `run_backtest_simulation`). Он живёт параллельно как новая
точка входа: новые стратегии (`momentum_breakout`, `reversion_to_ma`) и новые
интеграции запускаются через `BacktestEngine.run()`, в то время как
исторический grain_seed-конвейер ещё некоторое время использует старую
функцию для обратной совместимости. На этапе `engine-parity` тестов оба пути
будут давать совпадающие метрики.

`BacktestEngine.run()`:
- получает universe через `DataProvider.list_universe`;
- применяет `PipelineRunner.run` к снапшоту утра;
- по каждому принятому тикеру тянет интрадей-свечи через `DataProvider`;
- вызывает `Strategy.generate_signals`;
- проверяет `RiskManager.pre_trade_check` и обрабатывает выходы через
  `RiskManager.evaluate_exits`;
- проводит сделки через `SimExecution`;
- логирует через `RuntimeRecorder`.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingEnginesBacktest [1]
#/// Исходный модуль `backend/app/modules/robots/trading/engines/backtest.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.modules.robots.trading.contracts import (
    Candle,
    ExecutionMode,
    MarketSnapshot,
    Order,
    Position,
    Signal,
    SnapshotRow,
)
from app.modules.robots.trading.engines.context import RuntimeContext

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    trades: List[Dict[str, Any]]
    equity_curve: List[float]
    final_cash: float
    final_equity: float
    metrics: Dict[str, Any]


class BacktestEngine:
    """Универсальный движок бэктеста на единых контрактах."""

    def __init__(self, ctx: RuntimeContext):
        if ctx.mode != "BACKTEST":
            raise ValueError(f"BacktestEngine expects mode=BACKTEST, got {ctx.mode!r}")
        self.ctx = ctx

    async def run(
        self,
        *,
        from_date: date,
        to_date: date,
        initial_capital: float,
        intraday_interval: str = "M5",
    ) -> BacktestResult:
        ctx = self.ctx
        ctx.cash = float(initial_capital)
        ctx.equity = float(initial_capital)
        ctx.equity_curve = [ctx.equity]
        ctx.trade_log = []
        ctx.positions.clear()

        cur = from_date
        while cur <= to_date:
            await self._run_day(cur, intraday_interval=intraday_interval)
            cur += timedelta(days=1)

        # рассчёт сводных метрик отдаём отдельному модулю (`trading.metrics`),
        # здесь — заглушка с самыми базовыми числами.
        metrics = {
            "trades_total": len(ctx.trade_log),
            "final_equity": ctx.equity,
            "final_cash": ctx.cash,
            "realized_pnl": ctx.realized_pnl,
        }
        return BacktestResult(
            trades=list(ctx.trade_log),
            equity_curve=list(ctx.equity_curve),
            final_cash=ctx.cash,
            final_equity=ctx.equity,
            metrics=metrics,
        )

    async def _run_day(self, trade_date: date, *, intraday_interval: str) -> None:
        ctx = self.ctx

        # --- 1. universe + pipeline ---
        universe = ctx.universe or await ctx.data.list_universe(trade_date)
        snapshot = await ctx.data.get_daily_summary(universe, trade_date)
        snapshot = _filter_snapshot_for_universe(snapshot, ctx.robot_config)
        pipeline_result = ctx.pipeline.run(snapshot, trade_date=trade_date)
        await ctx.recorder.record_universe(trade_date, pipeline_result.accepted,
                                            pipeline_result.rejected, source="backtest")
        accepted = pipeline_result.accepted
        if not accepted:
            return

        # --- 2. подготовка интрадей-свечей ---
        candles_by_secid: Dict[str, List[Candle]] = {}
        for secid in accepted:
            candles = await ctx.data.get_intraday_candles(secid, trade_date, intraday_interval)
            if candles:
                candles_by_secid[secid] = candles
        if not candles_by_secid:
            return

        # все секиды имеют одинаковую длину (как минимум близкую) — это backtest
        # игнорируем секиды без свечей
        ctx.risk.begin_day(equity_at_open=ctx.equity)

        # --- 3. day-loop по индексу бара ---
        max_len = max(len(v) for v in candles_by_secid.values())
        secids = list(candles_by_secid.keys())

        # сигналы стратегии — на закрытии каждого бара
        for i in range(max_len):
            # обновим текущие цены позиций
            for sid, pos in list(ctx.positions.items()):
                series = candles_by_secid.get(sid) or []
                if i < len(series):
                    pos.current_price = float(series[i].close)

            # --- 3.1 выходы по RiskManager (SL/TP/Trailing) ---
            for sid, pos in list(ctx.positions.items()):
                series = candles_by_secid.get(sid) or []
                if i >= len(series):
                    continue
                exit_sig = ctx.risk.evaluate_exits(pos, series[i])
                if exit_sig is not None:
                    await self._execute_signal(exit_sig, candles_by_secid, i, day=trade_date)

            # --- 3.2 strategy.generate_signals ---
            window = self._build_window(candles_by_secid, i)
            try:
                raw = await ctx.strategy.generate_signals(window)
            except Exception as e:
                logger.warning("strategy.generate_signals failed: %s", e)
                continue

            # --- 3.3 обработка сигналов ---
            for figi, side in (raw or {}).items():
                if side is None:
                    continue
                series = candles_by_secid.get(figi)
                if not series or i >= len(series):
                    continue
                bar = series[i]
                sig = Signal(
                    secid=figi,
                    figi=figi,
                    side="BUY" if side.upper() == "BUY" else "SELL",
                    target_price=float(bar.close),
                    price_at_signal=float(bar.close),
                    bar_time=bar.time.isoformat() if hasattr(bar.time, "isoformat") else str(bar.time),
                    strategy=ctx.strategy.__class__.__name__,
                    reason=f"strategy.{side.lower()}",
                )
                await ctx.recorder.record_signal(sig)

                if sig.side == "BUY":
                    decision = ctx.risk.pre_trade_check(
                        sig, cash=ctx.cash, equity=ctx.equity, positions=ctx.positions,
                    )
                    if not decision.allow:
                        await ctx.recorder.record_risk_reject(sig, decision.reason)
                        continue
                    sig.quantity_hint = decision.quantity
                else:  # SELL → закрываем существующую позицию
                    pos = ctx.positions.get(figi)
                    if pos is None or pos.quantity <= 0:
                        continue
                    sig.quantity_hint = pos.quantity

                await self._execute_signal(sig, candles_by_secid, i, day=trade_date)

        # --- 4. EOD flatten через RiskManager.force_close_signals ---
        if ctx.positions:
            # время — последний бар первого секида
            last_t = max(
                candles_by_secid[s][-1].time for s in secids if candles_by_secid[s]
            )
            now_msk = last_t
            for sig in ctx.risk.force_close_signals(now_msk, ctx.positions):
                await ctx.recorder.record_signal(sig)
                await self._execute_signal(sig, candles_by_secid, i=-1, day=trade_date)

        ctx.risk.end_day(equity_at_close=ctx.equity, had_trades_today=bool(ctx.trade_log))
        ctx.equity_curve.append(ctx.equity)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _build_window(self, candles_by_secid: Dict[str, List[Candle]], i: int) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for sid, series in candles_by_secid.items():
            sub = series[: i + 1]
            out[sid] = [_candle_to_tinvest_dict(c) for c in sub]
        return out

    async def _execute_signal(
        self,
        sig: Signal,
        candles_by_secid: Dict[str, List[Candle]],
        i: int,
        *,
        day: date,
    ) -> None:
        ctx = self.ctx
        series = candles_by_secid.get(sig.secid) or []
        if not series:
            return
        # SimExecution принимает series в T-Invest dict-формате
        ti_series = [_candle_to_tinvest_dict(c) for c in series]
        if i < 0:
            i = len(ti_series) - 1

        order = Order(
            secid=sig.secid,
            figi=sig.figi,
            side="BUY" if sig.side == "BUY" else "SELL",
            type="MARKET",
            quantity=int(sig.quantity_hint or 0),
            price=sig.target_price,
            signal_id=sig.signal_id,
        )
        if order.quantity <= 0:
            return

        result = await ctx.execution.submit(order, series=ti_series, index=i)
        await ctx.recorder.record_order(result.order)

        if not result.accepted or result.fill is None:
            return

        fill = result.fill
        await ctx.recorder.record_fill(fill)

        if order.side == "BUY":
            invest = fill.fill_price * fill.quantity + fill.commission
            ctx.cash -= invest
            pos = ctx.positions.get(sig.secid)
            if pos is None:
                pos = Position(secid=sig.secid, figi=sig.figi, quantity=0,
                                avg_entry_price=0.0, side="LONG", opened_at=fill.ts or datetime.now(timezone.utc))
                ctx.positions[sig.secid] = pos
            total_qty = pos.quantity + fill.quantity
            if total_qty > 0:
                pos.avg_entry_price = ((pos.avg_entry_price * pos.quantity) + (fill.fill_price * fill.quantity)) / total_qty
            pos.quantity = total_qty
            pos.peak_price = max(pos.peak_price, fill.fill_price)
            pos.current_price = fill.fill_price
        else:
            pos = ctx.positions.get(sig.secid)
            if pos is None or pos.quantity <= 0:
                return
            qty = min(pos.quantity, fill.quantity)
            proceeds = fill.fill_price * qty - fill.commission
            ctx.cash += proceeds
            pnl = (fill.fill_price - pos.avg_entry_price) * qty - fill.commission
            ctx.realized_pnl += pnl
            ctx.risk.record_realized_pnl(pnl)
            pos.quantity -= qty
            if pos.quantity <= 0:
                ctx.positions.pop(sig.secid, None)

        # обновляем equity
        positions_value = sum(p.current_price * p.quantity for p in ctx.positions.values())
        ctx.equity = ctx.cash + positions_value

        ctx.trade_log.append({
            "secid": sig.secid,
            "side": order.side,
            "qty": fill.quantity,
            "price": fill.fill_price,
            "commission": fill.commission,
            "ts": fill.ts.isoformat() if fill.ts else None,
            "reason": sig.reason,
            "trade_date": day.isoformat(),
        })


# ---------------------------------------------------------------------------
# Конвертация Candle → T-Invest dict (для совместимости с SimExecution/strategy)
# ---------------------------------------------------------------------------

def _snapshot_row_to_filter_dict(row: SnapshotRow) -> Dict[str, Any]:
    return {
        "ticker": row.secid,
        "security_status": row.security_status,
        "trading_status": row.trading_status,
    }


def _filter_snapshot_for_universe(
    snapshot: MarketSnapshot,
    config: Optional[Dict[str, Any]],
) -> MarketSnapshot:
    if not config:
        return snapshot
    from app.modules.robots.universe import universe_filter_snapshot_row

    kept = {
        k: v
        for k, v in snapshot.rows.items()
        if universe_filter_snapshot_row(_snapshot_row_to_filter_dict(v), config)
    }
    return MarketSnapshot(
        as_of=snapshot.as_of,
        trade_date=snapshot.trade_date,
        board=snapshot.board,
        rows=kept,
    )


def _to_quotation(v: float) -> Dict[str, int]:
    """Преобразует число в формат T-Invest Quotation {units, nano}."""
    f = float(v or 0.0)
    units = int(f)
    nano = int(round((f - units) * 1e9))
    return {"units": units, "nano": nano}


def _candle_to_tinvest_dict(c: Candle) -> Dict[str, Any]:
    """Кандель в формат T-Invest API (quotation), который ожидает BrokerEmulator
    и существующие стратегии (`indicators.library.price_from_quotation` понимает
    оба варианта)."""
    return {
        "time": c.time.isoformat() if hasattr(c.time, "isoformat") else str(c.time),
        "open": _to_quotation(c.open),
        "high": _to_quotation(c.high),
        "low": _to_quotation(c.low),
        "close": _to_quotation(c.close),
        "volume": int(c.volume or 0),
    }


__all__ = ["BacktestEngine", "BacktestResult"]
