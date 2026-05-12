---
name: t-investments-market-data-guide
description: >-
  T-Invest (T-Bank) Invest Public API data surfaces relevant to BRDs: REST
  endpoints used in this repo, WebSocket streaming, and common limitations.
  Use when specifying data needs for strategies or backtests.
---

# T-Investments market data (BRD reference)

**Base REST URL (this project):** `https://invest-public-api.tbank.ru/rest`  
**WebSocket (streaming example in repo):** `wss://invest-public-api.tinkoff.ru/ws/...MarketDataStreamService/MarketDataStream`  
Official documentation may use parallel “production” hostnames; always align tokens and environment with the deployment you target.

When writing requirements, refer to **gRPC/REST service names** so engineering can map 1:1.

## Instruments

- **InstrumentsService/Shares** — listed equities (use `instrumentStatus`, e.g. base listing)
- **InstrumentsService/Etfs**, **Bonds** — other universes as needed  
BRD should specify: filter by exchange, currency, liquidity, and whether **FIGI** is the primary key for downstream candle and order calls.

## Historical candles

- **MarketDataService/GetCandles**  
Parameters to specify in BRDs: **figi**, **from** / **to** (UTC ISO timestamps), **interval** (e.g. day / hour enums per API).  
Limitations to flag: pagination / max range per request, possible gaps for illiquid names, rate limits.

## Realtime prices

- **MarketDataStreamService** (WebSocket) — subscriptions by instrument id; suitable for **live** signals and monitoring, not long archival history.  
Flag: reconnect logic, backoff, and **stale quote** risk if the stream drops.

## Portfolio and trading (context for full BRDs)

- Portfolio and order endpoints exist under Invest API (e.g. operations service patterns); for analyst BRDs, state **account_id** scope, **sandbox vs prod**, and **order types** (limit/market) expected—without designing API contracts.

## What to state in every data-heavy BRD

1. Whether the strategy needs **EOD only** vs **intraday** bars (drives `GetCandles` interval choice).
2. Whether **live** execution needs WebSocket vs polling REST.
3. **FIGI resolution** workflow from ticker (who maintains the mapping, refresh cadence).
4. Assumptions on **corporate actions** and **currency** of the instrument.

For implementation alignment in this repository, see `backend/app/modules/tinvest/methods/instruments.py` and `backend/app/modules/tinvest/facade.py` (behavior reference only—do not write code in analyst mode).
