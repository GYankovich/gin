# UX-08: Robots V2 — Live cockpit redesign

**Baselines:** [UX-04](UX-04-robots-v2-visual-alignment.md) (chrome/primitives), [UX-05](UX-05-glass-box-backtest-results.md) (backtest results), [UX-06](UX-06-monitor-day-summary-balance.md) (day/balance strips), [UX-07](UX-07-backtest-lab.md) (Lab zones).  
**Mockup (locked visual ref):** [mockups/robots/b-live-cockpit.html](mockups/robots/b-live-cockpit.html) + [mockups/robots/b-gin-skin.css](mockups/robots/b-gin-skin.css)  
**Chosen option: B — Live cockpit**  
**Viewport:** desktop-first **≥1440**; mobile stacks (must not break), not a design priority.

Redesign of existing `/robots` surfaces — **no new HTTP paths**. Prefer existing API field names (`sessionState`, `equity`, `cash`, `balanceSource`, …).

---

## Goal

Make Robots operational for traders:

1. **Fleet** answers “what’s on fire?” in one glance (KPI strip + dense table).
2. **Monitor** is a **cockpit**: P&L / status / equity / live feed above the fold; positions & orders primary; universe scan secondary.
3. **Audit** stops competing with the live event stream.
4. **Backtest + Lab** share one chrome family (segmented Робот | Лаборатория), keep glass-box results.

---

## Layout (zones)

### Fleet — `/robots`

```text
+-- RobotPageChrome / PageHero (ROBOT COMMAND · ФЛОТ) ----------+
| actions: filter SegmentedControl · Лаборатория · Создать      |
+----------------------------------------------------------------+
| A  Fleet KPI strip (dashboard-totals-card + StatTile ×6)       |
|    В работе · Ошибки · Δ дня флота · Экспозиция · Ожидают ·    |
|    Опросники                                                   |
+----------------------------------------------------------------+
| B  Trading robots DataTable (mockup B rows)                     |
|    status · name#id · mode · archetype · session · Δ · equity  |
|    · pos · activity · Запуск/Пауза · Правка · ⋯                 |
+----------------------------------------------------------------+
| C  Questionnaires DataTable (same dense row style as B)         |
+----------------------------------------------------------------+
```

**Desktop:** KPI always visible; trading + questionnaires = **dense tables** (Option B).  
**Row click (trading):** → `/robots/:id/monitor`. Questionnaire row → edit.

If list API lacks dayΔ/equity → show `—` and `[GAP]` (do not invent numbers).

---

### Monitor — `/robots/:id/monitor` (primary)

```text
+-- RobotPageChrome (LIVE COCKPIT · name) -----------------------+
| subnav: Флот · Лайв · Правка · Audit · Бэктест                 |
| actions: Мягкая / Жёсткая | Запуск                             |
+----------------------------------------------------------------+
| COCKPIT GRID (≥1440)                                           |
| K  KPI strip full width (Δ дня · Equity · Cash · Цикл ·        |
|    Позиции · Заявки open) — merges UX-06 day+balance+session   |
|    into one scannable row; keep balance footnote under K if    |
|    balanceSource needs honesty                                 |
+--------+---------------------------+---------------------------+
| S Stage| C Equity chart            | F Live stream + Decisions |
| card   | (dashboard-assets-card)   | (right column, sticky-ish)|
+--------+---------------------------+---------------------------+
| T1 Positions DataTable  |  T2 Orders/round-trips DataTable     |
| Universe scan = CollapsibleSection under T2 (default closed)   |
+----------------------------------------------------------------+
```

```text
Mobile / narrow: K → S → C → T1 → T2 → F → Universe collapse
```

**Hard rule:** On ≥1440 first paint, **K + S + C + F** visible without scrolling when possible; T1/T2 immediately below.

Replace today’s equal-weight 2-col dump (`MonitorUniverse` / `Decisions` / `Events` all peers) with this hierarchy.

---

