# SPEC-04: Monitor day summary — real account / paper balance

**Status:** Approved for design/implementation (defaults locked 2026-10-05)  
**Surface:** `/robots/:id/monitor` — `MonitorSummaryCard` («Сводка за день») inside `RobotV2MonitorPage`  
**API:** `GET /api/v2/robots/{id}/status` (`RobotV2Service.get_status`)  
**Extends:** robots_v2 monitor as-built; no billing/auth changes

---

## 1. Problem and users

**Problem.** «Сводка за день» already shows **real day trade stats** (from fills), but the **Equity / Cash** row is gated by `showSessionStats` (`statusLoaded && isActive && !isSyncing`). When the robot is idle, the UI shows «Робот не работает» even though:

- **Live + `tokenId`:** backend already fetches a lightweight broker portfolio snapshot (cash, equity, positions) on idle status.
- **Paper:** `metadata.lastVirtualCapital` is persisted on launch and used to resume capital, but idle status **does not** expose equity/cash today.

Robot #13 (paper/live-capable with token binding) makes this concrete: operators want **real balance visibility**, not stubs or a blank “not running” placeholder.

**Users.**

| Persona | Need |
|---------|------|
| Live operator | See broker account cash/equity on Monitor even when session is stopped |
| Paper tuner | See last paper capital when idle, clearly labeled as paper (not live account) |
| Founder / demo | Credible “what’s on the account / in the ledger” without starting the robot |

**Success metrics (product).**

- Idle live robot with successful broker fetch: Equity + Cash visible without Start.
- Idle paper with `lastVirtualCapital`: paper capital visible with RU disclaimer.
- Zero false “live account” labeling for paper mode.
- No new auth/billing surface.

---

## 2. Scope (in / out)

### In scope (P0)

- Decouple **balance tiles** (Equity/Cash) from **session-ops tiles** (Cycle / Позиции) in `MonitorSummaryCard`.
- Always show Equity/Cash when status provides values (active session **or** idle).
- Idle **live**: use existing broker snapshot fields; RU label that values are **account** («Счёт»), not robot-isolated allocation.
- Idle **paper**: expose and show last paper capital (prefer `metadata.lastVirtualCapital`; optional cheap ledger snapshot if already available).
- Clear empty/error states when balance cannot be loaded.
- Document API field gaps and additive status fields.

### In scope (P1 — optional)

- Day-start equity + day equity delta on the summary card — **only if trivial** after P0; otherwise keep deferred.

### Out of scope

- Billing, registration, auth, token UX redesign.
- Robot-isolated capital sleeves / sub-accounts (broker funds are whole-account).
- Changing day **trade** stats computation (`computeDayTradeStats` / fills).
- New WebSocket channel solely for idle balance (poll/status + existing live WS remain).
- Persist of full paper ledger to DB for idle mark-to-market (P0 uses last capital; richer MTM is future).

### Documented assumptions (agree unless flagged)

| # | Assumption | Spec stance |
|---|------------|-------------|
| A1 | Always show Equity/Cash when status API provides them (idle live included) | **Agree** `[R-1]` `[R-2]` |
| A2 | Idle paper: show `metadata.lastVirtualCapital` (or last ledger snapshot if cheap) with clear RU label that it is last paper capital / not live account | **Agree** `[R-3]` `[R-4]` |
| A3 | Live cash/equity = broker **account** funds (label «Счёт»), not robot-isolated allocation — product limitation must be visible | **Agree** `[R-5]` |
| A4 | Optional P1: day-start equity + day equity delta — mark P1 if not trivial | **Agree** `[R-10]` |
| A5 | No billing/auth changes | **Agree** `[R-11]` |

**Disagreement / correction vs naive reading of A1:** Today idle **paper** status returns **no** `equity`/`cash` (early return when `mode != "live"`). P0 **must** add those fields (or equivalents) for paper idle — UI alone cannot satisfy A2.

**Correction vs current UI:** `showSessionStats` hides the **entire** second grid (Equity, Cash, Cycle, Позиции). P0 must **split** balance vs session-ops so idle balance does not imply a running cycle.

---

## 3. Functional requirements `[R-n]`

