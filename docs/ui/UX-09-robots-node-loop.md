# UX-09: Robots node loop — VIEW · CONFIG · BACKTEST LAUNCH

**SPEC / baselines:** [UX-04](UX-04-robots-v2-visual-alignment.md) (chrome), [UX-05](UX-05-glass-box-backtest-results.md) (results zones A–P), [UX-06](UX-06-monitor-day-summary-balance.md) (day/balance honesty), [UX-07](UX-07-backtest-lab.md) (Lab), [UX-08](UX-08-robots-v2-live-cockpit.md) (Option B IA).  
**Stitch lock:** [STITCH-09](STITCH-09-robots-backtest.md) — Fleet compact `2b549ecb…` · Backtest calm `6815d6ce…` · aligned Live / Audit / Lab / Create.  
**Chosen visual:** **Locked Stitch quiet language** (not UX-08 KPI tile strips).  
**Viewport:** desktop-first **≥1440**; Russian UI; GIN dark terminal tokens.  
**Routes (no new HTTP paths):** `/robots`, `/robots/:id/monitor`, `/robots/:id/logs`, `/robots/edit/:id`, `/robots/new`, `/robots/:id/backtest`, `/robots/backtest`.

---

## Goal

One coherent **node loop** for a trading robot:

1. **Просмотр** — Live Cockpit answers “is it healthy?” with status + equity as the single above-the-fold focus.  
2. **Настройка** — calm wizard/edit; escape back to Лайв or Бэктест without dashboard noise.  
3. **Запуск бэктеста** — robot-scoped launch → quiet results (glass-box content, calm chrome) → history → Lab when the run is not about this robot.

Fleet (`/robots`) is the **entry list** (Stitch compact rows). This doc owns the three node screens; Fleet visual rules apply to any run/robot list on those screens.

---

## Visual lock (supersedes UX-08 KPI strips)

| Rule | Do | Don’t |
|------|----|--------|
| Metrics | Quiet **meta line** ≤3–4 numbers (text, mono) | `StatTile` / KPI tile strips on Fleet, Monitor, Backtest launch chrome |
| Focus | One primary focus per viewport (chart **or** table **or** form) | Equal-weight card dump |
| Accent | Cyan only on **primary CTA** + **running** state | Neon, badge clusters, glow |
| Surfaces | Flat panels, hairline dividers | Multi-shadow cards, Analytics `KpiTile` |
| Lists | Fleet compact row language | Card grids of robots/runs |

**UX-05 glass-box:** keep zones **A–P** and inspector **F**. Present zone **B** scoreboard as a **quiet meta metrics line** (same fields, no tile strip). Trades table stays quiet under the large equity chart (Stitch calm).

**UX-08 Option B:** keep cockpit **IA** (stage · chart · feed · positions/orders · universe collapse). Replace zone **K** StatTile strip with quiet meta. Fleet KPI strip from UX-08 is **out** — Fleet follows Stitch compact only.

---

## IA — node loop

```text
                    ┌─────────────┐
                    │  /robots    │  Флот (compact rows)
                    │  entry list │
                    └──────┬──────┘
                           │ row → Лайв
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌─────────────────┐
    │ VIEW       │  │ CONFIG     │  │ BACKTEST LAUNCH │
    │ /monitor   │◄─┤ /edit/:id  │─►│ /:id/backtest   │
    │            │  │ /new       │  │                 │
    └─────┬──────┘  └────────────┘  └────────┬────────┘
          │  subnav                          │ «Все прогоны в Lab»
          │  Флот·Лайв·Правка·Audit·Бэктест  ▼
          │                           /robots/backtest (UX-07)
          └── Audit /logs (stream stays on Лайв)
```

**Mental model**

| Mode | Question | Primary focus |
|------|----------|---------------|
| VIEW | Работает ли? Что в рынке? | Equity chart + status meta |
| CONFIG | Что торгует и с какими лимитами? | Form step |
| BACKTEST | Как бы отработал на истории? | Launch form → then equity results |

---

## Shared chrome

**Primitive:** `RobotPageChrome` → `PageHero` (`dashboard-hero--node`).

