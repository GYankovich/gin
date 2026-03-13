import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class TBankClient:
    """Клиент для работы с T-Bank Invest API"""

    BASE_URL = "https://invest-public-api.tbank.ru/rest"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def _make_request(
            self,
            endpoint: str,
            data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Базовый метод для выполнения POST-запросов к API
        """
        url = f"{self.BASE_URL}/{endpoint}"

        logger.info(f"Making request to {url}")
        logger.debug(f"Request data: {data}")

        try:
            # ВАЖНО: добавляем verify=False для отключения проверки SSL
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=data
                )

                logger.info(f"Response status: {response.status_code}")
                logger.debug(f"Response headers: {dict(response.headers)}")

                if response.status_code == 401:
                    error_text = await response.text() if response.text else "No error message"
                    logger.error(f"Unauthorized (401): {error_text}")
                    raise Exception(f"Неверный токен или токен истек. Получите новый токен в личном кабинете Т-Банка.")

                if response.status_code == 403:
                    error_text = await response.text() if response.text else "No error message"
                    logger.error(f"Forbidden (403): {error_text}")
                    raise Exception(f"Нет доступа к API. Проверьте права токена.")

                if response.status_code == 429:
                    logger.error("Rate limit exceeded (429)")
                    raise Exception("Слишком много запросов. Превышен лимит API. Попробуйте позже.")

                if response.status_code >= 500:
                    error_text = await response.text() if response.text else "No error message"
                    logger.error(f"Server error ({response.status_code}): {error_text}")
                    raise Exception(f"Ошибка на стороне Т-Банка. Попробуйте позже.")

                if response.status_code >= 400:
                    error_text = await response.text() if response.text else "No error message"
                    logger.error(f"Client error ({response.status_code}): {error_text}")
                    raise Exception(f"Ошибка запроса: {error_text[:200]}")

                response_json = response.json() if response.text else {}
                logger.debug(f"Response JSON: {response_json}")
                return response_json

        except httpx.TimeoutException:
            logger.error("Timeout exception")
            raise Exception("Таймаут при запросе к T-Bank API. Проверьте подключение к интернету.")
        except httpx.NetworkError as e:
            logger.error(f"Network error: {e}")
            raise Exception(f"Сетевая ошибка при подключении к T-Bank API: {str(e)}")
        except Exception as e:
            logger.error(f"Request error: {e}", exc_info=True)
            raise

    async def get_accounts(self) -> List[Dict]:
        """
        Получение списка счетов пользователя
        POST /tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts
        """
        try:
            data = {"status": "ACCOUNT_STATUS_UNSPECIFIED"}
            result = await self._make_request(
                "tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts",
                data
            )
            accounts = result.get("accounts", [])
            logger.info(f"Successfully retrieved {len(accounts)} accounts")
            return accounts
        except Exception as e:
            logger.error(f"Failed to get accounts: {e}")
            raise

    async def get_portfolio(self, account_id: str, currency: str = "RUB") -> Dict:
        """
        Получение портфеля по счету
        POST /tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio
        """
        try:
            data = {
                "accountId": account_id,
                "currency": currency
            }
            result = await self._make_request(
                "tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio",
                data
            )
            logger.info(f"Successfully retrieved portfolio for account {account_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to get portfolio for account {account_id}: {e}")
            raise


# ВАЖНО: эта функция должна быть на одном уровне с классом, а не внутри него
def create_tbank_client(token: str) -> TBankClient:
    """
    Фабрика для создания клиента T-Bank API
    """
    return TBankClient(token)