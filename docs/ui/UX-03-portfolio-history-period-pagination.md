# UX-03: Portfolio history period + infinite scroll

SPEC: `docs/SPEC-02-portfolio-history-period-pagination.md`  
Chosen option: **B** — unified **«История»** module (period in module head + nested snaps/ops)  
**Revision:** User feedback superseded former Option A (standalone «Период истории» card above separate collapses). Layout-only change; SPEC-02 API contracts unchanged.  
Supersedes: UX-01 toolbar period + KPI «Выбранный период»; UX-02 rows that treat toolbar period as stats filter; **UX-03 v1 Option A dedicated period bar**.  
Does not contradict: UX-02 chart full-history fetch + client zoom (День / Неделя / Месяц / Год / Всё).

**Locked defaults (from product):**

1. Sync when period unset → full observation window (`observation_from` → now), same as stats/chart — no artificial sync cap in UI copy.
2. `observation_from` = earliest snapshot date (`MIN(snapshot_date)`). Optional muted hint under «За всю историю»: «от первого снимка до сегодня».
3. History period UI: `DateRangePicker` + explicit **«Сбросить»** (all-time). Compact presets 7/30/90 remain nice-to-have only (see Option C); primary ship is dates + clear.

---

## Layout options (reviewed)

### Option A — Dedicated history period bar (**superseded**)

Standalone `Card.portfolio-history-period` between composition and two sibling history collapses. Rejected after review: period felt detached from the lists it filters.

```text
| E  Состав                                               |
| H  Card — «Период истории» + dates + Сбросить  (orphan) |
| F  CollapsibleSection — История снимков                 |
| G  CollapsibleSection — История операций + sync         |
```

### Option B — Unified «История» module (**chosen**)

After composition, one outer card/zone titled **«История»**. Module head holds shared **«Период истории»** controls. Inside: two nested `CollapsibleSection`s — **«Снимки»** and **«Операции»** (sync on ops `headerEnd`). One shared period; both lists reset together on change.

```text
+-- PageLayout / Navbar ----------------------------------+
| A  PageHero (dashboard-hero--node)                      |
| B  Card.portfolio-toolbar — [Счёт] only                 |
| C+D  dashboard-currency-grid (UX-02)                    |
|    | C Сводка («За всю историю») | D Chart + zoom     |
| E  Состав портфеля                                      |
| H  Card.dashboard-totals-card.portfolio-history-zone    |
|    ┌─ head ───────────────────────────────────────────┐ |
|    │ «История»                                        │ |
|    │ «Период истории» [DateRangePicker] [Сбросить]    │ |
|    └──────────────────────────────────────────────────┘ |
|    F  CollapsibleSection — Снимки     badge=count       |
|    G  CollapsibleSection — Операции   badge=count + sync│
+---------------------------------------------------------+
```

**Nested collapses vs tabs:** Prefer **nested `CollapsibleSection`s**, not tabs. Dashboard/portfolio already use collapses for progressive disclosure (accounts, assets, composition, stats period); both lists can be open at once (scan snaps then ops); tabs would hide one list and introduce a new IA pattern on `/portfolio`. Default: both nested sections **closed** (same as today’s F/G).

### Option C — Unified module + optional presets (secondary)

Same as B, plus compact 7/30/90 chips in the history head beside the picker. Ship only if product asks after B.

---

## Layout (zones)

Page root: `<div className="page" data-page="portfolio">` inside `PageLayout`. Vertical stack uses `dashboard-layout` gap. Desktop ≥1440 primary; mobile ≤767 stacked (required by SPEC).

| Zone | Name | Component / class hooks | Desktop ≥1440 | Mobile ≤767 |
|------|------|-------------------------|---------------|-------------|
| **A** | Hero | `PageHero` + `dashboard-hero--node` | Unchanged (UX-01) | Same |
| **B** | Toolbar | `Card.dashboard-totals-card.portfolio-toolbar` → only `Select` in `portfolio-toolbar__account` | Account ~280px left-aligned; **no** period controls | Account full width |
| **C** | Сводка | `dashboard-currency-grid` + `Card.dashboard-totals-card`; secondary title **«За всю историю»** | Side-by-side with D | Period metrics in `portfolio-stats-period-collapse`, title **«За всю историю»**, default closed |
| **D** | Chart | `dashboard-assets-card` / mobile `dashboard-assets-collapse`; UX-02 zoom | Full-history series; zoom client-only | Collapse default closed; height 240 |
| **E** | Состав | `PortfolioComposition` / `portfolio-composition-collapse` | `defaultOpen={true}`; **no** period filter | `defaultOpen={false}` |
| **H** | **История** (module) | Outer `Card.dashboard-totals-card.portfolio-history-zone`; head: `dashboard-totals-card__head` + `dashboard-panel-title` **«История»** + period row (`portfolio-history-period` controls) | One card wrapping F+G; period in head (not a separate floating card) | Full-width card; head stacks: title → period label → picker → clear |
| **F** | Снимки | Nested `CollapsibleSection.portfolio-collapse` (or `dashboard-accounts-collapse`); badge = **`count`** | Inside H; `defaultOpen={false}`; `DataTable` `maxHeight={420}`; infinite scroll | Same; mobile row patterns unchanged |
| **G** | Операции | Nested collapse; badge = **`count`**; sync `Button` in `headerEnd` | Inside H; sync does not toggle collapse | Same |