| Context | eyebrow | title | subnav | hero actions |
|---------|---------|-------|--------|--------------|
| Monitor | `LIVE COCKPIT` | robot name | Флот · Лайв · Правка · Audit · Бэктест | Мягкая / Жёсткая · **Запуск** (cyan when startable) |
| Edit | `SETUP NODE` | robot name / «Правка» | full set, active=edit | optional «На Лайв» / «Бэктест» text links in subtitle |
| Create | `SETUP NODE` | «Новый робот» | `fleetOnly` → only Флот | — |
| Robot backtest | `BACKTEST` | robot name | full set, active=backtest | **Запустить** / Отменить; scope `[Робот] \| [Лаборатория]` |
| Audit | `AUDIT` | robot name | full set, active=logs | Export · Refresh |
| Fleet | `ROBOT COMMAND` / continuity `ROBOT NODE` | `ФЛОТ` | — (PageHero, not detail tabs) | Лаборатория · Создать |

**Active tab:** cyan border on `dashboard-hero__cfg` (`robots-v2-chrome-nav--active`) — not a filled pill cluster.

**Confirm:** `RobotConfirmModal` for hard-stop / delete (never `window.confirm`).

---

## 1. VIEW — Live Cockpit `/robots/:id/monitor`

### Zones (≥1440)

```text
+-- RobotPageChrome (LIVE COCKPIT · name) ---------------------------+
| subnav · actions: Мягкая | Жёсткая | Запуск                        |
| stream badge: «стрим» / «стрим офлайн»                             |
+--------------------------------------------------------------------+
| M  Quiet meta line (≤4): Δ дня · Equity · Cash · Цикл              |
|    footnote: balanceSource / «обновлено …» (UX-06 honesty)         |
|    optional muted: позиции N · заявки N (text, not tiles)          |
+--------+-----------------------------------+-----------------------+
| S Stage| C Equity chart (PRIMARY FOCUS)    | F Live + Decisions    |
| card   | dashboard-assets-card             | compact column        |
| narrow |                                   | sticky-ish            |
+--------+-----------------------------------+-----------------------+
| T1 Positions DataTable  |  T2 Orders / round-trips DataTable       |
| Universe scan = CollapsibleSection under T2 (default closed)       |
+--------------------------------------------------------------------+
```

**Above the fold:** chrome + **M** + **S|C|F**. Chart is the hero; meta is a single hairline row under the hero — **not** `MonitorSummaryCard` StatTile grid.

**Hierarchy**

1. Session / run state (stage + cyan “running” if applicable)  
2. Quiet P&L / balance meta  
3. Equity curve  
4. Live stream + recent decisions (secondary, scannable)  
5. Positions / orders (primary tables below)  
6. Universe scan (collapsed)

### Components

| Zone | Map to |
|------|--------|
| Chrome | `RobotPageChrome` `active=monitor` |
| Meta M | Refactor `MonitorSummaryCard` → quiet meta line (same fields: day Δ, equity, cash, cycle; drop `portfolio-stats-grid` / `StatTile`) |
| Stage | `RobotStageCard` |
| Chart | `MonitorEquityChart` + `Chart` / theme colors |
| Feed | `MonitorEventsCard` + `MonitorDecisionsCard` (right column) |
| Tables | `MonitorPositionsCard` / `MonitorOrdersCard` → `DataTable` |
| Universe | `MonitorUniverseCard` in `CollapsibleSection` |
| Hard stop | `RobotConfirmModal` |
| Decision deep-dive | `DecisionInspectorDrawer` (optional P1) |

### Interactions

| Action | Result |
|--------|--------|
| Запуск | Existing start semantics; CTA cyan |
| Мягкая / Жёсткая | Soft stop immediate; Hard → modal |
| Meta | Display-only |
| Decision / event row | Optional inspector; no navigation away |
| Subnav Правка / Бэктест / Audit | Navigate; stream stays conceptual home on Лайв |
| WS offline | Badge «стрим офлайн» + feed empty «Стрим офлайн — события по REST» |

### States

| State | UI |
|-------|-----|
| Loading | Skeleton under meta + chart placeholder; hero stays |
| Idle session | Meta still shows day/balance; feed «Сессия не запущена — нажмите «Запуск»» |
| Running | Cyan accent on stage / status; chart updates |
| Empty positions/orders | DataTable `emptyText` RU |
| Error status | `dashboard-error-card` + Повторить |
| Stale | Caption «обновлено N с» / warn when stamp age known |
| Syncing | Muted «Синхронизация» |
| Balance unavailable | One-line UX-06 empty — never fake zeros |

### Copy (RU)

- Eyebrow `LIVE COCKPIT`; tab «Лайв»; Audit tab label «Audit»  
- «стрим» / «стрим офлайн»; «Цикл»; «триггер» (not wake)  
- Keep `sessionStateLabel` from `formatters.ts`

