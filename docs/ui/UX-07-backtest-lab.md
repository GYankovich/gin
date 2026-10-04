# UX-07: Backtest Lab hub (decoupled runs)

SPEC: docs/SPEC-05-backtest-lab-decoupled.md  
Chosen option: **B** — split Lab (launch ~38% + runs table ~62%; results full width below)  
Surface: `/robots/backtest` (+ `?run={runId}`); robot tab `/robots/:id/backtest` stays filtered  
Results: **reuse** [UX-05](UX-05-glass-box-backtest-results.md) / `BacktestResultsPanel` — no glass-box redesign  
Viewport: desktop-first **≥1440**; mobile stacks L1 → L2 → L4 (must not break)

**Locked product defaults**

| Topic | Value |
|-------|--------|
| Lab route | `/robots/backtest` under robots layout |
| Selected run | Same page `?run={runId}` (alias `?runId=` OK if already wired) |
| Robot delete | Nullify soft bind; keep run rows as orphans |
| P0 config authoring | Robot picker · last-used snapshot · advanced JSON (full wizard = P1) |
| Glass-box | UX-05 composition in L4 |

---

## Layout (zones)

### Desktop (≥1440) — Option B

```text
+-- L0 Chrome ----------------------------------------------------------+
| «Лаборатория бэктестов» · ← Флот · (optional cancel when active run)  |
+-------------------------------+---------------------------------------+
| L1 Launch card (~38%)         | L2 Runs table (~62%)                  |
| Источник конфига              | Все прогоны пользователя              |
| [Робот ▾] [Последний] [JSON]  | # · статус · период · капитал · KPIs  |
| Период · Капитал              | · bind badge · compare checkboxes     |
| [Запустить бэктест]           | empty → CTA pointing at L1            |
| inline 422 / 503 errors       | skeleton / error+retry                |
+-------------------------------+---------------------------------------+
| L3 Compare strip (only when exactly 2 runs selected)                  |
|    KPI tiles + config_diff summary · [Сравнить] already applied       |
+-----------------------------------------------------------------------+
| L4 when ?run= set                                                     |
|    RobotStageCard (queued / running / cancelling)                     |
|    BacktestResultsPanel per UX-05 (A–I + drawer F; no Lab-local J)    |
+-----------------------------------------------------------------------+
```

Split row uses existing `dashboard-layout` density; L1/L2 sit as sibling cards in one horizontal band (~38/62). L3 and L4 are full-width below.

When `?run=` is absent: L4 omitted (or a one-line hint under L2 — see Copy). Launch + table remain the first viewport.

### Mobile (must not break) `[R-10]`

```text
L0
L1 Launch (full width — primary CTA visible without horizontal scroll)
L2 Runs table (DataTable mobilePrimary / secondary patterns)
L3 Compare (if 2 selected) — stack under L2
L4 StageCard + BacktestResultsPanel (UX-05 mobile: A→… stack; inspector = full-screen sheet)
```

No horizontal clip of Start button or bind badges. Chart height rules follow UX-05.

### IA / navigation

| Entry | Behavior |
|-------|----------|
| Fleet hero / robots section action «Бэктест» | Navigate to `/robots/backtest` |
| Robot `RobotPageChrome` tab «Бэктест» | Stay on `/robots/:id/backtest` (filtered) |
| Robot tab escape hatch | Link «Все прогоны в Lab» → `/robots/backtest` (preserve optional `?run=` if opening a specific orphan later) |
| Lab → robot | Bind badge / «Робот #N» → `/robots/:id/backtest` or monitor (prefer robot backtest tab) |

Top-level Navbar change is **optional P0** — Fleet action is enough for first ship.

---

## Components (named → existing primitives)

