"""
Единые контракты данных торгового ядра (backtest + live).

См. docs/BRD-ARCH-03-unified-engine-architecture.md §3.

Принципы:
- Hot-path структуры (Candle, Position) — `dataclass(slots=True)` для скорости.
- API/persist структуры (Signal, Order, Fill, MarketSnapshot) — Pydantic v2 BaseModel.
- Все типы должны сериализоваться JSON и роудтрипить без потерь.
- Совместимы с существующим dict-форматом T-Invest свечей (units/nano).
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingContracts [1]
#/// Исходный модуль `backend/app/modules/robots/trading/contracts.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Режим исполнения
# ---------------------------------------------------------------------------

class ExecutionMode(str, Enum):
    BACKTEST = "BACKTEST"
    LIVE = "LIVE"
    PAPER = "PAPER"


# ---------------------------------------------------------------------------
# Candle — hot-path тип
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Candle:
    """OHLCV-свеча.

    Поля `secid`/`figi` оба опциональны, чтобы поддерживать оба идентификатора
    (MOEX ticker для backtest, T-Invest figi для live).
    """
    interval: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    secid: Optional[str] = None
    figi: Optional[str] = None
    volume_rub: Optional[float] = None

    @classmethod
    def from_tinvest_dict(
        cls,
        candle: Dict[str, Any],
        *,
        interval: str = "",
        secid: Optional[str] = None,
        figi: Optional[str] = None,
    ) -> "Candle":
        """Парсит T-Invest-словарь (open/high/low/close как {units, nano}, time как ISO-строка или dict)."""
        def _price(field_name: str) -> float:
            q = candle.get(field_name) or {}
            if isinstance(q, (int, float)):
                return float(q)
            if isinstance(q, str):
                try:
                    return float(q)
                except (TypeError, ValueError):
                    return 0.0
            units = int(q.get("units", 0) or 0)
            nano = int(q.get("nano", 0) or 0)
            return float(units) + float(nano) / 1e9

        t = candle.get("time")
        if isinstance(t, datetime):
            dt = t
        elif isinstance(t, str):
            s = t.replace("Z", "+00:00") if t.endswith("Z") else t
            try:
                dt = datetime.fromisoformat(s)
            except ValueError:
                dt = datetime.fromtimestamp(0, tz=timezone.utc)
        elif isinstance(t, dict):
            sec = int(t.get("seconds", 0) or 0)
            dt = datetime.fromtimestamp(sec, tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(0, tz=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        vol_raw = candle.get("volume", 0)
        try:
            vol = int(vol_raw) if vol_raw is not None else 0
        except (TypeError, ValueError):
            vol = 0

        return cls(
            interval=str(interval or ""),
            time=dt,
            open=_price("open"),
            high=_price("high"),
            low=_price("low"),
            close=_price("close"),
            volume=vol,
            secid=secid,
            figi=figi,
        )

    @classmethod
    def from_moex_row(
        cls,
        row: Dict[str, Any],
        *,
        interval: str = "",
        secid: Optional[str] = None,
    ) -> "Candle":
        """Парсит ряд из `shared_market_candles` / DMS-формата."""
        t = row.get("candle_time") or row.get("bucket_start") or row.get("time")
        if isinstance(t, datetime):
            dt = t
        elif isinstance(t, str):
            try:
                s = t.replace("Z", "+00:00") if t.endswith("Z") else t
                dt = datetime.fromisoformat(s)
            except ValueError:
                dt = datetime.fromtimestamp(0, tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(0, tz=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        def _f(key: str) -> float:
            v = row.get(key)
            try:
                return float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        try:
            vol = int(row.get("volume", 0) or 0)
        except (TypeError, ValueError):
            vol = 0

        return cls(
            interval=str(interval or ""),
            time=dt,
            open=_f("open"),
            high=_f("high"),
            low=_f("low"),
            close=_f("close"),
            volume=vol,
            secid=secid,
            figi=None,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в JSON-совместимый dict."""
        return {
            "secid": self.secid,
            "figi": self.figi,
            "interval": self.interval,
            "time": self.time.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "volume_rub": self.volume_rub,
        }


