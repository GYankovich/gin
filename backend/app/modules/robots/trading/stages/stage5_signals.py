"""
Stage 5: Генерация сигналов на основе стратегий из модуля strategies
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStagesStage5Signals [1]
#/// Исходный модуль `backend/app/modules/robots/trading/stages/stage5_signals.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Dict, List, Optional

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.indicators.service import indicator_service
from app.modules.robots.trading.strategies import get_strategy_class
from app.modules.robots.trading.costs import calculate_position_size
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Stage5Signals:
    """
    Генерация сигналов с использованием стратегий из модуля strategies
    """

    def __init__(self, broker: BrokerFacade, log_func=None):
        """
        Args:
            broker: Брокерский фасад
            log_func: Функция для логирования
        """
        self.broker = broker
        self.log_func = log_func

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE5] {message}")
        else:
            logger.info(f"[STAGE5] {message}")

    async def generate_signals(
            self,
            figis: List[str],
            strategy_name: str,
            strategy_params: Dict,
            risk_params: Dict,
            portfolio_value: float,
            free_funds: float,
            open_positions: List[Dict],
            account_positions: Optional[Dict[str, float]] = None,
            robot_id: Optional[int] = None,
            current_prices: Optional[Dict[str, float]] = None,
            log_api_call_func=None,
            token_id: int = None,
            user_id: int = None
    ) -> List[Dict]:
        """
        Генерирует сигналы на основе стратегии
        """
        self._write_log("🎯 Генерация сигналов")
        self._write_log(f"   Стратегия: {strategy_name}")
        self._write_log(f"   FIGIs: {figis}")
        self._write_log(f"   Открытые позиции: {len(open_positions)}")

        signals = []
        skip_summary: Dict[str, str] = {}
        create_summary: Dict[str, str] = {}
        holdings = {str(k or "").upper(): float(v or 0.0) for k, v in (account_positions or {}).items()}
        remaining_funds = float(free_funds or 0.0)

        try:
            # Получаем класс стратегии
            strategy_class = get_strategy_class(strategy_name)
            strategy = strategy_class(None, {**strategy_params, "figis": figis})

            # Получаем свечи для всех FIGI
            candles_data = await self._get_candles_for_strategy(
                figis,
                strategy_params,
                robot_id=robot_id,
                log_api_call_func=log_api_call_func,
            )

            # Генерируем сигналы через стратегию
            raw_signals = await strategy.generate_signals(candles_data)
            strategy_skip_reasons = dict(getattr(strategy, "skip_reasons", {}) or {})

            # Конвертируем сигналы в формат для Stage6
            for figi in figis:
                candle_count = len(candles_data.get(figi, []) or [])
                self._write_log(f"\n   📊 Анализ {figi} (свечей={candle_count}):")

                # Получаем текущую цену
                price_source = "ws"
                current_price = current_prices.get(figi) if current_prices else None
                if not current_price and current_prices:
                    # case-insensitive fallback
                    current_price = current_prices.get(str(figi).upper()) or current_prices.get(str(figi).lower())
                if not current_price:
                    candles = candles_data.get(figi, [])
                    if candles:
                        last_candle = candles[-1]
                        current_price = self._parse_candle_price(last_candle.get("close"))
                        if current_price:
                            price_source = "candle"
                            self._write_log(f"      📊 Цена из свечи: {current_price:.6f}")

                if not current_price:
                    # REST fallback (ByBit ticker / T-Invest last price) when WS not yet warm.
                    if user_id is not None and hasattr(self.broker, "get_last_price"):
                        try:
                            rest_px = await self.broker.get_last_price(user_id, figi)
                            if rest_px and float(rest_px) > 0:
                                current_price = float(rest_px)
                                price_source = "rest"
                                self._write_log(f"      📊 Цена из REST: {current_price:.6f}")
                        except Exception as e:
                            self._write_log(f"      ⚠️ REST price failed: {e}")

                if not current_price:
                    if candle_count <= 0:
                        reason = "NO_CANDLES_AND_NO_PRICE"
                    else:
                        reason = "NO_CURRENT_PRICE"
                    skip_summary[figi] = reason
                    self._write_log(f"      ⏭️ Пропуск: {reason} (свечей={candle_count})")
                    continue

                signal = raw_signals.get(figi)
                has_asset = holdings.get(str(figi).upper(), 0.0) > 0
                held_qty = float(holdings.get(str(figi).upper(), 0.0) or 0.0)
                sell_only_if_has_asset = bool(strategy_params.get("sell_only_if_has_asset", True))

                effective_signal = signal
                downgrade_reason: Optional[str] = None
                if effective_signal == "SELL" and sell_only_if_has_asset and not has_asset:
                    downgrade_reason = "SELL_DOWNGRADED_NO_ASSET"
                    effective_signal = None

                self._write_log(
                    f"      🔎 raw={signal or 'NONE'} effective={effective_signal or 'NONE'} "
                    f"price={float(current_price):.6f} src={price_source} "
                    f"has_asset={has_asset} held_qty={held_qty:.6f}"
                )
                strat_why = strategy_skip_reasons.get(figi)
                if strat_why and not effective_signal:
                    self._write_log(f"      📌 strategy_reason: {strat_why}")

                if effective_signal:
                    if effective_signal == "SELL" and not has_asset:
                        reason = "SELL_NO_ASSET_SHORT_FORBIDDEN"
                        skip_summary[figi] = reason
                        self._write_log(f"      ⏭️ Пропуск SELL: {reason}")
                        continue
                    max_position_percent = risk_params.get("max_position_percent", 10)
                    max_position_rub = risk_params.get("max_position_rub")
                    existing_position_value = held_qty * float(current_price)

                    if effective_signal == "SELL":
                        # Close/reduce from broker holdings, not BUY-style % sizing.
                        allow_short = bool(risk_params.get("allow_short", False))
                        if has_asset:
                            quantity = float(held_qty) if held_qty > 0 else 0.0
                        elif allow_short:
                            quantity = calculate_position_size(
                                portfolio_value=portfolio_value,
                                current_price=current_price,
                                max_position_percent=max_position_percent,
                                max_position_rub=max_position_rub,
                                free_funds=remaining_funds,
                                existing_position_value=0.0,
                            )
                        else:
                            quantity = 0
                    else:
                        # BUY: cap coin notional vs total broker portfolio equity.
                        quantity = calculate_position_size(
                            portfolio_value=portfolio_value,
                            current_price=current_price,
                            max_position_percent=max_position_percent,
                            max_position_rub=max_position_rub,
                            free_funds=remaining_funds,
                            existing_position_value=existing_position_value,
                        )
                    self._write_log(
                        f"      🔎 sizing: qty={quantity} free_funds={remaining_funds:.2f} "
                        f"portfolio={float(portfolio_value or 0):.2f} "
                        f"existing_coin_value={existing_position_value:.2f} "
                        f"max_pos_pct={float(max_position_percent):.2f} max_pos_rub={max_position_rub}"
                    )

                    if quantity > 0:
                        indicators = self._calculate_indicators_for_figi(
                            strategy_name=strategy_name,
                            candles=candles_data.get(figi, []),
                            strategy_params=strategy_params,
                        )
                        target_price = self._calculate_target_price(
                            signal=effective_signal,
                            current_price=current_price,
                            risk_params=risk_params,
                        )
                        if effective_signal == "BUY":
                            gross_return = float(risk_params.get("take_profit_percent", 3)) / 100.0
                            broker_commission = float(risk_params.get("broker_commission", 0.0005))
                            exchange_fee = float(risk_params.get("exchange_fee", 0.0001))
                            slippage = float(risk_params.get("slippage_bps", 0.0)) / 10000.0
                            ndfl = float(risk_params.get("ndfl", 0.13))
                            net_return = gross_return - broker_commission - exchange_fee - slippage - (ndfl * max(gross_return, 0))
                            self._write_log(
                                "      🔎 buy_economics: "
                                f"gross={gross_return:.4f} commission={broker_commission:.4f} "
                                f"exchange_fee={exchange_fee:.4f} slippage={slippage:.4f} "
                                f"ndfl={ndfl:.4f} net={net_return:.4f}"
                            )
                            if net_return <= 0:
                                reason = f"BUY_UNPROFITABLE net_return={net_return:.4f}"
                                skip_summary[figi] = reason
                                self._write_log(f"      ⏭️ Пропуск BUY: {reason}")
                                continue

                        create_reason = (
                            f"{effective_signal} qty={quantity} @ {float(current_price):.6f} "
                            f"src={price_source} candles={candle_count}"
                        )
                        if strat_why:
                            create_reason = f"{create_reason}; strategy={strat_why}"
                        signals.append({
                            "figi": figi,
                            "signal": effective_signal,
                            "price": current_price,
                            "target_price": target_price,
                            "indicators": indicators,
                            "quantity": quantity,
                            "strategy": strategy_name,
                            "strength": 100,
                            "create_reason": create_reason,
                        })
                        create_summary[figi] = create_reason
                        remaining_funds = max(0.0, remaining_funds - (quantity * current_price))
                        self._write_log(f"      ✅ Создан сигнал: {create_reason}")
                    else:
                        reason = (
                            "INSUFFICIENT_FUNDS_OR_SIZE_ZERO"
                            if effective_signal == "BUY"
                            else "SELL_QTY_ZERO"
                        )
                        skip_summary[figi] = reason
                        self._write_log(
                            f"      ⏭️ Пропуск: {reason} "
                            f"(free_funds={remaining_funds:.2f}, held_qty={held_qty:.6f})"
                        )
                else:
                    reason = (
                        downgrade_reason
                        or strategy_skip_reasons.get(figi)
                        or ("STRATEGY_NO_SIGNAL" if not signal else "SIGNAL_FILTERED")
                    )
                    skip_summary[figi] = reason
                    self._write_log(f"      ⏭️ Сигнал не создан: {reason}")

        except ValueError as e:
            self._write_log(f"   ❌ Неизвестная стратегия: {e}")
        except Exception as e:
            self._write_log(f"   ❌ Ошибка генерации сигналов: {e}")
            import traceback
            self._write_log(traceback.format_exc())

        self._write_log(f"\n   Итого сигналов: {len(signals)}")
        if create_summary:
            self._write_log(
                f"   Созданы: {len(create_summary)} — "
                + "; ".join(f"{sym}: {why}" for sym, why in create_summary.items())
            )
        if skip_summary:
            # Group identical reasons for readability
            by_reason: Dict[str, List[str]] = {}
            for sym, why in skip_summary.items():
                by_reason.setdefault(str(why), []).append(sym)
            parts = [
                f"{why} ×{len(syms)} [{', '.join(syms[:8])}{'…' if len(syms) > 8 else ''}]"
                for why, syms in by_reason.items()
            ]
            self._write_log(f"   Без сигнала: {len(skip_summary)} — " + "; ".join(parts))
        return signals

    def _extract_closes(self, candles: List[Dict]) -> List[float]:
        closes: List[float] = []
        for c in candles:
            parsed = self._parse_candle_price(c.get("close"))
            if parsed is not None:
                closes.append(parsed)
        return closes

    def _calculate_indicators_for_figi(self, strategy_name: str, candles: List[Dict], strategy_params: Dict) -> Dict[str, float]:
        # Для grain_seed детальные индикаторы рассчитываются внутри стратегии.
        closes = self._extract_closes(candles)
        if len(closes) < 3:
            return {}
        return {
            "last_close": round(closes[-1], 6),
            "prev_close": round(closes[-2], 6),
        }

    def _calculate_target_price(self, signal: str, current_price: float, risk_params: Dict) -> float:
        take_profit_pct = float(risk_params.get("take_profit_percent", 3.0))
        if signal == "BUY":
            return round(current_price * (1 + take_profit_pct / 100.0), 6)
        if signal == "SELL":
            return round(current_price * (1 - take_profit_pct / 100.0), 6)
        return round(current_price, 6)

    async def _get_candles_for_strategy(
            self,
            figis: List[str],
            strategy_params: Dict,
            robot_id: Optional[int] = None,
            log_api_call_func=None,
    ) -> Dict[str, List[Dict]]:
        """
        Получает свечи для всех FIGI с кэшированием

        Параметры свечей берутся ИСКЛЮЧИТЕЛЬНО из strategy_params
        """
        # Обязательные параметры — если нет, ошибка
        interval = strategy_params.get("interval")
        if not interval:
            raise ValueError("strategy_params.interval is required")

        days = strategy_params.get("candle_days", 60)

        self._write_log(f"   📊 Получение индикаторных данных из кэша (интервал={interval}, дней={days})")
        return await indicator_service.get_candles_batch(
            self.broker,
            figis,
            strategy_params,
            robot_id=robot_id,
            api_log_func=log_api_call_func,
        )

    def _parse_candle_price(self, price_data) -> Optional[float]:
        """Парсит цену из свечи (T-Invest quotation или float ByBit)."""
        if price_data is None:
            return None
        if isinstance(price_data, (int, float)):
            v = float(price_data)
            return v if v > 0 else None
        if isinstance(price_data, str):
            try:
                v = float(price_data)
                return v if v > 0 else None
            except (TypeError, ValueError):
                return None
        if not isinstance(price_data, dict):
            return None

        units = price_data.get("units", 0)
        nano = price_data.get("nano", 0)

        try:
            units = int(units) if units else 0
            nano = int(nano) if nano else 0
        except (TypeError, ValueError):
            return None

        v = units + nano / 1e9
        return v if v > 0 else None

