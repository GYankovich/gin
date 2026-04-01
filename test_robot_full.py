#!/usr/bin/env python
"""
Полный тест торгового робота
"""
import sys
import asyncio
from pathlib import Path

# Добавляем путь к backend
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.database import SessionLocal
from app.modules.robots.trading.robot import TradingRobot

TOKEN = "t.9hTTJdmghLPbQ2SuRfdXiqxaJUwgDMhiAj3EP2FJxZ2lus9pLc3MtjCliNRm-DvIz1pYxpFe46OySLfBc43dEw"

async def test_robot():
    print("=" * 60)
    print("🚀 Тест торгового робота")
    print("=" * 60)

    db = SessionLocal()

    try:
        robot = TradingRobot("test")
        robot.db = db

        # ID робота (замените на ваш)
        robot_id = 7
        user_id = 1
        token_id = 15

        print(f"\n🤖 Запуск робота {robot_id}...")

        result = await robot.run(
            robot_id=robot_id,
            user_id=user_id,
            token_id=token_id,
            token=TOKEN
        )

        print("\n📊 Результат:")
        print(f"   Статус: {result.get('status')}")
        print(f"   Получено цен: {result.get('prices_received', 0)}")
        print(f"   Сигналов: {result.get('signals_count', 0)}")
        print(f"   Сделок: {result.get('trades_count', 0)}")
        print(f"   Время: {result.get('execution_time_ms', 0)}ms")

        if result.get('signal_ids'):
            print(f"   Signal IDs: {result['signal_ids']}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
        print("\n✅ Тест завершен")

if __name__ == "__main__":
    asyncio.run(test_robot())