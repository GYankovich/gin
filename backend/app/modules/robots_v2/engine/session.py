"""Async trading session for robots v2 (paper + live + scalper ticks)."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

from app.core.database import SessionLocal
from app.modules.robots.trading.contracts import Candle
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.broker_factory import (
    create_broker_from_token,
    resolve_account_id,
    resolve_ticker_instrument_map,
)
from app.modules.robots_v2.engine.cycle import run_trading_cycle
from app.modules.robots_v2.engine.event_bus import event_bus
from app.modules.robots_v2.engine.execution import ExecutionService
from app.modules.robots_v2.engine.market_data import fetch_prices_for_session, poll_interval_seconds
from app.modules.robots_v2.engine.order_flow import OrderFlowAggregator
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.engine.reconcile import reconcile_from_broker
from app.modules.robots_v2.engine.types import SessionState, SessionStatus
from app.modules.robots_v2.risk.engine import RiskEngine
from app.modules.robots_v2.risk.eod import should_eod_flatten
from app.modules.robots_v2.universe.service import universe_service
from app.modules.robots_v2.universe.token_context import load_token_context

logger = logging.getLogger(__name__)

SCALPER_TICK_MIN_INTERVAL_SEC = 0.5
SCALPER_WS_TICK_MIN_INTERVAL_SEC = 0.5
EQUITY_CURVE_MAX_POINTS = 500


def _flatten_all_positions(ledger: PaperLedger, prices: dict[str, float]) -> list[dict[str, Any]]:
    fills: list[dict[str, Any]] = []
    for t, pos in list(ledger.positions.items()):
        px = prices.get(t, pos.avg_entry_price)
        pnl = ledger.apply_fill(
            ticker=t,
            side="SELL" if pos.is_long else "BUY",
            quantity=pos.quantity,
            price=px,
            reduce_only=True,
        )
        fills.append({"ticker": t, "kind": "flatten", "pnl": pnl, "price": px})
    return fills


class TradingSessionV2:
    def __init__(
        self,
        *,
        robot_id: int,
        user_id: int,
        token_id: int,
        config: dict[str, Any],
        virtual_capital: float,
        stop_mode: str = "soft",
    ) -> None:
        self.robot_id = robot_id
        self.user_id = user_id
        self.token_id = token_id
        self.raw_config = config
        self.virtual_capital = virtual_capital
        self.stop_mode = stop_mode
        self.state = SessionState.BOOTSTRAP
        self.cycle_number = 0
        self.universe: list[str] = []
        self.ledger: PaperLedger | None = None
        self.risk: RiskEngine | None = None
        self.execution: ExecutionService | None = None
        self.order_flow = OrderFlowAggregator(window_sec=30)
        self.candle_history: dict[str, list[Candle]] = {}
        self.last_prices: dict[str, float] = {}
        self.last_cycle_at: datetime | None = None
        self.last_decisions: list[dict[str, Any]] = []
        self.ws_healthy = True
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._scalper_task: asyncio.Task | None = None
        self._ws_task: asyncio.Task | None = None
        self._ws_queue: asyncio.Queue | None = None
        self._broker = None
        self._instrument_map: dict[str, str] = {}
        self._ticker_by_instrument: dict[str, str] = {}
        self._parsed: TradingRobotConfigV4 | None = None
        self._eod_done = False
        self._allow_short = False
        self._market = "moex"
        self._cycle_lock = asyncio.Lock()
        self._last_scalper_ws_tick_at: float = 0.0
        self._last_reconcile_at: float = 0.0
        self._reconcile_ok = True
        self._mode = "paper"
        self._equity_curve: deque[dict[str, Any]] = deque(maxlen=EQUITY_CURVE_MAX_POINTS)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"robots_v2_session_{self.robot_id}")

    async def stop(self, *, hard: bool = False) -> None:
        if self.risk:
            self.risk.pause_entries()
            if hard:
                self.risk.halt("hard_stop")
        self.state = SessionState.STOPPING
        self._stop_event.set()

    def status(self) -> SessionStatus:
        equity = self.virtual_capital
        cash = self.virtual_capital
        positions: list[dict[str, Any]] = []
        if self.ledger:
            equity = self.ledger.mark_equity(self.last_prices)
            cash = self.ledger.cash
            positions = self.ledger.open_positions_list(self.last_prices)
        return SessionStatus(
            robot_id=self.robot_id,
            session_state=self.state,
            mode=str((self.raw_config.get("core") or {}).get("mode", "paper")),
            cycle_number=self.cycle_number,
            equity=equity,
            cash=cash,
            open_positions=positions,
            universe=list(self.universe),
            last_cycle_at=self.last_cycle_at,
            ws_healthy=self.ws_healthy,
            decisions=self.last_decisions[-10:],
            equity_curve=list(self._equity_curve),
        )

    async def _run(self) -> None:
        try:
            self._parsed = TradingRobotConfigV4.model_validate(self.raw_config)
            mode = self._parsed.core.mode
            self._mode = mode
            db = SessionLocal()
            try:
                resolved = await universe_service.resolve(
                    db,
                    self.user_id,
                    token_id=self.token_id,
                    instrument_type=self._parsed.core.instrument_type,
                    universe_raw=self._parsed.universe.model_dump(by_alias=True),
                    robot_id=self.robot_id,
                )
                self.universe = [i.ticker for i in resolved.instruments]
                # ticker → FIGI/symbol for live orders (MOEX needs FIGI)
                resolved_map = {
                    i.ticker.upper(): (i.figi or i.symbol_id or i.ticker)
                    for i in resolved.instruments
                    if i.ticker
                }
                token_ctx = load_token_context(
                    db,
                    user_id=self.user_id,
                    token_id=self.token_id,
                    instrument_type=self._parsed.core.instrument_type,
                )
            finally:
                db.close()

            if not self.universe:
                self.state = SessionState.ERROR
                await event_bus.publish(self.robot_id, "health", {"level": "error", "message": "Empty universe"})
                return

            self._market = token_ctx.market
            self._allow_short = self._parsed.core.instrument_type in ("perpetual", "coin_futures")
            commission = self._parsed.risk.broker_commission_pct / 100.0
            self.ledger = PaperLedger(
                cash=self.virtual_capital,
                commission_rate=commission,
                allow_short=self._allow_short,
            )
            self.risk = RiskEngine(self._parsed.risk, allow_short=self._allow_short)
            self.risk.begin_session(self.virtual_capital)

            broker = None
            account_id = None
            if mode == "live":
                broker = create_broker_from_token(
                    token_ctx,
                    instrument_type=self._parsed.core.instrument_type,
                    robot_config=self.raw_config,
                )
                if broker is None:
                    self.state = SessionState.ERROR
                    await event_bus.publish(self.robot_id, "health", {
                        "level": "error", "message": "Live mode requires valid broker token",
                    })
                    return
                preferred = str((self.raw_config.get("core") or {}).get("accountId") or "").strip() or None
                account_id = await resolve_account_id(broker, preferred)
                if not account_id:
                    self.state = SessionState.ERROR
                    await event_bus.publish(self.robot_id, "health", {
                        "level": "error", "message": "Could not resolve broker accountId",
                    })
                    return
                try:
                    ok = await broker.connect_websocket(self.user_id)
                    self.ws_healthy = bool(ok)
                except Exception:
                    logger.exception("ws connect failed robot_id=%s", self.robot_id)
                    self.ws_healthy = False

            instrument_map = dict(resolved_map)
            meta = self.raw_config.get("metadata") if isinstance(self.raw_config.get("metadata"), dict) else {}
            if isinstance(meta.get("instrumentMap"), dict):
                instrument_map.update({str(k).upper(): str(v) for k, v in meta["instrumentMap"].items()})
            elif isinstance(self.raw_config.get("instrument_map"), dict):
                im = self.raw_config["instrument_map"]
                # v1 shape: { figi_by_ticker: {...} } or flat ticker→id
                if isinstance(im.get("figi_by_ticker"), dict):
                    instrument_map.update({str(k).upper(): str(v) for k, v in im["figi_by_ticker"].items()})
                else:
                    instrument_map.update({str(k).upper(): str(v) for k, v in im.items() if k != "ticker_by_figi"})

            if mode == "live":
                try:
                    resolved_live = await resolve_ticker_instrument_map(token_ctx, self.universe)
                    for tk, iid in resolved_live.items():
                        instrument_map.setdefault(tk, iid)
                except Exception:
                    logger.exception("instrument map resolve failed robot_id=%s", self.robot_id)

            self._instrument_map = {str(k).upper(): str(v) for k, v in instrument_map.items()}
            self._ticker_by_instrument = {v.upper(): k for k, v in self._instrument_map.items()}
            self._broker = broker

            self.execution = ExecutionService(
                mode=mode,
                robot_id=self.robot_id,
                ledger=self.ledger,
                slippage_pct=self._parsed.risk.slippage_pct,
                broker=broker,
                account_id=account_id,
                instrument_map=self._instrument_map,
            )

            # Scalper order-flow window from params
            if self._parsed.strategy.archetype == "scalper":
                win = int(self._parsed.strategy.params.get("minVolumeWindow") or 30)
                self.order_flow = OrderFlowAggregator(window_sec=win)

            self.state = SessionState.RUNNING
            await event_bus.publish(self.robot_id, "health", {
                "level": "ok",
                "state": "RUNNING",
                "mode": mode,
                "wsHealthy": self.ws_healthy,
            })

            poll_sec = poll_interval_seconds(self._parsed.core.schedule.poll_interval)
            is_scalper = self._parsed.strategy.archetype == "scalper"
            if is_scalper and mode == "live" and broker is not None:
                self._ws_task = asyncio.create_task(
                    self._ws_price_loop(),
                    name=f"robots_v2_ws_{self.robot_id}",
                )
            elif is_scalper:
                self._scalper_task = asyncio.create_task(
                    self._scalper_loop(),
                    name=f"robots_v2_scalper_{self.robot_id}",
                )

            while not self._stop_event.is_set():
                await self._poll_cycle(triggered_by="poll")
                if self.risk and self.risk.session_state.halt_session:
                    break
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=poll_sec)
                except asyncio.TimeoutError:
                    continue

            for task in (self._scalper_task, self._ws_task):
                if task:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            if self.stop_mode == "hard" and self.ledger and self.execution:
                for t, pos in list(self.ledger.positions.items()):
                    px = self.last_prices.get(t, pos.avg_entry_price)
                    from app.modules.robots.trading.contracts import OrderIntent
                    intent = OrderIntent(
                        kind="flatten",
                        figi=t,
                        side="SELL" if pos.is_long else "BUY",
                        quantity=float(pos.quantity),
                        price=px,
                        reduce_only=True,
                        reason="hard_stop",
                    )
                    await self.execution.execute_intent(intent, last_price=px)

            if broker is not None:
                try:
                    if self._ws_queue is not None:
                        ids = list(self._instrument_map.values()) or list(self.universe)
                        await broker.unsubscribe_prices(self.user_id, ids, self._ws_queue)
                    await broker.close_websocket(self.user_id)
                except Exception:
                    pass

            self.state = SessionState.TERMINATED
            await event_bus.publish(self.robot_id, "health", {"level": "ok", "state": "TERMINATED"})
        except Exception as exc:
            logger.exception("robots_v2 session failed robot_id=%s", self.robot_id)
            self.state = SessionState.ERROR
            await event_bus.publish(self.robot_id, "health", {"level": "error", "message": str(exc)})
        finally:
            from app.modules.robots_v2.engine.session_manager import session_manager
            session_manager.on_session_ended(self.robot_id)

    async def _scalper_loop(self) -> None:
        """Price-tick wake for paper scalper (REST-polled prices, rate-limited)."""
        while not self._stop_event.is_set():
            try:
                await self._poll_cycle(triggered_by="price_tick")
            except Exception:
                logger.exception("scalper tick failed robot_id=%s", self.robot_id)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=SCALPER_TICK_MIN_INTERVAL_SEC)
            except asyncio.TimeoutError:
                continue

    async def _ws_price_loop(self) -> None:
        """Subscribe broker lastPrice/kline stream → order-flow + scalper ticks."""
        broker = self._broker
        if broker is None:
            return
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._ws_queue = queue
        instruments = [self._instrument_map.get(t, t) for t in self.universe]
        try:
            await broker.subscribe_prices(self.user_id, instruments, queue)
            self.ws_healthy = True
            await event_bus.publish(self.robot_id, "health", {
                "level": "ok", "wsHealthy": True, "subscribed": len(instruments),
            })
        except Exception as exc:
            logger.exception("ws subscribe failed robot_id=%s", self.robot_id)
            self.ws_healthy = False
            await event_bus.publish(self.robot_id, "health", {
                "level": "warn", "wsHealthy": False, "message": str(exc)[:300],
            })
            # Fallback to REST scalper loop
            await self._scalper_loop()
            return

        while not self._stop_event.is_set():
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ws queue read failed robot_id=%s", self.robot_id)
                self.ws_healthy = False
                continue

            if not isinstance(msg, dict):
                continue
            msg_type = str(msg.get("type") or "")
            figi = str(msg.get("figi") or msg.get("symbol") or "").upper()
            price_raw = msg.get("price")
            if price_raw is None and isinstance(msg.get("candle"), dict):
                price_raw = msg["candle"].get("close")
            try:
                price = float(price_raw)
            except (TypeError, ValueError):
                continue
            if not figi or price <= 0:
                continue

            ticker = self._ticker_by_instrument.get(figi, figi)
            now = datetime.now(timezone.utc)

            if msg_type == "trade":
                side = str(msg.get("side") or "buy")
                vol = float(msg.get("volume") or msg.get("size") or 0) or 1.0
                turnover = msg.get("turnover")
                try:
                    turnover_f = float(turnover) if turnover is not None else None
                except (TypeError, ValueError):
                    turnover_f = None
                self.order_flow.on_trade(
                    ticker, price=price, side=side, volume=vol, now=now, turnover=turnover_f,
                )
                self.last_prices[ticker] = price
            else:
                # price / candle_closed — inferred side unless real trades already active
                candle = msg.get("candle") if isinstance(msg.get("candle"), dict) else None
                turnover = None
                if candle is not None:
                    try:
                        turnover = float(candle.get("turnover") or 0) or None
                    except (TypeError, ValueError):
                        turnover = None
                if turnover and turnover > 0:
                    # Closed candle with turnover: attribute as aggressive side by close vs open
                    side = "buy"
                    try:
                        o = float(candle.get("open") or price)
                        if price < o:
                            side = "sell"
                    except (TypeError, ValueError):
                        pass
                    self.order_flow.on_trade(
                        ticker, price=price, side=side, volume=1.0, now=now, turnover=turnover,
                    )
                else:
                    self.order_flow.on_price(ticker, price, volume=1.0, now=now)
                self.last_prices[ticker] = price

            loop = asyncio.get_running_loop()
            now_mono = loop.time()
            if now_mono - self._last_scalper_ws_tick_at < SCALPER_WS_TICK_MIN_INTERVAL_SEC:
                continue
            self._last_scalper_ws_tick_at = now_mono
            try:
                await self._poll_cycle(triggered_by="price_tick")
            except Exception:
                logger.exception("ws scalper tick failed robot_id=%s", self.robot_id)

    async def _poll_cycle(self, *, triggered_by: str) -> None:
        async with self._cycle_lock:
            if self._parsed is None or self.ledger is None or self.risk is None or self.execution is None:
                return
            if self.state not in (SessionState.RUNNING, SessionState.BOOTSTRAP):
                return

            # Prefer already-fresh WS prices on scalper ticks; fill gaps via REST.
            prices: dict[str, float] = {}
            if triggered_by == "price_tick" and self.last_prices:
                prices = {t: self.last_prices[t] for t in self.universe if t in self.last_prices}
            missing = [t for t in self.universe if t not in prices]
            if missing or not prices:
                db = SessionLocal()
                try:
                    fetched = await fetch_prices_for_session(
                        db,
                        market=self._market,
                        tickers=missing or self.universe,
                        token_id=self.token_id,
                        user_id=self.user_id,
                        instrument_type=self._parsed.core.instrument_type,
                    )
                finally:
                    db.close()
                prices.update(fetched)

            for t in self.universe:
                if t not in prices and t in self.last_prices:
                    prices[t] = self.last_prices[t]
            if not prices:
                return
            self.last_prices.update(prices)
            prices = {t: self.last_prices[t] for t in self.universe if t in self.last_prices}
            if not prices:
                return
            now = datetime.now(timezone.utc)

            # ADR-11: live broker is source of truth (throttled on scalper ticks)
            if self._mode == "live" and self._broker is not None and self.execution and self.execution.account_id:
                loop = asyncio.get_running_loop()
                now_mono = loop.time()
                should_reconcile = (
                    triggered_by == "poll"
                    or (now_mono - self._last_reconcile_at) >= 5.0
                )
                if should_reconcile:
                    rec = await reconcile_from_broker(
                        robot_id=self.robot_id,
                        broker=self._broker,
                        account_id=self.execution.account_id,
                        ledger=self.ledger,
                        instrument_map=self._instrument_map,
                        universe=self.universe,
                    )
                    self._last_reconcile_at = now_mono
                    self._reconcile_ok = rec.ok
                    if not rec.ok:
                        await event_bus.publish(self.robot_id, "health", {
                            "level": "error",
                            "message": f"reconcile failed: {rec.error}",
                            "code": "RECONCILE_FAILED",
                        })
                        self.last_cycle_at = now
                        return  # PreFlight: block cycle when broker sync impossible

            # Avoid double-counting order-flow when WS already ingested the tick
            if triggered_by != "price_tick" or self._ws_task is None:
                for t, px in prices.items():
                    self.order_flow.on_price(t, px, volume=1.0, now=now)

            for t, px in prices.items():
                hist = self.candle_history.setdefault(t, [])
                hist.append(Candle(
                    interval=self._parsed.strategy.timeframe or "5m",
                    time=now,
                    open=px, high=px, low=px, close=px, volume=0, secid=t,
                ))
                if len(hist) > 200:
                    self.candle_history[t] = hist[-200:]

            self.cycle_number += 1

            if should_eod_flatten(
                risk=self._parsed.risk,
                schedule=self._parsed.core.schedule,
                instrument_type=self._parsed.core.instrument_type,
            ):
                if not self._eod_done:
                    flat_fills = _flatten_all_positions(self.ledger, prices)
                    self.risk.pause_entries()
                    self._eod_done = True
                    self.last_decisions = [{
                        "code": "EOD_FLATTEN",
                        "message": "EOD flatten window — positions closed, entries paused",
                        "allow": False,
                    }]
                    await event_bus.publish(self.robot_id, "decision", {
                        "code": "EOD_FLATTEN",
                        "fills": len(flat_fills),
                    })
                self.last_cycle_at = now
                if self.ledger:
                    eq = self.ledger.mark_equity(prices)
                    self._equity_curve.append({
                        "time": now.isoformat(),
                        "equity": round(eq, 2),
                        "cycle": self.cycle_number,
                    })
                return

            flow = None
            if self._parsed.strategy.archetype == "scalper":
                flow = self.order_flow.snapshots(self.universe, now=now)

            # Scalper entries only on price_tick; poll still runs exits via cycle
            result = await run_trading_cycle(
                robot_id=self.robot_id,
                user_id=self.user_id,
                config=self._parsed,
                universe=self.universe,
                ledger=self.ledger,
                risk=self.risk,
                prices=prices,
                candle_history=self.candle_history,
                session_id=self.robot_id,
                cycle_number=self.cycle_number,
                triggered_by=triggered_by,
                allow_short=self._allow_short,
                execution=self.execution,
                order_flow=flow,
                ws_healthy=self.ws_healthy,
            )
            self.last_decisions = result.get("decisions") or []
            self.last_cycle_at = now
            eq = self.ledger.mark_equity(prices)
            self._equity_curve.append({
                "time": now.isoformat(),
                "equity": round(eq, 2),
                "cycle": self.cycle_number,
            })