### Audit — `/robots/:id/logs` (rename chrome label «Audit»)

```text
RobotPageChrome active=logs (label «Audit»)
Toolbar: SegmentedControl — Исполнения | Заявки | Циклы
  ❌ Remove «Поток» as primary peer (or demote to last + banner:
     «Живой поток — на Лайве»)
Tables: DataTable as today
Optional: row → inspector side panel (desktop) with fill/order fields
Export / Refresh stay in hero actions
```

Route path may stay `/logs`; **UI copy** = Audit.

---

### Backtest robot + Lab chrome

```text
Same RobotPageChrome family OR Lab PageHero with node classes
Hero SegmentedControl: [Робот #id] | [Лаборатория]
  · Робот → current RobotV2BacktestPage launch + filtered history
  · Лаборатория → navigate /robots/backtest (UX-07 L1–L4)

Results: BacktestResultsPanel unchanged composition (UX-05)
History: BacktestHistoryCard; escape «Все прогоны в Lab» kept when on robot tab
Optimization card: secondary, below history or collapsed
```

Do **not** redesign glass-box zones A–P here; only chrome + entry.

---

### Wizard — `/robots/new`, `/robots/edit/:id`

Keep 3-column shell (steps | form | summary). Visual only: use `dashboard-totals-card` surfaces, node hero, primary cyan Save. Advanced strategy fields under CollapsibleSection. No IA change required for B lock.

---

## Components (map to existing primitives)

| Zone / widget | Primitive |
|---------------|-----------|
| Hero + subnav | `PageHero` / `RobotPageChrome` (`dashboard-hero--node`) |
| Fleet/Lab/Create cfg | `Button` `dashboard-hero__cfg` / primary `btn--sm` |
| Confirm hard-stop/delete | `RobotConfirmModal` |
| Fleet / monitor KPIs | `StatTile` in `dashboard-totals-card` + `portfolio-stats-grid` |
| Stage | `RobotStageCard` |
| Equity | `Chart` via `MonitorEquityChart` / existing Chart wrapper; colors from `--color-up` |
| Tables | `DataTable` |
| Filters / period / audit source | `SegmentedControl` |
| Live stream / decisions | refactor `MonitorEventsCard` + `MonitorDecisionsCard` into right column |
| Universe | `MonitorUniverseCard` inside `CollapsibleSection` |
| Positions / orders | `MonitorPositionsCard` / `MonitorOrdersCard` |
| Backtest results | `BacktestResultsPanel` (UX-05) |
| Lab launch | UX-07 `LabConfigForm` + history |
| Badges / PnL | `Badge`, `robots-v2-pnl--up/down` |
| Empty / error | `dashboard-empty`, `dashboard-error-card` + retry |
| Loading | `Skeleton` / existing fleet/monitor skeletons |

**Do not use:** Analytics `KpiTile`.

---

## Interaction map

| Action | Result |
|--------|--------|
| Fleet row click (trading) | Navigate monitor |
| Fleet status / start-stop | Existing menus; hard-stop → Modal |
| Fleet filter chips | Client filter by session/mode (no new API) |
| Monitor Start / Soft / Hard | Unchanged semantics; Hard → Modal |
| Monitor KPI | Display-only |
| Stream offline | Badge «стрим офлайн» on feed + hero; REST poll fallback copy (RU) |
| Audit row click | Optional inspector panel; deep-link hint to Лайв |
| Backtest segment Lab | `/robots/backtest` |
| Backtest segment Robot | Stay on `/robots/:id/backtest` |
| History open run | Existing `?run=` / panel open |
| Keyboard (P1) | Monitor: none required P0; Lab keep `r`/`n` from UX-07 |

---

## States

