#!/usr/bin/env python
"""
Простой тест WebSocket для получения цен
"""
import sys
import asyncio
from pathlib import Path

# Добавляем путь к backend
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from app.modules.tinvest.websocket.price_manager import PriceStreamManager

TOKEN = "t.9hTTJdmghLPbQ2SuRfdXiqxaJUwgDMhiAj3EP2FJxZ2lus9pLc3MtjCliNRm-DvIz1pYxpFe46OySLfBc43dEw"
FIGI = "BBG000B9XRY4"  # SBER


async def test_websocket():
    """Тест WebSocket подключения и получения цен"""
    print("=" * 60)
    print("🚀 Тест WebSocket получения цен")
    print("=" * 60)

    ws = PriceStreamManager(TOKEN)

    # Счетчик полученных цен
    price_count = 0

    # Колбэк для получения цен
    async def on_price(price_info):
        nonlocal price_count
        price_count += 1
        print(f"📈 {price_info['figi']}: {price_info['price']:.4f} руб.")

    ws.on_price(FIGI, on_price)

    try:
        # Подключаемся
        print("\n🔌 Подключаемся к WebSocket...")
        await ws.connect()

        # Подписываемся на цену
        print(f"📡 Подписываемся на {FIGI}...")
        await ws.subscribe([FIGI])

        print("\n⏱️ Получение цен в течение 30 секунд...")
        print("   (нажмите Ctrl+C для досрочного завершения)\n")

        # Получаем сообщения 30 секунд
        await ws.receive_messages(timeout=30.0)

        print(f"\n📊 Получено цен: {price_count}")

        last_price = ws.get_last_price(FIGI)
        if last_price:
            print(f"   Последняя цена {FIGI}: {last_price:.4f} руб.")
        else:
            print("   ⚠️ Цены не получены")

    except KeyboardInterrupt:
        print("\n\n⏹️ Прервано пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await ws.close()
        print("\n✅ Тест завершен")


if __name__ == "__main__":
    asyncio.run(test_websocket())