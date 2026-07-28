from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.core.logging_config import get_logger
from app.modules.bybit import BybitHttpClient, BybitWebSocketClient, parse_kline_event
from app.modules.robots.trading.brokers.base import BrokerFacade

logger = get_logger(__name__)

_STABLE_WALLET_COINS = frozenset({"USDT", "USDC", "USD", "BUSD"})

_ACCOUNT_KIND_UNIFIED = "UNIFIED"
_ACCOUNT_KIND_FUND = "FUND"
_ACCOUNT_KIND_COPY = "COPY"

_ACCOUNT_LABELS = {
    _ACCOUNT_KIND_UNIFIED: "ByBit Unified",
    _ACCOUNT_KIND_FUND: "ByBit Funding",
    _ACCOUNT_KIND_COPY: "ByBit Copy Trading",
}

_INTERVAL_TO_BYBIT = {
    "CANDLE_INTERVAL_1_MIN": "1",
    "CANDLE_INTERVAL_3_MIN": "3",
    "CANDLE_INTERVAL_5_MIN": "5",
    "CANDLE_INTERVAL_15_MIN": "15",
    "CANDLE_INTERVAL_30_MIN": "30",
    "CANDLE_INTERVAL_HOUR": "60",
    "CANDLE_INTERVAL_2_HOUR": "120",
    "CANDLE_INTERVAL_4_HOUR": "240",
    "CANDLE_INTERVAL_DAY": "D",
    "M1": "1",
    "M3": "3",
    "M5": "5",
    "M15": "15",
    "M30": "30",
    "H1": "60",
    "H2": "120",
    "H4": "240",
    "D1": "D",
    "1M": "1",
    "3M": "3",
    "5M": "5",
    "15M": "15",
    "30M": "30",
    "1H": "60",
    "2H": "120",
    "4H": "240",
    "1D": "D",
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "4h": "240",
    "1d": "D",
}


