# app/modules/analytics/service.py
#///EPIC Analytics.ITEM Engine.TOPIC Portfolio Metrics Computation [1]
#/// Сервис аналитики: вычисление KPI, доходностей, просадок, статистик сделок
#/// и подготовка временных рядов для графиков аналитического интерфейса.
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Dict, Any
from datetime import datetime
import math
from collections import defaultdict, deque
from app.modules.market_data import service as market_data_service

from . import queries


class AnalyticsService:
    """Сервис для аналитики по портфелям"""

    def __init__(self):
        self.db: Optional[Session] = None

    def _execute(self, query_tuple: tuple[str, Dict[str, Any]], fetch_all: bool = True) -> List[Any]:
        """
        Утилита для выполнения запросов
        """
        sql, params = query_tuple
        result = self.db.execute(text(sql), params)
        return result.fetchall() if fetch_all else result.first()

    @staticmethod
    def _safe_str(value, default: str = '') -> str:
        """Безопасное преобразование в строку"""
        if value is None:
            return default
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        if isinstance(value, (int, float)):
            return str(value)
        return str(value)

    @staticmethod
    def _safe_float(value, default: Optional[float] = 0.0) -> Optional[float]:
        """Безопасное преобразование в float"""
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        """Безопасное преобразование в int"""
        if value is None:
            return default
        try:
            if isinstance(value, float) and value.is_integer():
                return int(value)
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_datetime(value, default: Optional[datetime] = None) -> Optional[datetime]:
        """Безопасное преобразование в datetime"""
        if value is None:
            return default
        return value

    def _row_to_account_summary(self, row) -> dict:
        """Преобразует строку результата в словарь для AccountSummary"""
        return {
            "id": self._safe_int(row[0]),
            "account_id": self._safe_str(row[1]),
            "name": self._safe_str(row[2], None) if row[2] else None,
            "type": self._safe_str(row[3], 'unknown'),
            "status": self._safe_str(row[4], 'active'),
            "last_snapshot_date": self._safe_datetime(row[5]),
            "total_value": self._safe_float(row[6], 0.0),
            "currency": self._safe_str(row[7], 'RUB'),
            "positions_count": self._safe_int(row[8], 0),
            "last_token_id": self._safe_int(row[9], 0) if len(row) > 9 and row[9] is not None else None,
            "daily_yield": self._safe_float(row[10], None) if len(row) > 10 else None,
            "expected_yield": self._safe_float(row[11], None) if len(row) > 11 else None,
        }

    def _row_to_history_item(self, row, has_snapshot_id: bool = True) -> dict:
        """Преобразует строку результата в элемент истории"""
        if has_snapshot_id:
            return {
                "snapshot_id": self._safe_int(row[0]),
                "date": self._safe_datetime(row[1]),
                "total_value": self._safe_float(row[2], 0.0),
                "daily_yield": self._safe_float(row[3], None),
                "expected_yield": self._safe_float(row[4], None),
            }
        else:
            return {
                "date": self._safe_datetime(row[0]),
                "total_value": self._safe_float(row[1], 0.0),
                "daily_yield": self._safe_float(row[2], None),
                "expected_yield": self._safe_float(row[3], None),
            }

    def _row_to_distribution_item(self, row, total_value: float) -> dict:
        """Преобразует строку результата в элемент распределения"""
        value = self._safe_float(row[1], 0.0)
        return {
            "instrument_type": self._safe_str(row[0], 'unknown'),
            "value": value,
            "percentage": (value / total_value) if total_value > 0 else 0,
            "count": self._safe_int(row[2], 0),
            "avg_price": self._safe_float(row[3], None) if len(row) > 3 else None,
            "min_price": self._safe_float(row[4], None) if len(row) > 4 else None,
            "max_price": self._safe_float(row[5], None) if len(row) > 5 else None,
        }

    def _row_to_last_snapshot(self, row) -> Optional[dict]:
        """Преобразует строку результата в последний снимок"""
        if not row:
            return None

        return {
            "id": self._safe_int(row[0]),
            "date": self._safe_datetime(row[1]),
            "total_value": self._safe_float(row[2], 0.0),
            "shares_value": self._safe_float(row[3], 0.0) if len(row) > 3 else 0.0,
            "bonds_value": self._safe_float(row[4], 0.0) if len(row) > 4 else 0.0,
            "etf_value": self._safe_float(row[5], 0.0) if len(row) > 5 else 0.0,
            "currencies_value": self._safe_float(row[6], 0.0) if len(row) > 6 else 0.0,
            "expected_yield": self._safe_float(row[7], 0.0) if len(row) > 7 else 0.0,
            "daily_yield": self._safe_float(row[8], 0.0) if len(row) > 8 else 0.0,
            "daily_yield_relative": self._safe_float(row[9], 0.0) if len(row) > 9 else 0.0,
        }

    def _row_to_account_info(self, row) -> Optional[dict]:
        """Преобразует строку результата в информацию о счете"""
        if not row:
            return None

        return {
            "id": self._safe_str(row[1]),  # account_id (внешний)
            "name": self._safe_str(row[2], None),
            "type": self._safe_str(row[3], 'unknown'),
            "status": self._safe_str(row[4], 'active'),
        }

    def get_accounts_summary(
            self,
            db: Session,
            user_id: int,
            include_inactive: bool = False,
            min_value: Optional[float] = None
    ) -> List[dict]:
        """
        Получить все портфели пользователя с последним снимком
        """
        self.db = db
        query_tuple = queries.build_accounts_summary_query(
            user_id=user_id,
            include_inactive=include_inactive,
            min_total_value=min_value
        )

        result = self._execute(query_tuple)
        return [self._row_to_account_summary(row) for row in result]

    def get_account_history(
            self,
            db: Session,
            account_id: int,
            days: int = 30,
            from_date: Optional[datetime] = None,
            to_date: Optional[datetime] = None,
            interval: Optional[str] = None
    ) -> List[dict]:
        """
        История снимков портфеля с возможностью фильтрации
        """
        self.db = db
        query_tuple = queries.build_account_history_query(
            account_id=account_id,
            days=days,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )

        result = self._execute(query_tuple)

        # Определяем, есть ли snapshot_id в результате
        has_snapshot_id = interval is None
        return [self._row_to_history_item(row, has_snapshot_id) for row in result]

    def get_account_distribution(
            self,
            db: Session,
            account_id: int,
            instrument_types: Optional[List[str]] = None,
            min_value: Optional[float] = None,
            snapshot_id: Optional[int] = None
    ) -> List[dict]:
        """
        Распределение активов по типам
        """
        self.db = db
        query_tuple = queries.build_distribution_query(
            account_id=account_id,
            snapshot_id=snapshot_id,
            instrument_types=instrument_types,
            min_value=min_value
        )

        positions = self._execute(query_tuple)

        # Считаем общую сумму для процентов
        total = sum(self._safe_float(p[1], 0.0) for p in positions) if positions else 0

        return [self._row_to_distribution_item(p, total) for p in positions]

    def check_account_ownership(self, db: Session, account_id: int, user_id: int) -> Optional[dict]:
        """
        Проверяет, принадлежит ли счет пользователю
        """
        self.db = db
        query = queries.build_account_ownership_check_query()
        result = db.execute(
            text(query),
            {"account_id": account_id, "user_id": user_id}
        ).first()

        return self._row_to_account_info(result)

    def get_account_detail(
            self,
            db: Session,
            account_id: int,
            user_id: int,
            days: int = 30,
            include_distribution: bool = True
    ) -> Optional[dict]:
        """
        Детальная информация по конкретному портфелю
        """
        self.db = db

        # Проверяем принадлежность
        account_info = self.check_account_ownership(db, account_id, user_id)
        if not account_info:
            return None

        # Получаем последний снимок
        query_tuple = queries.build_last_snapshot_query(account_id)
        last_snapshot_row = self._execute(query_tuple, fetch_all=False)
        last_snapshot_dict = self._row_to_last_snapshot(last_snapshot_row)

        # Получаем ID последнего снимка для распределения
        last_snapshot_id = None
        if last_snapshot_dict and include_distribution:
            last_snapshot_id = last_snapshot_dict.get('id')

        # История
        history = self.get_account_history(db, account_id, days=days)

        # Распределение (если нужно)
        distribution = []
        if include_distribution and last_snapshot_id:
            distribution = self.get_account_distribution(
                db,
                account_id,
                snapshot_id=last_snapshot_id
            )

        return {
            "account": account_info,
            "last_snapshot": last_snapshot_dict,
            "history": history,
            "distribution": distribution,
        }

    def get_overall_summary(
            self,
            db: Session,
            user_id: int,
            include_inactive: bool = False
    ) -> dict:
        """
        Сводка по всем портфелям пользователя
        """
        accounts = self.get_accounts_summary(
            db,
            user_id,
            include_inactive=include_inactive
        )

        total_value = sum(a.get("total_value", 0) for a in accounts)
        total_daily_yield = sum(a.get("daily_yield", 0) for a in accounts if a.get("daily_yield"))
        total_expected_yield = sum(a.get("expected_yield", 0) for a in accounts if a.get("expected_yield"))

        return {
            "total_value": total_value,
            "total_daily_yield": total_daily_yield,
            "total_expected_yield": total_expected_yield,
            "accounts_count": len(accounts),
            "accounts": accounts,
        }

    def get_account_positions(
            self,
            db: Session,
            account_id: int,
            user_id: int,
            snapshot_id: Optional[int] = None,
            instrument_types: Optional[List[str]] = None
    ) -> List[dict]:
        """
        Получить позиции по счету (из последнего или конкретного снимка)
        """
        self.db = db

        # Проверяем принадлежность
        if not self.check_account_ownership(db, account_id, user_id):
            return []

        # Если не указан snapshot_id, берем последний
        if snapshot_id is None:
            query_tuple = queries.build_last_snapshot_query(account_id, fields=['id'])
            last = self._execute(query_tuple, fetch_all=False)
            if not last:
                return []
            snapshot_id = last[0]

        # Получаем позиции
        query = """
                SELECT
                    id,
                    figi,
                    ticker,
                    instrument_type,
                    quantity,
                    current_price,
                    (current_price * quantity) as total_value,
                    expected_yield,
                    daily_yield,
                    average_position_price,
                    blocked
                FROM ganaly.portfolio_positions
                WHERE snapshot_id = :snapshot_id \
                """

        params = {"snapshot_id": snapshot_id}

        if instrument_types:
            query += " AND instrument_type = ANY(:instrument_types)"
            params["instrument_types"] = instrument_types

        query += " ORDER BY total_value DESC"

        result = db.execute(text(query), params).fetchall()

        positions = []
        for row in result:
            positions.append({
                "id": self._safe_int(row[0]),
                "figi": self._safe_str(row[1], None),
                "ticker": self._safe_str(row[2], None),
                "instrument_type": self._safe_str(row[3], 'unknown'),
                "quantity": self._safe_float(row[4], 0.0),
                "current_price": self._safe_float(row[5], 0.0),
                "total_value": self._safe_float(row[6], 0.0),
                "expected_yield": self._safe_float(row[7], None),
                "daily_yield": self._safe_float(row[8], None),
                "avg_price": self._safe_float(row[9], None),
                "blocked": bool(row[10]) if row[10] else False,
            })

        return positions

    def get_account_operations(
            self,
            db: Session,
            account_id: int,
            user_id: int,
            from_date: datetime,
            to_date: datetime,
            operation_type: Optional[str] = None,
            limit: int = 5000,
    ) -> List[dict]:
        self.db = db
        if not self.check_account_ownership(db, account_id, user_id):
            return []
        sql = """
              SELECT
                  operation_id,
                  operation_date,
                  operation_type,
                  figi,
                  instrument_type,
                  quantity,
                  price,
                  payment,
                  payment_currency,
                  status,
                  extra_data
              FROM ganaly.portfolio_operations
              WHERE account_id = :account_id
                AND operation_date >= :from_date
                AND operation_date <= :to_date
              """
        params: Dict[str, Any] = {
            "account_id": account_id,
            "from_date": from_date,
            "to_date": to_date,
        }
        if operation_type:
            sql += " AND operation_type = :operation_type"
            params["operation_type"] = operation_type
        sql += " ORDER BY operation_date DESC LIMIT :limit"
        params["limit"] = limit
        rows = db.execute(text(sql), params).fetchall()
        out: List[dict] = []
        for r in rows:
            extra = r[10] or {}
            out.append({
                "operation_id": self._safe_str(r[0]),
                "operation_date": self._safe_datetime(r[1]),
                "operation_type": self._safe_str(r[2]),
                "figi": self._safe_str(r[3], None) if r[3] else None,
                "instrument_type": self._safe_str(r[4], None) if r[4] else None,
                "quantity": self._safe_float(r[5], 0.0) or 0.0,
                "price": self._safe_float(r[6], 0.0) or 0.0,
                "payment": self._safe_float(r[7], 0.0) or 0.0,
                "currency": self._safe_str(r[8], None) if r[8] else None,
                "status": self._safe_str(r[9]),
                "type_text": self._safe_str(extra.get("type_text"), None) if extra else None,
            })
        return out

    def get_account_chart_series(
            self,
            db: Session,
            account_id: int,
            user_id: int,
            from_date: datetime,
            to_date: datetime,
            figis: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        self.db = db
        if not self.check_account_ownership(db, account_id, user_id):
            return None

        history = self.get_account_history(
            db=db,
            account_id=account_id,
            from_date=from_date,
            to_date=to_date,
            days=0,
        )
        portfolio_series = [
            {"date": h.get("date"), "value": float(h.get("total_value") or 0.0)}
            for h in history
        ]
        drawdown_series = self._compute_drawdown_series(history)

        available_rows = db.execute(
            text(
                """
                SELECT DISTINCT pp.figi, pp.ticker
                FROM ganaly.portfolio_positions pp
                WHERE pp.snapshot_id = (
                    SELECT ps.id
                    FROM ganaly.portfolio_snapshots ps
                    WHERE ps.account_id = :account_id
                    ORDER BY ps.snapshot_date DESC
                    LIMIT 1
                )
                ORDER BY pp.figi
                """
            ),
            {"account_id": account_id},
        ).fetchall()
        available_instruments = [
            {"figi": self._safe_str(r[0]), "ticker": self._safe_str(r[1], None) if r[1] else None}
            for r in available_rows if r[0]
        ]

        figis_set = {str(f).strip() for f in (figis or []) if str(f).strip()}
        rows = db.execute(
            text(
                """
                SELECT
                    ps.snapshot_date,
                    pp.figi,
                    MAX(pp.ticker) AS ticker,
                    SUM(pp.quantity * pp.current_price) AS value
                FROM ganaly.portfolio_snapshots ps
                JOIN ganaly.portfolio_positions pp ON pp.snapshot_id = ps.id
                WHERE ps.account_id = :account_id
                  AND ps.snapshot_date >= :from_date
                  AND ps.snapshot_date <= :to_date
                  AND (:no_filter = 1 OR pp.figi = ANY(:figis))
                GROUP BY ps.snapshot_date, pp.figi
                HAVING SUM(pp.quantity) > 0
                ORDER BY ps.snapshot_date ASC, pp.figi ASC
                """
            ),
            {
                "account_id": account_id,
                "from_date": from_date,
                "to_date": to_date,
                "figis": list(figis_set),
                "no_filter": 1 if not figis_set else 0,
            },
        ).fetchall()
        grouped: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            dt = r[0]
            figi = self._safe_str(r[1])
            ticker = self._safe_str(r[2], None) if r[2] else None
            value = float(r[3] or 0.0)
            if figi not in grouped:
                grouped[figi] = {"figi": figi, "ticker": ticker, "points": []}
            grouped[figi]["points"].append({"date": dt, "value": value})
        instruments_series: List[Dict[str, Any]] = list(grouped.values())

        return {
            "account_id": account_id,
            "from_date": from_date,
            "to_date": to_date,
            "portfolio_series": portfolio_series,
            "drawdown_series": drawdown_series,
            "instruments_series": instruments_series,
            "available_instruments": available_instruments,
        }


    # --- Robot trading analytics ---

    def robot_belongs_to_user(
            self, db: Session, robot_id: int, user_id: int, schema: str = "ganaly"
    ) -> bool:
        q = queries.build_robot_ownership_query(schema)
        return db.execute(
            text(q), {"robot_id": robot_id, "user_id": user_id}
        ).first() is not None

    def get_robot_metrics(
            self,
            db: Session,
            robot_id: int,
            recent_limit: int = 20,
            schema: str = "ganaly",
            user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        KPI торгового робота: win rate, PnL, drawdown, profit factor и т.д.
        """
        self.db = db
        if user_id is not None and not self.robot_belongs_to_user(db, robot_id, user_id, schema):
            return None

        summary_sql = queries.build_robot_trades_summary_query(schema)
        row = db.execute(text(summary_sql), {"robot_id": robot_id}).first()
        if not row:
            return None

        total_trades = self._safe_int(row[0])
        closed_trades = self._safe_int(row[2])
        winning = self._safe_int(row[3])
        losing = self._safe_int(row[4])
        total_pnl = self._safe_float(row[5], 0.0)
        avg_profit = self._safe_float(row[6])
        avg_loss = self._safe_float(row[7])
        best_trade = self._safe_float(row[8])
        worst_trade = self._safe_float(row[9])
        avg_duration = self._safe_float(row[10])
        total_commission = self._safe_float(row[11], 0.0) if len(row) > 11 else 0.0

        win_rate = (winning / closed_trades * 100) if closed_trades > 0 else None

        gross_profit = (avg_profit or 0) * winning
        gross_loss = abs((avg_loss or 0) * losing)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

        pnl_sql = queries.build_robot_closed_pnl_series_query(schema)
        pnl_rows = db.execute(text(pnl_sql), {"robot_id": robot_id}).fetchall()
        pnl_series = [self._safe_float(r[0], 0.0) for r in pnl_rows]
        max_drawdown = self._calc_max_drawdown(pnl_series)
        sharpe, sortino, calmar = self._calc_risk_adjusted_metrics(pnl_series)

        status_sql = f"""
            SELECT status, COUNT(*)::int
            FROM {schema}.robot_trades
            WHERE robot_id = :robot_id
            GROUP BY status
        """
        status_rows = db.execute(text(status_sql), {"robot_id": robot_id}).fetchall()
        status_counts = {self._safe_str(r[0], "").lower(): self._safe_int(r[1], 0) for r in status_rows}
        filled_count = status_counts.get("closed", 0)
        partial_count = status_counts.get("partial", 0)
        rejected_count = status_counts.get("rejected", 0)
        cancelled_count = status_counts.get("cancelled", 0)
        terminal_count = filled_count + partial_count + rejected_count + cancelled_count
        fill_rate = (filled_count / terminal_count * 100.0) if terminal_count > 0 else None
        reject_rate = (rejected_count / terminal_count * 100.0) if terminal_count > 0 else None

        trades_sql = queries.build_robot_recent_trades_query(schema)
        trade_rows = db.execute(text(trades_sql), {"robot_id": robot_id, "limit": recent_limit}).fetchall()
        recent_trades = [
            {
                "id": self._safe_int(r[0]),
                "figi": self._safe_str(r[1]),
                "side": self._safe_str(r[2]),
                "quantity": self._safe_float(r[3], 0.0),
                "entry_price": self._safe_float(r[4]),
                "exit_price": self._safe_float(r[5]),
                "profit": self._safe_float(r[6]),
                "profit_percent": self._safe_float(r[7]),
                "status": self._safe_str(r[8]),
                "created_at": self._safe_datetime(r[9]),
                "closed_at": self._safe_datetime(r[10]),
            }
            for r in trade_rows
        ]

        metrics = {
            "robot_id": robot_id,
            "total_trades": total_trades,
            "open_trades": self._safe_int(row[1]),
            "closed_trades": closed_trades,
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": round(win_rate, 2) if win_rate is not None else None,
            "total_pnl": round(total_pnl, 2),
            "avg_profit": round(avg_profit, 2) if avg_profit else None,
            "avg_loss": round(avg_loss, 2) if avg_loss else None,
            "best_trade": round(best_trade, 2) if best_trade else None,
            "worst_trade": round(worst_trade, 2) if worst_trade else None,
            "max_drawdown": round(max_drawdown, 2) if max_drawdown else None,
            "profit_factor": round(profit_factor, 2) if profit_factor else None,
            "avg_trade_duration_hours": round(avg_duration, 2) if avg_duration else None,
            "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
            "sortino_ratio": round(sortino, 4) if sortino is not None else None,
            "calmar_ratio": round(calmar, 4) if calmar is not None else None,
            "fill_rate": round(fill_rate, 2) if fill_rate is not None else None,
            "reject_rate": round(reject_rate, 2) if reject_rate is not None else None,
            "partial_fills": partial_count,
            "rejected_orders": rejected_count,
            "total_commission": round(total_commission, 2) if total_commission else 0.0,
        }

        return {"metrics": metrics, "recent_trades": recent_trades}

    def get_user_robots_trading_overview(
            self,
            db: Session,
            user_id: int,
            schema: str = "ganaly",
    ) -> Dict[str, Any]:
        """
        Агрегированные торговые метрики по всем роботам пользователя.
        """
        self.db = db
        agg_sql = queries.build_user_robots_trades_aggregate_query(schema)
        row = db.execute(text(agg_sql), {"user_id": user_id}).first()
        if not row:
            return self._empty_trading_overview()

        total_trades = self._safe_int(row[0])
        open_trades = self._safe_int(row[1])
        closed_trades = self._safe_int(row[2])
        winning = self._safe_int(row[3])
        losing = self._safe_int(row[4])
        total_pnl = self._safe_float(row[5], 0.0)
        total_commission = self._safe_float(row[6], 0.0)
        robots_with_closed = self._safe_int(row[7], 0)
        sum_wins = self._safe_float(row[8], 0.0)
        sum_losses = self._safe_float(row[9], 0.0)

        win_rate = (winning / closed_trades * 100) if closed_trades > 0 else None
        profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else None

        pnl_sql = queries.build_user_robots_closed_pnl_series_query(schema)
        pnl_rows = db.execute(text(pnl_sql), {"user_id": user_id}).fetchall()
        pnl_series = [self._safe_float(r[0], 0.0) for r in pnl_rows]
        max_drawdown = self._calc_max_drawdown(pnl_series)
        sharpe, sortino, calmar = self._calc_risk_adjusted_metrics(pnl_series)

        return {
            "robots_with_closed_trades": robots_with_closed,
            "total_trades": total_trades,
            "open_trades": open_trades,
            "closed_trades": closed_trades,
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": round(win_rate, 2) if win_rate is not None else None,
            "total_pnl": round(total_pnl, 2),
            "total_commission": round(total_commission, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor else None,
            "max_drawdown": round(max_drawdown, 2) if max_drawdown else None,
            "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
            "sortino_ratio": round(sortino, 4) if sortino is not None else None,
            "calmar_ratio": round(calmar, 4) if calmar is not None else None,
        }

    @staticmethod
    def _empty_trading_overview() -> Dict[str, Any]:
        return {
            "robots_with_closed_trades": 0,
            "total_trades": 0,
            "open_trades": 0,
            "closed_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": None,
            "total_pnl": 0.0,
            "total_commission": 0.0,
            "profit_factor": None,
            "max_drawdown": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "calmar_ratio": None,
        }

    @staticmethod
    def _calc_max_drawdown(profits: List[float]) -> Optional[float]:
        if not profits:
            return None
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in profits:
            cumulative += p
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        return max_dd if max_dd > 0 else None

    @staticmethod
    def _calc_risk_adjusted_metrics(profits: List[float]) -> tuple[Optional[float], Optional[float], Optional[float]]:
        if not profits:
            return None, None, None
        n = len(profits)
        mean = sum(profits) / n
        if n > 1:
            var = sum((p - mean) ** 2 for p in profits) / (n - 1)
            std = math.sqrt(var)
        else:
            std = 0.0
        downside = [p for p in profits if p < 0]
        if len(downside) > 1:
            d_mean = sum(downside) / len(downside)
            d_var = sum((p - d_mean) ** 2 for p in downside) / (len(downside) - 1)
            downside_std = math.sqrt(d_var)
        elif len(downside) == 1:
            downside_std = abs(downside[0])
        else:
            downside_std = 0.0
        sharpe = (mean / std * math.sqrt(max(1, n))) if std > 0 else None
        sortino = (mean / downside_std * math.sqrt(max(1, n))) if downside_std > 0 else None

        max_dd = AnalyticsService._calc_max_drawdown(profits) or 0.0
        total_return = sum(profits)
        calmar = (total_return / max_dd) if max_dd > 0 else None
        return sharpe, sortino, calmar

    def get_account_statistics(
            self,
            db: Session,
            account_id: int,
            user_id: int,
            from_date: datetime,
            to_date: datetime,
    ) -> Optional[Dict[str, Any]]:
        self.db = db
        if not self.check_account_ownership(db, account_id, user_id):
            return None

        own_funds_sql = """
            SELECT
                COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_INPUT' THEN payment ELSE 0 END), 0)
                -
                COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_OUTPUT' THEN payment ELSE 0 END), 0)
            FROM ganaly.portfolio_operations
            WHERE account_id = :account_id
        """
        own_funds_row = db.execute(text(own_funds_sql), {"account_id": account_id}).first()
        own_funds = self._safe_float(own_funds_row[0] if own_funds_row else 0.0, 0.0) or 0.0

        latest_snapshot_row = db.execute(
            text(
                """
                SELECT total_amount_portfolio, snapshot_date
                FROM ganaly.portfolio_snapshots
                WHERE account_id = :account_id
                ORDER BY snapshot_date DESC
                LIMIT 1
                """
            ),
            {"account_id": account_id},
        ).first()
        current_total_value = self._safe_float(
            latest_snapshot_row[0] if latest_snapshot_row else 0.0,
            0.0,
        ) or 0.0
        latest_snapshot_date = self._safe_datetime(latest_snapshot_row[1], None) if latest_snapshot_row else None

        overall_roi_percent: Optional[float] = None
        if abs(own_funds) > 1e-9:
            overall_roi_percent = ((current_total_value - own_funds) / own_funds) * 100.0

        first_input_row = db.execute(
            text(
                """
                SELECT MIN(operation_date)
                FROM ganaly.portfolio_operations
                WHERE account_id = :account_id
                  AND operation_type = 'OPERATION_TYPE_INPUT'
                """
            ),
            {"account_id": account_id},
        ).first()
        first_input_date = self._safe_datetime(first_input_row[0], None) if first_input_row else None

        avg_monthly_roi_percent: Optional[float] = None
        if overall_roi_percent is not None and first_input_date and latest_snapshot_date:
            months = max((latest_snapshot_date - first_input_date).total_seconds() / (86400.0 * 30.4375), 0.0)
            if months > 1e-9:
                avg_monthly_roi_percent = overall_roi_percent / months

        period_inflow_sql = """
            SELECT
                COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_INPUT' THEN payment ELSE 0 END), 0)
                -
                COALESCE(abs(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_OUTPUT' THEN payment ELSE 0 END)), 0)
            FROM ganaly.portfolio_operations
            WHERE account_id = :account_id
              AND operation_date < :from_date
        """
        period_inflow_row = db.execute(
            text(period_inflow_sql),
            {"account_id": account_id, "from_date": from_date},
        ).first()
        period_inflow = self._safe_float(period_inflow_row[0] if period_inflow_row else 0.0, 0.0) or 0.0

        period_history = self.get_account_history(
            db=db,
            account_id=account_id,
            from_date=from_date,
            to_date=to_date,
            days=0,
        )

        end_value: Optional[float] = None
        max_drawdown_percent: Optional[float] = None
        max_growth_percent: Optional[float] = None
        period_roi_percent: Optional[float] = None

        values = [self._safe_float(item.get("total_value"), 0.0) or 0.0 for item in period_history]
        if values:
            start_value = values[0]
            end_value = values[-1]
            max_value = max(values)

            if abs(start_value) > 1e-9:
                max_growth_percent = ((max_value - start_value) / start_value) * 100.0
                period_roi_percent = ((end_value - start_value) / start_value) * 100.0

            peak = values[0]
            max_drawdown = 0.0
            for value in values:
                if value > peak:
                    peak = value
                if peak > 1e-9:
                    drawdown = ((peak - value) / peak) * 100.0
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown
            max_drawdown_percent = max_drawdown

        return {
            "account_id": account_id,
            "overall": {
                "own_funds": own_funds,
                "current_total_value": current_total_value,
                "roi_percent": round(overall_roi_percent, 4) if overall_roi_percent is not None else None,
                "avg_monthly_roi_percent": round(avg_monthly_roi_percent, 4) if avg_monthly_roi_percent is not None else None,
            },
            "period": {
                "from_date": from_date,
                "to_date": to_date,
                "period_inflow": period_inflow,
                "max_drawdown_percent": round(max_drawdown_percent, 4) if max_drawdown_percent is not None else None,
                "max_growth_percent": round(max_growth_percent, 4) if max_growth_percent is not None else None,
                "end_value": round(end_value, 4) if end_value is not None else None,
                "period_roi_percent": round(period_roi_percent, 4) if period_roi_percent is not None else None,
            },
        }

    @staticmethod
    def _compute_drawdown_series(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        peak = None
        for item in points:
            value = float(item.get("total_value") or 0.0)
            dt = item.get("date")
            if peak is None or value > peak:
                peak = value
            dd = ((value - peak) / peak * 100.0) if peak and peak > 1e-9 else 0.0
            out.append({"date": dt, "drawdown_percent": dd})
        return out

    @staticmethod
    def _avg_hold_label(hours: Optional[float]) -> Optional[str]:
        if hours is None:
            return None
        if hours < 24:
            return "скальпинг"
        if hours < 24 * 3:
            return "дейтрейд"
        return "позиционка"

    def _build_fifo_trade_metrics(
            self,
            db: Session,
            account_id: int,
            from_date: datetime,
            to_date: datetime,
    ) -> Dict[str, Any]:
        # Важно: учитываем только полноценные торговые циклы BUY/SELL.
        # Комиссии/вознаграждения/налоги в серии убытков не участвуют.
        sql = """
              SELECT operation_date, operation_type, figi, quantity, price, payment
              FROM ganaly.portfolio_operations
              WHERE account_id = :account_id
                AND operation_date <= :to_date
                AND figi IS NOT NULL
                AND operation_type IN (
                    'OPERATION_TYPE_BUY', 'OPERATION_TYPE_BUY_CARD', 'OPERATION_TYPE_BUY_MARGIN',
                    'OPERATION_TYPE_SELL', 'OPERATION_TYPE_SELL_CARD', 'OPERATION_TYPE_SELL_MARGIN'
                )
              ORDER BY operation_date ASC, id ASC
              """
        rows = db.execute(text(sql), {"account_id": account_id, "to_date": to_date}).fetchall()
        fifo: Dict[str, deque] = defaultdict(deque)
        closed: List[Dict[str, Any]] = []

        buy_types = {"OPERATION_TYPE_BUY", "OPERATION_TYPE_BUY_CARD", "OPERATION_TYPE_BUY_MARGIN"}
        sell_types = {"OPERATION_TYPE_SELL", "OPERATION_TYPE_SELL_CARD", "OPERATION_TYPE_SELL_MARGIN"}
        for r in rows:
            op_date = r[0]
            op_type = self._safe_str(r[1], "")
            figi = self._safe_str(r[2], "")
            qty = float(r[3] or 0.0)
            price = float(r[4] or 0.0)
            if qty <= 0 or not figi:
                continue
            if op_type in buy_types:
                fifo[figi].append({"qty": qty, "price": price, "date": op_date})
            elif op_type in sell_types:
                remaining = qty
                while remaining > 1e-9 and fifo[figi]:
                    lot = fifo[figi][0]
                    matched = min(remaining, lot["qty"])
                    pnl = (price - lot["price"]) * matched
                    if from_date <= op_date <= to_date:
                        hold_hours = (op_date - lot["date"]).total_seconds() / 3600.0 if lot["date"] else None
                        closed.append({"pnl": pnl, "close_date": op_date, "hold_hours": hold_hours})
                    lot["qty"] -= matched
                    remaining -= matched
                    if lot["qty"] <= 1e-9:
                        fifo[figi].popleft()

        closed_count = len(closed)
        wins = [t for t in closed if t["pnl"] > 0]
        losses = [t for t in closed if t["pnl"] < 0]
        winning_count = len(wins)
        losing_count = len(losses)
        total_profit = sum(t["pnl"] for t in wins)
        total_loss_abs = abs(sum(t["pnl"] for t in losses))
        avg_win = (total_profit / winning_count) if winning_count else None
        avg_loss = (sum(t["pnl"] for t in losses) / losing_count) if losing_count else None
        win_rate = (winning_count / closed_count * 100.0) if closed_count else None
        profit_factor = (total_profit / total_loss_abs) if total_loss_abs > 1e-9 else None
        ratio = (abs(avg_win) / abs(avg_loss)) if avg_win is not None and avg_loss not in (None, 0) else None

        max_streak = 0
        max_streak_sum = 0.0
        cur_streak = 0
        cur_sum = 0.0
        for t in sorted(closed, key=lambda x: x["close_date"]):
            if t["pnl"] < 0:
                cur_streak += 1
                cur_sum += t["pnl"]
                if cur_streak > max_streak:
                    max_streak = cur_streak
                    max_streak_sum = cur_sum
            else:
                cur_streak = 0
                cur_sum = 0.0

        holds = [t["hold_hours"] for t in closed if t["hold_hours"] is not None]
        avg_hold = (sum(holds) / len(holds)) if holds else None

        return {
            "realized_pnl": sum(t["pnl"] for t in closed) if closed else None,
            "closed_trades_count": closed_count,
            "winning_trades_count": winning_count,
            "losing_trades_count": losing_count,
            "win_rate_percent": win_rate,
            "profit_factor": profit_factor,
            "max_consecutive_losses": max_streak,
            "max_consecutive_losses_sum": max_streak_sum if max_streak > 0 else None,
            "avg_winning_trade": avg_win,
            "avg_losing_trade": avg_loss,
            "avg_win_loss_ratio": ratio,
            "avg_hold_hours": avg_hold,
        }

    @staticmethod
    def _calc_average_recovery_days(values: List[float], dates: List[datetime]) -> Optional[float]:
        if len(values) < 3:
            return None
        peak = values[0]
        peak_idx = 0
        recovery_days: List[float] = []
        in_drawdown = False
        trough_idx = 0
        for i in range(1, len(values)):
            v = values[i]
            if v >= peak:
                if in_drawdown and trough_idx < i:
                    recovery_days.append((dates[i] - dates[trough_idx]).total_seconds() / 86400.0)
                peak = v
                peak_idx = i
                in_drawdown = False
                trough_idx = i
            else:
                in_drawdown = True
                if values[trough_idx] > v:
                    trough_idx = i
                if peak_idx >= trough_idx:
                    trough_idx = i
        if not recovery_days:
            return None
        return sum(recovery_days) / len(recovery_days)

    async def get_account_statistics_extended(
            self,
            db: Session,
            account_id: int,
            user_id: int,
            from_date: datetime,
            to_date: datetime,
    ) -> Optional[Dict[str, Any]]:
        base_stats = self.get_account_statistics(db, account_id, user_id, from_date, to_date)
        if not base_stats:
            return None

        period_ops_sql = """
            SELECT operation_type, payment
            FROM ganaly.portfolio_operations
            WHERE account_id = :account_id
              AND operation_date >= :from_date
              AND operation_date <= :to_date
        """
        op_rows = db.execute(text(period_ops_sql), {
            "account_id": account_id,
            "from_date": from_date,
            "to_date": to_date,
        }).fetchall()
        sum_input = sum(float(r[1] or 0.0) for r in op_rows if r[0] == "OPERATION_TYPE_INPUT")
        sum_output = sum(float(r[1] or 0.0) for r in op_rows if r[0] == "OPERATION_TYPE_OUTPUT")
        net_flow = sum_input - sum_output
        dividends = sum(float(r[1] or 0.0) for r in op_rows if r[0] == "OPERATION_TYPE_DIVIDEND")
        # Терминология по вашему бизнес-слою:
        # TRACK_MFEE = комиссия брокера, TRACK_PFEE = вознаграждение.
        broker_fees = sum(float(r[1] or 0.0) for r in op_rows if r[0] == "OPERATION_TYPE_TRACK_MFEE")
        track_fees = sum(float(r[1] or 0.0) for r in op_rows if r[0] == "OPERATION_TYPE_TRACK_PFEE")
        taxes_paid = sum(
            float(r[1] or 0.0)
            for r in op_rows
            if r[0] in {"OPERATION_TYPE_TAX", "OPERATION_TYPE_DIVIDEND_TAX"}
        )

        fifo_metrics = self._build_fifo_trade_metrics(db, account_id, from_date, to_date)

        period_history = self.get_account_history(
            db=db,
            account_id=account_id,
            from_date=from_date,
            to_date=to_date,
            days=0,
        )
        values = [float(x.get("total_value") or 0.0) for x in period_history]
        dates = [x.get("date") for x in period_history]
        drawdown_period = self._compute_drawdown_series(period_history)
        max_dd = min((p["drawdown_percent"] for p in drawdown_period), default=0.0)
        current_dd = drawdown_period[-1]["drawdown_percent"] if drawdown_period else None
        avg_recovery_days = self._calc_average_recovery_days(values, dates) if values and all(dates) else None
        avg_portfolio = (sum(values) / len(values)) if values else None

        all_history = self.get_account_history(db=db, account_id=account_id, days=3650)
        drawdown_full = self._compute_drawdown_series(all_history)

        portfolio_return = base_stats["period"]["period_roi_percent"]
        imoex_return = None
        benchmark_unavailable = False
        try:
            imoex_return = await market_data_service.get_imoex_return_percent(from_date, to_date)
        except Exception:
            benchmark_unavailable = True
        relative_return = (portfolio_return - imoex_return) if portfolio_return is not None and imoex_return is not None else None

        current_total = float(base_stats["overall"]["current_total_value"] or 0.0)
        dividends_share = (dividends / current_total * 100.0) if current_total > 1e-9 else None
        unrealized_row = db.execute(
            text(
                """
                SELECT COALESCE(SUM(pp.quantity * (pp.current_price - pp.average_position_price)), 0)
                FROM ganaly.portfolio_positions pp
                WHERE pp.snapshot_id = (
                    SELECT ps.id
                    FROM ganaly.portfolio_snapshots ps
                    WHERE ps.account_id = :account_id
                    ORDER BY ps.snapshot_date DESC
                    LIMIT 1
                )
                """
            ),
            {"account_id": account_id},
        ).first()
        unrealized = float(unrealized_row[0] or 0.0) if unrealized_row else 0.0

        return {
            "account_id": account_id,
            "from_date": from_date,
            "to_date": to_date,
            "overall": base_stats["overall"],
            "capital_flow": {
                "net_capital_inflow": round(net_flow, 4),
                "dividends_received": round(abs(dividends), 4),
                "dividends_share_of_portfolio_percent": round(dividends_share, 4) if dividends_share is not None else None,
                "realized_pnl": round(fifo_metrics["realized_pnl"], 4) if fifo_metrics["realized_pnl"] is not None else None,
                "unrealized_pnl": round(unrealized, 4),
            },
            "trading_performance": {
                "closed_trades_count": fifo_metrics["closed_trades_count"],
                "winning_trades_count": fifo_metrics["winning_trades_count"],
                "losing_trades_count": fifo_metrics["losing_trades_count"],
                "win_rate_percent": round(fifo_metrics["win_rate_percent"], 4) if fifo_metrics["win_rate_percent"] is not None else None,
                "win_rate_ratio_text": (
                    f"{fifo_metrics['winning_trades_count']} из {fifo_metrics['closed_trades_count']}"
                    if fifo_metrics["closed_trades_count"] > 0 else None
                ),
                "profit_factor": round(fifo_metrics["profit_factor"], 4) if fifo_metrics["profit_factor"] is not None else None,
                "max_consecutive_losses": fifo_metrics["max_consecutive_losses"],
                "max_consecutive_losses_sum": round(fifo_metrics["max_consecutive_losses_sum"], 4) if fifo_metrics["max_consecutive_losses_sum"] is not None else None,
                "avg_winning_trade": round(fifo_metrics["avg_winning_trade"], 4) if fifo_metrics["avg_winning_trade"] is not None else None,
                "avg_losing_trade": round(fifo_metrics["avg_losing_trade"], 4) if fifo_metrics["avg_losing_trade"] is not None else None,
                "avg_win_loss_ratio": round(fifo_metrics["avg_win_loss_ratio"], 4) if fifo_metrics["avg_win_loss_ratio"] is not None else None,
            },
            "operational_metrics": {
                "average_hold_time_hours": round(fifo_metrics["avg_hold_hours"], 4) if fifo_metrics["avg_hold_hours"] is not None else None,
                "average_hold_time_label": self._avg_hold_label(fifo_metrics["avg_hold_hours"]),
                "total_broker_fees": round(abs(broker_fees), 4),
                "total_track_fees": round(abs(track_fees), 4),
                "total_taxes": round(abs(taxes_paid), 4),
                "track_fees_share_of_avg_portfolio_percent": (
                    round(abs(track_fees) / avg_portfolio * 100.0, 4)
                    if avg_portfolio and avg_portfolio > 1e-9 else None
                ),
            },
            "benchmark_metrics": {
                "portfolio_return_percent": portfolio_return,
                "imoex_return_percent": round(imoex_return, 4) if imoex_return is not None else None,
                "relative_return_percent": round(relative_return, 4) if relative_return is not None else None,
                "benchmark_unavailable": benchmark_unavailable,
            },
            "risk_recovery": {
                "max_drawdown_percent": round(abs(max_dd), 4) if drawdown_period else None,
                "average_recovery_days": round(avg_recovery_days, 4) if avg_recovery_days is not None else None,
                "current_drawdown_percent": round(current_dd, 4) if current_dd is not None else None,
            },
            "drawdown_series": [
                {"date": p["date"], "drawdown_percent": round(p["drawdown_percent"], 4)}
                for p in drawdown_full
            ],
        }


analytics_service = AnalyticsService()