| ID | Phase | Requirement |
|----|-------|-------------|
| `[R-1]` | P0 | When `GET …/status` includes numeric `equity` and/or `cash`, Monitor summary **shows** those tiles regardless of session active/idle/syncing. |
| `[R-2]` | P0 | Idle **live** with `tokenId`: continue (or restore) broker snapshot path; surface cash/equity already computed in `_fetch_idle_broker_positions`. |
| `[R-3]` | P0 | Idle **paper**: status includes paper balance source — at minimum `lastVirtualCapital` from robot metadata as both a dedicated field and as `cash`/`equity` when no richer ledger exists (cash ≈ equity ≈ last capital at stop/start). |
| `[R-4]` | P0 | RU labeling distinguishes sources: live account «Счёт» vs paper «Бумажный капитал» / «Последний paper-капитал» (designer finalizes copy; see §8). |
| `[R-5]` | P0 | Live labels/disclaimer make clear values are **whole broker account**, not per-robot allocation / allocatedCapital sleeve. |
| `[R-6]` | P0 | Session-ops tiles (Cycle, Позиции count) remain gated to active session (or syncing rules as today); they must **not** block balance tiles. |
| `[R-7]` | P0 | If balance unavailable (no token, broker timeout, never-started paper): show honest empty/placeholder — **not** fake zeros that look like a real account. Prefer omit tiles or «Нет данных» over `0`. |
| `[R-8]` | P0 | Status response includes machine-readable `balanceSource` (and optionally `balanceLabelKey`) so UI does not infer labels only from `mode`. |
| `[R-9]` | P0 | Existing active-session equity/cash from session snapshot unchanged in meaning; WS live updates continue to refresh numbers while running. |
| `[R-10]` | P1 | Optional: `dayStartEquity` + `dayEquityDelta` (and RU tiles) when cheap to compute from session/audit; otherwise defer. |
| `[R-11]` | All | No auth/billing/token-product changes. |
| `[R-12]` | P0 | Syncing state: balance may still show last known session or broker values; do not replace balance row with only «Робот синхронизируется» — that message stays for session-ops / hero, not for hiding account funds. |

### Paper idle semantics (normative)

| State | What to show | Source |
|-------|--------------|--------|
| Paper, never started, no `lastVirtualCapital` | No Equity/Cash tiles (or single «Нет данных») | — |
| Paper, idle, `lastVirtualCapital` set | Equity ≈ Cash ≈ last capital; label paper | `robots_v2.metadata.lastVirtualCapital` |
| Paper, active session | Live ledger equity/cash from session snap | session manager |
| Paper, just stopped | Prefer last session equity/cash if still in process memory; else fall back to `lastVirtualCapital` | **Resolved:** on soft/hard stop, write final ledger equity into `metadata.lastVirtualCapital` when available (cheap); idle then shows end-of-session capital |

### Live idle semantics (normative)

| State | What to show | Source |
|-------|--------------|--------|
| Live, no `tokenId` | No balance (error/empty) | — |
| Live, idle, broker OK | Cash + Equity, source `broker`, label «Счёт» | existing idle fetch + 20s cache |
| Live, idle, broker timeout/fail | Last cached broker snap if any; else empty + message | cache / `positionsSource` |
| Live, active | Session snap (broker-backed per ADR) | `positionsSource: session` |

---

## 4. Non-functional

| Topic | Requirement |
|-------|-------------|
| Latency | Idle broker fetch already capped (~6s timeout, 20s TTL). P0 must not add a second uncapped broker call from the UI. |
| Tenancy | Status remains scoped by authenticated `user_id` + robot ownership (unchanged). |
| Audit | No new audit tables for P0 balance display. |
| Risk / honesty | Mislabeling paper as live account is a **P0 defect**. Whole-account live funds disclaimer is required copy, not optional tooltip-only. |
| Mobile | Desktop-first; mobile must not break — balance row stacks with existing summary grids. |

---

## 5. Data model `[ref: R-3, R-8, R-10]`

### 5.1 Existing (no migration required for P0 core)

| Store | Use |
|-------|-----|
| `robots_v2.metadata.lastVirtualCapital` | Paper idle capital (already written on launch) |
| In-memory session snap `equity` / `cash` | Active session |
| In-process `_IDLE_BROKER_CACHE` | Idle live broker cash/equity/positions |

### 5.2 Paper stop persist (P0 required — resolved 2026-10-05)