| State | UI |
|-------|-----|
| Loading | Skeleton in KPI + table/chart placeholders; hero copy stays |
| Empty fleet | `dashboard-empty` in groups + Create CTA |
| Empty positions/orders | DataTable `emptyText` RU |
| Error list/status | `dashboard-error-card` + Повторить; toast OK for transient WS |
| WS connected | Badge `badge--up` «стрим» |
| WS offline | `badge--neutral` «стрим офлайн» + feed empty copy |
| Stale positions | Caption «обновлено N с» / warn if age > threshold when API gives stamp |
| Idle session | KPI still shows day + balance (UX-06); stage/placeholder for session ops |
| Syncing | Badge «Синхронизация»; session ops placeholder |
| Balance unavailable (live) | Footnote / one-line as UX-06 |

---

## Token notes

- Page: `data-page="robots"`, dark default `data-theme`.
- Surfaces: `var(--bg-card)`, `var(--border-subtle)`, `var(--radius-lg)` — solid cards, **no** Analytics glow tiles.
- Hero: `dashboard-hero--node` (no full cyber bg on robots — match UX-04).
- PnL: `--color-up` / `--color-down` (no hardcoded chart hex in new code).
- Primary CTA: cyan `btn--primary`; destructive: `btn--danger`; chrome nav: `dashboard-hero__cfg` + active cyan border.
- Density: StatTile mono values; table `text-xs`; cockpit gap `space-3`–`space-4`.

---

## Copy (RU)

| Place | Copy |
|-------|------|
| Fleet eyebrow | `ROBOT COMMAND` (or keep `ROBOT NODE` if product prefers continuity) |
| Fleet title | `ФЛОТ` |
| Monitor eyebrow | `LIVE COCKPIT` / `LIVE NODE` |
| Chrome tab logs | `Audit` (was «Логи») |
| Stream badges | «стрим» / «стрим офлайн» (not `online` / `WS`) |
| Stage meta | «триггер» not `wake` in user-facing strings |
| Session KPI | «Цикл» not `Cycle` |
| Audit banner | «Живой поток — на вкладке Лайв» |
| Fleet empty | «Нет торговых роботов» / «Нет опросников портфеля» |
| Cockpit feed empty (idle) | «Сессия не запущена — нажмите «Запуск»» |
| Cockpit feed empty (running, offline) | «Стрим офлайн — события по REST» |

Keep `sessionStateLabel` and status RU from `formatters.ts`.

---

## Phased delivery (for UI engineer)

### Phase 0 — quick wins (can ship without fleet aggregates API)

- RU copy pass (stream, цикл, триггер, Audit label).
- Chart series colors → CSS variables / theme.
- Monitor hero stream badge (replace EN `online`).
- Logs: demote/remove Поток peer; banner to Лайв.
- Skeleton polish on Audit tables.

### Phase 1 — structural B

- Fleet KPI strip + trading **cards** layout (placeholder `—` where GAP).
- Monitor CSS grid cockpit (K/S/C/F/T1/T2) + universe collapse.
- Backtest hero SegmentedControl Робот | Лаборатория.
- Wizard card surface alignment only.

### Phase 2

- Fleet search/sort; monitor freshness captions; audit inspector drawer; optional keyboard.

---

## Out of scope for UI engineer

- New REST/WS endpoints or field renames.
- Option C global IA (Флот|Lab as only module tabs; deleting `/logs` route) — not in B lock.
- UX-05 P2 glass-box product debate (already in code — separate sign-off).
- Mobile-first redesign.
- Production changes outside `frontend/src/pages/robots-v2/**` and shared UI primitives as needed for layout.

---

## Gaps for analyst / backend

- `[GAP: fleet list fields — day PnL (Δ дня), equity, open positions count, last error / skip reason per robot]`
- `[GAP: fleet aggregates — counts by sessionState, sum day Δ, exposure]` — else client-only from enriched list
- `[GAP: explicit stale threshold or server clock for positionsUpdatedAt / equity as-of]` — for honest «устарело»
- Soft: Audit inspector needs no new API if row payload already in audit responses

Placeholder rule: missing GAP fields → `—` / omit tile / muted hint «нет в списке», never fake zeros.