**Zone order (canonical):** A → B → C|D → E → **H(F,G)**.

There is **no** standalone period card between E and F. Period lives only in **H head**.

### Module head structure (concrete)

```text
Card.portfolio-history-zone
├── .dashboard-totals-card__head.portfolio-history-zone__head
│   ├── h3.dashboard-panel-title  «История»
│   └── .portfolio-history-period  (aria-label="Период истории")
│       ├── span / label  «Период истории»
│       ├── DateRangePicker
│       └── Button  «Сбросить»  (ghost, sm; disabled when unset)
└── .portfolio-history-zone__body
    ├── CollapsibleSection  title «Снимки»   badge=count
    └── CollapsibleSection  title «Операции» badge=count  headerEnd=Sync
```

Visual unity: single `--bg-card` surface, one border; nested collapses use existing collapse chrome without an extra outer card per list. Optional light divider between F and G (hairline `--border-subtle`) if nesting feels flat — not required for v1.

---

## Components (named, mapped)

| Widget | Primitive | Notes |
|--------|-----------|-------|
| Account toolbar | `Card`, `Select` | Period **not** in B |
| Lifetime KPIs | `StatTile` grids | «За всю историю»; full-window stats |
| Chart | `Chart`, zoom `SegmentedControl`, `Toggle` | UX-02; independent of history period |
| History module | `Card` + head + nested collapses | Class `portfolio-history-zone` |
| Period (in H head) | `DateRangePicker`, `Button` «Сбросить» | Shared; default unset = all-time |
| Snapshots | Nested `CollapsibleSection`, `DataTable` | Title **«Снимки»** (short; module already says История) |
| Operations | Nested `CollapsibleSection`, `DataTable`, sync `Button` | Title **«Операции»**; sync in `headerEnd` |
| Load more | Bottom skeleton in table scrollport | Do not blank table |
| Empty / error | `dashboard-empty` / toasts | `[R-11]` copy |

**Do not use:** `KpiTile`; tabs for snaps/ops; period controls in toolbar B; standalone Option A period card.

---

## Shared period control (in H head)

| Rule | Behavior |
|------|----------|
| Default | **Unset** → all-time for snaps + ops + `count` |
| Apply | Both from+to set → reset F+G (`offset=0`), clear rows, refetch both; **stats/chart/composition not refetched** |
| Clear | **«Сбросить»** → unset → same dual refetch; prefer **disabled** when already unset |
| Partial range | Do not call API with only one bound; match existing `DateRangePicker` completion |
| Account change | Reset period to unset; reload all account-scoped data |
| Placement | **Only** inside `portfolio-history-zone` head — next to / under module title «История» |
| aria | Control group `aria-label="Период истории"` |

Optional muted microcopy under period row: «Фильтр снимков и операций» (clarifies independence from chart zoom).

---

## Badges and pagination

| Surface | Rule |
|---------|------|
| Badge F / G | Server **`count`** for current filter. Never loaded row length. |
| First paint | Hide badge or `…` until first response; then show `count` |
| Page size | `limit=50`; append when `offset + loaded < count` |
| Order | Newest → oldest |
| Period / account / sync success | Reset both lists to page 0 |

### Infinite scroll affordances

**Desktop (≥1440):**

- `DataTable` `maxHeight` ~420 inside each nested section.
- Scroll near end or IntersectionObserver sentinel.
- Load-more: inline bottom skeleton; keep rows + scroll position.
- Optional footer «Показаны все N» — nice-to-have.

**Mobile (≤767):**

- History module full width under composition.
- Head stacks vertically (title → «Период истории» → picker → clear); no horizontal overflow.
- Nested collapses still default closed; infinite scroll when section open (section-local scroll if `maxHeight`, else viewport sentinel).
- No mandatory «Загрузить ещё» button for v1.

**Load-more error:** toast or inline retry under that table; **do not** wipe page 0 or the sibling list.

---

## Interaction map

| Action | Result |
|--------|--------|
| Select account (B) | Clear period; reload positions, full-window stats/chart, snaps/ops page 0; URL `accountId` |
| Set dates (H head) | Reset F+G; refetch both; badges → new `count` |
| «Сбросить» | Unset; refetch both all-time |
| Toggle «Снимки» / «Операции» | Open/close nested section only; period stays visible in module head |
| Scroll near end F or G | Append next page if more remain |
| Snapshot row click | Load composition for `snapshot_id` |
| Chart zoom / papers | Client-only (UX-02) |
| Sync (G `headerEnd`) | Period set → that range; unset → MIN snapshot → now. Token warning if missing. Success → ops page 0 + full-window stats |
| Sync / period clicks | Must **not** toggle parent card or nested collapses |

**Keyboard:** focus-visible on Select, DateRangePicker, Сбросить, Sync, collapse toggles; no new global shortcuts.