# ---------------------------------------------------------------------------
# Snapshot — состояние рынка на момент времени
# ---------------------------------------------------------------------------

class SnapshotRow(BaseModel):
    """Строка снапшота по одному инструменту.

    Поля совместимы с тем, что отдаёт `DmsService._fetch_moex_board_snapshot`.
    Любое поле может быть None, если источник не предоставил его на момент `as_of`.
    """
    model_config = ConfigDict(extra="allow")

    secid: str
    figi: Optional[str] = None
    last_price: Optional[float] = None
    open: Optional[float] = None
    prev_close: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread_pct: Optional[float] = None
    volume_rub: Optional[float] = None
    volume_lots: Optional[float] = None
    num_trades: Optional[int] = None
    capitalization: Optional[float] = None
    gap_pct: Optional[float] = None
    atr_pct: Optional[float] = None
    security_status: Optional[str] = None
    trading_status: Optional[str] = None
    issue_size: Optional[float] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class MarketSnapshot(BaseModel):
    """Срез рынка на момент `as_of` (обычно — утро торгового дня D)."""
    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    trade_date: date
    board: str = "TQBR"
    rows: Dict[str, SnapshotRow] = Field(default_factory=dict)

    def get(self, secid: str) -> Optional[SnapshotRow]:
        return self.rows.get(secid.upper())

    def secids(self) -> List[str]:
        return list(self.rows.keys())


# ---------------------------------------------------------------------------
# Signal — намерение на вход / выход
# ---------------------------------------------------------------------------

SignalSide = Literal["BUY", "SELL", "CLOSE"]


class Signal(BaseModel):
    """Сигнал на вход/выход с метаданными.

    `side="CLOSE"` означает закрытие открытой позиции (направление берётся из
    позиции, чтобы стратегия не дублировала состояние портфеля).
    """
    model_config = ConfigDict(extra="allow")

    signal_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    secid: Optional[str] = None
    figi: Optional[str] = None
    side: SignalSide
    confidence: Optional[float] = None
    quantity_hint: Optional[int] = None
    price_at_signal: Optional[float] = None
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    take_price: Optional[float] = None
    reason: str = ""
    rule: Optional[str] = None
    strategy: Optional[str] = None
    bar_time: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# OrderIntent — единый intent до Execution (exits + entries)
# ---------------------------------------------------------------------------

OrderIntentKind = Literal["entry", "exit_sl_tp", "exit_strategy", "flatten"]


@dataclass(slots=True)
class OrderIntent:
    """Намерение выставить заявку. Place делает только Execution/Stage6."""

    kind: OrderIntentKind
    figi: str
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float
    reduce_only: bool = False
    reason: str = ""
    signal_id: Optional[Any] = None
    trade_id: Optional[int] = None
    estimated_profit: Optional[float] = None
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def intent_source(self) -> str:
        return self.kind

    def to_stage6_signal(self) -> Dict[str, Any]:
        """Dict shape expected by Stage6Orders.execute_signals / execute_intents."""
        payload = dict(self.meta or {})
        payload.update({
            "figi": self.figi,
            "signal": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "reduce_only": self.reduce_only,
            "intent_kind": self.kind,
            "intent_source": self.kind,
            "reason": self.reason,
            "order_type": self.order_type,
            "_signal_id": self.signal_id,
            "trade_id": self.trade_id,
            "estimated_profit": self.estimated_profit,
        })
        return payload

    @classmethod
    def from_strategy_signal(cls, signal: Dict[str, Any]) -> "OrderIntent":
        side = str(signal.get("signal") or "").upper()
        if side not in {"BUY", "SELL"}:
            side = "BUY"
        kind: OrderIntentKind = "exit_strategy" if side == "SELL" else "entry"
        # Explicit flag from Stage5 when closing/reducing holdings; never imply for shorts.
        reduce_only = bool(signal.get("reduce_only"))
        return cls(
            kind=kind,
            figi=str(signal.get("figi") or ""),
            side=side,  # type: ignore[arg-type]
            quantity=float(signal.get("quantity") or 0),
            price=float(signal.get("price") or 0),
            reduce_only=reduce_only,
            reason=str(signal.get("create_reason") or signal.get("reason") or ""),
            signal_id=signal.get("_signal_id") or signal.get("signal_id"),
            meta={k: v for k, v in signal.items() if k not in {
                "figi", "signal", "quantity", "price", "create_reason", "reason",
                "_signal_id", "signal_id", "reduce_only",
            }},
        )


