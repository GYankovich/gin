"""
Торговый робот - модульная архитектура
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingRobot [1]
#/// Исходный модуль `backend/app/modules/robots/trading/robot.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime, timezone
from typing import Dict, Any, List
from pathlib import Path

from app.modules.robots.base.base_robot import BaseRobot
from app.modules.robots.common.mixins import TradePersistenceMixin
from app.modules.robots.trading.stages.stage1_collect import Stage1Collect
from app.modules.robots.trading.stages.stage2_websocket import Stage2WebSocket
from app.modules.robots.trading.stages.stage3_portfolio import Stage3Portfolio
from app.modules.robots.trading.stages.stage4_positions import Stage4Positions
from app.modules.robots.trading.stages.stage5_signals import Stage5Signals
from app.modules.robots.trading.execution import build_live_execution_service
from app.modules.robots.trading.brokers import create_broker_facade, normalize_broker_type


class TradingRobot(BaseRobot, TradePersistenceMixin):
    """
    Торговый робот - модульная архитектура
    """

    def __init__(self, robot_name: str = "trading"):
        super().__init__(
            robot_type="trading",
            robot_name=robot_name,
            version="1.0.0"
        )
        self._current_robot_id = None

    async def run(self, robot_id: int, user_id: int, token_id: int, token: str, **kwargs) -> Dict[str, Any]:
        """Запускает робота с логированием в БД и файл"""
        self._current_robot_id = robot_id
        return await super().run(robot_id, user_id, token_id, token, **kwargs)

    async def execute(
            self,
            robot_id: int,
            user_id: int,
            token_id: int,
            token: str,
            **kwargs
    ) -> Dict[str, Any]:
        """
        Основная работа робота - модульная архитектура
        """
        start_time = datetime.now(timezone.utc)

        # Используем файловый логгер из BaseRobot
        self.log.info("=" * 80)
        self.log.info(f"🚀 ЗАПУСК ТОРГОВОГО РОБОТА {robot_id}")
        self.log.info(f"Время запуска: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log.info("=" * 80)

        # Execution log уже создан в BaseRobot.run()
        self.log.info(f"Execution log ID: {self._execution_log_id}")

        # Результаты этапов
        robots_to_run = []
        prices = {}
        portfolio = {}
        open_positions = []
        signals = []
        trades = []
        closed_trades = []

        try:
            # ========== STAGE 1: Сбор роботов по расписанию ==========
            stage1 = Stage1Collect(self.db, self.schema, self._write_log_wrapper)
            robots_to_run = await stage1.execute()

            if not robots_to_run:
                self.log.info("❌ Нет роботов для запуска")
                return {"status": "skipped", "reason": "no_robots"}

            # Берем первого робота
            robot = robots_to_run[0]
            robot_config = robot.get("config", {})
            account_id = robot_config.get("account_id")
            allowed_figis = robot_config.get("allowed_figis", [])
            strategy_name = robot_config.get("strategy", "grain_seed")
            strategy_params = robot_config.get("strategy_params", {})
            risk_params = robot_config.get("risk", {})
            broker_type = normalize_broker_type(robot_config.get("broker_type", "tinvest"))
            broker = create_broker_facade(broker_type, token)

            self.log.info(f"🤖 Выбран робот {robot['robot_id']}")
            self.log.info(f"   Account ID: {account_id}")
            self.log.info(f"   FIGIs: {allowed_figis}")
            self.log.info(f"   Strategy: {strategy_name}")

            # ========== STAGE 2: WebSocket и цены ==========
            stage2 = Stage2WebSocket(
                broker=broker,
                user_id=user_id,
                robot_id=robot_id,
                broker_type=broker_type,
                log_func=self._write_log_wrapper
            )
            if not await stage2.connect():
                raise Exception("WebSocket connection failed")

            await stage2.subscribe(allowed_figis)
            prices = await stage2.receive_prices(duration_seconds=30)

            # ========== STAGE 3: Портфель и баланс ==========
            stage3 = Stage3Portfolio(account_id, broker, self._write_log_wrapper)
            portfolio = await stage3.get_portfolio()

            from app.modules.robots.trading.broker_position_sync import (
                configured_leverage,
                extract_account_position_meta,
            )
            from app.modules.robots.trading.brokers.margin import resolve_margin_params

            account_meta = extract_account_position_meta(portfolio.get("positions") or [])
            account_positions = {k: float(v.get("qty") or 0) for k, v in account_meta.items()}
            risk_params = dict(risk_params or {})
            bybit_cfg = robot_config.get("bybit") if isinstance(robot_config.get("bybit"), dict) else {}
            category = str(bybit_cfg.get("instrument_category") or "").strip().lower()
            if broker_type == "bybit":
                lev = configured_leverage(robot_config, risk_params)
                margin = resolve_margin_params(robot_config)
                risk_params["max_leverage"] = lev
                risk_params["instrument_category"] = category or "linear"
                risk_params["margin_enabled"] = bool(margin.get("enabled")) or category == "spot"
            risk_params["free_funds"] = float(portfolio.get("free_funds") or 0)

            # ========== STAGE 4: Планирование SL/TP exits (без place) ==========
            stage4 = Stage4Positions(
                self.db, self.schema, broker, account_id, robot_id, self._write_log_wrapper
            )
            open_positions = await stage4.get_open_positions()

            from app.modules.robots.trading.contracts import OrderIntent
            from app.modules.robots.trading.symbol_guard import SymbolGuard

            guard = SymbolGuard(broker=broker, account_id=account_id or "", log_func=self._write_log_wrapper)
            exit_intents = await stage4.plan_stop_loss_take_profit(
                open_positions,
                prices,
                risk_params,
                guard=guard,
                account_positions=account_positions,
            )

            # ========== STAGE 5: Генерация сигналов ==========
            stage5 = Stage5Signals(broker, self._write_log_wrapper)
            signals = await stage5.generate_signals(
                figis=allowed_figis,
                strategy_name=strategy_name,
                strategy_params=strategy_params,
                risk_params=risk_params,
                portfolio_value=portfolio.get("total_value", 0),
                free_funds=portfolio.get("free_funds", 0),
                open_positions=open_positions,
                account_positions=account_positions,
                current_prices=prices,
                log_api_call_func=self._log_api_call_wrapper,  # ← передаём для логирования в БД
                token_id=token_id,
                user_id=user_id,
                pending_order_figis=guard.blocked_figis(),
            )

            # Сохраняем сигналы в БД
            signal_ids = []
            if signals:
                signal_ids = await self.save_signals(self.db, self.schema, robot_id, signals)
                self.log.info(f"   💾 Сохранено сигналов: {len(signal_ids)}")

            # ========== STAGE 6: Единый Execution path ==========
            entry_intents = [OrderIntent.from_strategy_signal(s) for s in signals]
            all_intents = list(exit_intents) + entry_intents
            closed_trades = []
            if all_intents:
                execution = build_live_execution_service(
                    db=self.db,
                    schema=self.schema,
                    broker=broker,
                    account_id=account_id,
                    robot_id=robot_id,
                    token_id=token_id,
                    user_id=user_id,
                    log_func=self._write_log_wrapper,
                    in_flight_orders=guard.in_flight_orders,
                    account_positions=account_positions,
                )
                trades = await execution.submit_intents(all_intents, risk_params=risk_params)
                closed_trades = [t for t in trades if str(t.get("intent_source") or "") == "exit_sl_tp"]
                trade_ids = await self.save_trades(self.db, self.schema, robot_id, trades)
                self.log.info(f"   💾 Сохранено сделок: {len(trade_ids)}")
                executed_signal_ids = [
                    int(t["signal_id"])
                    for t in trades
                    if t.get("signal_id") and t.get("status") not in {"failed", "skipped"}
                ]
                marked = await self.mark_signals_executed(self.db, self.schema, executed_signal_ids)
                if marked:
                    self.log.info(f"   ✅ Отмечено исполненных сигналов: {marked}")

            # Закрываем WebSocket
            await stage2.close()
            await broker.close()

            execution_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            self.log.info("=" * 80)
            self.log.info(f"✅ РАБОТА ЗАВЕРШЕНА за {execution_time_ms}ms")
            self.log.info(f"   Сигналов: {len(signals)}")
            self.log.info(f"   Сделок: {len(trades)}")
            self.log.info(f"   Закрыто позиций: {len(closed_trades)}")
            self.log.info("=" * 80)

            return {
                "status": "success",
                "portfolio_value": portfolio.get("total_value", 0),
                "free_funds": portfolio.get("free_funds", 0),
                "signals_count": len(signals),
                "trades_count": len(trades),
                "closed_trades_count": len(closed_trades),
                "execution_time_ms": execution_time_ms
            }

        except Exception as e:
            error_msg = str(e)
            self.log.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {error_msg}")
            import traceback
            self.log.error(traceback.format_exc())
            return {"status": "error", "message": error_msg}

    def _write_log_wrapper(self, message: str):
        """Обёртка для записи в файловый лог (для stages)"""
        self.log.info(message)

    async def _log_api_call_wrapper(self, **kwargs):
        """Обёртка для логирования API вызовов в БД"""
        return await self.log_api_call(**kwargs)