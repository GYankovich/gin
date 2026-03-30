"""
Торговый робот - модульная архитектура
"""
from datetime import datetime, timezone
from typing import Dict, Any, List
import logging
import json

from app.modules.robots.base.base_robot import BaseRobot
from app.modules.robots.trading.stages.stage1_collect import Stage1Collect
from app.modules.robots.trading.stages.stage2_websocket import Stage2WebSocket
from app.modules.robots.trading.stages.stage3_portfolio import Stage3Portfolio
from app.modules.robots.trading.stages.stage4_positions import Stage4Positions
from app.modules.robots.trading.stages.stage5_signals import Stage5Signals
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders

logger = logging.getLogger(__name__)


class TradingRobot(BaseRobot):
    """
    Торговый робот - модульная архитектура
    """

    def __init__(self, robot_name: str = "trading"):
        super().__init__(
            robot_type="trading",
            robot_name=robot_name,
            version="1.0.0"
        )
        self._file_log = None
        self._current_robot_id = None

    def _get_file_logger(self, robot_id: int):
        """Создает файловый логгер для робота"""
        if self._file_log is None:
            from pathlib import Path
            log_dir = Path("logs/trading_robots")
            log_dir.mkdir(parents=True, exist_ok=True)

            log_file = log_dir / f"robot_{robot_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            self._file_log = open(log_file, 'w', encoding='utf-8')
            self._write_log(f"Лог файл создан: {log_file}")
            self._write_log(f"Робот ID: {robot_id}, Версия: {self.version}")

        self._current_robot_id = robot_id
        return self._file_log

    def _write_log(self, message: str):
        """Записывает сообщение в файловый лог"""
        if self._file_log:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            robot_prefix = f"[ROBOT_{self._current_robot_id}]" if self._current_robot_id else "[ROBOT_?]"
            self._file_log.write(f"[{timestamp}] {robot_prefix} {message}\n")
            self._file_log.flush()

    async def _save_signals(self, robot_id: int, signals: List[Dict]) -> List[int]:
        """Сохраняет сигналы в БД"""
        if not self.db or not signals:
            return []

        signal_ids = []
        for signal in signals:
            query = """
                INSERT INTO {}.robot_signals
                (robot_id, figi, signal_type, signal_strength, price_at_signal, was_executed, created_at)
                VALUES
                (:robot_id, :figi, :signal_type, :signal_strength, :price, 0, :now)
                RETURNING id
            """.format(self.schema)

            result = self.db.execute(
                text(query),
                {
                    "robot_id": robot_id,
                    "figi": signal["figi"],
                    "signal_type": signal["signal"].lower(),
                    "signal_strength": 100,
                    "price": signal["price"],
                    "now": datetime.now(timezone.utc)
                }
            ).first()

            if result:
                signal_ids.append(result[0])

        if signal_ids:
            self.db.commit()
        return signal_ids

    async def run(self, robot_id: int, user_id: int, token_id: int, token: str, **kwargs) -> Dict[str, Any]:
        """Запускает робота"""
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
        self._current_robot_id = robot_id

        # Инициализация
        self._get_file_logger(robot_id)
        self._write_log("=" * 80)
        self._write_log(f"🚀 ЗАПУСК ТОРГОВОГО РОБОТА {robot_id}")
        self._write_log(f"Время запуска: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_log("=" * 80)

        # Создаем запись в execution_log
        await self._create_execution_log(robot_id)
        self._write_log(f"Execution log ID: {self._execution_log_id}")

        # Результаты этапов
        robots_to_run = []
        prices = {}
        portfolio = {}
        open_positions = []
        signals = []
        trades = []

        try:
            # ========== STAGE 1: Сбор роботов по расписанию ==========
            stage1 = Stage1Collect(self.db, self.schema, self._write_log)
            robots_to_run = await stage1.execute()

            if not robots_to_run:
                self._write_log("❌ Нет роботов для запуска")
                await self._complete_execution_log(status=1, message="Нет роботов для запуска")
                return {"status": "skipped", "reason": "no_robots"}

            # Берем первого робота (для теста)
            robot = robots_to_run[0]
            robot_config = robot.get("config", {})
            account_id = robot_config.get("account_id")
            allowed_figis = robot_config.get("allowed_figis", [])
            strategy_name = robot_config.get("strategy", "ma_cross")
            strategy_params = robot_config.get("strategy_params", {})
            risk_params = robot_config.get("risk", {})

            self._write_log(f"🤖 Выбран робот {robot['robot_id']}")
            self._write_log(f"   Account ID: {account_id}")
            self._write_log(f"   FIGIs: {allowed_figis}")
            self._write_log(f"   Strategy: {strategy_name}")

            # ========== STAGE 2: WebSocket и цены ==========
            stage2 = Stage2WebSocket(token, robot_id, self._write_log)
            if not await stage2.connect():
                raise Exception("WebSocket connection failed")

            await stage2.subscribe(allowed_figis)
            prices = await stage2.receive_prices(duration_seconds=30)

            # ========== STAGE 3: Портфель и баланс ==========
            stage3 = Stage3Portfolio(self.db, token, user_id, token_id, robot_id, self._write_log)
            portfolio = await stage3.get_portfolio()

            # Проверка лимитов
            max_position_rub = risk_params.get("max_position_rub", float('inf'))
            free_funds = portfolio.get("free_funds", 0)

            if free_funds < max_position_rub:
                self._write_log(f"⚠️ Свободных средств ({free_funds:.2f}) меньше лимита ({max_position_rub:.2f})")
                max_position_rub = free_funds

            # ========== STAGE 4: Управление позициями ==========
            stage4 = Stage4Positions(self.db, self.schema, token, account_id, robot_id, self._write_log)
            open_positions = await stage4.get_open_positions()

            # Проверка stop-loss/take-profit
            closed_trades = await stage4.check_stop_loss_take_profit(open_positions, prices, risk_params)

            # ========== STAGE 5: Генерация сигналов ==========
            stage5 = Stage5Signals(self._write_log)
            signals = await stage5.generate_signals(
                candles={},  # TODO: добавить получение свечей
                prices=prices,
                figis=allowed_figis,
                strategy_name=strategy_name,
                strategy_params=strategy_params,
                risk_params=risk_params,
                portfolio_value=portfolio.get("total_value", 0),
                free_funds=free_funds,
                open_positions=open_positions
            )

            # ========== STAGE 6: Выставление заявок ==========
            if signals:
                stage6 = Stage6Orders(
                    self.db, self.schema, token, account_id, robot_id, token_id, user_id, self._write_log
                )
                trades = await stage6.execute_signals(signals)
                trade_ids = await stage6.save_trades(robot_id, trades)
            else:
                trade_ids = []

            # Закрываем WebSocket
            await stage2.close()

            execution_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            await self._complete_execution_log(
                status=1,
                message=f"Сигналов: {len(signals)}, Сделок: {len(trades)}, Закрыто: {len(closed_trades)}",
                execution_time_ms=execution_time_ms
            )

            self._write_log("=" * 80)
            self._write_log(f"✅ РАБОТА ЗАВЕРШЕНА за {execution_time_ms}ms")
            self._write_log(f"   Сигналов: {len(signals)}")
            self._write_log(f"   Сделок: {len(trades)}")
            self._write_log(f"   Закрыто позиций: {len(closed_trades)}")
            self._write_log("=" * 80)

            if self._file_log:
                self._file_log.close()
                self._file_log = None

            return {
                "status": "success",
                "portfolio_value": portfolio.get("total_value", 0),
                "free_funds": free_funds,
                "signals_count": len(signals),
                "trades_count": len(trades),
                "closed_trades_count": len(closed_trades),
                "trade_ids": trade_ids,
                "execution_time_ms": execution_time_ms
            }

        except Exception as e:
            error_msg = str(e)
            self._write_log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {error_msg}")
            import traceback
            self._write_log(traceback.format_exc())
            await self._complete_execution_log(status=2, message=error_msg[:500])

            if self._file_log:
                self._file_log.close()
                self._file_log = None

            return {"status": "error", "message": error_msg}