---

## 2. CONFIG — Edit / Wizard `/robots/edit/:id`, `/robots/new`

### Zones

```text
+-- RobotPageChrome -----------------------------------------------+
| Create: fleetOnly · Edit: full subnav active=edit                |
| Escape (edit): subtitle links «← Лайв» · «Бэктест»               |
+--------+------------------------------+--------------------------+
| Steps  | Form (PRIMARY FOCUS)         | Summary rail             |
| list   | one step at a time           | name · mode · archetype  |
|        | primary fields always open   | token · risk caps        |
|        | advanced = CollapsibleSection|                          |
+--------+------------------------------+--------------------------+
| Footer CTA: Сохранить / Создать и запустить (cyan primary)       |
+------------------------------------------------------------------+
```

**Calm form language:** flat `Card` / field rows, hairline section dividers, no KPI strip, no live cockpit widgets. One job = current step.

### Steps (existing IA — no new steps)

**Trading** (`TRADING_STEPS`): Основное → Стратегия → Активы → Риск  

**Portfolio sync** (`PORTFOLIO_STEPS`): Основное → Синхрон  

### Primary vs collapsible

| Step | Primary (always visible) | Collapsible / advanced |
|------|--------------------------|------------------------|
| Основное | name, goal/mode, token | — |
| Стратегия | archetype cards, schedule essentials | Fine-tuned strategy params |
| Активы | universe mode + list/index/screener core | Preview pagination extras |
| Риск | capital, position/loss limits, stop mode | EOD / edge-case toggles |
| Синхрон | account + schedule | Advanced sync flags |

### Create vs edit

| | Create `/robots/new` | Edit `/robots/edit/:id` |
|--|----------------------|-------------------------|
| Chrome | `fleetOnly` (Флот only) | Full node subnav |
| CTA | «Создать и запустить» / «Создать синхронизацию» | «Сохранить» · «Сохранить без запуска» · «Сохранить и запустить» |
| Draft | Local restore modal | Load from robot; draft restore if dirty |
| Escape | ← Флот | ← Лайв, Бэктест, Audit via subnav |
| After save+start | → Monitor | → Monitor |
| After save only | → Monitor or Fleet (keep current product behavior) | Stay edit or → Monitor |

### Components

| Widget | Map to |
|--------|--------|
| Chrome | `RobotPageChrome` |
| Steps / fields | `RobotV2WizardPage` + `wizardDraft` |
| Controls | `SegmentedControl`, `Select`, `Toggle`, `WeekdaysMaskField`, `FormLabelTooltip` |
| Surfaces | `Card` flat; `Button` primary cyan on save |
| Restore / delete | `RobotConfirmModal` |
| Loading | `Skeleton` |

### Interactions

| Action | Result |
|--------|--------|
| Step click | Jump step (validate soft; don’t block navigation P0) |
| Сохранить и запустить | Persist + start → `/robots/:id/monitor` |
| Subnav Лайв / Бэктест | Leave form (prompt if dirty — keep existing draft modal pattern) |
| Create cancel | ← `/robots` |

### States

| State | UI |
|-------|-----|
| Loading robot (edit) | Skeleton form |
| Validation error | Inline field errors RU |
| Save error | Toast / banner; stay on step |
| Empty tokens | Select empty + link copy to add token if product already has it |

### Copy

- Eyebrow `SETUP NODE`  
- Step titles from `STEP_COPY`  
- Primary CTA cyan only

---

## 3. BACKTEST LAUNCH — Robot-scoped `/robots/:id/backtest`

### Distinguish robot vs Lab

| | Robot backtest | Lab ([UX-07](UX-07-backtest-lab.md)) |
|--|----------------|--------------------------------------|
| Route | `/robots/:id/backtest` | `/robots/backtest` |
| Config source | **This robot’s** saved config (+ optional param overrides if API already allows) | Настроить · Робот · Прошлый |
| History | Filtered to this robot | All runs + bind badges |
| Chrome | Full `RobotPageChrome` + `[Робот \| Лаборатория]` | Lab hero «Лаборатория» · ← Флот |
| Escape | «Все прогоны в Lab» | Bind «Робот #N» → robot backtest |

Scope control: `SegmentedControl` — **Робот** (stay) · **Лаборатория** (navigate `/robots/backtest`).

### Zones

