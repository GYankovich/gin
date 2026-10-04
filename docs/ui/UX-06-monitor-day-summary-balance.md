# UX-06: Monitor day summary — balance vs session-ops

SPEC: docs/SPEC-04-monitor-day-summary-balance.md  
Chosen option: **single layout** (small surface; no A/B/C)  
Surface: `/robots/:id/monitor` — `MonitorSummaryCard` («Сводка за день») inside `RobotV2MonitorPage`  
Viewport: desktop-first **≥1440**; mobile must stack without clipping tiles

---

## Layout (zones)

Keep one `Card` (`dashboard-totals-card`). Split the former single session grid into **independent** strips so idle «Робот не работает» never hides balance.

```text
MonitorSummaryCard
├── Head: «Сводка за день · {dayLabel}»
├── A  Day trade strip     (always when statusLoaded; else «Загрузка…»)
├── B  Balance strip       (when equity and/or cash present; else omit or one-line empty)
├── Bƒ Footnote            (one line under B when balanceSource needs honesty)
└── C  Session-ops strip   (Cycle + Позиции when session active & !syncing)
    OR D Placeholder       («Робот не работает» / «Робот синхронизируется») — replaces C only
```

### Desktop (≥1440)

```text
+-- Сводка за день · 5 окт 2026 --------------------------------------+
| [Сделки] [Сумма +] [Сумма −] [Дельта]          ← zone A (4 StatTiles) |
| [Equity · Счёт] [Cash · Счёт]                  ← zone B (1–2 tiles)  |
|  Счёт брокера · робот не выделяет отдельный баланс  ← Bƒ footnote   |
| [Cycle] [Позиции]   OR   «Робот не работает»   ← zone C / D          |
+---------------------------------------------------------------------+
```

Idle live with broker OK: **A + B + Bƒ + D** (no Cycle/Позиции).  
Active session: **A + B + (optional short Bƒ) + C**.  
Idle paper with `paper_last`: **A + B + paper Bƒ + D**.

### Mobile (must not break)

```text
A → B → Bƒ → C|D   (single column)
Each strip: existing portfolio-stats-grid / robots-v2-*-stats wraps to 2×2 then 1-col
No horizontal clip; footnote wraps under tiles
```

---

## Components (named → existing primitives)

| Zone | Widget | Map to |
|------|--------|--------|
| Card shell | Day summary | `MonitorSummaryCard` → `Card` `dashboard-totals-card` |
| Head | Title | `dashboard-totals-card__head` + `dashboard-panel-title` |
| A | Day trade KPIs | `portfolio-stats-grid dashboard-summary-grid robots-v2-day-stats` + `StatTile` (unchanged labels) |
| B | Equity / Cash | **New** grid `robots-v2-balance-stats` + `StatTile` — independent of session gate |
| Bƒ | Source honesty | `p` / caption under B (`dashboard-empty` tone or quieter mono caption — match existing monitor secondary text) |
| C | Cycle, Позиции | `robots-v2-session-stats` + `StatTile` — **only** these two tiles (Equity/Cash removed from this grid) |
| D | Idle / syncing | Existing `robots-v2-session-placeholder` copy — **must not** wrap or replace B |

### Props contract (UI engineer — extend `MonitorSummaryCard`)

Replace boolean `showSessionStats` as the sole gate with explicit strips:

| Prop | Role |
|------|------|
| Existing day-trade props | Zone A unchanged |
| `showBalance` | `true` when at least one of equity/cash is a finite number from status |
| `equityLabel` / `cashLabel` | Formatted strings; omit individual `StatTile` if that field is null |
| `equityTileLabel` / `cashTileLabel` | RU labels from `balanceSource` matrix below |
| `balanceFootnote` | `string \| null` — Bƒ |
| `balanceAsOfLabel` | Optional freshness suffix in footnote (e.g. «обновлено …») when `balanceAsOf` present |
| `showSessionOps` | Cycle + Позиции only — today’s `statusLoaded && isActive && !isSyncing` |
| `isSyncing` | Drives D copy when `!showSessionOps` |
| `cycle` / `positionsCount` | Session-ops values |

Parent (`RobotV2MonitorPage`) maps `GET …/status` fields: `equity`, `cash`, `balanceSource`, `balanceAsOf`, `mode` — do not infer live vs paper from mode alone when `balanceSource` is present `[R-8]`.

