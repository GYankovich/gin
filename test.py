#!/usr/bin/env python
"""
Получение актуальных FIGI через InstrumentsClient
"""
import sys
from pathlib import Path

backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

import asyncio
import ssl
import httpx

TOKEN = "t.9hTTJdmghLPbQ2SuRfdXiqxaJUwgDMhiAj3EP2FJxZ2lus9pLc3MtjCliNRm-DvIz1pYxpFe46OySLfBc43dEw"

async def get_shares():
    """Получает список акций"""
    url = "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.InstrumentsService/Shares"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}

    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        response = await client.post(url, json=data, headers=headers)
        if response.status_code == 200:
            return response.json().get("instruments", [])
        else:
            print(f"Ошибка: {response.status_code}")
            return []

async def main():
    shares = await get_shares()

    print("Актуальные FIGI для популярных акций:")
    print("-" * 80)

    tickers = ["SBER", "YNDX", "GAZP", "LKOH", "ROSN", "TATN", "VTBR"]

    for share in shares:
        ticker = share.get("ticker", "")
        if ticker in tickers:
            figi = share.get("figi", "")
            name = share.get("name", "")
            print(f"{ticker:6} | {figi:20} | {name[:50]}")

    print("-" * 80)
    print(f"Всего акций: {len(shares)}")

if __name__ == "__main__":
    asyncio.run(main())