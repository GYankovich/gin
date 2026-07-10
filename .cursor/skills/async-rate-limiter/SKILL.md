---
name: async-rate-limiter
description: >-
  Async-friendly rate limiting for outbound HTTP and broker APIs: token buckets,
  sliding windows, and per-key isolation. Use when calling T-Invest, MOEX, or
  other throttled external services from asyncio code.
---

# Async rate limiter

## Requirements

- **Per credential or per host** isolation (dict of limiters keyed by token or base URL).
- **Thread-safe / task-safe**: `asyncio.Lock` around shared deque or counter.
- **Sliding window** or **token bucket**; prefer sliding window when vendor documents “N requests per minute”.

## Reference implementation (this repo)

- `backend/app/modules/robots/trading/brokers/rate_limiter.py` — `TokenRateLimiter`, `get_token_rate_limiter`.

## Usage pattern

```python
limiter = await get_token_rate_limiter(token_fingerprint)
await limiter.acquire()
# ... perform HTTP/SDK call ...
```

- Do not create unbounded limiter instances per request; reuse the registry pattern.

## Configuration

- Limits from `settings` or robot config; document defaults in code.

## Testing

- Fake clock or inject small window/limit in tests to assert waiting vs immediate permit.

## Related

- T-Invest client: `skill://t-investments-client-implementation`.
- MOEX client: `skill://moex-python-client`.