| Field | Type | Notes |
|-------|------|--------|
| `metadata.lastVirtualCapital` | number | On paper soft/hard stop, set to final ledger equity (or cash if flat) so idle reflects end-of-session, not only start capital `[ref: R-3]` |
| `metadata.lastPaperEquityAt` | ISO timestamptz string | Optional freshness for UI |

**No new tables for P0.**

### 5.3 P1 (day equity)

| Approach | Notes |
|----------|--------|
| Derive from first cycle equity of trading day in audit | Only if query is cheap and already indexed |
| Or stamp `dayStartEquity` into session when `begin_trading_day` runs | Session-only; idle would need last stamp in metadata |

Mark **P1** — do not block P0.

---

## 6. API and WebSocket contracts `[ref: R-1…R-9]`

### 6.1 `GET /api/v2/robots/{robot_id}/status` (additive)

| Field | Value |
|--------|--------|
| Auth | Existing bearer / session |
| Idempotency | n/a (GET) |
| Breaking changes | **None** — additive fields; existing `equity`/`cash` remain |

**Response additions / clarifications** (`RobotV2StatusResponse`, `extra="allow"` already):

| Field | Type | When | `[ref]` |
|-------|------|------|---------|
| `equity` | `number \| null` | Session; idle live broker; idle paper last capital | `[R-1]` |
| `cash` | `number \| null` | Same | `[R-1]` |
| `balanceSource` | `"session" \| "broker" \| "paper_last" \| null` | Machine source for labels | `[R-8]` |
| `balanceAsOf` | ISO string \| null | `positionsUpdatedAt` or metadata timestamp | `[R-4]` |
| `lastVirtualCapital` | `number \| null` | Paper (idle or active echo) | `[R-3]` |
| `dayStartEquity` | `number \| null` | **P1 only** | `[R-10]` |
| `dayEquityDelta` | `number \| null` | **P1 only** | `[R-10]` |

**Idle paper P0 behavior (backend):** when no session and `mode == "paper"`:

```json
{
  "robotId": 13,
  "sessionState": null,
  "mode": "paper",
  "message": "No active session",
  "cash": 1000000,
  "equity": 1000000,
  "balanceSource": "paper_last",
  "lastVirtualCapital": 1000000,
  "balanceAsOf": null,
  "openPositions": [],
  "positionsSource": null
}
```

**Idle live (already largely true):** ensure `balanceSource: "broker"` when cash/equity come from idle fetch; keep `positionsSource: "broker"`.

**Active session:** `balanceSource: "session"` (even if underlying marks are broker).

### 6.2 Errors / empty

| Case | HTTP | Body fields |
|------|------|-------------|
| Robot not found / not owned | 404 | unchanged |
| Idle live broker fail | 200 | `equity`/`cash` null, `balanceSource` null, `message` explains |
| Paper never capitalized | 200 | null balances |

### 6.3 WebSocket

No new channel. While session active, existing equity updates continue. Idle Monitor relies on status poll (existing page behavior).

### 6.4 Versioning

Same `/api/v2/robots` prefix; additive only.

---

## 7. Sequence / C4

```mermaid
sequenceDiagram
  autonumber
  participant UI as Monitor UI [ref: R-1]
  participant API as GET status [ref: R-2]
  participant SM as SessionManager
  participant DB as robots_v2 metadata
  participant BR as Broker adapter

  UI->>API: GET /robots/{id}/status
  alt active session
    API->>SM: status(robot_id)
    SM-->>API: equity, cash, cycle…
    API-->>UI: balanceSource=session
  else idle live + tokenId
    API->>DB: load robot
    API->>BR: idle portfolio snapshot (cached ≤20s)
    BR-->>API: cash, positions → equity
    API-->>UI: balanceSource=broker
  else idle paper
    API->>DB: metadata.lastVirtualCapital
    API-->>UI: equity=cash=lastVirtual, balanceSource=paper_last
  end
  UI->>UI: Show balance tiles; gate Cycle/Позиции separately
```

---

## 8. Screen inventory (no pixels) `[ref: R-1, R-4, R-5, R-6, R-7]`

**Page:** Robot V2 Monitor (`RobotV2MonitorPage`)  
**Zone:** `MonitorSummaryCard` — «Сводка за день · {date}»

