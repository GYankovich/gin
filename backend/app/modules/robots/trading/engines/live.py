"""
LiveTradingEngine — тонкий оркестратор реальной торговли.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §9.

Этот движок **не подменяет** существующий `trading/session.py` (большой
конвейер Stage1..Stage6). Он живёт параллельно и используется новыми
интеграциями, которые работают строго на единых контрактах. На этапе
`engine-parity` мы проверяем, что результаты BacktestEngine и LiveTradingEngine
(в режиме paper / sandbox) совпадают.

Алгоритм одного «тика» (`tick`):
1. Получаем актуальный список свечей через `DataProvider.get_intraday_candles`
   для всех инструментов из `universe`.
2. Вызываем `Strategy.generate_signals(...)`.
3. На каждый сигнал делаем `RiskManager.pre_trade_check`/`evaluate_exits` →
   `Execution.submit`.
4. Логируем через `RuntimeRecorder`.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingEnginesLive [1]
#/// Исходный модуль `backend/app/modules/robots/trading/engines/live.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.modules.robots.trading.contracts import Candle, Order, Position, Signal
from app.modules.robots.trading.engines.context import RuntimeContext
from app.modules.robots.trading.engines.trading_loop import apply_fill_to_context

logger = logging.getLogger(__name__)


class LiveTradingEngine:
    """Универсальный live-движок на единых контрактах."""

    def __init__(self, ctx: RuntimeContext):
        if ctx.mode != "LIVE":
            raise ValueError(f"LiveTradingEngine expects mode=LIVE, got {ctx.mode!r}")
        self.ctx = ctx
        self._stop = asyncio.Event()

    async def start(
        self,
        *,
        intraday_interval: str = "M5",
        tick_seconds: int = 60,
        heartbeat_seconds: int = 30,
    ) -> None:
        """Запускает основной цикл live-торговли.

        Цикл крутится до вызова `stop()`. Каждый `tick_seconds` мы:
        - тянем актуальные свечи и обновляем цены позиций;
        - вызываем стратегию и RiskManager;
        - отправляем ордера через `Execution.submit`.
        """
        ctx = self.ctx
        # утренняя фильтрация — один раз в день
        today = datetime.now(timezone.utc).date()
        await self._morning_universe(today)
        ctx.risk.begin_day(equity_at_open=ctx.equity)

        last_heartbeat = datetime.now(timezone.utc)
        while not self._stop.is_set():
            try:
                await self._tick(intraday_interval)
            except Exception as e:
                logger.exception("LiveTradingEngine tick failed: %s", e)

            # heartbeat
            now = datetime.now(timezone.utc)
            if (now - last_heartbeat).total_seconds() >= heartbeat_seconds:
                last_heartbeat = now
                logger.info(
                    "LiveTradingEngine heartbeat: equity=%.2f cash=%.2f positions=%d",
                    ctx.equity, ctx.cash, len(ctx.positions),
                )

            # ребиаленс универса в начале нового дня
            cur_date = datetime.now(timezone.utc).date()
            if cur_date != today:
                ctx.risk.end_day(equity_at_close=ctx.equity, had_trades_today=bool(ctx.trade_log))
                today = cur_date
                await self._morning_universe(today)
                ctx.risk.begin_day(equity_at_open=ctx.equity)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=tick_seconds)
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------
    # внутренние шаги
    # ------------------------------------------------------------------

    async def _morning_universe(self, trade_date: date) -> None:
        ctx = self.ctx
        universe = ctx.universe or await ctx.data.list_universe(trade_date)
        snapshot = await ctx.data.get_daily_summary(universe, trade_date)
        result = ctx.pipeline.run(snapshot, trade_date=trade_date)
        await ctx.recorder.record_universe(trade_date, result.accepted, result.rejected, source="live")
        ctx.universe = result.accepted
        logger.info("Live universe for %s: accepted=%d rejected=%d",
                     trade_date, len(result.accepted), len(result.rejected))

    async def _tick(self, intraday_interval: str) -> None:
        ctx = self.ctx
        today = datetime.now(timezone.utc).date()
        if not ctx.universe:
            return

        candles_by_secid: Dict[str, List[Candle]] = {}
        for secid in ctx.universe:
            try:
                candles = await ctx.data.get_intraday_candles(secid, today, intraday_interval)
            except Exception as e:
                logger.warning("get_intraday_candles failed for %s: %s", secid, e)
                continue
            if candles:
                candles_by_secid[secid] = candles
        if not candles_by_secid:
            return

        # обновляем текущие цены позиций
        for sid, pos in list(ctx.positions.items()):
            series = candles_by_secid.get(sid)
            if series:
                pos.current_price = float(series[-1].close)

        # выходы по RiskManager на последнем баре
        for sid, pos in list(ctx.positions.items()):
            series = candles_by_secid.get(sid)
            if not series:
                continue
            sig = ctx.risk.evaluate_exits(pos, series[-1])
            if sig is not None:
                await ctx.recorder.record_signal(sig)
                await self._submit_market_order(sig)

        # стратегия
        window = {
            sid: [_candle_to_tinvest_dict(c) for c in series]
            for sid, series in candles_by_secid.items()
        }
        try:
            raw = await ctx.strategy.generate_signals(window)
        except Exception as e:
            logger.warning("strategy.generate_signals failed: %s", e)
            return

        for figi, side in (raw or {}).items():
            if side is None:
                continue
            series = candles_by_secid.get(figi)
            if not series:
                continue
            bar = series[-1]
            sig = Signal(
                secid=figi,
                figi=figi,
                side="BUY" if str(side).upper() == "BUY" else "SELL",
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
            else:
                pos = ctx.positions.get(figi)
                if pos is None or pos.quantity <= 0:
                    continue
                sig.quantity_hint = pos.quantity

            await self._submit_market_order(sig)

    async def _submit_market_order(self, sig: Signal) -> None:
        ctx = self.ctx
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
        result = await ctx.execution.submit(order)
        await ctx.recorder.record_order(result.order)
        if result.fill is not None:
            await ctx.recorder.record_fill(result.fill)
            apply_fill_to_context(ctx, sig, result.fill)


def _to_quotation(v: float) -> Dict[str, int]:
    f = float(v or 0.0)
    units = int(f)
    nano = int(round((f - units) * 1e9))
    return {"units": units, "nano": nano}


def _candle_to_tinvest_dict(c: Candle) -> Dict[str, Any]:
    return {
        "time": c.time.isoformat() if hasattr(c.time, "isoformat") else str(c.time),
        "open": _to_quotation(c.open),
        "high": _to_quotation(c.high),
        "low": _to_quotation(c.low),
        "close": _to_quotation(c.close),
        "volume": int(c.volume or 0),
    }


__all__ = ["LiveTradingEngine"]
