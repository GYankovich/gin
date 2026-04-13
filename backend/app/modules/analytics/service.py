# app/modules/analytics/service.py
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Dict, Any
from datetime import datetime
import math

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


analytics_service = AnalyticsService()