| Zone | Widget | Map to |
|------|--------|--------|
| L0 | Page chrome | Prefer `RobotPageChrome`-like hero **without** robot id tabs, **or** fleet-style `PageHero` under `RobotsV2Layout` — title «Лаборатория бэктестов», eyebrow e.g. `BACKTEST LAB`, back/link to Флот |
| L0 actions | Cancel active Lab run | `Button` danger sm — same semantics as robot backtest cancel when selected/active run is queued/running |
| L1 | Launch card | `Card` `portfolio-toolbar` / `robots-v2-backtest-toolbar` patterns from `RobotV2BacktestPage` |
| L1 source | Config source control | `SegmentedControl` or compact radio row: «Робот» · «Последний» · «JSON» |
| L1 robot | Soft-bind picker | `Select` of user’s robots (optional); omitting robot ⇒ unbound Lab run (`robotId` omitted) |
| L1 last | Last-used snapshot | Button/chip «Последний конфиг» — hydrate from last Lab start in `sessionStorage` / last completed run’s `config_snapshot` (client-side); if none → disabled + hint |
| L1 JSON | Advanced paste | `CollapsibleSection` + textarea (monospace); validate JSON client-side before POST |
| L1 period | Presets + range | `SegmentedControl` presets + `DateRangePicker` `variant="fields"` (same as robot backtest toolbar) |
| L1 capital | Number field | Existing `robots-v2-field` / `robots-v2-input` |
| L1 CTA | Start | `Button` «Запустить бэктест» → `POST …/backtest` without `robotId` unless picker set |
| L2 | Runs table | Reuse / adapt `BacktestHistoryCard` **or** sibling `DataTable` with same columns + **bind** column |
| L2 bind | Badge | `Badge`: «Робот #N» (`bound`) / «Без робота» (orphan) from `robot_id` / `bound` |
| L2 config hint | Archetype / label | Optional column from list `config_label` when API provides it |
| L3 | Compare | Existing compare UI from `BacktestHistoryCard` (KPI `StatTile` + `config_diff`) via `POST /backtest/compare` — orphan↔orphan and orphan↔bound allowed `[R-7]` |
| L4 progress | Stage | `RobotStageCard` — unchanged progress semantics |
| L4 results | Glass-box | **`BacktestResultsPanel` only** — zones A–I + inspector F per UX-05; **do not** embed Lab history as UX-05 zone J inside the panel (L2 is the Lab history) |
| Robot tab | Escape | Text link / `Button` link variant under history: «Все прогоны в Lab» |

### List columns (L2) — P0

| Column | Source |
|--------|--------|
| Select (compare) | client |
| `#` / `run_id` | list |
| Статус | `status` + `Badge` |
| Период | `requested_from` → `requested_to` |
| Капитал | `initial_capital` |
| Доходность / Max DD / Sharpe / Сделки | metrics fields as today |
| Привязка | `robot_id` / `bound` → badge |
| (optional) Конфиг | `config_label` if present |

Sort default: `started_at` DESC (API order). Row highlight when `run_id === ?run`.

### P1 hooks (inventory only — not P0 build)

| Zone | Widget |
|------|--------|
| L4 header / results actions | «Сохранить как робота» → modal (name, optional token, attach history) |
| Success | Toast + navigate wizard/edit of new robot — no auto-start |

### P2 hooks (do not implement)

Filters (robot / unbound / status / dates / archetype), richer cross-compare chrome, run display titles/tags.

---

## Interaction map (clicks, keyboard)

| Action | Result |
|--------|--------|
| Open `/robots/backtest` | Load all user runs (`GET …/backtest/runs` without `robot_id`); L4 hidden |
| Change L1 source mode | Swap picker / last hydrate / JSON editor; clear opposing invalid state |
| Pick robot in L1 | Soft-bind: POST includes `robotId`; run appears in Lab **and** that robot’s tab |
| Clear robot / mode JSON or last without robot | Unbound start — `robotId` omitted |
| Click «Запустить бэктест» | Validate → POST → on `202` set `?run={run_id}`, show L4 StageCard, refresh L2 |
| Click L2 row | Navigate/replace query `?run={id}`; load detail + glass-box subresources; scroll L4 into view on desktop |
| Toggle compare checkboxes | Max 2 selected; enable L3 / Compare control (same as history card) |
| Compare | `POST /backtest/compare`; show L3 metrics + config_diff |
| Cancel (active run) | Existing cancel endpoint; StageCard + honesty banner per UX-05 |
| Click bind badge «Робот #N» | Go to that robot’s backtest tab (stopPropagation so row doesn’t also only set `?run`) |
| Robot tab «Все прогоны в Lab» | `/robots/backtest` |
| Glass-box marker/row/chip | Per UX-05 (drawer / sheet) — unchanged |
| Deep-link `/robots/backtest?run=901` | Select row 901, load L4; if run missing/unauthorized → L2 error toast + clear query |

**Keyboard (desktop, Lab chrome)**

| Key | Behavior |
|-----|----------|
| `r` | Refresh L2 list (when focus not in input/textarea) |
| `n` | Focus L1 primary control (source or Start) — nice-to-have |
| `Esc` | Close UX-05 inspector F when open; otherwise no-op |
| UX-05 `j`/`k` | Still apply when L4 inspector open |

---

