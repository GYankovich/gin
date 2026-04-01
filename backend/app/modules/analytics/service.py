# app/modules/analytics/service.py
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Dict, Any
from datetime import datetime

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
            "daily_yield": self._safe_float(row[9], None) if len(row) > 9 else None,
            "expected_yield": self._safe_float(row[10], None) if len(row) > 10 else None,
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


    # --- Robot trading analytics ---

    def get_robot_metrics(
            self,
            db: Session,
            robot_id: int,
            recent_limit: int = 20,
            schema: str = "ganaly",
    ) -> Optional[Dict[str, Any]]:
        """
        KPI торгового робота: win rate, PnL, drawdown, profit factor и т.д.
        """
        self.db = db
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

        win_rate = (winning / closed_trades * 100) if closed_trades > 0 else None

        gross_profit = (avg_profit or 0) * winning
        gross_loss = abs((avg_loss or 0) * losing)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

        pnl_sql = queries.build_robot_closed_pnl_series_query(schema)
        pnl_rows = db.execute(text(pnl_sql), {"robot_id": robot_id}).fetchall()
        max_drawdown = self._calc_max_drawdown([self._safe_float(r[0], 0.0) for r in pnl_rows])

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
        }

        return {"metrics": metrics, "recent_trades": recent_trades}

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


analytics_service = AnalyticsService()