"""
Параметры риск-менеджмента (единый источник правды).

См. docs/BRD-ARCH-03-unified-engine-architecture.md §7.

RiskParams — обобщает `GrainSeedRisk` из `robots/schemas.py` и добавляет поля,
которых там не было (max_concurrent_positions, stop_loss_mode, trailing_*,
max_daily_loss_pct в %). `GrainSeedRisk` сохраняется как обратно совместимый
alias на RiskParams (см. robots/schemas.py).
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingRiskParams [1]
#/// Исходный модуль `backend/app/modules/robots/trading/risk/params.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


StopLossMode = Literal["fixed", "trailing"]


class RiskParams(BaseModel):
    """Единые параметры риск-менеджмента (общие для всех стратегий)."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # --- размер позиции ---
    max_position_pct: float = Field(default=10.0, description="Максимум % портфеля на одну позицию")
    max_position_rub: float = Field(default=50_000.0, description="Максимум в рублях на одну позицию")
    min_trade_amount_rub: float = Field(
        default=500.0,
        description="Мин. нотионал сделки (₽ / USDT) — Stage6 MIN_TRADE_AMOUNT",
    )

    # --- лимиты по убытку ---
    max_daily_loss_pct: float = Field(default=1.0, description="Максимум дневного убытка в %")
    max_daily_loss_rub: float = Field(default=10_000.0, description="Максимум дневного убытка в рублях")
    max_drawdown_percent: Optional[float] = Field(default=20.0, description="Макс. просадка портфеля в % (0 = без лимита)")
    # Обратная совместимость c GrainSeedRisk:
    max_daily_loss: Optional[float] = Field(default=None, description="(legacy) то же, что max_daily_loss_rub")

    # --- концентрация ---
    max_concurrent_positions: int = Field(default=3, description="Макс. одновременных позиций")
    allow_short: bool = Field(default=False, description="Разрешать открытие short-позиций")
    max_leverage: float = Field(default=1.0, description="Макс. плечо относительно equity")

    # --- стопы и тейк ---
    stop_loss_mode: StopLossMode = Field(default="fixed", description="fixed или trailing")
    stop_loss_pct: float = Field(default=2.0, description="Фиксированный стоп в %")
    take_profit_pct: float = Field(default=3.0, description="Тейк в %")
    trailing_activation_pct: float = Field(default=0.5, description="При какой прибыли активируется трейлинг")
    trailing_step_pct: float = Field(default=0.2, description="Шаг трейлинга")
    # Soft TP guards (SL never delayed).
    min_hold_seconds: float = Field(default=120.0, description="Не закрывать по TP раньше N секунд после входа")
    min_tp_move_bps: float = Field(default=10.0, description="Мин. движение цены от entry в bps для TP")

    # --- издержки ---
    commission_pct: float = Field(default=0.05, description="Комиссия брокера в %")

    # --- серия убыточных дней ---
    day_loss_streak_limit: int = Field(default=3, description="Стоп после N убыточных дней подряд")

    # --- резерв средств ---
    free_funds_reserve_pct: float = Field(default=50.0, description="Резерв свободных средств в %")

    # --- время принудительного закрытия ---
    force_close_time: str = Field(default="18:45", description="МСК HH:MM — принудительное закрытие")

    # --- риск на сделку (для sizing по дистанции до стопа) ---
    risk_per_trade_pct: float = Field(default=2.0, description="Риск на сделку в % от капитала")

    # --- legacy-поля GrainSeedRisk (для обратной совместимости с конфигами роботов) ---
    stop_loss_percent: Optional[float] = Field(default=None, description="(legacy) то же, что stop_loss_pct")
    take_profit_percent: Optional[float] = Field(default=None, description="(legacy) то же, что take_profit_pct")
    max_position_percent: Optional[float] = Field(default=None, description="(legacy) то же, что max_position_pct")
    trading_hours_start: Optional[str] = Field(default="10:00 MSK", description="Начало торговой сессии")
    trading_hours_end: Optional[str] = Field(default="18:45 MSK", description="Конец торговой сессии")
    allowed_weekdays: Optional[int] = Field(default=31, description="Бит-маска допустимых дней недели")

    @field_validator("max_daily_loss_pct", "stop_loss_pct", "take_profit_pct", "max_position_pct",
                     "trailing_activation_pct", "trailing_step_pct", "commission_pct",
                     "free_funds_reserve_pct", "risk_per_trade_pct", "max_leverage",
                     "min_hold_seconds", "min_tp_move_bps")
    @classmethod
    def _non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("параметр риска должен быть >= 0")
        return v

    def normalize(self) -> "RiskParams":
        """Подтягивает legacy-поля в новые имена, если новые не заданы.

        Если в конфиге пришёл `stop_loss_percent`, но `stop_loss_pct` дефолтный —
        используем legacy-значение. Это критично для обратной совместимости с
        сохранёнными `GrainSeedConfig.risk` в роботах.
        """
        data = self.model_dump()
        # Алиасы (legacy -> новые)
        if data.get("stop_loss_percent") is not None and data.get("stop_loss_pct") == 2.0:
            data["stop_loss_pct"] = data["stop_loss_percent"]
        if data.get("take_profit_percent") is not None and data.get("take_profit_pct") == 3.0:
            data["take_profit_pct"] = data["take_profit_percent"]
        if data.get("max_position_percent") is not None and data.get("max_position_pct") == 10.0:
            data["max_position_pct"] = data["max_position_percent"]
        if data.get("max_daily_loss") is not None and data.get("max_daily_loss_rub") == 10_000.0:
            data["max_daily_loss_rub"] = data["max_daily_loss"]
        return RiskParams(**data)

    @classmethod
    def from_legacy_dict(cls, raw: Optional[Dict[str, Any]]) -> "RiskParams":
        """Безопасное построение из старого `risk_params` dict (любые поля)."""
        if not raw:
            return cls()
        try:
            return cls(**raw).normalize()
        except Exception:
            # Если в dict есть невалидные значения — пытаемся пропустить лишнее.
            allowed = set(cls.model_fields.keys())
            safe = {k: v for k, v in raw.items() if k in allowed}
            return cls(**safe).normalize()

    # --- удобные геттеры ---

    @property
    def effective_stop_loss_pct(self) -> float:
        return float(self.stop_loss_percent if self.stop_loss_percent is not None else self.stop_loss_pct)

    @property
    def effective_take_profit_pct(self) -> float:
        return float(self.take_profit_percent if self.take_profit_percent is not None else self.take_profit_pct)

    @property
    def effective_max_position_pct(self) -> float:
        return float(self.max_position_percent if self.max_position_percent is not None else self.max_position_pct)

    @property
    def effective_max_daily_loss_rub(self) -> float:
        return float(self.max_daily_loss if self.max_daily_loss is not None else self.max_daily_loss_rub)


__all__ = ["RiskParams", "StopLossMode"]
