---
name: websocket-real-time
description: >-
  WebSocket client patterns for this repo: useWebSocket hook, reconnect,
  JSON messages, connection status UI, pairing with Zustand or local state.
  Use when adding live prices, robot events, or streaming dashboards.
---

# WebSocket real-time patterns

## Default hook

Use **`frontend/src/hooks/useWebSocket.ts`**:

- **`url`**: full `ws://` or `wss://` URL (often derived from `window.location` + API path — follow existing pages).
- **`enabled`**: set `false` until required params exist (e.g. selected robot id).
- **`onMessage`**: keep **stable** with `useCallback` in the parent so the effect does not thrash.
- **`reconnectInterval`**: default `3000` ms; increase for noisy networks only when product asks.
- Returns **`{ connected, send }`**; `send` JSON-stringifies objects.

Reference usage: **`frontend/src/pages/LivePage.tsx`**.

## UI contract

Every streaming surface should show:

1. **Disconnected** — badge or banner (“нет соединения”), optional manual reconnect button calling the same URL remount pattern or exposing reconnect if added later.
2. **Connected** — subtle indicator; do not toast on every reconnect unless debugging.
3. **Stale data** — if messages carry timestamps, show “обновлено …” or warn when older than N seconds (when backend provides clock).

## Message handling

- Parser already tries **`JSON.parse`**; fall back to raw string.
- Prefer **narrow types**: validate with a type guard or schema before updating store.
- **Batched updates**: for high-frequency ticks, throttle UI updates (`requestAnimationFrame` or 100–250 ms throttle) to avoid React overload.

## Auth and URLs

- Do not embed secrets in query strings; follow backend expectations for tokens (cookies vs query) already used in this project.
- Use **`wss:`** in production when the page is served over HTTPS.

## Related

- Server contract and logging: see **`skill://api-contract-template`** for HTTP; WS payloads should be documented the same way when crossing teams.

## Anti-patterns

- Opening a raw `WebSocket` in a page without cleanup while `useWebSocket` exists.
- Calling `setState` on every message without deduplication or batching for burst traffic.