| Zone | Content | Data | States |
|------|---------|------|--------|
| A — Day trade strip | Сделки, Сумма +, Сумма −, Дельта | Existing day stats from round-trips | Loading / loaded (unchanged) |
| B — Balance strip (**new always-on when data**) | Equity, Cash (RU labels per source) | `equity`, `cash`, `balanceSource`, `balanceAsOf` | Hidden if both null; loading inherits `statusLoaded`; broker stale: show value + optional freshness |
| C — Session ops strip | Cycle, Позиции | session-only | **Resolved P0:** Cycle/Позиции session-gated only — idle live position count does **not** appear in summary `[R-6]` |
| D — Placeholder | Replaces **only** zone C when idle/syncing | — | «Робот не работает» / «Робот синхронизируется» — **must not** replace zone B when balances exist `[R-12]` |

**Copy keys (designer finalizes RU):**

| `balanceSource` | Equity label | Cash label | Footnote |
|-----------------|--------------|------------|----------|
| `session` + mode live | Equity · Счёт | Cash · Счёт | Optional short note: средства брокерского счёта |
| `broker` | Equity · Счёт | Cash · Счёт | «Счёт брокера · робот не выделяет отдельный баланс» |
| `paper_last` | Equity · Paper | Cash · Paper | «Последний бумажный капитал · не живой счёт» |
| `session` + mode paper | Equity · Paper | Cash · Paper | — |

**P1 zone (optional):** Day equity start + Δ day under zone B.

**Empty/error:**

- Status loading: keep «Загрузка…» for zone A; zone B waits for status.
- No balance: omit B or one-line «Баланс недоступен».
- Do not show `0` / `0` as success for missing broker/paper data `[R-7]`.

---

## 9. Acceptance criteria

### Backend

- [ ] Idle live + token: `equity`/`cash` present on 200 when broker snap OK; `balanceSource=broker`.
- [ ] Idle paper + `lastVirtualCapital`: `equity`/`cash`/`lastVirtualCapital` present; `balanceSource=paper_last`.
- [ ] Idle paper without capital: balances null, not `0` pretending to be account.
- [ ] Active session: unchanged numeric meaning; `balanceSource=session`.
- [ ] No auth/billing changes.
- [ ] Paper stop updates `lastVirtualCapital` from final ledger equity when available (**required** — resolved 2026-10-05).

### UI

- [ ] Equity/Cash visible for idle live when API returns them (Robot #13-class).
- [ ] Equity/Cash visible for idle paper with paper labels / footnote.
- [ ] «Робот не работает» does **not** hide available balances.
- [ ] Cycle/Позиции still session-gated per `[R-6]`.
- [ ] Live copy communicates whole-account («Счёт») limitation.
- [ ] Missing balances do not render as fake zeros.
- [ ] Mobile layout: summary grids remain usable (no horizontal clip of tiles).

### E2E / manual

- [ ] Live robot stop → Monitor still shows broker cash/equity within cache/timeout policy.
- [ ] Paper robot stop → Monitor shows last paper capital with paper labeling.
- [ ] Start session → numbers switch to session source without UI flicker bugs (brief loading OK).

---

## 10. Open questions — RESOLVED (defaults locked 2026-10-05)

| Topic | Resolution |
|-------|------------|
| Paper stop → `lastVirtualCapital` | **YES** — on soft/hard stop, write final ledger equity into `metadata.lastVirtualCapital` when available |
| Idle live «Позиции» in summary | **NO for P0** — Cycle/Позиции remain session-gated only |
| P1 day-start equity source | **Deferred to P1** after P0 ships (audit/cycle vs metadata stamp TBD then) |
| RU footnote copy | **Designer owns** final strings; §8 label keys remain normative intent |

---

## 11. Handoff

**Designer gets:** §8 zones A–D, label matrix, empty/error rules, split of balance vs «Робот не работает».  
**Backend gets:** §5–§7 — idle paper fields, `balanceSource`, **required** stop-time `lastVirtualCapital` update, acceptance.  
**UI gets:** contracts §6 + approved UX; change `showSessionStats` gating so balance is independent.

✅ SPEC ready: docs/SPEC-04-monitor-day-summary-balance.md

**Designer gets**: screen inventory (§8), user flows, empty/error states  
**Backend gets**: data model (§5), API/WS (§6), sequences (§7)  
**UI gets**: contracts (§6) + will wait for approved UX spec

Open questions: none for P0 (see §10 RESOLVED).
