from typing import Dict, Any, Optional
import logging

from app.modules.robots.workers.base_worker import BaseWorker
from app.modules.tinvest.methods.clients import create_tbank_client
from app.modules.tinvest.service import TInvestService

logger = logging.getLogger(__name__)


class PortfolioUpdaterWorker(BaseWorker):
    """
    Робот для обновления портфеля пользователя
    """

    def __init__(self):
        super().__init__(
            name="portfolio_updater",
            version="1.0.0"
        )

    async def work(self, token_id: int, user_id: int, token: str) -> Dict[str, Any]:
        """
        Обновление всех портфелей для токена
        """
        try:
            client = create_tbank_client(token)

            # Получаем все счета
            accounts_raw = await client.get_accounts()

            if not accounts_raw:
                logger.warning(f"No accounts found for token {token_id}")
                return {
                    "token_id": token_id,
                    "user_id": user_id,
                    "accounts_found": 0,
                    "portfolios_updated": 0,
                    "snapshots_saved": 0
                }

            # Преобразуем счета в наш формат
            accounts = []
            for acc in accounts_raw:
                accounts.append({
                    "id": acc.get("id"),
                    "type": acc.get("type", "").replace("ACCOUNT_TYPE_", ""),
                    "name": acc.get("name", ""),
                    "status": acc.get("status", "").replace("ACCOUNT_STATUS_", ""),
                    "opened_date": acc.get("openedDate"),
                    "closed_date": acc.get("closedDate"),
                    "access_level": acc.get("accessLevel", "").replace("ACCOUNT_ACCESS_LEVEL_", "")
                })

            # Для каждого счета получаем портфель
            portfolios_updated = 0
            snapshots_saved = 0

            for account in accounts:
                try:
                    # Получаем данные портфеля
                    portfolio_data = await TInvestService.get_portfolio_data(token, account["id"])

                    # Сохраняем снимок в БД
                    snapshot_id = await TInvestService.save_portfolio_snapshot(
                        db=self.db,
                        user_id=user_id,
                        account_id=account["id"],
                        account_data=account,
                        portfolio_data=portfolio_data
                    )

                    portfolios_updated += 1
                    if snapshot_id:
                        snapshots_saved += 1

                except Exception as e:
                    logger.error(f"Error updating account {account['id']}: {e}")

            # Обновляем время последнего использования токена
            await TInvestService.update_token_last_used(self.db, token_id)

            return {
                "token_id": token_id,
                "user_id": user_id,
                "accounts_found": len(accounts),
                "portfolios_updated": portfolios_updated,
                "snapshots_saved": snapshots_saved
            }

        except Exception as e:
            logger.error(f"Portfolio updater worker failed: {e}")
            raise