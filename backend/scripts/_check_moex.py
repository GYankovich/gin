import asyncio
import httpx

async def main():
    url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    params = {"iss.meta": "off", "iss.only": "securities,marketdata", "securities.start": 0, "marketdata.start": 0}
    async with httpx.AsyncClient(timeout=20, verify=False) as client:
        resp = await client.get(url, params=params)
    print("status", resp.status_code)
    data = resp.json() if resp.status_code == 200 else {}
    sec = (data.get("securities") or {}).get("data") or []
    md = (data.get("marketdata") or {}).get("data") or []
    print("sec_rows", len(sec), "md_rows", len(md))
    if resp.status_code != 200:
        print(resp.text[:500])

asyncio.run(main())
