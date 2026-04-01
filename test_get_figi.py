#!/usr/bin/env python
"""
Получение актуальных FIGI для акций через T-Invest API
"""
import sys
import asyncio
from pathlib import Path

# Добавляем путь к backend
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

import httpx
import ssl
from datetime import datetime

TOKEN = "t.9hTTJdmghLPbQ2SuRfdXiqxaJUwgDMhiAj3EP2FJxZ2lus9pLc3MtjCliNRm-DvIz1pYxpFe46OySLfBc43dEw"


async def get_shares():
    """Получает список акций через InstrumentsService"""
    url = "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.InstrumentsService/Shares"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}

    # Отключаем проверку SSL
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    async with httpx.AsyncClient(verify=ssl_context, timeout=30) as client:
        response = await client.post(url, json=data, headers=headers)

        if response.status_code != 200:
            print(f"❌ Ошибка: {response.status_code}")
            print(f"   {response.text}")
            return []

        result = response.json()
        return result.get("instruments", [])


async def get_figi_by_ticker(ticker: str):
    """Ищет FIGI по тикеру"""
    shares = await get_shares()
    for share in shares:
        if share.get("ticker", "").upper() == ticker.upper():
            return share.get("figi")
    return None


async def main():
    print("=" * 60)
    print("🔍 Поиск FIGI для популярных акций")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Список популярных тикеров
    popular_tickers = [
        "SBER",   # Сбербанк
        "YNDX",   # Яндекс
        "GAZP",   # Газпром
        "LKOH",   # Лукойл
        "ROSN",   # Роснефть
        "TATN",   # Татнефть
        "VTBR",   # ВТБ
        "NLMK",   # НЛМК
        "CHMF",   # Северсталь
        "MGNT",   # Магнит
    ]

    print("\n📡 Запрос списка акций...")
    shares = await get_shares()

    if not shares:
        print("❌ Не удалось получить список акций")
        return

    print(f"✅ Получено {len(shares)} акций\n")

    # Создаем словарь для быстрого поиска
    shares_by_ticker = {s.get("ticker"): s for s in shares}

    print("📊 Найденные FIGI:")
    print("-" * 80)
    print(f"{'Тикер':<10} {'FIGI':<25} {'Название'}")
    print("-" * 80)

    for ticker in popular_tickers:
        share = shares_by_ticker.get(ticker)
        if share:
            figi = share.get("figi")
            name = share.get("name", "")[:50]
            print(f"{ticker:<10} {figi:<25} {name}")
        else:
            print(f"{ticker:<10} {'❌ НЕ НАЙДЕН':<25} -")

    print("-" * 80)

    # Также покажем первые 5 акций для примера
    print("\n📋 Примеры других акций (первые 5):")
    print("-" * 80)
    for share in shares[:5]:
        ticker = share.get("ticker", "N/A")
        figi = share.get("figi", "N/A")
        name = share.get("name", "N/A")[:40]
        print(f"{ticker:<10} {figi:<25} {name}")

    print("-" * 80)
    print(f"\n💡 Совет: используйте эти FIGI в конфиге робота:")
    print('"allowed_figis": ["BBG000B9XRY4", "BBG000B9Y5X2"]')


async def search_ticker(ticker: str):
    """Поиск FIGI по конкретному тикеру"""
    print(f"\n🔍 Поиск FIGI для {ticker.upper()}...")
    figi = await get_figi_by_ticker(ticker)

    if figi:
        print(f"✅ Найден: {figi}")
    else:
        print(f"❌ Тикер {ticker} не найден")

        # Покажем похожие тикеры
        shares = await get_shares()
        similar = [s.get("ticker") for s in shares if ticker.upper() in s.get("ticker", "").upper()]
        if similar:
            print(f"   Возможно, вы искали: {', '.join(similar[:5])}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Поиск FIGI для акций")
    parser.add_argument("ticker", nargs="?", help="Тикер для поиска (опционально)")
    args = parser.parse_args()

    if args.ticker:
        asyncio.run(search_ticker(args.ticker))
    else:
        asyncio.run(main())