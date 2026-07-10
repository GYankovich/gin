from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBacktestMetrics [1]
#/// Исходный модуль `backend/app/modules/robots/trading/backtest/metrics.py` — автоматическая разметка для Obsidian Source Scanner.

import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.modules.robots.trading.costs import annualization_days_for_broker


class BacktestMetricsCalculator:
    """Calculate aggregate metrics from simulation artifacts."""

    @staticmethod
    def calculate(
        *,
        res: Any,
        broker_type: Optional[str] = None,
        calendar_days_cnt: Optional[int] = None,
    ) -> Dict[str, Any]:
        winning = [t for t in res.trades if t.get("pnl_net") is not None and float(t.get("pnl_net") or 0) > 0]
        closed = [t for t in res.trades if t.get("pnl_net") is not None]
        avg_pnl = (sum(float(t.get("pnl_net") or 0) for t in closed) / len(closed)) if closed else None
        win_rate = (len(winning) * 100.0 / len(closed)) if closed else None
        gross_profit_val = sum(float(t.get("pnl_net") or 0) for t in winning)
        gross_loss_val = abs(sum(float(t.get("pnl_net") or 0) for t in closed if float(t.get("pnl_net") or 0) < 0))
        net_profit_val = float(res.final_equity or 0) - float(res.initial_capital or 0)
        fee_summary = dict(getattr(res, "fee_summary", None) or {})
        total_commission_val = float(
            fee_summary.get("total_commission")
            if fee_summary.get("total_commission") is not None
            else sum(float(t.get("commission") or 0) for t in res.trades)
        )
        total_funding_val = float(fee_summary.get("total_funding") or 0)
        loss_trades_count = len([t for t in closed if float(t.get("pnl_net") or 0) < 0])
        profit_factor_val = (gross_profit_val / gross_loss_val) if gross_loss_val > 0 else None
        avg_win_val = (gross_profit_val / len(winning)) if winning else None
        avg_loss_val = (
            sum(float(t.get("pnl_net") or 0) for t in closed if float(t.get("pnl_net") or 0) < 0) / loss_trades_count
            if loss_trades_count > 0
            else None
        )

        equity_by_day: Dict[date, float] = {}
        for p in (res.equity_curve or []):
            tm = None
            try:
                if p.get("time"):
                    tm = datetime.fromisoformat(str(p.get("time")).replace("Z", "+00:00"))
            except Exception:
                tm = None
            if not tm:
                continue
            equity_by_day[tm.date()] = float(p.get("equity", 0) or 0)
        sorted_equity_days = sorted(equity_by_day.keys())
        daily_equity_points: List[float] = [float(res.initial_capital or 0)] + [float(equity_by_day[d]) for d in sorted_equity_days]
        daily_returns = []
        for i in range(1, len(daily_equity_points)):
            prev = daily_equity_points[i - 1]
            cur = daily_equity_points[i]
            if prev > 0:
                daily_returns.append((cur / prev) - 1.0)
        trading_days_cnt = len(sorted_equity_days)
        ann_days = annualization_days_for_broker(broker_type)
        calendar_cnt = int(calendar_days_cnt) if calendar_days_cnt is not None else trading_days_cnt
        annualized_return_val = None
        if trading_days_cnt > 0 and res.initial_capital > 0 and res.final_equity > 0:
            years = trading_days_cnt / float(ann_days)
            if years > 0:
                annualized_return_val = ((res.final_equity / res.initial_capital) ** (1.0 / years) - 1.0) * 100.0
        volatility_annual_val = None
        sharpe_val = None
        sortino_val = None
        if daily_returns:
            mean_r = sum(daily_returns) / len(daily_returns)
            var_r = sum((x - mean_r) ** 2 for x in daily_returns) / len(daily_returns)
            std_r = math.sqrt(var_r)
            downside = [x for x in daily_returns if x < 0]
            downside_std = math.sqrt(sum((x - 0.0) ** 2 for x in downside) / len(downside)) if downside else 0.0
            volatility_annual_val = std_r * math.sqrt(float(ann_days)) * 100.0
            sharpe_val = (mean_r / std_r * math.sqrt(float(ann_days))) if std_r > 0 else None
            sortino_val = (mean_r / downside_std * math.sqrt(float(ann_days))) if downside_std > 0 else None
        calmar_val = None
        if res.max_drawdown_percent and float(res.max_drawdown_percent or 0) > 0 and annualized_return_val is not None:
            calmar_val = annualized_return_val / float(res.max_drawdown_percent)
        max_dd_duration = 0
        cur_dd_duration = 0
        peak_eq = float(res.initial_capital or 0)
        for eq in daily_equity_points[1:]:
            if eq >= peak_eq:
                peak_eq = eq
                cur_dd_duration = 0
            else:
                cur_dd_duration += 1
                if cur_dd_duration > max_dd_duration:
                    max_dd_duration = cur_dd_duration

        return {
            "winning": winning,
            "closed": closed,
            "avg_pnl": avg_pnl,
            "win_rate": win_rate,
            "gross_profit_val": gross_profit_val,
            "gross_loss_val": gross_loss_val,
            "net_profit_val": net_profit_val,
            "total_commission_val": total_commission_val,
            "total_funding_val": total_funding_val,
            "fee_summary": fee_summary,
            "profit_factor_val": profit_factor_val,
            "avg_win_val": avg_win_val,
            "avg_loss_val": avg_loss_val,
            "equity_by_day": equity_by_day,
            "trading_days_cnt": trading_days_cnt,
            "calendar_days_cnt": calendar_cnt,
            "annualization_days": ann_days,
            "annualized_return_val": annualized_return_val,
            "volatility_annual_val": volatility_annual_val,
            "sharpe_val": sharpe_val,
            "sortino_val": sortino_val,
            "calmar_val": calmar_val,
            "max_dd_duration": max_dd_duration,
        }