**Do not** render `fmtNum(0)` / `"0"` when values are null — omit tile or show empty strip message `[R-7]`.

---

## Interaction map (clicks, keyboard)

| Action | Result |
|--------|--------|
| Status poll / WS equity update (active) | Zone B numbers refresh in place; labels stay tied to `balanceSource` |
| Idle → Start → active | B may switch `broker`/`paper_last` → `session`; brief loading OK; avoid flicker to fake zeros |
| Stop → idle | B remains if API still returns cash/equity; C swaps to D |
| Click tiles | None (display-only; no drawer) |
| Keyboard | No new shortcuts; page refresh behavior unchanged |

---

## States (loading / empty / error / stale)

| State | Zone A | Zone B | Zone C/D |
|-------|--------|--------|----------|
| Status not loaded | «Загрузка…» | Hidden | Hidden |
| Loaded, balances present | Day stats | Equity/Cash tiles + Bƒ | C if active; else D |
| Loaded, both equity & cash null | Day stats | Omit B **or** one-line «Баланс недоступен» (prefer omit when never capitalized paper / no token; use one-line when live token expected but broker failed) | C or D |
| Syncing + balances known | Day stats | Keep last known B | D: «Робот синхронизируется» — **do not** hide B `[R-12]` |
| Broker stale (cached idle snap) | Day stats | Show values; Bƒ may append freshness from `balanceAsOf` | D if idle |
| Paper never started | Day stats | No fake zeros — omit B | D |

Error honesty: live without token / broker fail → null balances + empty message, never `0`/`0` that look like an empty account.

---

## Token notes (up/down, density)

- Day strip P&L: keep `robots-v2-pnl--up/down/neutral` on Сумма +/− and Дельта.
- Equity / Cash: **neutral** value color (account size, not day P&L). Do not tint green/red solely because source is broker.
- Density: same `StatTile` / `portfolio-stat-tile` as today; balance strip may be 2 tiles (not stretch to 4 empty slots).
- Surfaces: `var(--bg-card)`, borders as sibling monitor cards; no new palette.

---

## Copy (labels, empty-state text) — RU final

### Zone A (unchanged)

| Tile | Label |
|------|-------|
| Trades | Сделки |
| Gross plus | Сумма + |
| Gross minus | Сумма − |
| Net day | Дельта |

### Zone B — tile labels by `balanceSource`

| `balanceSource` | Equity `StatTile.label` | Cash `StatTile.label` |
|-----------------|-------------------------|------------------------|
| `broker` | Equity · Счёт | Cash · Счёт |
| `session` + live mode | Equity · Счёт | Cash · Счёт |
| `session` + paper mode | Equity · Paper | Cash · Paper |
| `paper_last` | Equity · Paper | Cash · Paper |
| null / unknown with numbers | Equity | Cash |

If only one of equity/cash is non-null, show that single tile with the same label pattern.

### Zone Bƒ — footnotes (required honesty)

| `balanceSource` | Footnote |
|-----------------|----------|
| `broker` | Счёт брокера · робот не выделяет отдельный баланс |
| `session` + live | Средства брокерского счёта |
| `paper_last` | Последний бумажный капитал · не живой счёт |
| `session` + paper | Бумажный капитал сессии |
| null + empty line shown | Баланс недоступен |

Optional freshness: append ` · обновлено {local time}` when `balanceAsOf` is set (idle broker cache / `lastPaperEquityAt`).

### Zone C / D

| Tile / state | Copy |
|--------------|------|
| Cycle | Cycle |
| Positions | Позиции |
| Idle placeholder | Робот не работает |
| Syncing placeholder | Робот синхронизируется |

### Empty / error one-liners

| Case | Copy |
|------|------|
| Live, no token / broker fail, no cache | Баланс недоступен |
| Paper, never capitalized | *(omit B — no line)* |
| Loading status | Загрузка… |

---

## Out of scope for UI engineer

- P1 day-start equity / day equity delta tiles (`dayStartEquity`, `dayEquityDelta`) — placeholder only if product later unlocks; do not implement in P0.
- New WebSocket channel for idle balance.
- Token / billing / auth UX.
- Showing idle live position count in zone C (SPEC default: session-gated only).
- Changing day trade stats computation.

---

## Gaps

None for P0 display if backend ships `equity` / `cash` / `balanceSource` / `balanceAsOf` / `lastVirtualCapital` per SPEC-04 §6. UI must not invent parallel field names.