# ---------------------------------------------------------------------------
# Order и Fill
# ---------------------------------------------------------------------------

OrderType = Literal["MARKET", "LIMIT"]
OrderStatus = Literal["NEW", "PARTIALLY_FILLED", "FILLED", "REJECTED", "CANCELLED"]


class Order(BaseModel):
    model_config = ConfigDict(extra="allow")

    order_id: UUID = Field(default_factory=uuid4)
    signal_id: Optional[UUID] = None
    secid: Optional[str] = None
    figi: Optional[str] = None
    side: Literal["BUY", "SELL"]
    type: OrderType = "LIMIT"
    price: Optional[float] = None
    quantity: int = 0
    tif: str = "DAY"
    status: OrderStatus = "NEW"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    broker_order_id: Optional[str] = None
    reject_reason: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class Fill(BaseModel):
    model_config = ConfigDict(extra="allow")

    order_id: UUID
    fill_price: float
    quantity: int
    commission: float = 0.0
    slippage: float = 0.0
    tax: float = 0.0
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Position — открытая позиция (hot-path)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Position:
    side: Literal["LONG", "SHORT"]
    quantity: int
    avg_entry_price: float
    secid: Optional[str] = None
    figi: Optional[str] = None
    current_price: float = 0.0
    peak_price: float = 0.0
    trough_price: float = 0.0
    opened_at: Optional[datetime] = None
    realized_pnl: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def unrealized_pnl(self) -> float:
        if self.quantity <= 0 or self.current_price <= 0 or self.avg_entry_price <= 0:
            return 0.0
        if self.side == "LONG":
            return (self.current_price - self.avg_entry_price) * self.quantity
        return (self.avg_entry_price - self.current_price) * self.quantity


# ---------------------------------------------------------------------------
# CostParams — стандартные издержки
# ---------------------------------------------------------------------------

class CostParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commission_pct: float = 0.05    # процент брокера (0.05 => 0.05%, не 5%)
    ndfl_rate: float = 0.13
    slippage_pct: float = 0.0


# ---------------------------------------------------------------------------
# Утилиты для интероперабельности с legacy-форматом
# ---------------------------------------------------------------------------

def candles_to_tinvest_dicts(candles: List[Candle]) -> List[Dict[str, Any]]:
    """Конвертирует список Candle обратно в T-Invest-словарь (для legacy-стратегий)."""
    out: List[Dict[str, Any]] = []
    for c in candles:
        def _to_q(v: float) -> Dict[str, int]:
            units = int(v)
            nano = int(round((v - units) * 1e9))
            return {"units": units, "nano": nano}
        out.append({
            "open": _to_q(c.open),
            "high": _to_q(c.high),
            "low": _to_q(c.low),
            "close": _to_q(c.close),
            "volume": int(c.volume),
            "time": c.time.isoformat() if isinstance(c.time, datetime) else str(c.time),
        })
    return out


def candles_from_tinvest_dicts(
    raw: List[Dict[str, Any]],
    *,
    interval: str = "",
    figi: Optional[str] = None,
    secid: Optional[str] = None,
) -> List[Candle]:
    """Парсит список T-Invest-словарей в Candle."""
    return [Candle.from_tinvest_dict(c, interval=interval, figi=figi, secid=secid) for c in raw or []]


__all__ = [
    "ExecutionMode",
    "Candle",
    "SnapshotRow",
    "MarketSnapshot",
    "Signal",
    "SignalSide",
    "OrderIntent",
    "OrderIntentKind",
    "Order",
    "OrderType",
    "OrderStatus",
    "Fill",
    "Position",
    "CostParams",
    "candles_to_tinvest_dicts",
    "candles_from_tinvest_dicts",
]