---

## States

### Loading

| Context | UI |
|---------|-----|
| Page / account | `PortfolioSkeleton` — include one skeleton block for history **module** (not three orphan bars) |
| F/G first page | Skeleton inside that nested section (~120px), `aria-busy` |
| F/G load more | Bottom row skeleton; table stays |
| Badge | `…` or hidden until `count` known |
| Period controls | Remain usable; lists show loading independently |

### Empty (`[R-11]`)

| Table | Period unset | Period set |
|-------|--------------|------------|
| Snapshots | «Нет истории» | «Нет снимков за выбранный период» |
| Operations | «Нет операций» | «Нет операций за выбранный период» |

Empty states stay **per nested section** (do not replace whole «История» card with a single empty). Composition: «Нет позиций».

### Error

| Context | UI |
|---------|-----|
| Stats / chart | Section retry (`dashboard-error-card` + «Повторить») |
| Load more | Toast or inline retry under that nested table |
| Sync fail | «Ошибка синхронизации операций» |
| Sync no token | UX-01 warning toast |

### Chart empty

- «Нет данных графика.» (no «за выбранный период»).
- Zoom «Всё» = fitContent of loaded series only.

### Sync date source

| Period in H head | Sync `from`/`to` |
|------------------|------------------|
| Unset | Earliest **snapshot** date → end of today |
| Set | Shared history `from`/`to` |

No artificial sync-cap copy.

---

## Token notes

- Outer module: `--bg-card`, `--border-subtle`, `dashboard-totals-card`.
- Nested collapses: existing `portfolio-collapse` / `dashboard-accounts-collapse` patterns; badges `dashboard-accounts-collapse__count` / `portfolio-collapse__count`.
- P&L: `--color-up` / `--color-down`.
- New page classes: `portfolio-history-zone`, `portfolio-history-zone__head`, `portfolio-history-zone__body`, `portfolio-history-period` (controls row inside head), `portfolio-history-period__clear`.
- Prefer shared: `dashboard-layout`, `dashboard-currency-grid`, `dashboard-panel-title`, `dashboard-settings-group__bulk` (sync).
- Do **not** ship standalone `portfolio-history-period` as its own full-width card (Option A).

---

## Copy

| Surface | Russian |
|---------|---------|
| Module title (H) | История |
| Period label (in head) | Период истории |
| Clear | Сбросить |
| Nested F | Снимки |
| Nested G | Операции |
| Stats secondary | За всю историю |
| Optional muted under stats | от первого снимка до сегодня |
| Optional muted under period | Фильтр снимков и операций |
| Sync | Синхронизировать |
| Empty / toasts | States + UX-01 sync toasts |

Legacy titles «История снимков» / «История операций» are shortened because the parent module is already **«История»**. Do **not** reuse «Выбранный период» for KPIs.

---

## No contradiction with UX-02

| Concern | Resolution |
|---------|------------|
| Chart fetch / zoom | Full window + client presets; independent of H period |
| C\|D grid | Unchanged |
| Toolbar → stats | Obsolete; stats always full window |
| History filter | Only inside «История» module head; does not move chart range |

---

## Out of scope for UI engineer

- SPEC-02 API / schema changes (consume existing contracts only)
- Cursor pagination, WebSocket history
- Making stats/chart/sync APIs accept omitted dates
- Option C preset chips
- Tabs instead of nested collapses
- Reintroducing Option A standalone period card
- FIFO / formulas / robots / new HTTP paths

**Gaps:** `[GAP: needs earliest snapshot date on account summary if not already exposed]` only if FE cannot derive MIN for sync/stats without a new field.

---

## Acceptance checklist (UI engineer)

- [ ] **B:** Toolbar = account `Select` only; no period controls in `portfolio-toolbar`
- [ ] **C:** KPI secondary title **«За всю историю»** (desktop + mobile); full-window stats
- [ ] Optional muted «от первого снимка до сегодня» under that title
- [ ] **D:** Chart full window + UX-02 zoom; changing history period does **not** refetch chart
- [ ] **E:** Composition ignores history period
- [ ] **H:** Single outer card **«История»** (`portfolio-history-zone`); period controls **in module head** (DateRangePicker + **«Сбросить»**); default unset = all-time
- [ ] **No** standalone Option A period card between composition and lists
- [ ] Nested collapses **«Снимки»** and **«Операции»** (not tabs); both default closed
- [ ] Changing period resets both lists to `offset=0` and refetches together; account change clears period
- [ ] Badges = response **`count`**; infinite scroll append (50); load-more skeleton; empty copy per `[R-11]` per section
- [ ] Sync in ops `headerEnd`; unset → full observation window (MIN snapshot → now); set → head dates; success → ops page 0 + stats
- [ ] Desktop ≥1440 and mobile ≤767: order A→B→C→D→E→H(F,G); history head stacks cleanly on mobile
- [ ] Class hooks: `dashboard-totals-card`, `dashboard-currency-grid`, `portfolio-history-zone`, nested collapses
- [ ] Dark + light readable; focus-visible on period + sync + collapses
