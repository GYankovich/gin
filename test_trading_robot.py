#!/usr/bin/env python
"""
Финальный тест WebSocket с правильным URL
"""
import asyncio
import websockets
import ssl
import json
from datetime import datetime

TOKEN = "t.9hTTJdmghLPbQ2SuRfdXiqxaJUwgDMhiAj3EP2FJxZ2lus9pLc3MtjCliNRm-DvIz1pYxpFe46OySLfBc43dEw"

# Рабочий URL
WS_URL = "wss://invest-public-api.tinkoff.ru/ws/tinkoff.public.invest.api.contract.v1.MarketDataStreamService/MarketDataStream"

# FIGI
FIGIS = [
    "BBG004730ZJ9"
]

def parse_price(price_data):
    """Безопасно парсит цену из units/nano"""
    if not price_data:
        return None

    units = price_data.get("units", 0)
    nano = price_data.get("nano", 0)

    # Преобразуем в числа
    try:
        units = int(units) if units else 0
    except (TypeError, ValueError):
        units = 0

    try:
        nano = int(nano) if nano else 0
    except (TypeError, ValueError):
        nano = 0

    return units + nano / 1e9

async def test_websocket():
    print("=" * 60)
    print("🚀 Тест WebSocket T-Invest API")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"URL: {WS_URL}")
    print(f"FIGI: {FIGIS}")
    print("=" * 60)

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        async with websockets.connect(
                WS_URL,
                ssl=ssl_context,
                additional_headers={
                    "Authorization": f"Bearer {TOKEN}"
                },
                subprotocols=["json"],
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
        ) as websocket:
            print("✅ WebSocket подключен!")

            # Подписываемся на цены
            instruments = [{"figi": figi, "instrumentId": figi} for figi in FIGIS]
            subscribe_msg = {
                "subscribeLastPriceRequest": {
                    "subscriptionAction": "SUBSCRIPTION_ACTION_SUBSCRIBE",
                    "instruments": instruments
                }
            }

            print("📡 Отправляем подписку...")
            await websocket.send(json.dumps(subscribe_msg))

            # Получаем ответ на подписку
            response = await asyncio.wait_for(websocket.recv(), timeout=10)
            response_data = json.loads(response)

            if "subscribeLastPriceResponse" in response_data:
                subs = response_data["subscribeLastPriceResponse"].get("lastPriceSubscriptions", [])
                for s in subs:
                    figi = s.get("figi")
                    status = s.get("subscriptionStatus", "UNKNOWN")
                    print(f"   {figi}: {status}")
                print("✅ Подписка подтверждена")

            # Ждем цены в течение 60 секунд
            print("\n⏱️ Ожидание цен в течение 60 секунд...")
            prices_received = {}

            for i in range(60):
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(msg)

                    if "lastPrice" in data:
                        price_data = data["lastPrice"]
                        figi = price_data.get("figi")
                        price = parse_price(price_data.get("price"))
                        time = price_data.get("time", "")

                        if price is not None:
                            print(f"📈 {figi}: {price:.4f} руб. ({datetime.now().strftime('%H:%M:%S')})")
                            prices_received[figi] = price
                    elif "ping" in data:
                        print("🏓 Ping от сервера")
                    elif "pong" in data:
                        pass
                    elif "subscribeLastPriceResponse" in data:
                        pass
                    else:
                        # Показываем другие сообщения (для отладки)
                        if i % 10 == 0:
                            print(f"📨 Другое: {list(data.keys())}")

                except asyncio.TimeoutError:
                    if i % 10 == 0:
                        print(f"   ⏳ ожидание... ({i+1}/60)")
                    continue

            print(f"\n📊 Получено цен:")
            for figi, price in prices_received.items():
                print(f"   {figi}: {price:.4f} руб.")

            if not prices_received:
                print("   ⚠️ Цены не получены. Возможно, сейчас нет торгов.")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_websocket())