class ByBitBrokerFacade(BrokerFacade):
    broker_type = "bybit"

    def __init__(
        self,
        token: str,
        *,
        testnet: bool = False,
        api_secret: str | None = None,
        instrument_category: str = "linear",
        http_client: BybitHttpClient | None = None,
        ws_client: BybitWebSocketClient | None = None,
        user_id: int | None = None,
        token_id: int | None = None,
        context_type: str | None = None,
        context_ref: str | None = None,
    ) -> None:
        self._token = str(token or "").strip()
        self._instrument_category = str(instrument_category or "linear").strip().lower()
        self._http = http_client or BybitHttpClient(
            testnet=testnet,
            api_key=self._token or None,
            api_secret=api_secret,
            user_id=user_id,
            token_id=token_id,
            context_type=context_type or "bybit_http",
            context_ref=context_ref,
        )
        self._ws = ws_client or BybitWebSocketClient(testnet=testnet)
        self._ws_task: asyncio.Task | None = None
        self._ws_lock = asyncio.Lock()
        self._queue_to_symbols: dict[asyncio.Queue, Set[str]] = {}
        self._symbol_to_queues: dict[str, Set[asyncio.Queue]] = {}
        self._subscribed_symbols: Set[str] = set()
        self._last_prices: dict[str, float] = {}
        self._ws_interval = "5"
        self._asset_overview_cache: dict[str, Any] | None = None
        self._order_symbols: dict[str, str] = {}
        self._lot_filters: dict[str, dict[str, float]] = {}

    @property
    def cache_namespace(self) -> str:
        head = self._token[:12] if self._token else "anonymous"
        return f"{self.broker_type}:{head}"

    @property
    def auth_token(self) -> str:
        return self._token

    def make_account_id(self, kind: str) -> str:
        """Stable per-user ByBit account id: bybit:UNIFIED|FUND|COPY.

        Scoped by portfolio_accounts.user_id (composite unique), so API-key
        rotation does not create duplicate accounts.
        """
        return f"bybit:{str(kind or '').strip().upper()}"

    def parse_account_kind(self, account_id: str) -> str:
        raw = str(account_id or "").strip()
        upper = raw.upper()
        if upper in {"BYBIT_UNIFIED", "BYBIT:UNIFIED"} or upper.endswith(":UNIFIED"):
            return _ACCOUNT_KIND_UNIFIED
        if upper in {"BYBIT:FUND", "BYBIT_FUND"} or upper.endswith(":FUND"):
            return _ACCOUNT_KIND_FUND
        if upper in {"BYBIT:COPY", "BYBIT_COPY"} or upper.endswith(":COPY"):
            return _ACCOUNT_KIND_COPY
        # Legacy / unknown → treat as unified trading account
        return _ACCOUNT_KIND_UNIFIED

    async def _load_asset_overview(self, *, force: bool = False) -> dict[str, Any]:
        if self._asset_overview_cache is not None and not force:
            return self._asset_overview_cache
        try:
            resp = await self._http.get_asset_overview()
            self._asset_overview_cache = resp if isinstance(resp, dict) else {}
        except Exception as exc:
            logger.warning("ByBit asset-overview failed: %s", exc)
            self._asset_overview_cache = {}
        return self._asset_overview_cache

    async def get_accounts(self) -> List[Dict[str, Any]]:
        overview = await self._load_asset_overview(force=True)
        result = overview.get("result") if isinstance(overview, dict) else {}
        rows = list((result or {}).get("list") or []) if isinstance(result, dict) else []

        found: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            acc_type = str(row.get("accountType") or "").strip().upper()
            if acc_type in {_ACCOUNT_KIND_UNIFIED, _ACCOUNT_KIND_FUND}:
                found.add(acc_type)
            for cat in list(row.get("categories") or []):
                if not isinstance(cat, dict):
                    continue
                name = str(cat.get("category") or "").strip().lower()
                if "copy" in name:
                    found.add(_ACCOUNT_KIND_COPY)

        # Always expose the three account kinds (empty balances still syncable / hideable in UI).
        kinds = [_ACCOUNT_KIND_UNIFIED, _ACCOUNT_KIND_FUND, _ACCOUNT_KIND_COPY]
        if not found:
            # Fallback: at least UNIFIED exists if wallet-balance works.
            try:
                await self._http.get_wallet_balance(account_type="UNIFIED")
                found.add(_ACCOUNT_KIND_UNIFIED)
            except Exception:
                pass
            found.update(kinds)

        accounts: List[Dict[str, Any]] = []
        for kind in kinds:
            if kind not in found and kind != _ACCOUNT_KIND_UNIFIED:
                # Still include FUND/COPY so UI can show them even if overview omitted empty wallets.
                pass
            accounts.append(
                {
                    "id": self.make_account_id(kind),
                    "type": kind,
                    "name": _ACCOUNT_LABELS.get(kind, f"ByBit {kind}"),
                    "status": "OPEN",
                    "opened_date": None,
                    "closed_date": None,
                }
            )
        return accounts

    async def get_portfolio(self, account_id: str) -> Dict[str, Any]:
        kind = self.parse_account_kind(account_id)
        if kind == _ACCOUNT_KIND_FUND:
            return await self._portfolio_fund(account_id)
        if kind == _ACCOUNT_KIND_COPY:
            return await self._portfolio_copy(account_id)
        return await self._portfolio_unified(account_id)

    async def _portfolio_unified(self, account_id: str) -> Dict[str, Any]:
        data = await self._http.get_wallet_balance(account_type="UNIFIED")
        wallets = list((data.get("result") or {}).get("list") or [])
        wallet = wallets[0] if wallets else {}
        total_equity = self._safe_float(wallet.get("totalEquity"))
        free_funds = self._safe_float(wallet.get("totalAvailableBalance"))
        positions: list[dict[str, Any]] = []
        currency_total = 0.0
        futures_total = 0.0
        expected_yield = 0.0

        for coin_row in list(wallet.get("coin") or []):
            coin = str(coin_row.get("coin") or "").strip().upper()
            qty = self._safe_float(coin_row.get("walletBalance"))
            if not coin or qty <= 0 or coin not in _STABLE_WALLET_COINS:
                continue
            currency_total += qty
            positions.append(
                {
                    "figi": coin,
                    "ticker": coin,
                    "instrument_type": "currency",
                    "quantity": {"decimal": qty, "currency": coin},
                    "current_price": {"decimal": 1.0, "currency": coin},
                    "average_position_price": {"decimal": 1.0, "currency": coin},
                    "expected_yield": {"decimal": 0.0, "currency": coin},
                    "daily_yield": {"decimal": 0.0, "currency": coin},
                    "blocked": False,
                    "class_code": "BYBIT",
                    "position_uid": f"BYBIT:{coin}",
                    "instrument_uid": f"BYBIT:{coin}",
                }
            )

        category = self._instrument_category
        if category and category != "spot":
            try:
                pos_data = await self._http.get_positions(
                    category=category,
                    settle_coin="USDT",
                )
                rows = list((pos_data.get("result") or {}).get("list") or [])
                for row in rows:
                    symbol = str(row.get("symbol") or "").strip().upper()
                    size = self._safe_float(row.get("size"))
                    if not symbol or size <= 0:
                        continue
                    side = str(row.get("side") or "Buy").strip() or "Buy"
                    is_short = side.lower() in {"sell", "short"}
                    # Signed qty: long > 0, short < 0 (DB has no side column).
                    signed_qty = -size if is_short else size
                    mark = self._safe_float(row.get("markPrice"))
                    avg = self._safe_float(row.get("avgPrice"))
                    upnl = self._safe_float(row.get("unrealisedPnl"))
                    liq = self._safe_float(row.get("liqPrice"))
                    notional = size * (mark or avg)
                    futures_total += abs(notional)
                    expected_yield += upnl
                    positions.append(
                        {
                            "figi": symbol,
                            "ticker": symbol,
                            "instrument_type": "crypto_perpetual",
                            "quantity": {"decimal": signed_qty, "currency": "USDT"},
                            "side": side,
                            "current_price": {"decimal": mark or avg, "currency": "USDT"},
                            "average_position_price": {"decimal": avg, "currency": "USDT"},
                            "expected_yield": {"decimal": upnl, "currency": "USDT"},
                            "daily_yield": {"decimal": 0.0, "currency": "USDT"},
                            "liq_price": liq,
                            "mark_price": mark or avg,
                            "blocked": False,
                            "class_code": "BYBIT",
                            "position_uid": f"BYBIT:{symbol}:{side}",
                            "instrument_uid": f"BYBIT:{symbol}",
                        }
                    )
            except Exception as exc:
                logger.warning("ByBit position list failed: %s", exc)

        from app.modules.robots.trading.account_health import (
            extract_wallet_margin_health,
            min_liq_distance_pct,
        )

        margin_health = extract_wallet_margin_health(wallet if isinstance(wallet, dict) else {})
        margin_health["min_liq_distance_pct"] = min_liq_distance_pct(positions)

        out = self._canonical_portfolio(
            account_id=account_id,
            total=total_equity,
            currency="USDT",
            positions=positions,
            free_funds=free_funds,
            total_currencies=currency_total or None,
            total_futures=futures_total or None,
            expected_yield=expected_yield,
            wallet_balance=wallets,
        )
        out["margin_health"] = margin_health
        return out

    async def _portfolio_fund(self, account_id: str) -> Dict[str, Any]:
        data = await self._http.get_all_coins_balance(account_type="FUND")
        result = (data.get("result") or {}) if isinstance(data, dict) else {}
        balances = list(result.get("balance") or [])
        positions: list[dict[str, Any]] = []
        total = 0.0
        for row in balances:
            if not isinstance(row, dict):
                continue
            coin = str(row.get("coin") or "").strip().upper()
            qty = self._safe_float(row.get("walletBalance") or row.get("transferBalance"))
            if not coin or qty <= 0:
                continue
            # FUND balances are coin units; stables count 1:1 toward USDT total.
            usd = qty if coin in _STABLE_WALLET_COINS else 0.0
            total += usd
            positions.append(
                {
                    "figi": coin,
                    "ticker": coin,
                    "instrument_type": "currency",
                    "quantity": {"decimal": qty, "currency": coin},
                    "current_price": {"decimal": 1.0 if coin in _STABLE_WALLET_COINS else 0.0, "currency": coin},
                    "average_position_price": {"decimal": 1.0 if coin in _STABLE_WALLET_COINS else 0.0, "currency": coin},
                    "expected_yield": {"decimal": 0.0, "currency": coin},
                    "daily_yield": {"decimal": 0.0, "currency": coin},
                    "blocked": False,
                    "class_code": "BYBIT_FUND",
                    "position_uid": f"BYBIT:FUND:{coin}",
                    "instrument_uid": f"BYBIT:FUND:{coin}",
                }
            )
        # Prefer overview equity for FUND when available (better USD valuation).
        overview_equity = await self._overview_account_equity(_ACCOUNT_KIND_FUND)
        if overview_equity is not None and overview_equity > 0:
            total = overview_equity
        return self._canonical_portfolio(
            account_id=account_id,
            total=total,
            currency="USDT",
            positions=positions,
            free_funds=total,
            total_currencies=total or None,
        )

    async def _portfolio_copy(self, account_id: str) -> Dict[str, Any]:
        overview = await self._load_asset_overview()
        result = overview.get("result") if isinstance(overview, dict) else {}
        rows = list((result or {}).get("list") or []) if isinstance(result, dict) else []
        positions: list[dict[str, Any]] = []
        total = 0.0
        for row in rows:
            if not isinstance(row, dict):
                continue
            for cat in list(row.get("categories") or []):
                if not isinstance(cat, dict):
                    continue
                name = str(cat.get("category") or "").strip().lower()
                if "copy" not in name:
                    continue
                total = self._safe_float(cat.get("equity"))
                for coin_row in list(cat.get("coinDetail") or []):
                    if not isinstance(coin_row, dict):
                        continue
                    coin = str(coin_row.get("coin") or "").strip().upper()
                    qty = self._safe_float(coin_row.get("equity"))
                    if not coin or qty <= 0:
                        continue
                    positions.append(
                        {
                            "figi": coin,
                            "ticker": coin,
                            "instrument_type": "currency",
                            "quantity": {"decimal": qty, "currency": coin},
                            "current_price": {"decimal": 1.0, "currency": coin},
                            "average_position_price": {"decimal": 1.0, "currency": coin},
                            "expected_yield": {"decimal": 0.0, "currency": coin},
                            "daily_yield": {"decimal": 0.0, "currency": coin},
                            "blocked": False,
                            "class_code": "BYBIT_COPY",
                            "position_uid": f"BYBIT:COPY:{coin}",
                            "instrument_uid": f"BYBIT:COPY:{coin}",
                        }
                    )
        if total <= 0 and not positions:
            # Empty copy account — still return canonical zero portfolio.
            total = 0.0
        return self._canonical_portfolio(
            account_id=account_id,
            total=total,
            currency="USDT",
            positions=positions,
            free_funds=total,
            total_currencies=total or None,
        )

    async def _overview_account_equity(self, account_type: str) -> float | None:
        overview = await self._load_asset_overview()
        result = overview.get("result") if isinstance(overview, dict) else {}
        rows = list((result or {}).get("list") or []) if isinstance(result, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("accountType") or "").strip().upper() == account_type.upper():
                return self._safe_float(row.get("totalEquity"))
        return None

    @staticmethod
    def _canonical_portfolio(
        *,
        account_id: str,
        total: float,
        currency: str,
        positions: list[dict[str, Any]],
        free_funds: float = 0.0,
        total_currencies: float | None = None,
        total_futures: float | None = None,
        expected_yield: float = 0.0,
        wallet_balance: list | None = None,
    ) -> Dict[str, Any]:
        money = lambda v: {"decimal": float(v or 0), "currency": currency}
        return {
            "account_id": account_id,
            "wallet_balance": wallet_balance or [],
            "total_amount_portfolio": money(total),
            "total_amount_shares": None,
            "total_amount_bonds": None,
            "total_amount_etf": None,
            "total_amount_currencies": money(total_currencies) if total_currencies is not None else None,
            "total_amount_futures": money(total_futures) if total_futures is not None else None,
            "total_amount_options": None,
            "expected_yield": money(expected_yield),
            "daily_yield": money(0.0),
            "daily_yield_relative": money(0.0),
            "free_funds": float(free_funds or 0),
            "positions": positions,
        }

    async def get_free_funds(self, account_id: str) -> float:
        kind = self.parse_account_kind(account_id)
        if kind != _ACCOUNT_KIND_UNIFIED:
            portfolio = await self.get_portfolio(account_id)
            return float(portfolio.get("free_funds") or 0)
        data = await self._http.get_wallet_balance(account_type="UNIFIED")
        wallets = list((data.get("result") or {}).get("list") or [])
        if not wallets:
            return 0.0
        coins = wallets[0].get("coin") if isinstance(wallets[0], dict) else None
        if isinstance(coins, list):
            for c in coins:
                if str(c.get("coin") or "").upper() in ("USDT", "USDC"):
                    try:
                        return float(c.get("availableToWithdraw") or c.get("walletBalance") or 0)
                    except Exception:
                        continue
        try:
            return float(wallets[0].get("totalAvailableBalance") or 0)
        except Exception:
            return 0.0

    async def get_operations(
        self,
        account_id: str,
        from_dt: datetime,
        to_dt: datetime,
        *,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        kind = self.parse_account_kind(account_id)
        if kind == _ACCOUNT_KIND_UNIFIED:
            return await self._fetch_unified_transaction_ops(from_dt, to_dt, max_pages=max_pages)
        if kind == _ACCOUNT_KIND_FUND:
            return await self._fetch_fund_ops(from_dt, to_dt, max_pages=max_pages)
        return []

    async def _fetch_unified_transaction_ops(
        self,
        from_dt: datetime,
        to_dt: datetime,
        *,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        start = from_dt if from_dt.tzinfo else from_dt.replace(tzinfo=timezone.utc)
        end = to_dt if to_dt.tzinfo else to_dt.replace(tzinfo=timezone.utc)
        if end < start:
            return []

        ops: list[dict[str, Any]] = []
        pages_budget = max(1, int(max_pages or 10))
        window_ms = 7 * 24 * 3600 * 1000
        cursor_start = int(start.timestamp() * 1000)
        cursor_end = int(end.timestamp() * 1000)
        window_from = cursor_start

        while window_from <= cursor_end and pages_budget > 0:
            window_to = min(window_from + window_ms, cursor_end)
            page_cursor: str | None = None
            while pages_budget > 0:
                pages_budget -= 1
                resp = await self._http.get_transaction_log(
                    account_type="UNIFIED",
                    start_ms=window_from,
                    end_ms=window_to,
                    limit=50,
                    cursor=page_cursor,
                )
                result = (resp.get("result") or {}) if isinstance(resp, dict) else {}
                rows = list(result.get("list") or [])
                for row in rows:
                    mapped = self._map_transaction_log_row(row)
                    if mapped:
                        ops.append(mapped)
                page_cursor = result.get("nextPageCursor") or None
                if not page_cursor or not rows:
                    break
            window_from = window_to + 1

        return ops

    async def _fetch_fund_ops(
        self,
        from_dt: datetime,
        to_dt: datetime,
        *,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """FUND ledger: fundinghistory + inter-transfers involving FUND."""
        start = from_dt if from_dt.tzinfo else from_dt.replace(tzinfo=timezone.utc)
        end = to_dt if to_dt.tzinfo else to_dt.replace(tzinfo=timezone.utc)
        if end < start:
            return []

        pages_budget = max(1, int(max_pages or 10))
        half = max(1, pages_budget // 2)
        transfer_budget = half
        history_budget = pages_budget - half

        transfers = await self._fetch_fund_inter_transfers(start, end, max_pages=transfer_budget)
        history = await self._fetch_fund_history(start, end, max_pages=history_budget)

        by_id: dict[str, dict[str, Any]] = {}
        for row in transfers + history:
            op_id = str(row.get("id") or "").strip()
            if op_id:
                by_id[op_id] = row
        return sorted(by_id.values(), key=lambda o: str(o.get("date") or ""))

    async def _fetch_fund_inter_transfers(
        self,
        start: datetime,
        end: datetime,
        *,
        max_pages: int,
    ) -> List[Dict[str, Any]]:
        ops: list[dict[str, Any]] = []
        pages_budget = max(1, int(max_pages or 1))
        window_ms = 7 * 24 * 3600 * 1000
        cursor_start = int(start.timestamp() * 1000)
        cursor_end = int(end.timestamp() * 1000)
        window_from = cursor_start

        while window_from <= cursor_end and pages_budget > 0:
            window_to = min(window_from + window_ms, cursor_end)
            page_cursor: str | None = None
            while pages_budget > 0:
                pages_budget -= 1
                resp = await self._http.get_inter_transfer_list(
                    start_ms=window_from,
                    end_ms=window_to,
                    limit=50,
                    cursor=page_cursor,
                )
                result = (resp.get("result") or {}) if isinstance(resp, dict) else {}
                rows = list(result.get("list") or [])
                for row in rows:
                    mapped = self._map_inter_transfer_row(row)
                    if mapped:
                        ops.append(mapped)
                page_cursor = result.get("nextPageCursor") or None
                if not page_cursor or not rows:
                    break
            window_from = window_to + 1

        return ops

    async def _fetch_fund_history(
        self,
        start: datetime,
        end: datetime,
        *,
        max_pages: int,
    ) -> List[Dict[str, Any]]:
        ops: list[dict[str, Any]] = []
        pages_budget = max(1, int(max_pages or 1))
        window_s = 7 * 24 * 3600
        cursor_start = int(start.timestamp())
        cursor_end = int(end.timestamp())
        window_from = cursor_start

        while window_from <= cursor_end and pages_budget > 0:
            window_to = min(window_from + window_s, cursor_end)
            page_cursor: str | None = None
            while pages_budget > 0:
                pages_budget -= 1
                resp = await self._http.get_asset_funding_history(
                    create_time_from_s=window_from,
                    create_time_to_s=window_to,
                    limit=100,
                    cursor=page_cursor,
                )
                result = (resp.get("result") or {}) if isinstance(resp, dict) else {}
                rows = list(result.get("list") or [])
                for row in rows:
                    mapped = self._map_funding_history_row(row)
                    if mapped:
                        ops.append(mapped)
                page_cursor = result.get("nextPageCursor") or None
                if not page_cursor or not rows:
                    break
            window_from = window_to + 1

        return ops

    def _map_transaction_log_row(self, row: Any) -> Dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        op_id = str(row.get("id") or row.get("tradeId") or "").strip()
        if not op_id:
            return None
        ts_ms = self._safe_float(row.get("transactionTime"))
        if ts_ms > 0:
            dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            date_iso = dt.isoformat().replace("+00:00", "Z")
        else:
            date_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        currency = str(row.get("currency") or "USDT").upper()
        change = self._safe_float(row.get("change"))
        qty = self._safe_float(row.get("qty"))
        price = self._safe_float(row.get("tradePrice"))
        symbol = str(row.get("symbol") or "").strip().upper() or None
        tx_type = str(row.get("type") or "TRANSACTION").strip().upper()
        category = str(row.get("category") or "").strip().lower()

        return {
            "id": f"bybit:{op_id}",
            "date": date_iso,
            "figi": symbol,
            "instrumentType": category or "crypto",
            "instrumentUid": f"BYBIT:{symbol}" if symbol else None,
            "positionUid": None,
            "operationType": f"BYBIT_{tx_type}",
            "type": tx_type,
            "quantity": qty,
            "quantityRest": 0,
            "currency": currency,
            "payment": {"decimal": change, "currency": currency},
            "price": {"decimal": price, "currency": currency},
            "state": "OPERATION_STATE_EXECUTED",
            "parentOperationId": None,
            "trades": [],
            "assetUid": None,
            "childOperations": [],
        }

    def _map_inter_transfer_row(self, row: Any) -> Dict[str, Any] | None:
        """Map internal transfer involving FUND into canonical operation DTO."""
        if not isinstance(row, dict):
            return None
        from_acc = str(row.get("fromAccountType") or "").strip().upper()
        to_acc = str(row.get("toAccountType") or "").strip().upper()
        if _ACCOUNT_KIND_FUND not in {from_acc, to_acc}:
            return None
        status = str(row.get("status") or "").strip().upper()
        if status and status not in {"SUCCESS", "STATUS_SUCCESS", "OK"}:
            return None
        transfer_id = str(row.get("transferId") or "").strip()
        if not transfer_id:
            return None

        ts_ms = self._safe_float(row.get("timestamp"))
        if ts_ms > 0:
            dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            date_iso = dt.isoformat().replace("+00:00", "Z")
        else:
            date_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        coin = str(row.get("coin") or "USDT").upper()
        amount = abs(self._safe_float(row.get("amount")))
        # FUND perspective: inflow when destination is FUND, outflow when source is FUND.
        if to_acc == _ACCOUNT_KIND_FUND:
            signed = amount
            direction = "IN"
        else:
            signed = -amount
            direction = "OUT"
        peer = to_acc if direction == "OUT" else from_acc
        op_type = f"TRANSFER_{direction}_{peer}" if peer else f"TRANSFER_{direction}"

        return {
            "id": f"bybit:xfer:{transfer_id}",
            "date": date_iso,
            "figi": coin,
            "instrumentType": "crypto",
            "instrumentUid": f"BYBIT:FUND:{coin}",
            "positionUid": None,
            "operationType": f"BYBIT_{op_type}",
            "type": op_type,
            "quantity": amount,
            "quantityRest": 0,
            "currency": coin,
            "payment": {"decimal": signed, "currency": coin},
            "price": {"decimal": 0, "currency": coin},
            "state": "OPERATION_STATE_EXECUTED",
            "parentOperationId": None,
            "trades": [],
            "assetUid": None,
            "childOperations": [],
        }

    def _map_funding_history_row(self, row: Any) -> Dict[str, Any] | None:
        """Map /v5/asset/fundinghistory row into canonical operation DTO."""
        if not isinstance(row, dict):
            return None
        currency = str(row.get("currency") or "").strip().upper()
        if not currency:
            return None
        amount = abs(self._safe_float(row.get("txnAmt")))
        direction = str(row.get("ioDirection") or "").strip().upper()
        if direction == "O":
            signed = -amount
            dir_label = "OUT"
        else:
            signed = amount
            dir_label = "IN"

        busi = str(
            row.get("showBusiTypeEn")
            or row.get("showBusiType")
            or row.get("descriptionEn")
            or "FUND"
        ).strip()
        # Inter-account transfers come from query-inter-transfer-list; skip here to avoid doubles.
        busi_l = busi.lower()
        if "transfer" in busi_l:
            return None
        busi_key = "".join(ch if ch.isalnum() else "_" for ch in busi.upper()).strip("_") or "FUND"
        op_type = f"FUND_{dir_label}_{busi_key}"[:80]

        create_s = self._safe_float(row.get("createTime"))
        if create_s > 1e12:
            # Already ms
            ts = create_s / 1000.0
        elif create_s > 0:
            ts = create_s
        else:
            ts = 0.0
        if ts > 0:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            date_iso = dt.isoformat().replace("+00:00", "Z")
        else:
            date_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Stable id: time + currency + direction + amount + afterAmt
        after = str(row.get("afterAmt") or "")
        member = str(row.get("memberId") or "")
        op_id = f"fund:{member}:{int(create_s)}:{currency}:{direction}:{row.get('txnAmt')}:{after}"

        return {
            "id": f"bybit:{op_id}",
            "date": date_iso,
            "figi": currency,
            "instrumentType": "crypto",
            "instrumentUid": f"BYBIT:FUND:{currency}",
            "positionUid": None,
            "operationType": f"BYBIT_{op_type}",
            "type": op_type,
            "quantity": amount,
            "quantityRest": 0,
            "currency": currency,
            "payment": {"decimal": signed, "currency": currency},
            "price": {"decimal": 0, "currency": currency},
            "state": "OPERATION_STATE_EXECUTED",
            "parentOperationId": None,
            "trades": [],
            "assetUid": None,
            "childOperations": [],
        }

    @staticmethod
    def _safe_float(v: Any) -> float:
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    async def get_candles(self, figi: str, from_date: datetime, to_date: datetime, interval: str) -> List[Dict[str, Any]]:
        symbol = str(figi or "").upper()
        bybit_interval = self._normalize_interval(interval)
        data = await self._http.get_kline(
            category=self._instrument_category,
            symbol=symbol,
            interval=bybit_interval,
            start_ms=int(from_date.timestamp() * 1000),
            end_ms=int(to_date.timestamp() * 1000),
            limit=1000,
        )
        rows = list((data.get("result") or {}).get("list") or [])
        out: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 7:
                continue
            try:
                out.append(
                    {
                        "time": datetime.utcfromtimestamp(int(row[0]) / 1000).isoformat() + "Z",
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                        "turnover": float(row[6]),
                    }
                )
            except Exception:
                continue
        out.sort(key=lambda x: x["time"])
        return out

    async def set_leverage(self, figi: str, leverage: int | float) -> Dict[str, Any]:
        """Set isolated/cross leverage for symbol. No-op when leverage<=0 or spot."""
        symbol = str(figi or "").upper()
        lev = int(float(leverage or 0))
        if not symbol or lev <= 0:
            return {"skipped": True, "reason": "leverage_disabled"}
        if str(self._instrument_category or "").lower() == "spot":
            return {"skipped": True, "reason": "spot"}
        resp = await self._http.set_leverage(
            category=self._instrument_category,
            symbol=symbol,
            buy_leverage=lev,
            sell_leverage=lev,
        )
        return {"symbol": symbol, "leverage": lev, "raw": resp}

    async def post_order(
        self,
        figi: str,
        quantity: float | int,
        price: float,
        direction: str,
        account_id: str,
        *,
        reduce_only: bool = False,
        qty_round_up: bool = False,
    ) -> Dict[str, Any]:
        _ = account_id
        symbol = str(figi or "").upper()
        side = self._map_side(direction)
        px = float(price or 0.0)
        qty = await self._format_order_qty(
            symbol,
            quantity,
            round_up=bool(qty_round_up),
            price=px,
        )
        if not symbol or px <= 0 or float(qty) <= 0:
            raise ValueError("invalid order payload")
        resp = await self._http.create_order(
            category=self._instrument_category,
            symbol=symbol,
            side=side,
            order_type="Limit",
            qty=qty,
            price=str(px),
            time_in_force="GTC",
            reduce_only=bool(reduce_only),
        )
        result = (resp.get("result") or {}) if isinstance(resp, dict) else {}
        order_id = str(result.get("orderId") or "")
        if order_id:
            self._order_symbols[order_id] = symbol
        return {
            "orderId": result.get("orderId"),
            "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
            "raw": resp,
            "qty": qty,
            "price": px,
        }

    async def get_order_state(self, account_id: str, order_id: str) -> Dict[str, Any]:
        _ = account_id
        oid = str(order_id or "")
        row = await self._fetch_order_row(oid)
        if row.get("symbol"):
            self._order_symbols[oid] = str(row["symbol"]).upper()
        status = self._map_order_status(str(row.get("orderStatus") or "New"))
        return {
            "orderId": str(row.get("orderId") or oid),
            "executionReportStatus": status,
            "lotsExecuted": self._as_float(row.get("cumExecQty")),
            "lotsRequested": self._as_float(row.get("qty")),
            "executedOrderPrice": self._as_float(row.get("avgPrice")),
            "executedCommission": self._as_float(row.get("cumExecFee")),
            "symbol": row.get("symbol") or self._order_symbols.get(oid),
            "side": row.get("side"),
            "stages": [row] if row else [],
        }

    async def post_market_order(
        self,
        figi: str,
        quantity: float | int,
        direction: str,
        account_id: str,
    ) -> Dict[str, Any]:
        _ = account_id
        symbol = str(figi or "").upper()
        side = self._map_side(direction)
        qty = await self._format_order_qty(symbol, quantity)
        if not symbol or float(qty) <= 0:
            raise ValueError("invalid market order payload")
        resp = await self._http.create_order(
            category=self._instrument_category,
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
        )
        result = (resp.get("result") or {}) if isinstance(resp, dict) else {}
        order_id = str(result.get("orderId") or "")
        if order_id:
            self._order_symbols[order_id] = symbol
        return {
            "orderId": result.get("orderId"),
            "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
            "raw": resp,
        }

    async def get_orders(self, account_id: str) -> List[Dict[str, Any]]:
        # Linear/spot open orders live on UNIFIED only. FUND/COPY share the same
        # API key response — returning them for every kind duplicated portfolio_orders.
        if self.parse_account_kind(account_id) != _ACCOUNT_KIND_UNIFIED:
            return []
        settle = "USDT" if str(self._instrument_category or "").lower() == "linear" else None
        resp = await self._http.get_open_orders(
            category=self._instrument_category,
            settle_coin=settle,
        )
        rows = list(((resp.get("result") or {}).get("list") or [])) if isinstance(resp, dict) else []
        out: List[Dict[str, Any]] = []
        for row in rows:
            oid = str(row.get("orderId") or "")
            sym = str(row.get("symbol") or "").upper()
            if oid and sym:
                self._order_symbols[oid] = sym
            out.append(self._normalize_order_row(row))
        return out

    async def get_order_history(self, account_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        """Closed / filled / cancelled orders from ByBit history."""
        if self.parse_account_kind(account_id) != _ACCOUNT_KIND_UNIFIED:
            return []
        lim = max(1, min(int(limit or 50), 50))
        resp = await self._http.get_order_history(
            category=self._instrument_category,
            limit=lim,
        )
        rows = list(((resp.get("result") or {}).get("list") or [])) if isinstance(resp, dict) else []
        out: List[Dict[str, Any]] = []
        for row in rows:
            oid = str(row.get("orderId") or "")
            sym = str(row.get("symbol") or "").upper()
            if oid and sym:
                self._order_symbols[oid] = sym
            out.append(self._normalize_order_row(row))
        return out

    def _normalize_order_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        oid = str(row.get("orderId") or "")
        sym = str(row.get("symbol") or "").upper()
        status_raw = str(row.get("orderStatus") or "New")
        created_ms = row.get("createdTime") or row.get("updatedTime")
        created_at = None
        try:
            if created_ms is not None and str(created_ms).strip() != "":
                created_at = datetime.fromtimestamp(float(created_ms) / 1000.0, tz=timezone.utc).isoformat()
        except Exception:
            created_at = None
        return {
            "id": oid or f"{sym}:{row.get('orderLinkId') or ''}",
            "order_id": oid,
            "figi": sym,
            "symbol": sym,
            "side": str(row.get("side") or ""),
            "quantity": self._as_float(row.get("qty")),
            "filled_qty": self._as_float(row.get("cumExecQty")),
            "price": self._as_float(row.get("price")),
            "avg_price": self._as_float(row.get("avgPrice")),
            "status": status_raw,
            "executionReportStatus": self._map_order_status(status_raw),
            "order_type": str(row.get("orderType") or ""),
            "reduce_only": bool(row.get("reduceOnly")),
            "created_at": created_at,
        }

    async def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        oid = str(order_id or "")
        symbol = await self._resolve_order_symbol(account_id, oid)
        if not symbol:
            raise ValueError(f"cannot cancel order {oid}: symbol unknown (refusing BTCUSDT fallback)")
        resp = await self._http.cancel_order(
            category=self._instrument_category,
            symbol=symbol,
            order_id=oid,
        )
        result = (resp.get("result") or {}) if isinstance(resp, dict) else {}
        return {
            "orderId": result.get("orderId") or str(order_id or ""),
            "executionReportStatus": "EXECUTION_REPORT_STATUS_CANCELLED",
            "raw": resp,
        }

    async def connect_websocket(self, user_id: int) -> bool:
        try:
            await self._ws.connect()
            await self._ensure_ws_loop()
            return True
        except Exception:
            logger.exception("ByBit WS connect failed user=%s", user_id)
            return False

    async def subscribe_prices(
        self,
        user_id: int,
        figis: List[str],
        queue,
        candle_interval: Optional[str] = None,
    ) -> Dict[str, str]:
        if not await self.connect_websocket(user_id):
            return {str(f): "NO_CONNECTION" for f in figis}
        interval = self._normalize_interval(candle_interval)
        self._ws_interval = interval
        symbols = [str(f).upper() for f in figis if str(f or "").strip()]
        new_symbols: list[str] = []
        async with self._ws_lock:
            tracked = self._queue_to_symbols.setdefault(queue, set())
            for symbol in symbols:
                tracked.add(symbol)
                listeners = self._symbol_to_queues.setdefault(symbol, set())
                if not listeners and symbol not in self._subscribed_symbols:
                    new_symbols.append(symbol)
                listeners.add(queue)
        if new_symbols:
            await self._ws.subscribe_klines(symbols=new_symbols, interval=interval)
            self._subscribed_symbols.update(new_symbols)
        return {s: ("SUBSCRIBE_SENT" if s in new_symbols else "ALREADY_SUBSCRIBED") for s in symbols}

    async def unsubscribe_prices(self, user_id: int, figis: List[str], queue) -> None:
        symbols = [str(f).upper() for f in figis if str(f or "").strip()]
        async with self._ws_lock:
            tracked = self._queue_to_symbols.get(queue, set())
            for symbol in symbols:
                tracked.discard(symbol)
                listeners = self._symbol_to_queues.get(symbol)
                if listeners:
                    listeners.discard(queue)
                    if not listeners:
                        self._symbol_to_queues.pop(symbol, None)
                        self._subscribed_symbols.discard(symbol)
            if not tracked and queue in self._queue_to_symbols:
                self._queue_to_symbols.pop(queue, None)

    async def get_last_price(
        self,
        user_id: int,
        figi: str,
        *,
        force_refresh: bool = False,
    ) -> Optional[float]:
        _ = user_id
        symbol = str(figi or "").upper()
        cached = self._last_prices.get(symbol)
        if not force_refresh and cached is not None and cached > 0:
            return cached
        try:
            resp = await self._http.get_tickers(category=self._instrument_category, symbol=symbol)
            rows = list(((resp.get("result") or {}).get("list") or [])) if isinstance(resp, dict) else []
            if not rows:
                return cached if cached and cached > 0 else None
            row = rows[0] if isinstance(rows[0], dict) else {}
            price = self._as_float(row.get("lastPrice"))
            if price > 0:
                self._last_prices[symbol] = price
                return price
        except Exception:
            return cached if cached and cached > 0 else None
        return cached if cached and cached > 0 else None

    async def close_websocket(self, user_id: int, queue=None) -> None:
        if queue is None:
            await self._ws.close()
            self._subscribed_symbols.clear()
            self._symbol_to_queues.clear()
            self._queue_to_symbols.clear()
            if self._ws_task and not self._ws_task.done():
                self._ws_task.cancel()
                await asyncio.gather(self._ws_task, return_exceptions=True)
            self._ws_task = None
            return
        async with self._ws_lock:
            symbols = list(self._queue_to_symbols.get(queue, set()))
        if symbols:
            await self.unsubscribe_prices(user_id, symbols, queue)

    async def force_resubscribe_websocket(self, user_id: int) -> bool:
        if not self._symbol_to_queues:
            return False
        try:
            await self._ws.close()
            await self._ws.connect()
            await self._ensure_ws_loop()
            symbols = list(self._symbol_to_queues.keys())
            if symbols:
                await self._ws.subscribe_klines(symbols=symbols, interval=self._ws_interval)
                self._subscribed_symbols = set(symbols)
            return True
        except Exception:
            logger.exception("ByBit WS force resubscribe failed user=%s", user_id)
            return False

    async def close(self) -> None:
        await self.close_websocket(user_id=0, queue=None)
        await self._http.close()

    async def _ensure_ws_loop(self) -> None:
        if self._ws_task is None or self._ws_task.done():
            self._ws_task = asyncio.create_task(self._ws_receiver_loop())

    async def _ws_receiver_loop(self) -> None:
        while True:
            try:
                msg = await self._ws.recv_json(timeout_seconds=1.0)
                if not msg:
                    await asyncio.sleep(0)
                    continue
                events = parse_kline_event(msg)
                for ev in events:
                    self._last_prices[ev.symbol] = ev.close
                    listeners = list(self._symbol_to_queues.get(ev.symbol, set()))
                    if not listeners:
                        continue
                    # Always emit price so Stage2/session get ticks between candle closes.
                    price_payload = {
                        "type": "price",
                        "figi": ev.symbol,
                        "price": ev.close,
                    }
                    for q in listeners:
                        self._put_nowait_drop_oldest(q, price_payload)
                    if ev.confirm:
                        candle_payload = {
                            "type": "candle_closed",
                            "figi": ev.symbol,
                            "price": ev.close,
                            "candle": {
                                "time": datetime.utcfromtimestamp(ev.end_ms / 1000).isoformat() + "Z",
                                "open": ev.open,
                                "high": ev.high,
                                "low": ev.low,
                                "close": ev.close,
                                "volume": ev.volume,
                                "isComplete": True,
                            },
                        }
                        for q in listeners:
                            self._put_nowait_drop_oldest(q, candle_payload)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("ByBit WS receiver loop error")
                await asyncio.sleep(1)

    @staticmethod
    def _put_nowait_drop_oldest(queue: asyncio.Queue, item: Dict[str, Any]) -> None:
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            pass
        try:
            queue.get_nowait()
        except Exception:
            pass
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    @staticmethod
    def _normalize_interval(interval: Optional[str]) -> str:
        return _INTERVAL_TO_BYBIT.get(str(interval or "5").upper(), "5")


    async def _fetch_order_row(self, order_id: str) -> dict[str, Any]:
        oid = str(order_id or "")
        if not oid:
            return {}
        open_resp = await self._http.get_open_orders(
            category=self._instrument_category,
            order_id=oid,
        )
        open_rows = list(((open_resp.get("result") or {}).get("list") or [])) if isinstance(open_resp, dict) else []
        if open_rows:
            return open_rows[0] if isinstance(open_rows[0], dict) else {}
        # Filled/cancelled orders leave realtime — fall back to history.
        get_hist = getattr(self._http, "get_order_history", None)
        if get_hist is None:
            return {}
        hist_resp = await get_hist(
            category=self._instrument_category,
            order_id=oid,
            limit=1,
        )
        hist_rows = list(((hist_resp.get("result") or {}).get("list") or [])) if isinstance(hist_resp, dict) else []
        if hist_rows and isinstance(hist_rows[0], dict):
            return hist_rows[0]
        return {}

    async def _resolve_order_symbol(self, account_id: str, order_id: str) -> str:
        _ = account_id
        oid = str(order_id or "")
        cached = str(self._order_symbols.get(oid) or "").upper()
        if cached:
            return cached
        row = await self._fetch_order_row(oid)
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            self._order_symbols[oid] = symbol
        return symbol

    async def _lot_filter_for(self, symbol: str) -> dict[str, float]:
        sym = str(symbol or "").upper()
        if sym in self._lot_filters:
            return self._lot_filters[sym]
        qty_step = 0.001
        min_qty = 0.001
        # Linear USDT perps typically require minOrderAmt >= 5.
        min_order_amt = 5.0 if self._instrument_category == "linear" else 0.0
        try:
            resp = await self._http.get_instruments_info(
                category=self._instrument_category,
                symbol=sym,
                limit=1,
            )
            rows = list(((resp.get("result") or {}).get("list") or [])) if isinstance(resp, dict) else []
            row = rows[0] if rows and isinstance(rows[0], dict) else {}
            lot = row.get("lotSizeFilter") if isinstance(row.get("lotSizeFilter"), dict) else {}
            qty_step = self._as_float(lot.get("qtyStep")) or qty_step
            min_qty = self._as_float(lot.get("minOrderQty")) or min_qty
            amt = self._as_float(lot.get("minOrderAmt") or lot.get("minNotionalValue"))
            if amt > 0:
                min_order_amt = amt
        except Exception:
            logger.debug("ByBit instruments-info unavailable for %s; using defaults", sym, exc_info=True)
        filt = {
            "qty_step": max(qty_step, 1e-12),
            "min_qty": max(min_qty, 0.0),
            "min_order_amt": max(min_order_amt, 0.0),
        }
        if sym:
            self._lot_filters[sym] = filt
        return filt

    async def _format_order_qty(
        self,
        symbol: str,
        quantity: float | int,
        *,
        round_up: bool = False,
        price: float | None = None,
    ) -> str:
        raw = float(quantity or 0.0)
        if raw <= 0:
            return "0"
        filt = await self._lot_filter_for(symbol)
        step = float(filt["qty_step"])
        min_qty = float(filt["min_qty"])
        min_amt = float(filt.get("min_order_amt") or 0.0)
        if round_up:
            steps = math.ceil((raw / step) - 1e-12)
        else:
            steps = math.floor((raw / step) + 1e-12)
        qty = max(0.0, steps * step)
        if qty + 1e-12 < min_qty:
            if round_up or min_qty > 0:
                # Bump to min lot when sizing up (notional path); else reject as before.
                if round_up:
                    qty = math.ceil((min_qty / step) - 1e-12) * step
                else:
                    return "0"
            else:
                return "0"
        px = float(price or 0.0)
        if round_up and px > 0 and min_amt > 0:
            # Ensure qty * price meets ByBit minOrderAmt after step rounding.
            guard = 0
            while qty * px + 1e-12 < min_amt and guard < 10_000:
                qty += step
                guard += 1
        return self._qty_to_str(qty, step)

    @staticmethod
    def _qty_to_str(qty: float, step: float) -> str:
        from decimal import Decimal, ROUND_DOWN
        try:
            d_step = Decimal(str(step))
            q = Decimal(str(qty)).quantize(d_step, rounding=ROUND_DOWN)
            text = format(q, "f")
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return text or "0"
        except Exception:
            text = f"{qty:.12f}".rstrip("0").rstrip(".")
            return text or "0"

    @staticmethod
    def _map_side(direction: str) -> str:
        d = str(direction or "").upper()
        return "Buy" if "BUY" in d else "Sell"

    @staticmethod
    def _map_order_status(raw: str) -> str:
        value = str(raw or "").strip().lower()
        if value in {"new", "created"}:
            return "EXECUTION_REPORT_STATUS_NEW"
        if value in {"partiallyfilled", "partially_filled"}:
            return "EXECUTION_REPORT_STATUS_PARTIALLYFILL"
        if value in {"filled", "filledfull"}:
            return "EXECUTION_REPORT_STATUS_FILL"
        if value in {"cancelled", "canceled"}:
            return "EXECUTION_REPORT_STATUS_CANCELLED"
        if value in {"rejected"}:
            return "EXECUTION_REPORT_STATUS_REJECTED"
        return "EXECUTION_REPORT_STATUS_NEW"

    @staticmethod
    def _as_int(v: Any) -> int:
        try:
            return int(float(v or 0))
        except Exception:
            return 0

    @staticmethod
    def _as_float(v: Any) -> float:
        try:
            return float(v or 0)
        except Exception:
            return 0.0
