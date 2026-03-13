from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime, timedelta


class AnalyticsService:
    """Сервис для аналитики по портфелям (работает только с БД)"""

    @staticmethod
    def get_accounts_summary(db: Session, user_id: int) -> List[dict]:
        """
        Получить все портфели пользователя с последним снимком
        """
        query = text("""
                     SELECT
                         pa.id,
                         pa.account_id,
                         pa.account_name,
                         pa.account_type,
                         pa.account_status,
                         ps.snapshot_date as last_snapshot_date,
                         ps.total_amount_portfolio as total_value,
                         ps.currency,
                         (SELECT COUNT(*) FROM ganaly.portfolio_positions WHERE snapshot_id = ps.id) as positions_count
                     FROM ganaly.portfolio_accounts pa
                              LEFT JOIN LATERAL (
                         SELECT id, snapshot_date, total_amount_portfolio, currency
                         FROM ganaly.portfolio_snapshots
                         WHERE account_id = pa.id
                         ORDER BY snapshot_date DESC
                             LIMIT 1
            ) ps ON true
                     WHERE pa.user_id = :user_id
                     """)
        result = db.execute(query, {"user_id": user_id}).fetchall()
        accounts = []
        for row in result:
            accounts.append({
                "id": row[0],
                "account_id": row[1],
                "name": row[2],
                "type": row[3],
                "status": row[4],
                "last_snapshot_date": row[5],
                "total_value": float(row[6]) if row[6] else 0,
                "currency": row[7] or "RUB",
                "positions_count": row[8] or 0,
            })
        return accounts

    @staticmethod
    def get_account_history(db: Session, account_id: int, days: int = 30) -> List[dict]:
        """
        История снимков портфеля за последние N дней
        """
        query = text("""
                     SELECT
                         id,
                         snapshot_date,
                         total_amount_portfolio,
                         daily_yield,
                         expected_yield
                     FROM ganaly.portfolio_snapshots
                     WHERE account_id = :account_id
                       AND snapshot_date >= :from_date
                     ORDER BY snapshot_date ASC
                     """)
        from_date = datetime.utcnow() - timedelta(days=days)
        result = db.execute(query, {"account_id": account_id, "from_date": from_date}).fetchall()
        history = []
        for row in result:
            history.append({
                "snapshot_id": row[0],
                "date": row[1],
                "total_value": float(row[2]),
                "daily_yield": float(row[3]) if row[3] else None,
                "expected_yield": float(row[4]) if row[4] else None,
            })
        return history

    @staticmethod
    def get_account_distribution(db: Session, account_id: int) -> List[dict]:
        """
        Распределение активов по типам (на основе последнего снимка)
        """
        # Последний снимок
        last_snapshot = db.execute(
            text("SELECT id FROM ganaly.portfolio_snapshots WHERE account_id = :account_id ORDER BY snapshot_date DESC LIMIT 1"),
            {"account_id": account_id}
        ).first()
        if not last_snapshot:
            return []
        snapshot_id = last_snapshot[0]

        # Получаем позиции
        positions = db.execute(
            text("""
                 SELECT
                     instrument_type,
                     SUM(current_price * quantity) as total_value,
                     COUNT(*) as count
                 FROM ganaly.portfolio_positions
                 WHERE snapshot_id = :snapshot_id
                 GROUP BY instrument_type
                 """),
            {"snapshot_id": snapshot_id}
        ).fetchall()

        # Преобразуем Decimal в float для вычислений
        total = sum(float(p[1]) for p in positions) if positions else 0

        distribution = []
        for p in positions:
            value = float(p[1])
            distribution.append({
                "instrument_type": p[0],
                "value": value,
                "percentage": (value / total) if total > 0 else 0,
                "count": p[2],
            })
        return distribution

    @staticmethod
    def get_account_detail(db: Session, account_id: int, user_id: int) -> Optional[dict]:
        """
        Детальная информация по конкретному портфелю
        """
        # Проверяем принадлежность пользователю
        account = db.execute(
            text("SELECT id, account_id, account_name, account_type, account_status FROM ganaly.portfolio_accounts WHERE id = :account_id AND user_id = :user_id"),
            {"account_id": account_id, "user_id": user_id}
        ).first()
        if not account:
            return None

        # Последний снимок
        last_snapshot = db.execute(
            text("""
                 SELECT
                     id,
                     snapshot_date,
                     total_amount_portfolio,
                     total_amount_shares,
                     total_amount_bonds,
                     total_amount_etf,
                     total_amount_currencies,
                     expected_yield,
                     daily_yield,
                     daily_yield_relative
                 FROM ganaly.portfolio_snapshots
                 WHERE account_id = :account_id
                 ORDER BY snapshot_date DESC
                     LIMIT 1
                 """),
            {"account_id": account_id}
        ).first()

        last_snapshot_dict = None
        if last_snapshot:
            last_snapshot_dict = {
                "id": last_snapshot[0],
                "date": last_snapshot[1],
                "total_value": float(last_snapshot[2]),
                "shares_value": float(last_snapshot[3]) if last_snapshot[3] else 0,
                "bonds_value": float(last_snapshot[4]) if last_snapshot[4] else 0,
                "etf_value": float(last_snapshot[5]) if last_snapshot[5] else 0,
                "currencies_value": float(last_snapshot[6]) if last_snapshot[6] else 0,
                "expected_yield": float(last_snapshot[7]) if last_snapshot[7] else 0,
                "daily_yield": float(last_snapshot[8]) if last_snapshot[8] else 0,
                "daily_yield_relative": float(last_snapshot[9]) if last_snapshot[9] else 0,
            }

        # История
        history = AnalyticsService.get_account_history(db, account_id)
        # Распределение
        distribution = AnalyticsService.get_account_distribution(db, account_id)

        return {
            "account": {
                "id": account[1],
                "name": account[2],
                "type": account[3],
                "status": account[4],
            },
            "last_snapshot": last_snapshot_dict,
            "history": history,
            "distribution": distribution,
        }

    @staticmethod
    def get_overall_summary(db: Session, user_id: int) -> dict:
        """
        Сводка по всем портфелям пользователя
        """
        accounts = AnalyticsService.get_accounts_summary(db, user_id)
        total_value = sum(a["total_value"] for a in accounts)
        total_daily_yield = sum(a.get("daily_yield", 0) for a in accounts if a.get("daily_yield"))
        total_expected_yield = sum(a.get("expected_yield", 0) for a in accounts if a.get("expected_yield"))
        return {
            "total_value": total_value,
            "total_daily_yield": total_daily_yield,
            "total_expected_yield": total_expected_yield,
            "accounts_count": len(accounts),
            "accounts": accounts,
        }


analytics_service = AnalyticsService()