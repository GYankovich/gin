"""
Stage 5: Генерация сигналов на основе стратегий из модуля strategies
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStagesStage5Signals [1]
#/// Исходный модуль `backend/app/modules/robots/trading/stages/stage5_signals.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Dict, List, Optional, Set

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.indicators.service import indicator_service
from app.modules.robots.trading.strategies import get_strategy_class
from app.modules.robots.trading.risk.manager import RiskManager
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
            user_id: int = None,
            pending_order_figis: Optional[Set[str]] = None,
    ) -> List[Dict]:
        """
        Генерирует сигналы на основе стратегии.
        В live-логи пишет только итоговый результат цикла Stage5.
        """
        signals = []
        skip_summary: Dict[str, str] = {}
        create_summary: Dict[str, str] = {}
        holdings = {str(k or "").upper(): float(v or 0.0) for k, v in (account_positions or {}).items()}
        remaining_funds = float(free_funds or 0.0)
        pending = {str(x or "").upper() for x in (pending_order_figis or set()) if str(x or "").strip()}

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
                figi_key = str(figi or "").upper()
                if figi_key in pending:
                    skip_summary[figi] = "ORDER_IN_FLIGHT"
                    continue

                candle_count = len(candles_data.get(figi, []) or [])

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

                if not current_price:
                    # REST fallback (ByBit ticker / T-Invest last price) when WS not yet warm.
                    if user_id is not None and hasattr(self.broker, "get_last_price"):
                        try:
                            rest_px = await self.broker.get_last_price(user_id, figi)
                            if rest_px and float(rest_px) > 0:
                                current_price = float(rest_px)
                                price_source = "rest"
                        except Exception:
                            pass

                if not current_price:
                    if candle_count <= 0:
                        reason = "NO_CANDLES_AND_NO_PRICE"
                    else:
                        reason = "NO_CURRENT_PRICE"
                    skip_summary[figi] = reason
                    continue

                signal = raw_signals.get(figi)
                # Signed broker map: long>0, short<0. Strategy SELL needs long qty.
                held_qty = max(0.0, float(holdings.get(str(figi).upper(), 0.0) or 0.0))
                effective_signal = signal
                strat_why = strategy_skip_reasons.get(figi)

                if effective_signal:
                    quantity, risk_skip = RiskManager.size_live_strategy_signal(
                        side=str(effective_signal),
                        current_price=float(current_price),
                        portfolio_value=portfolio_value,
                        free_funds=remaining_funds,
                        held_qty=held_qty,
                        risk_params=risk_params,
                        strategy_params=strategy_params,
                    )
                    if risk_skip or quantity is None or quantity <= 0:
                        skip_summary[figi] = risk_skip or "SIGNAL_FILTERED"
                        continue

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

                    create_reason = effective_signal
                    if strat_why:
                        create_reason = f"{effective_signal} · {strat_why}"
                    signals.append({
                        "figi": figi,
                        "signal": effective_signal,
                        "price": current_price,
                        "target_price": target_price,
                        "indicators": indicators,
                        "quantity": quantity,
                        "strategy": strategy_name,
                        "strength": 100,
                        "reduce_only": str(effective_signal).upper() == "SELL" and held_qty > 0,
                        "intent_source": "exit_strategy" if str(effective_signal).upper() == "SELL" else "entry",
                        "create_reason": (
                            f"{effective_signal} qty={quantity} @ {float(current_price):.6f} "
                            f"src={price_source}"
                            + (f"; strategy={strat_why}" if strat_why else "")
                        ),
                    })
                    create_summary[figi] = create_reason
                    remaining_funds = max(0.0, remaining_funds - (quantity * current_price))
                else:
                    reason = (
                        strategy_skip_reasons.get(figi)
                        or ("STRATEGY_NO_SIGNAL" if not signal else "SIGNAL_FILTERED")
                    )
                    skip_summary[figi] = reason

        except ValueError as e:
            self._write_log(f"❌ Неизвестная стратегия: {e}")
        except Exception as e:
            self._write_log(f"❌ Ошибка генерации сигналов: {e}")
            import traceback
            self._write_log(traceback.format_exc())

        self._write_stage5_summary(create_summary, skip_summary)
        return signals

    def _write_stage5_summary(
        self,
        create_summary: Dict[str, str],
        skip_summary: Dict[str, str],
    ) -> None:
        """Короткий итог цикла: счётчики + строки «монета — причина»."""
        self._write_log(
            f"Создано сигналов: {len(create_summary)} / пропущено: {len(skip_summary)}"
        )
        for sym, why in create_summary.items():
            self._write_log(f"{sym} — {why}")
        for sym, why in skip_summary.items():
            self._write_log(f"{sym} — {why}")

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

