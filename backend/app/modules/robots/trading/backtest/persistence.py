from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBacktestPersistence [1]
#/// Исходный модуль `backend/app/modules/robots/trading/backtest/persistence.py` — автоматическая разметка для Obsidian Source Scanner.

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import BigInteger, Date, DateTime, Float, Integer, String, Text, table, column
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy import text


@dataclass
class BacktestPersistPayload:
    equity_by_day: Dict[date, float]
    trading_days_cnt: int
    win_rate: Any
    annualized_return_val: Any
    max_dd_duration: int
    sharpe_val: Any
    sortino_val: Any
    calmar_val: Any
    volatility_annual_val: Any
    gross_profit_val: float
    gross_loss_val: float
    total_commission_val: float
    net_profit_val: float
    profit_factor_val: Any
    avg_pnl: Any
    avg_win_val: Any
    avg_loss_val: Any
    winning_count: int
    closed_count: int
    start_date: date
    end_date: date


def _parse_bar_time(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


def _finite_float(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x or x in (float("inf"), float("-inf")):
        return default
    return x


def _clamp_numeric(v: Any, *, precision: int, scale: int) -> float:
    """Clamp to PostgreSQL NUMERIC(precision, scale) range."""
    x = _finite_float(v)
    max_abs = (10 ** (precision - scale)) - (10 ** (-scale))
    return round(max(-max_abs, min(max_abs, x)), scale)


class BacktestPersistence:
    """Persist backtest artifacts into dedicated backtest schema."""

    def __init__(self, db: Session):
        self.db = db

    def persist_run_details(
        self,
        *,
        bt_run_id: int,
        res: Any,
        slippage_pct: float,
        payload: BacktestPersistPayload,
        on_progress: Optional[Callable[[], None]] = None,
        chunk_size: int = 500,
    ) -> None:
        self._bulk_persist_signals(bt_run_id, res, chunk_size=chunk_size, on_progress=on_progress)
        self._bulk_persist_trades_and_orders(
            bt_run_id, res, slippage_pct=slippage_pct, chunk_size=chunk_size, on_progress=on_progress,
        )
        day_trade_counts, day_commission, day_slippage, day_positions_value = self._aggregate_trade_day_stats(
            res, slippage_pct=slippage_pct,
        )
        self._bulk_persist_equity_and_positions(
            bt_run_id=bt_run_id,
            res=res,
            payload=payload,
            day_trade_counts=day_trade_counts,
            day_commission=day_commission,
            day_slippage=day_slippage,
            day_positions_value=day_positions_value,
            chunk_size=chunk_size,
            on_progress=on_progress,
        )
        self._persist_metrics_row(
            bt_run_id=bt_run_id,
            res=res,
            payload=payload,
            day_slippage=day_slippage,
        )
        if on_progress is not None:
            on_progress()

    def _bulk_persist_signals(
        self,
        bt_run_id: int,
        res: Any,
        *,
        chunk_size: int,
        on_progress: Optional[Callable[[], None]],
    ) -> None:
        signals_tbl = table(
            "backtest_signals",
            column("backtest_run_id", BigInteger),
            column("trade_date", Date),
            column("ticker", String),
            column("direction", String),
            column("signal_time", DateTime(timezone=True)),
            column("price_at_signal", Float),
            column("quantity_lots", Integer),
            column("reason", String),
            schema=None,
        )
        rows: List[Dict[str, Any]] = []
        for s in getattr(res, "signals", None) or []:
            s_time = _parse_bar_time(s.get("bar_time"))
            if not s_time:
                continue
            rows.append({
                "backtest_run_id": bt_run_id,
                "trade_date": s_time.date(),
                "ticker": s.get("figi"),
                "direction": str(s.get("signal_type") or "").upper(),
                "signal_time": s_time,
                "price_at_signal": s.get("price"),
                "quantity_lots": None,
                "reason": str(s.get("reason") or "GENERATED")[:50],
            })
        for off in range(0, len(rows), chunk_size):
            batch = rows[off : off + chunk_size]
            if batch:
                self.db.execute(pg_insert(signals_tbl).values(batch))
            if on_progress is not None:
                on_progress()

    def _bulk_persist_trades_and_orders(
        self,
        bt_run_id: int,
        res: Any,
        *,
        slippage_pct: float,
        chunk_size: int,
        on_progress: Optional[Callable[[], None]],
    ) -> None:
        orders_tbl = table(
            "backtest_orders",
            column("id", BigInteger),
            column("backtest_run_id", BigInteger),
            column("signal_id", BigInteger),
            column("ticker", String),
            column("direction", String),
            column("order_type", String),
            column("limit_price", Float),
            column("requested_quantity", Integer),
            column("executed_quantity", Integer),
            column("avg_execution_price", Float),
            column("slippage_cost", Float),
            column("commission_cost", Float),
            column("status", String),
            column("placed_at", DateTime(timezone=True)),
            column("filled_at", DateTime(timezone=True)),
            schema=None,
        )
        trades_tbl = table(
            "backtest_trades",
            column("backtest_run_id", BigInteger),
            column("order_id", BigInteger),
            column("ticker", String),
            column("direction", String),
            column("quantity", Integer),
            column("price", Float),
            column("commission", Float),
            column("trade_time", DateTime(timezone=True)),
            schema=None,
        )
        order_rows: List[Dict[str, Any]] = []
        trade_meta: List[Dict[str, Any]] = []
        for t in getattr(res, "trades", None) or []:
            t_time = _parse_bar_time(t.get("bar_time"))
            if not t_time:
                continue
            slip_cost = 0.0
            try:
                px = float(t.get("price") or 0.0)
                qty = float(t.get("quantity") or 0.0)
                if px > 0 and qty > 0:
                    slip_cost = (px * qty) * (max(0.0, float(slippage_pct or 0.0)) / 100.0)
            except Exception:
                slip_cost = 0.0
            order_rows.append({
                "backtest_run_id": bt_run_id,
                "signal_id": None,
                "ticker": t.get("figi"),
                "direction": str(t.get("side") or "").upper(),
                "order_type": "LIMIT",
                "limit_price": t.get("price"),
                "requested_quantity": t.get("quantity"),
                "executed_quantity": t.get("quantity"),
                "avg_execution_price": t.get("price"),
                "slippage_cost": slip_cost,
                "commission_cost": t.get("commission") or 0,
                "status": "FILLED",
                "placed_at": t_time,
                "filled_at": t_time,
            })
            trade_meta.append(t)

        for off in range(0, len(order_rows), chunk_size):
            ord_batch = order_rows[off : off + chunk_size]
            tr_batch = trade_meta[off : off + chunk_size]
            if not ord_batch:
                continue
            order_ids = list(
                self.db.execute(
                    pg_insert(orders_tbl).values(ord_batch).returning(orders_tbl.c.id)
                ).scalars().all()
            )
            trade_rows: List[Dict[str, Any]] = []
            for ord_id, t in zip(order_ids, tr_batch):
                t_time = _parse_bar_time(t.get("bar_time"))
                if not t_time:
                    continue
                trade_rows.append({
                    "backtest_run_id": bt_run_id,
                    "order_id": ord_id,
                    "ticker": t.get("figi"),
                    "direction": str(t.get("side") or "").upper(),
                    "quantity": t.get("quantity"),
                    "price": t.get("price"),
                    "commission": t.get("commission") or 0,
                    "trade_time": t_time,
                })
            if trade_rows:
                self.db.execute(pg_insert(trades_tbl).values(trade_rows))
            if on_progress is not None:
                on_progress()

    @staticmethod
    def _aggregate_trade_day_stats(
        res: Any,
        *,
        slippage_pct: float,
    ) -> tuple[Dict[date, int], Dict[date, float], Dict[date, float], Dict[date, float]]:
        day_trade_counts: Dict[date, int] = {}
        day_commission: Dict[date, float] = {}
        day_slippage: Dict[date, float] = {}
        for t in getattr(res, "trades", None) or []:
            t_time = _parse_bar_time(t.get("bar_time"))
            if not t_time:
                continue
            d = t_time.date()
            px = float(t.get("price") or 0.0)
            qty = float(t.get("quantity") or 0.0)
            slip_val = (px * qty) * (max(0.0, float(slippage_pct or 0.0)) / 100.0) if px > 0 and qty > 0 else 0.0
            day_trade_counts[d] = int(day_trade_counts.get(d, 0)) + 1
            day_commission[d] = float(day_commission.get(d, 0.0)) + float(t.get("commission") or 0)
            day_slippage[d] = float(day_slippage.get(d, 0.0)) + slip_val

        day_positions_value: Dict[date, float] = {}
        for dp in getattr(res, "daily_positions", None) or []:
            td = dp.get("trade_date")
            try:
                dd = datetime.fromisoformat(str(td)).date() if isinstance(td, str) else td
            except Exception:
                dd = None
            if not dd:
                continue
            qty = float(dp.get("quantity") or 0.0)
            cur_px = float(dp.get("current_price") or 0.0)
            if qty <= 0 or cur_px <= 0:
                continue
            day_positions_value[dd] = float(day_positions_value.get(dd, 0.0)) + (qty * cur_px)
        return day_trade_counts, day_commission, day_slippage, day_positions_value

    def _bulk_persist_equity_and_positions(
        self,
        *,
        bt_run_id: int,
        res: Any,
        payload: BacktestPersistPayload,
        day_trade_counts: Dict[date, int],
        day_commission: Dict[date, float],
        day_slippage: Dict[date, float],
        day_positions_value: Dict[date, float],
        chunk_size: int,
        on_progress: Optional[Callable[[], None]],
    ) -> None:
        equity_tbl = table(
            "backtest_equity_curve",
            column("backtest_run_id", BigInteger),
            column("trade_date", Date),
            column("cash", Float),
            column("positions_value", Float),
            column("total_equity", Float),
            column("daily_pnl", Float),
            column("daily_return_percent", Float),
            column("commission_paid", Float),
            column("slippage_paid", Float),
            column("trades_count", Integer),
            column("drawdown", Float),
            column("drawdown_percent", Float),
            schema=None,
        )
        positions_tbl = table(
            "backtest_positions",
            column("backtest_run_id", BigInteger),
            column("trade_date", Date),
            column("ticker", String),
            column("quantity", Integer),
            column("avg_entry_price", Float),
            column("current_price", Float),
            column("unrealized_pnl", Float),
            column("realized_pnl", Float),
            column("updated_at", DateTime(timezone=True)),
            schema=None,
        )

        prev_equity = float(res.initial_capital or 0)
        peak_equity_daily = float(res.initial_capital or 0)
        equity_rows: List[Dict[str, Any]] = []
        for d in sorted(payload.equity_by_day.keys()):
            eq = float(payload.equity_by_day[d])
            positions_val = float(day_positions_value.get(d, 0.0))
            cash_val = eq - positions_val
            daily_pnl_val = eq - prev_equity
            daily_ret = ((eq / prev_equity) - 1.0) * 100.0 if prev_equity > 0 else 0.0
            if eq > peak_equity_daily:
                peak_equity_daily = eq
            dd_abs = max(0.0, peak_equity_daily - eq)
            dd_pct = (dd_abs / peak_equity_daily * 100.0) if peak_equity_daily > 0 else 0.0
            equity_rows.append({
                "backtest_run_id": bt_run_id,
                "trade_date": d,
                "cash": cash_val,
                "positions_value": positions_val,
                "total_equity": eq,
                "daily_pnl": daily_pnl_val,
                "daily_return_percent": _clamp_numeric(daily_ret, precision=8, scale=4),
                "commission_paid": float(day_commission.get(d, 0.0)),
                "slippage_paid": float(day_slippage.get(d, 0.0)),
                "trades_count": int(day_trade_counts.get(d, 0)),
                # drawdown NUMERIC(8,4) — процент, не абсолют в рублях (см. drawdown_percent)
                "drawdown": _clamp_numeric(dd_pct, precision=8, scale=4),
                "drawdown_percent": _clamp_numeric(dd_pct, precision=6, scale=2),
            })
            prev_equity = eq

        excluded_eq = pg_insert(equity_tbl).excluded
        for off in range(0, len(equity_rows), chunk_size):
            batch = equity_rows[off : off + chunk_size]
            if not batch:
                continue
            stmt = pg_insert(equity_tbl).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["backtest_run_id", "trade_date"],
                set_={
                    "total_equity": excluded_eq.total_equity,
                    "cash": excluded_eq.cash,
                    "positions_value": excluded_eq.positions_value,
                    "daily_pnl": excluded_eq.daily_pnl,
                    "daily_return_percent": excluded_eq.daily_return_percent,
                    "commission_paid": excluded_eq.commission_paid,
                    "slippage_paid": excluded_eq.slippage_paid,
                    "trades_count": excluded_eq.trades_count,
                    "drawdown": excluded_eq.drawdown,
                    "drawdown_percent": excluded_eq.drawdown_percent,
                },
            )
            self.db.execute(stmt)

        pos_rows: List[Dict[str, Any]] = []
        now_utc = datetime.now(timezone.utc)
        for dp in getattr(res, "daily_positions", None) or []:
            pos_rows.append({
                "backtest_run_id": bt_run_id,
                "trade_date": dp.get("trade_date"),
                "ticker": dp.get("ticker"),
                "quantity": dp.get("quantity"),
                "avg_entry_price": dp.get("avg_entry_price"),
                "current_price": dp.get("current_price"),
                "unrealized_pnl": dp.get("unrealized_pnl"),
                "realized_pnl": dp.get("realized_pnl"),
                "updated_at": now_utc,
            })
        excluded_pos = pg_insert(positions_tbl).excluded
        for off in range(0, len(pos_rows), chunk_size):
            batch = pos_rows[off : off + chunk_size]
            if not batch:
                continue
            stmt = pg_insert(positions_tbl).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["backtest_run_id", "trade_date", "ticker"],
                set_={
                    "quantity": excluded_pos.quantity,
                    "avg_entry_price": excluded_pos.avg_entry_price,
                    "current_price": excluded_pos.current_price,
                    "unrealized_pnl": excluded_pos.unrealized_pnl,
                    "realized_pnl": excluded_pos.realized_pnl,
                    "updated_at": excluded_pos.updated_at,
                },
            )
            self.db.execute(stmt)

        if on_progress is not None:
            on_progress()

    def _persist_metrics_row(
        self,
        *,
        bt_run_id: int,
        res: Any,
        payload: BacktestPersistPayload,
        day_slippage: Dict[date, float],
    ) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO backtest_metrics
                (backtest_run_id, start_date, end_date, trading_days, total_trades, winning_trades, losing_trades,
                 win_rate, total_return_percent, annualized_return_percent, max_drawdown_percent, max_drawdown_duration,
                 sharpe_ratio, sortino_ratio, calmar_ratio, volatility_annual, initial_capital, final_equity,
                 gross_profit, gross_loss, total_commission, total_slippage, net_profit, profit_factor, profit_per_trade, avg_win, avg_loss)
                VALUES
                (:backtest_run_id, :start_date, :end_date, :trading_days, :total_trades, :winning_trades, :losing_trades,
                 :win_rate, :total_return_percent, :annualized_return_percent, :max_drawdown_percent, :max_drawdown_duration,
                 :sharpe_ratio, :sortino_ratio, :calmar_ratio, :volatility_annual, :initial_capital, :final_equity,
                 :gross_profit, :gross_loss, :total_commission, :total_slippage, :net_profit, :profit_factor, :profit_per_trade, :avg_win, :avg_loss)
                ON CONFLICT (backtest_run_id) DO UPDATE SET
                    total_trades = EXCLUDED.total_trades,
                    winning_trades = EXCLUDED.winning_trades,
                    losing_trades = EXCLUDED.losing_trades,
                    win_rate = EXCLUDED.win_rate,
                    total_return_percent = EXCLUDED.total_return_percent,
                    annualized_return_percent = EXCLUDED.annualized_return_percent,
                    max_drawdown_percent = EXCLUDED.max_drawdown_percent,
                    max_drawdown_duration = EXCLUDED.max_drawdown_duration,
                    sharpe_ratio = EXCLUDED.sharpe_ratio,
                    sortino_ratio = EXCLUDED.sortino_ratio,
                    calmar_ratio = EXCLUDED.calmar_ratio,
                    volatility_annual = EXCLUDED.volatility_annual,
                    final_equity = EXCLUDED.final_equity,
                    gross_profit = EXCLUDED.gross_profit,
                    gross_loss = EXCLUDED.gross_loss,
                    total_commission = EXCLUDED.total_commission,
                    total_slippage = EXCLUDED.total_slippage,
                    net_profit = EXCLUDED.net_profit,
                    profit_factor = EXCLUDED.profit_factor,
                    profit_per_trade = EXCLUDED.profit_per_trade,
                    avg_win = EXCLUDED.avg_win,
                    avg_loss = EXCLUDED.avg_loss
                """
            ),
            {
                "backtest_run_id": bt_run_id,
                "start_date": payload.start_date,
                "end_date": payload.end_date,
                "trading_days": payload.trading_days_cnt,
                "total_trades": len(res.trades),
                "winning_trades": payload.winning_count,
                "losing_trades": max(0, payload.closed_count - payload.winning_count),
                "win_rate": _clamp_numeric(payload.win_rate, precision=5, scale=2),
                "total_return_percent": _clamp_numeric(res.total_return_percent, precision=8, scale=2),
                "annualized_return_percent": _clamp_numeric(
                    payload.annualized_return_val, precision=8, scale=2,
                ),
                "max_drawdown_percent": _clamp_numeric(res.max_drawdown_percent, precision=6, scale=2),
                "max_drawdown_duration": payload.max_dd_duration,
                "sharpe_ratio": _clamp_numeric(payload.sharpe_val, precision=6, scale=2),
                "sortino_ratio": _clamp_numeric(payload.sortino_val, precision=6, scale=2),
                "calmar_ratio": _clamp_numeric(payload.calmar_val, precision=6, scale=2),
                "volatility_annual": _clamp_numeric(payload.volatility_annual_val, precision=6, scale=2),
                "initial_capital": res.initial_capital,
                "final_equity": res.final_equity,
                "gross_profit": payload.gross_profit_val,
                "gross_loss": payload.gross_loss_val,
                "total_commission": payload.total_commission_val,
                "total_slippage": float(sum(day_slippage.values())),
                "net_profit": payload.net_profit_val,
                "profit_factor": _clamp_numeric(payload.profit_factor_val, precision=6, scale=2),
                "profit_per_trade": payload.avg_pnl,
                "avg_win": payload.avg_win_val,
                "avg_loss": payload.avg_loss_val,
            },
        )
        self.db.execute(
            text(
                """
                UPDATE backtest_runs
                SET status='COMPLETED',
                    progress_percent=100,
                    completed_at=:completed_at
                WHERE id=:id
                """
            ),
            {"id": bt_run_id, "completed_at": datetime.now(timezone.utc)},
        )