## States (loading / empty / error / stale)

| State | L1 | L2 | L4 |
|-------|----|----|----|
| Initial load | Idle form | Skeleton rows | Hidden unless `?run=` |
| No runs ever | Form ready | Empty: «Нет прогонов» + CTA «Настройте первый бэктест слева» | Hidden |
| Enqueue validation 422 | Inline error under fields / JSON | Unchanged | Unchanged |
| Enqueue 503 / queue | Inline error + retry | Unchanged | Unchanged |
| Queued / running | Start disabled or secondary | Row status badge updates on poll | StageCard; no fake trades |
| SUCCESS | Form stays for next iterate | Row KPIs filled; row selected | Full UX-05 panel |
| Failed run | — | Badge down/warn | Honesty / error per UX-05 |
| List fetch error | Usable | `dashboard-error-card` + «Повторить» | If `?run=` still try detail |
| Orphan after robot delete | — | Badge «Без робота» (nullified bind) | Results still open by `run_id` |
| Stale progress | — | Poll list lightly | Poll status as robot page today |
| Mobile | Full-width stack | Same empty/error | UX-05 sheet inspector |

Realtime WS: **none** for Lab P0 (poll only) — same as robot backtest.

---

## Token notes (up/down, density)

- Dark-first; honor `data-theme` light.
- P&L / return columns: `robots-v2-pnl--up/down` + `var(--color-up)` / `var(--color-down)`.
- Bind badges: neutral for «Без робота»; subtle cyan/info or existing Badge variant for «Робот #N» — not success-green (binding ≠ profitable).
- Cards: `var(--bg-card)`, `var(--border-subtle)` — match robots-v2 backtest toolbar / history cards.
- Density: trading-table patterns; L2 `maxHeight` scroll body so L1+L2 stay usable when history is long.
- Do not invent a new palette or purple/glow Lab skin.

---

## Copy (labels, empty-state text) — RU

### L0

| Element | Copy |
|---------|------|
| Title | Лаборатория бэктестов |
| Eyebrow | BACKTEST LAB |
| Back | ← Флот |
| Cancel | Отменить |

### L1

| Element | Copy |
|---------|------|
| Card title | Новый прогон |
| Source modes | Робот · Последний · JSON |
| Robot select placeholder | Без робота (Lab) |
| Last config | Последний конфиг |
| Last empty | Нет сохранённого конфига — выберите робота или вставьте JSON |
| JSON section | Конфиг (JSON) |
| Period aria | Период бэктеста |
| Capital | Капитал |
| CTA | Запустить бэктест |
| Soft-bind hint | Опционально: привязать к роботу для истории на его вкладке |
| 422 generic | Проверьте конфиг и период |
| 503 generic | Очередь занята — повторите позже |

### L2 / L3

| Element | Copy |
|---------|------|
| Table title | Все прогоны |
| Empty | Нет прогонов |
| Empty CTA | Настройте первый бэктест слева |
| Bind bound | Робот #{id} |
| Bind orphan | Без робота |
| Refresh | Обновить |
| Compare | Сравнить |
| Compare need 2 | Выберите два прогона |
| List error | Не удалось загрузить историю |

### L4 / robot tab

| Element | Copy |
|---------|------|
| No selection hint (optional) | Выберите прогон в таблице, чтобы открыть результаты |
| Robot escape | Все прогоны в Lab |
| P1 (later) | Сохранить как робота |

Glass-box honesty / reject / inspector strings: **unchanged** from UX-05.

---

## Out of scope for UI engineer

- Redesigning UX-05 glass-box zones, DecisionInspectorDrawer, scrubber, narrative, etc.
- P1 save-as-robot modal implementation until product unlocks P1 (inventory above only).
- P2 filters, tags, dual glass-box compare.
- New HTTP paths / Lab API aliases (use existing `POST/GET …/backtest` contracts from SPEC-05 §6).
- Billing, auth, Navbar-only Lab (Fleet entry is sufficient).
- Full visual config wizard on Lab (P1 with save-as-robot).
- Parameter-grid / optimizer Lab.

---

## Gaps

- `[GAP: needs API for config_label on list items]` — optional column; if absent, omit column or derive lightly from `config_snapshot.strategy.archetype` when list payload already embeds snapshot (do not add a new endpoint in UI).
- `[GAP: needs API for bound boolean]` — if missing, derive `bound = robot_id != null` in UI.
- Last-used snapshot is **client** persistence unless backend later adds a dedicated “last Lab config” resource — no blocker for P0.
