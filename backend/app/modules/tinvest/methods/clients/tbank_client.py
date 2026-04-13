import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

TBANK_GET_OPERATIONS_BY_CURSOR_ENDPOINT = (
    "tinkoff.public.invest.api.contract.v1.OperationsService/GetOperationsByCursor"
)


def _normalize_operation_for_upsert(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    GetOperationsByCursor возвращает OperationItem (items): часть полей и вложенность
    отличаются от GetOperations (operations) — приводим к виду, который ждёт sync в БД.
    """
    op = dict(raw) if isinstance(raw, dict) else {}
    ty = op.get("type")
    if op.get("operationType") is None and isinstance(ty, str) and ty.startswith("OPERATION_TYPE_"):
        op["operationType"] = ty

    if op.get("trades") is None:
        ti = op.get("tradesInfo") or op.get("trades_info")
        op["trades"] = (ti.get("trades") if isinstance(ti, dict) else None) or []

    if isinstance(ty, str) and ty.startswith("OPERATION_TYPE_"):
        human = op.get("name") or op.get("description")
        if human:
            op["type"] = human

    if not op.get("currency"):
        pay = op.get("payment")
        if isinstance(pay, dict) and pay.get("currency"):
            op["currency"] = pay["currency"]

    return op


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
            data: Optional[Dict] = None,
            *,
            timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Базовый метод для выполнения POST-запросов к API
        """
        url = f"{self.BASE_URL}/{endpoint}"

        logger.info(f"Making request to {url}")
        logger.debug(f"Request data: {data}")

        try:
            # ВАЖНО: добавляем verify=False для отключения проверки SSL
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
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

    async def get_operations(
            self,
            account_id: str,
            from_dt: datetime,
            to_dt: datetime,
            state: str = "OPERATION_STATE_UNSPECIFIED",
    ) -> Dict[str, Any]:
        """
        Получение операций по счету.
        POST /tinkoff.public.invest.api.contract.v1.OperationsService/GetOperations
        """
        try:
            data = {
                "accountId": account_id,
                "from": from_dt.isoformat().replace("+00:00", "Z"),
                "to": to_dt.isoformat().replace("+00:00", "Z"),
                "state": state,
            }
            result = await self._make_request(
                "tinkoff.public.invest.api.contract.v1.OperationsService/GetOperations",
                data,
            )
            logger.info(f"Successfully retrieved operations for account {account_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to get operations for account {account_id}: {e}")
            raise

    async def get_operations_all_pages(
            self,
            account_id: str,
            from_dt: datetime,
            to_dt: datetime,
            state: str = "OPERATION_STATE_UNSPECIFIED",
            page_limit: int = 1000,
    ) -> Dict[str, Any]:
        """
        Все операции за период через GetOperationsByCursor (лимит до 1000 на страницу).
        GetOperations без курсора отдаёт ограниченный набор (типично ~150).
        """
        page_limit = max(1, min(page_limit, 1000))
        raw_items: List[Dict[str, Any]] = []
        page_responses: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        pages = 0
        max_pages = 500

        while pages < max_pages:
            data: Dict[str, Any] = {
                "accountId": account_id,
                "from": from_dt.isoformat().replace("+00:00", "Z"),
                "to": to_dt.isoformat().replace("+00:00", "Z"),
                "state": state,
                "limit": page_limit,
            }
            if cursor:
                data["cursor"] = cursor

            result = await self._make_request(
                TBANK_GET_OPERATIONS_BY_CURSOR_ENDPOINT,
                data,
                timeout=60.0,
            )
            pages += 1
            page_responses.append(result)

            batch = result.get("items") or result.get("operations") or []
            raw_items.extend(batch)

            next_cursor = result.get("nextCursor") or result.get("next_cursor") or None
            if isinstance(next_cursor, str) and not next_cursor.strip():
                next_cursor = None

            has_next_raw = result.get("hasNext", result.get("has_next"))
            if has_next_raw is None:
                has_next = bool(next_cursor)
            else:
                has_next = bool(has_next_raw)

            if not next_cursor:
                if has_next:
                    logger.warning(
                        "GetOperationsByCursor: hasNext=true, но nextCursor пуст — остановка пагинации"
                    )
                break
            if not has_next:
                break
            cursor = next_cursor

        if pages >= max_pages:
            logger.warning(
                "get_operations_all_pages: достигнут лимит %s страниц для счёта %s",
                max_pages,
                account_id,
            )

        operations = [_normalize_operation_for_upsert(item) for item in raw_items]
        logger.info(
            "Retrieved %s operations for account %s in %s page(s)",
            len(operations),
            account_id,
            pages,
        )
        return {
            "operations": operations,
            "nextCursor": None,
            "pageCount": pages,
            "rawItemCount": len(raw_items),
            "pages": page_responses,
        }


# ВАЖНО: эта функция должна быть на одном уровне с классом, а не внутри него
def create_tbank_client(token: str) -> TBankClient:
    """
    Фабрика для создания клиента T-Bank API
    """
    return TBankClient(token)