```text
+-- RobotPageChrome (BACKTEST · name) · [Робот|Лаборатория] ---------+
| actions: Запустить бэктест (cyan) / Отменить                        |
+---------------------------------------------------------------------+
| L  Launch strip (PRIMARY when no results focus)                     |
|    period presets SegmentedControl + DateRangePicker                |
|    capital field · optional param note (robot config is source)     |
|    CTA Запустить                                                    |
+---------------------------------------------------------------------+
| R  Running: RobotStageCard (cyan running)                           |
+---------------------------------------------------------------------+
| Q  Results — BacktestResultsPanel (UX-05 A–P, quiet chrome)         |
|    A honesty · B meta metrics line (≤4–6 key nums as text)          |
|    C anatomy · D LARGE equity chart (focus) · E reject lens         |
|    H quiet trades DataTable · G/I collapses · F inspector drawer    |
+---------------------------------------------------------------------+
| HX History — compact rows (Fleet list language)                     |
|    BacktestHistoryCard; row → ?run= ; «Все прогоны в Lab»           |
|    Optimization card: secondary / collapsed below history           |
+---------------------------------------------------------------------+
```

**Viewport focus rule**

- Before/during run: **L** (form) is primary.  
- After success: scroll/focus **D** equity; launch strip collapses visually to a single toolbar row (period · capital · Run) — not a second dashboard.

### Components

| Zone | Map to |
|------|--------|
| Chrome + scope | `RobotPageChrome` + `SegmentedControl` Робот/Лаборатория |
| Launch | Existing toolbar on `RobotV2BacktestPage` (`DateRangePicker`, capital `robots-v2-field`, presets) |
| CTA | `Button` «Запустить бэктест» |
| Progress | `RobotStageCard` |
| Results | `BacktestResultsPanel` — UX-05 zones; **B** as quiet meta line |
| Scrubber / P2 | `BacktestPriceScrubber`, narrative, lifecycle — only if UX-05 P2 approved |
| History | `BacktestHistoryCard` — row density like Fleet compact |
| Compare | Existing compare in history card |
| Opt | `RobotV2OptimizationCard` secondary |
| Save-as (Lab path) | `SaveAsRobotModal` — Lab-owned; robot page may keep if already wired |

### Interactions

| Action | Result |
|--------|--------|
| Запустить | Existing POST run; disable duplicate; cyan busy |
| Отменить | Cancel queued/running |
| Лаборатория segment | `/robots/backtest` |
| History row | Open results `?run=` |
| «Все прогоны в Lab» | `/robots/backtest` (optional preserve `?run=`) |
| Marker / trade / signal | Open inspector **F** (UX-05) |
| Keyboard | P0 none; Lab keeps `r`/`n` from UX-07 |

### States

| State | UI |
|-------|-----|
| Idle no history | Launch strip + empty history «Нет прогонов для этого робота» |
| Queued / running | StageCard + cyan; results hidden or previous run dimmed |
| Success | Quiet meta + large chart + trades |
| Failed / cancelled | Honesty / error banner; keep history row |
| Loading history | Skeleton rows (Fleet-like) |
| Partial / truncated | UX-05 zone A banner always visible |

### Copy

- «Запустить бэктест» / «Отменить»  
- «Все прогоны в Lab»  
- Scope: «Робот» · «Лаборатория»  
- Empty history RU as above  

---

## Component map (summary)

| Concern | Primitive / file |
|---------|------------------|
| Shared hero | `RobotPageChrome`, `PageHero` |
| Confirm | `RobotConfirmModal` |
| Stage | `RobotStageCard` |
| Monitor meta | `MonitorSummaryCard` → quiet line |
| Monitor chart / tables / feed | `MonitorEquityChart`, `MonitorPositionsCard`, `MonitorOrdersCard`, `MonitorEventsCard`, `MonitorDecisionsCard`, `MonitorUniverseCard` |
| Tables | `DataTable` |
| Filters / scope / period | `SegmentedControl`, `DateRangePicker` |
| Backtest results | `BacktestResultsPanel`, `backtestGlassBox.ts` |
| History | `BacktestHistoryCard` |
| Lab launch | `LabConfigForm` + `BacktestLabPage` (UX-07) |
| Wizard | `RobotV2WizardPage`, `wizardDraft` |
| Badges / PnL | `Badge`, `robots-v2-pnl--up/down` |
| Empty / error / load | `dashboard-empty`, `dashboard-error-card`, `Skeleton` |
| Fleet rows (lists) | `FleetRobotCard` language / dense horizontal rows |

