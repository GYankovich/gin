"""
Расчет комиссий, налогов и точки безубыточности
"""
from typing import Dict, Optional
from decimal import Decimal, ROUND_HALF_UP


class TradingCosts:
    """
    Калькулятор торговых издержек
    """

    # Комиссия брокера (в долях)
    BROKER_COMMISSION = 0.0005  # 0.05%

    # НДФЛ на прибыль (в долях)
    TAX_RATE = 0.15  # 15%

    # Ежемесячное обслуживание (руб)
    MONTHLY_FEE = 390.0

    def __init__(self, price: float, quantity: int, is_buy: bool = True):
        """
        Args:
            price: Цена инструмента
            quantity: Количество лотов
            is_buy: True - покупка, False - продажа
        """
        self.price = Decimal(str(price))
        self.quantity = Decimal(str(quantity))
        self.is_buy = is_buy

    def calculate_commission(self) -> float:
        """
        Рассчитывает комиссию брокера
        Комиссия взимается как при покупке, так и при продаже
        """
        amount = self.price * self.quantity
        commission = amount * Decimal(str(self.BROKER_COMMISSION))
        return float(commission.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def calculate_tax(self, profit: float) -> float:
        """
        Рассчитывает налог с прибыли (только при продаже)

        Args:
            profit: Прибыль в рублях
        """
        if profit <= 0:
            return 0.0

        tax = Decimal(str(profit)) * Decimal(str(self.TAX_RATE))
        return float(tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def calculate_break_even_price(self) -> float:
        """
        Рассчитывает цену безубыточности для сделки
        Учитывает:
        - Комиссию при покупке
        - Комиссию при продаже
        - Налог на прибыль (15% от чистой прибыли после комиссий)

        Формула:
        P_break = P_entry * (1 + 2*C) / (1 - T)
        где:
        P_entry - цена входа
        C - комиссия (0.05%)
        T - налог (15%)
        """
        entry_price = self.price

        # Комиссия при покупке и продаже
        commission_rate = Decimal(str(self.BROKER_COMMISSION))

        # Формула: entry * (1 + 2C) / (1 - T)
        numerator = entry_price * (Decimal('1') + Decimal('2') * commission_rate)
        denominator = Decimal('1') - Decimal(str(self.TAX_RATE))

        break_even = numerator / denominator

        return float(break_even.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def calculate_min_profit_price(self, target_profit_percent: float) -> float:
        """
        Рассчитывает цену, при которой достигается целевая прибыль с учетом налогов и комиссий

        Args:
            target_profit_percent: Целевая прибыль в процентах (например, 3 = 3%)
        """
        entry_price = self.price
        commission_rate = Decimal(str(self.BROKER_COMMISSION))
        tax_rate = Decimal(str(self.TAX_RATE))
        target = Decimal(str(target_profit_percent)) / Decimal('100')

        # Целевая цена с учетом комиссий и налога
        # (P_target - P_entry - 2*C*P_entry) * (1 - T) = target * P_entry
        # P_target = P_entry * (1 + target/(1-T) + 2C)

        target_price = entry_price * (
                Decimal('1') +
                target / (Decimal('1') - tax_rate) +
                Decimal('2') * commission_rate
        )

        return float(target_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def calculate_actual_profit(self, exit_price: float) -> Dict[str, float]:
        """
        Рассчитывает фактическую прибыль с учетом всех издержек

        Args:
            exit_price: Цена продажи

        Returns:
            Dict с ключами:
            - gross_profit: Валовая прибыль
            - commission_buy: Комиссия при покупке
            - commission_sell: Комиссия при продаже
            - tax: Налог
            - net_profit: Чистая прибыль
            - net_profit_percent: Чистая прибыль в процентах от вложений
        """
        entry_price = self.price
        quantity = self.quantity
        exit_price_dec = Decimal(str(exit_price))

        # Суммы
        buy_amount = entry_price * quantity
        sell_amount = exit_price_dec * quantity

        # Комиссии
        commission_buy = buy_amount * Decimal(str(self.BROKER_COMMISSION))
        commission_sell = sell_amount * Decimal(str(self.BROKER_COMMISSION))
        total_commission = commission_buy + commission_sell

        # Валовая прибыль
        gross_profit = sell_amount - buy_amount - total_commission

        # Налог (только на прибыль)
        tax = Decimal('0')
        if gross_profit > 0:
            tax = gross_profit * Decimal(str(self.TAX_RATE))

        # Чистая прибыль
        net_profit = gross_profit - tax

        # Процент от вложений (с учетом комиссии при покупке)
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

    Args:
        portfolio_value: Стоимость всего портфеля
        current_price: Текущая цена инструмента
        max_position_percent: Максимальный процент портфеля для одной позиции
        max_position_rub: Максимальная сумма в рублях для одной позиции
        free_funds: Доступные свободные средства

    Returns:
        Количество лотов для покупки
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
    """
    Рассчитывает цену стоп-лосса

    Args:
        entry_price: Цена входа
        stop_loss_percent: Процент стоп-лосса (например, 2 = 2%)
        is_long: True - длинная позиция, False - короткая

    Returns:
        Цена стоп-лосса
    """
    if is_long:
        return entry_price * (1 - stop_loss_percent / 100)
    else:
        return entry_price * (1 + stop_loss_percent / 100)


def calculate_take_profit_price(
        entry_price: float,
        take_profit_percent: float,
        is_long: bool = True
) -> float:
    """
    Рассчитывает цену тейк-профита с учетом комиссий и налогов

    Args:
        entry_price: Цена входа
        take_profit_percent: Целевая прибыль в процентах (например, 3 = 3%)
        is_long: True - длинная позиция, False - короткая

    Returns:
        Цена тейк-профита
    """
    costs = TradingCosts(entry_price, 1, is_buy=is_long)

    if is_long:
        return costs.calculate_min_profit_price(take_profit_percent)
    else:
        # Для короткой позиции формула аналогичная, но зеркальная
        return entry_price * (1 - take_profit_percent / 100)