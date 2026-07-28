---
name: api-contract-template
description: >-
  REST and WebSocket API contract outline for trading backends: resources,
  payloads, errors, idempotency, and versioning. Use when designing or
  documenting HTTP/WS surfaces.
---

# API contract template

For each endpoint or WS channel, document the following sections. Tie each resource to `[ref: BRD-XX]`.

## REST resource sheet

| Field | Value |
|--------|--------|
| BRD ref | `[ref: BRD-XX]` |
| Method / path | e.g. `POST /v1/orders` |
| Auth | Bearer / API key / session |
| Idempotency | `Idempotency-Key` header? yes/no |
| Request schema | JSON fields + types + required |
| Response `200` | JSON schema |
| Errors | `400` validation, `401`, `403`, `404`, `409`, `429` bodies |
| Rate limit | per user / per token; burst |

## WebSocket channel sheet

| Field | Value |
|--------|--------|
| BRD ref | `[ref: BRD-XX]` |
| URL | `wss://...` |
| Subprotocol / framing | JSON messages / protobuf |
| Client → server | subscribe / unsubscribe / heartbeat shapes |
| Server → client | event types + payload schema |
| Backpressure | drop policy, max queue |
| Reconnect | snapshot + delta strategy |

## Versioning

- URI prefix (`/v1`) or header (`Accept-Version`). State deprecation and sunset for breaking changes.

## Example request/response (minimal)

```json
// POST /v1/example
{ "figi": "string", "quantity": "integer" }

// 200
{ "id": "uuid", "status": "enum" }
```