**Do not use:** Analytics `KpiTile`; Monitor/Fleet/Backtest-launch `StatTile` strips.

---

## Token notes

- `data-page="robots"`, dark default `data-theme`.  
- Surfaces: `var(--bg-card)`, `var(--border-subtle)`, flat — no glow.  
- PnL: `--color-up` / `--color-down`.  
- Primary CTA / running: cyan `btn--primary` only.  
- Destructive: `btn--danger`.  
- Density: meta `text-xs` / mono values; tables compact; gap `space-3`–`space-4`.  
- Hero: `dashboard-hero--node` (UX-04 — no full cyber bg).

---

## Acceptance criteria

### Cross-loop

- [ ] Subnav Флот · Лайв · Правка · Audit · Бэктест on all robot detail screens; create uses fleetOnly.  
- [ ] No KPI tile strips on Monitor, Edit, Robot Backtest launch chrome, or Fleet entry.  
- [ ] Cyan reserved for primary CTA + running; no badge/neon clusters.  
- [ ] Desktop ≥1440 layouts match zone maps; mobile stacks must not break (not a design priority).  
- [ ] Russian copy; status via `sessionStateLabel` / existing formatters.  
- [ ] No new HTTP paths or invented resource names.

### VIEW

- [ ] Above fold: chrome + quiet meta + stage + equity + live column.  
- [ ] Equity is the single primary visual focus.  
- [ ] Positions/orders below; universe collapsed by default.  
- [ ] Soft/hard stop + start wired; hard via modal.  
- [ ] Stream online/offline badges in RU.

### CONFIG

- [ ] Calm 3-column shell; one step focus; advanced under collapse.  
- [ ] Edit vs create chrome/CTA differences as table above.  
- [ ] Escape to Лайв / Бэктест from edit without inventing routes.

### BACKTEST

- [ ] Launch: period + capital + cyan Run; robot config is source of truth.  
- [ ] Results use `BacktestResultsPanel` UX-05 zones with quiet meta (not StatTile strip).  
- [ ] Large equity chart + quiet trades table.  
- [ ] History compact rows; link to Lab.  
- [ ] Робот \| Лаборатория scope control behaves as specified.

### Visual parity

- [ ] Align to Stitch Fleet compact + Backtest calm (+ aligned Live/Create screens in STITCH-09).  
- [ ] History/run lists read like Fleet rows.

---

## Gaps

- `[GAP: fleet list fields — day PnL, equity, open positions, last error per robot]` — Fleet entry only; show `—` (from UX-08).  
- `[GAP: explicit stale threshold / server clock for positionsUpdatedAt / equity as-of]` — Monitor honesty caption.  
- `[GAP: robot backtest launch param overrides beyond period/capital]` — if product wants editable strategy knobs on launch without Lab; today treat robot config as immutable source and send users to Правка or Lab «Настроить».  
- Soft: Audit inspector needs no new API if row payload already present.

Placeholder rule: missing GAP fields → `—` / omit / muted «нет в списке», never fake zeros.

---

## Out of scope for UI engineer

- New REST/WS endpoints or field renames.  
- Redesigning glass-box **content** semantics (UX-05 P2 still needs product approval).  
- Lab IA rewrite (UX-07 stays); only calm chrome alignment.  
- Mobile-first redesign.  
- Production code outside `frontend/src/pages/robots-v2/**` and shared primitives needed for quiet meta / density.

---

## Cross-links

| Doc | Role |
|-----|------|
| [UX-04](UX-04-robots-v2-visual-alignment.md) | Chrome / primitives baseline |
| [UX-05](UX-05-glass-box-backtest-results.md) | Results zones A–P + inspector |
| [UX-06](UX-06-monitor-day-summary-balance.md) | Day/balance honesty |
| [UX-07](UX-07-backtest-lab.md) | Lab hub vs robot-scoped |
| [UX-08](UX-08-robots-v2-live-cockpit.md) | Option B IA; **KPI strips superseded by this doc** |
| [STITCH-09](STITCH-09-robots-backtest.md) | Locked Stitch screens + DS |

---

## Handoff

```text
✅ UX spec ready: docs/ui/UX-09-robots-node-loop.md

UI engineer implements VIEW + CONFIG + BACKTEST LAUNCH against existing robot APIs.
Gaps for analyst/backend: see Gaps section above.
```
