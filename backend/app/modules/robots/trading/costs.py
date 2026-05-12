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
    br = cfg.get("broker_commission_rate")
    tx = cfg.get("ndfl_rate")
    out_br = float(br) if br is not None else base_br
    out_tx = float(tx) if tx is not None else base_tx
    return out_br, out_tx


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
        free_funds: float = None
) -> int:
    """
    Рассчитывает размер позиции в лотах
    """
    if free_funds is None:
        free_funds = portfolio_value
    max_by_percent = portfolio_value * (max_position_percent / 100)
    max_by_rub = max_position_rub if max_position_rub else float('inf')
    max_amount = min(max_by_percent, max_by_rub, free_funds)

    lots = int(max_amount / current_price)
    return max(1, lots)


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
