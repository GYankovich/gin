"""
Расчет комиссий, налогов и точки безубыточности.
Ставки по умолчанию — из settings.robots; робот может переопределить в config.costs.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingCosts [1]
#/// Исходный модуль `backend/app/modules/robots/trading/costs.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Any, Dict, Optional
from decimal import Decimal, ROUND_HALF_UP


def resolve_robot_cost_rates(robot_config: Optional[Dict[str, Any]]) -> tuple[float, float]:
    """
    Комиссия и НДФЛ: сначала config.costs робота, иначе settings.robots.
    Возвращает (broker_commission_rate, ndfl_rate) как доли (0.0005 = 0.05%).
    """
    from app.core.config import settings

    base_br = float(settings.robots.broker_commission_rate)
    base_tx = float(settings.robots.ndfl_rate)
    cfg = (robot_config or {}).get("costs") or {}
    if not isinstance(cfg, dict):
        return base_br, base_tx
    broker_type = str((robot_config or {}).get("broker_type") or "tinvest").strip().lower()
    if broker_type == "bybit":
        maker = cfg.get("maker_fee_rate")
        taker = cfg.get("taker_fee_rate")
        # Для старых путей (одна ставка) используем taker как более консервативную.
        out_br = float(taker if taker is not None else maker if maker is not None else base_br)
        # Crypto backtest/live: налог не применяется, если явно не задан ndfl_rate.
        out_tx = float(cfg["ndfl_rate"]) if cfg.get("ndfl_rate") is not None else 0.0
        return out_br, out_tx
    br = cfg.get("broker_commission_rate")
    tx = cfg.get("ndfl_rate")
    out_br = float(br) if br is not None else base_br
    out_tx = float(tx) if tx is not None else base_tx
    return out_br, out_tx


def resolve_crypto_fee_rates(robot_config: Optional[Dict[str, Any]]) -> tuple[float, float]:
    """
    Возвращает maker/taker rate для crypto path.
    Если указана только одна из ставок — вторая наследуется от неё.
    """
    cfg = (robot_config or {}).get("costs") or {}
    if not isinstance(cfg, dict):
        return 0.0001, 0.0006
    maker = cfg.get("maker_fee_rate")
    taker = cfg.get("taker_fee_rate")
    if maker is None and taker is None:
        return 0.0001, 0.0006
    if maker is None:
        maker = taker
    if taker is None:
        taker = maker
    return float(maker), float(taker)


def resolve_backtest_sim_rates(robot_config: Optional[Dict[str, Any]]) -> tuple[float, float, float, float]:
    """
    Ставки для SimBacktestBrokerFacade: (commission_rate, maker_fee, taker_fee, ndfl_rate).
    Crypto (bybit): ndfl_rate=0 по умолчанию.
    """
    br, ndfl = resolve_robot_cost_rates(robot_config)
    broker_type = str((robot_config or {}).get("broker_type") or "tinvest").strip().lower()
    cfg = (robot_config or {}).get("costs") or {}
    if not isinstance(cfg, dict):
        cfg = {}
    if broker_type == "bybit":
        maker, taker = resolve_crypto_fee_rates(robot_config)
        return br, maker, taker, ndfl
    maker = float(cfg["maker_fee_rate"]) if cfg.get("maker_fee_rate") is not None else br
    taker = float(cfg["taker_fee_rate"]) if cfg.get("taker_fee_rate") is not None else br
    return br, maker, taker, ndfl


def resolve_backtest_execution(config: Optional[Dict[str, Any]]) -> str:
    """
    Order style for sim backtest:
      - limit_maker: post_order (maker fee)
      - market_taker: post_market_order (taker fee)
    """
    cfg = (config or {}).get("costs") or {}
    if isinstance(cfg, dict) and cfg.get("backtest_execution"):
        return str(cfg["backtest_execution"]).strip().lower()
    broker = str((config or {}).get("broker_type") or "tinvest").strip().lower()
    if broker == "bybit":
        return "market_taker"
    return "limit_maker"


def resolve_backtest_fee_model(config: Optional[Dict[str, Any]]) -> str:
    """maker_taker | taker_only | maker_only — override fee on both order types."""
    cfg = (config or {}).get("costs") or {}
    if isinstance(cfg, dict) and cfg.get("backtest_fee_model"):
        return str(cfg["backtest_fee_model"]).strip().lower()
    return "maker_taker"


def annualization_days_for_broker(broker_type: Optional[str]) -> int:
    return 365 if str(broker_type or "").strip().lower() == "bybit" else 252


class TradingCosts:
    """
    Калькулятор торговых издержек
    """

    MONTHLY_FEE = 390.0

    # Обратная совместимость (значения по умолчанию совпадают с RobotsSettings)
    BROKER_COMMISSION = 0.0005
    TAX_RATE = 0.15

    def __init__(
            self,
            price: float,
            quantity: int,
            is_buy: bool = True,
            *,
            broker_commission_rate: Optional[float] = None,
            ndfl_rate: Optional[float] = None,
    ):
        """
        Args:
            price: Цена инструмента
            quantity: Количество лотов
            is_buy: True - покупка, False - продажа
            broker_commission_rate: доля от оборота; None — из settings.robots
            ndfl_rate: доля налога с прибыли; None — из settings.robots
        """
        from app.core.config import settings

        self.price = Decimal(str(price))
        self.quantity = Decimal(str(quantity))
        self.is_buy = is_buy
        self.broker_commission_rate = Decimal(str(
            broker_commission_rate if broker_commission_rate is not None
            else settings.robots.broker_commission_rate
        ))
        self.ndfl_rate = Decimal(str(
            ndfl_rate if ndfl_rate is not None else settings.robots.ndfl_rate
        ))

    def calculate_commission(self) -> float:
        """
        Рассчитывает комиссию брокера
        Комиссия взимается как при покупке, так и при продаже
        """
        amount = self.price * self.quantity
        commission = amount * self.broker_commission_rate
        return float(commission.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def calculate_tax(self, profit: float) -> float:
        """
        Рассчитывает налог с прибыли (только при продаже)

        Args:
            profit: Прибыль в рублях
        """
        if profit <= 0:
            return 0.0

        tax = Decimal(str(profit)) * self.ndfl_rate
        return float(tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def calculate_break_even_price(self) -> float:
        """
        Рассчитывает цену безубыточности для сделки
        """
        entry_price = self.price
        commission_rate = self.broker_commission_rate
        numerator = entry_price * (Decimal('1') + Decimal('2') * commission_rate)
        denominator = Decimal('1') - self.ndfl_rate

        break_even = numerator / denominator

        return float(break_even.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def calculate_min_profit_price(self, target_profit_percent: float) -> float:
        """
        Рассчитывает цену, при которой достигается целевая прибыль с учетом налогов и комиссий

        Args:
            target_profit_percent: Целевая прибыль в процентах (например, 3 = 3%)
        """
        entry_price = self.price
        commission_rate = self.broker_commission_rate
        tax_rate = self.ndfl_rate
        target = Decimal(str(target_profit_percent)) / Decimal('100')

        target_price = entry_price * (
                Decimal('1') +
                target / (Decimal('1') - tax_rate) +
                Decimal('2') * commission_rate
        )

        return float(target_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def calculate_actual_profit(self, exit_price: float) -> Dict[str, float]:
        """
        Рассчитывает фактическую прибыль с учетом всех издержек
        """
        entry_price = self.price
        quantity = self.quantity
        exit_price_dec = Decimal(str(exit_price))

        buy_amount = entry_price * quantity
        sell_amount = exit_price_dec * quantity

        commission_buy = buy_amount * self.broker_commission_rate
        commission_sell = sell_amount * self.broker_commission_rate
        total_commission = commission_buy + commission_sell

        gross_profit = sell_amount - buy_amount - total_commission

        tax = Decimal('0')
        if gross_profit > 0:
            tax = gross_profit * self.ndfl_rate

        net_profit = gross_profit - tax

        invested = buy_amount + commission_buy
        net_profit_percent = (net_profit / invested) * Decimal('100')

        return {
            "gross_profit": float(gross_profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "commission_buy": float(commission_buy.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "commission_sell": float(commission_sell.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "tax": float(tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "net_profit": float(net_profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "net_profit_percent": float(net_profit_percent.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        }


def calculate_position_size(
        portfolio_value: float,
        current_price: float,
        max_position_percent: float = 10.0,
        max_position_rub: float = None,
        free_funds: float = None,
        existing_position_value: float = 0.0,
) -> float:
    """Size a new BUY from broker portfolio equity (may be fractional for crypto).

    Caps:
    - max_position_percent of *total* portfolio_value for this instrument
      (remaining room after existing_position_value of the same coin)
    - optional absolute max_position_rub
    - free_funds

    Returns 0 when even one full price unit does not fit the remaining budget.
    Broker facades apply lot-step rounding (ByBit qtyStep / MOEX lots).
    """
    if current_price is None or float(current_price) <= 0:
        return 0.0
    price = float(current_price)
    equity = max(0.0, float(portfolio_value or 0.0))
    if free_funds is None:
        free_funds = equity
    cash = max(0.0, float(free_funds or 0.0))
    existing = max(0.0, float(existing_position_value or 0.0))

    max_by_percent = equity * (float(max_position_percent or 0.0) / 100.0)
    remaining_by_pct = max(0.0, max_by_percent - existing)
    max_by_rub = float(max_position_rub) if max_position_rub not in (None, "") else float("inf")
    max_amount = min(remaining_by_pct, max_by_rub, cash)

    if max_amount < price:
        # Still allow fractional crypto size when budget < 1 full coin.
        raw = max_amount / price
        return float(raw) if raw > 0 else 0.0
    return float(max_amount / price)


def calculate_stop_loss_price(
        entry_price: float,
        stop_loss_percent: float,
        is_long: bool = True
) -> float:
    """Рассчитывает цену стоп-лосса"""
    if is_long:
        return entry_price * (1 - stop_loss_percent / 100)
    else:
        return entry_price * (1 + stop_loss_percent / 100)


def calculate_take_profit_price(
        entry_price: float,
        take_profit_percent: float,
        is_long: bool = True,
        *,
        broker_commission_rate: Optional[float] = None,
        ndfl_rate: Optional[float] = None,
) -> float:
    """
    Рассчитывает цену тейк-профита с учетом комиссий и налогов
    """
    costs = TradingCosts(
        entry_price, 1, is_buy=is_long,
        broker_commission_rate=broker_commission_rate,
        ndfl_rate=ndfl_rate,
    )

    if is_long:
        return costs.calculate_min_profit_price(take_profit_percent)
    else:
        return entry_price * (1 - take_profit_percent / 100)
