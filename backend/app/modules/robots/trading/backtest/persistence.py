from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBacktestPersistence [1]
#/// Исходный модуль `backend/app/modules/robots/trading/backtest/persistence.py` — автоматическая разметка для Obsidian Source Scanner.

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session


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
    ) -> None:
        for s in res.signals:
            s_time = None
            try:
                if s.get("bar_time"):
                    s_time = datetime.fromisoformat(str(s.get("bar_time")).replace("Z", "+00:00"))
            except Exception:
                s_time = None
            if not s_time:
                continue
            self.db.execute(
                text(
                    """
                    INSERT INTO backtest.backtest_signals
                    (backtest_run_id, trade_date, ticker, direction, signal_time, price_at_signal, quantity_lots, reason)
                    VALUES
                    (:backtest_run_id, :trade_date, :ticker, :direction, :signal_time, :price_at_signal, :quantity_lots, :reason)
                    """
                ),
                {
                    "backtest_run_id": bt_run_id,
                    "trade_date": s_time.date(),
                    "ticker": s.get("figi"),
                    "direction": str(s.get("signal_type") or "").upper(),
                    "signal_time": s_time,
                    "price_at_signal": s.get("price"),
                    "quantity_lots": None,
                    "reason": str(s.get("reason") or "GENERATED")[:50],
                },
            )

        for t in res.trades:
            t_time = None
            try:
                if t.get("bar_time"):
                    t_time = datetime.fromisoformat(str(t.get("bar_time")).replace("Z", "+00:00"))
            except Exception:
                t_time = None
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
            ord_id = self.db.execute(
                text(
                    """
                    INSERT INTO backtest.backtest_orders
                    (backtest_run_id, signal_id, ticker, direction, order_type, limit_price, requested_quantity,
                     executed_quantity, avg_execution_price, slippage_cost, commission_cost, status, placed_at, filled_at)
                    VALUES
                    (:backtest_run_id, NULL, :ticker, :direction, 'LIMIT', :limit_price, :requested_quantity,
                     :executed_quantity, :avg_execution_price, :slippage_cost, :commission_cost, 'FILLED', :placed_at, :filled_at)
                    RETURNING id
                    """
                ),
                {
                    "backtest_run_id": bt_run_id,
                    "ticker": t.get("figi"),
                    "direction": str(t.get("side") or "").upper(),
                    "limit_price": t.get("price"),
                    "requested_quantity": t.get("quantity"),
                    "executed_quantity": t.get("quantity"),
                    "avg_execution_price": t.get("price"),
                    "slippage_cost": slip_cost,
                    "commission_cost": t.get("commission") or 0,
                    "placed_at": t_time,
                    "filled_at": t_time,
                },
            ).scalar()
            self.db.execute(
                text(
                    """
                    INSERT INTO backtest.backtest_trades
                    (backtest_run_id, order_id, ticker, direction, quantity, price, commission, trade_time)
                    VALUES
                    (:backtest_run_id, :order_id, :ticker, :direction, :quantity, :price, :commission, :trade_time)
                    """
                ),
                {
                    "backtest_run_id": bt_run_id,
                    "order_id": ord_id,
                    "ticker": t.get("figi"),
                    "direction": str(t.get("side") or "").upper(),
                    "quantity": t.get("quantity"),
                    "price": t.get("price"),
                    "commission": t.get("commission") or 0,
                    "trade_time": t_time,
                },
            )

        day_trade_counts: Dict[date, int] = {}
        day_commission: Dict[date, float] = {}
        day_slippage: Dict[date, float] = {}
        for t in res.trades:
            try:
                tt = datetime.fromisoformat(str(t.get("bar_time") or "").replace("Z", "+00:00"))
            except Exception:
                continue
            d = tt.date()
            px = float(t.get("price") or 0.0)
            qty = float(t.get("quantity") or 0.0)
            slip_val = (px * qty) * (max(0.0, float(slippage_pct or 0.0)) / 100.0) if px > 0 and qty > 0 else 0.0
            day_trade_counts[d] = int(day_trade_counts.get(d, 0)) + 1
            day_commission[d] = float(day_commission.get(d, 0.0)) + float(t.get("commission") or 0)
            day_slippage[d] = float(day_slippage.get(d, 0.0)) + slip_val

        day_positions_value: Dict[date, float] = {}
        for dp in res.daily_positions:
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

        prev_equity = float(res.initial_capital or 0)
        peak_equity_daily = float(res.initial_capital or 0)
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
            self.db.execute(
                text(
                    """
                    INSERT INTO backtest.backtest_equity_curve
                    (backtest_run_id, trade_date, cash, positions_value, total_equity, daily_pnl, daily_return_percent,
                     commission_paid, slippage_paid, trades_count, drawdown, drawdown_percent)
                    VALUES
                    (:backtest_run_id, :trade_date, :cash, :positions_value, :total_equity, :daily_pnl, :daily_return_percent,
                     :commission_paid, :slippage_paid, :trades_count, :drawdown, :drawdown_percent)
                    ON CONFLICT (backtest_run_id, trade_date) DO UPDATE SET
                        total_equity = EXCLUDED.total_equity,
                        cash = EXCLUDED.cash,
                        positions_value = EXCLUDED.positions_value,
                        daily_pnl = EXCLUDED.daily_pnl,
                        daily_return_percent = EXCLUDED.daily_return_percent,
                        commission_paid = EXCLUDED.commission_paid,
                        slippage_paid = EXCLUDED.slippage_paid,
                        trades_count = EXCLUDED.trades_count,
                        drawdown = EXCLUDED.drawdown,
                        drawdown_percent = EXCLUDED.drawdown_percent
                    """
                ),
                {
                    "backtest_run_id": bt_run_id,
                    "trade_date": d,
                    "cash": cash_val,
                    "positions_value": positions_val,
                    "total_equity": eq,
                    "daily_pnl": daily_pnl_val,
                    "daily_return_percent": daily_ret,
                    "commission_paid": float(day_commission.get(d, 0.0)),
                    "slippage_paid": float(day_slippage.get(d, 0.0)),
                    "trades_count": int(day_trade_counts.get(d, 0)),
                    "drawdown": dd_abs,
                    "drawdown_percent": dd_pct,
                },
            )
            prev_equity = eq

        for dp in res.daily_positions:
            self.db.execute(
                text(
                    """
                    INSERT INTO backtest.backtest_positions
                    (backtest_run_id, trade_date, ticker, quantity, avg_entry_price, current_price, unrealized_pnl, realized_pnl, updated_at)
                    VALUES
                    (:backtest_run_id, :trade_date, :ticker, :quantity, :avg_entry_price, :current_price, :unrealized_pnl, :realized_pnl, :updated_at)
                    ON CONFLICT (backtest_run_id, trade_date, ticker) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        avg_entry_price = EXCLUDED.avg_entry_price,
                        current_price = EXCLUDED.current_price,
                        unrealized_pnl = EXCLUDED.unrealized_pnl,
                        realized_pnl = EXCLUDED.realized_pnl,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "backtest_run_id": bt_run_id,
                    "trade_date": dp.get("trade_date"),
                    "ticker": dp.get("ticker"),
                    "quantity": dp.get("quantity"),
                    "avg_entry_price": dp.get("avg_entry_price"),
                    "current_price": dp.get("current_price"),
                    "unrealized_pnl": dp.get("unrealized_pnl"),
                    "realized_pnl": dp.get("realized_pnl"),
                    "updated_at": datetime.now(timezone.utc),
                },
            )

        self.db.execute(
            text(
                """
                INSERT INTO backtest.backtest_metrics
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
                "start_date": start_date,
                "end_date": end_date,
                "trading_days": payload.trading_days_cnt,
                "total_trades": len(res.trades),
                "winning_trades": payload.winning_count,
                "losing_trades": max(0, payload.closed_count - payload.winning_count),
                "win_rate": payload.win_rate,
                "total_return_percent": res.total_return_percent,
                "annualized_return_percent": payload.annualized_return_val,
                "max_drawdown_percent": res.max_drawdown_percent,
                "max_drawdown_duration": payload.max_dd_duration,
                "sharpe_ratio": payload.sharpe_val,
                "sortino_ratio": payload.sortino_val,
                "calmar_ratio": payload.calmar_val,
                "volatility_annual": payload.volatility_annual_val,
                "initial_capital": res.initial_capital,
                "final_equity": res.final_equity,
                "gross_profit": payload.gross_profit_val,
                "gross_loss": payload.gross_loss_val,
                "total_commission": payload.total_commission_val,
                "total_slippage": float(sum(day_slippage.values())),
                "net_profit": payload.net_profit_val,
                "profit_factor": payload.profit_factor_val,
                "profit_per_trade": payload.avg_pnl,
                "avg_win": payload.avg_win_val,
                "avg_loss": payload.avg_loss_val,
            },
        )
        self.db.execute(
            text(
                """
                UPDATE backtest.backtest_runs
                SET status='COMPLETED',
                    progress_percent=100,
                    completed_at=:completed_at
                WHERE id=:id
                """
            ),
            {"id": bt_run_id, "completed_at": datetime.now(timezone.utc)},
        )

