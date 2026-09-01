# UX-01: Portfolio page visual alignment with Dashboard

SPEC: docs/SPEC-01-portfolio-dashboard-visual-alignment.md  
Chosen option: **A** (unified vertical stack)

## Layout options (reviewed)

### Option A — Unified vertical stack (recommended)

Single `dashboard-layout` column; one stats card holds overall + period KPIs; chart in `dashboard-assets-card`; tables in dashboard-style collapsibles. Matches `DashboardPage` rhythm: hero → layout stack → card surfaces → progressive disclosure.

```text
+-- PageLayout / Navbar / MobileTabBar -------------------+
| A  PageHero (dashboard-hero--node)                     |
+--------------------------------------------------------+
| B  Card.portfolio-toolbar (account | period | dates)   |
| C  Card.dashboard-totals-card (overall + period stats) |
| D  Card.dashboard-assets-card OR dashboard-assets-     |
|    collapse (mobile) — chart + toggle + legend         |
| E  PortfolioComposition (CollapsibleSection, open)     |
| F  CollapsibleSection — snapshots table                |
| G  CollapsibleSection — operations + sync headerEnd    |
+--------------------------------------------------------+
```

### Option B — Split stats cards

Same zones A, B, D–G; zone **C** becomes **two** cards: `dashboard-totals-card` (4 overall KPIs only) + second `dashboard-totals-card` (period grid). Clearer separation between lifetime vs period metrics, but adds ~48px vertical gap and diverges from dashboard (one totals card per entity). Period block still collapses on mobile inside card 2.

```text
| C1 Card.dashboard-totals-card — «Общее» (4 StatTiles)  |
| C2 Card.dashboard-totals-card — «Выбранный период»     |
```

**Recommendation:** Option A. Dashboard never splits summary metrics across two cards for the same scope; unified stats card preserves scan path (toolbar → headline KPIs → period detail) and reduces scroll on ≥1440. Option B is acceptable only if user explicitly wants stronger overall/period visual separation.

---

## Layout (zones A–G)

Page root: `<div className="page" data-page="portfolio">` inside existing `PageLayout`.

| Zone | Component(s) | CSS / class targets | Desktop ≥1440 | Mobile ≤767 |
|------|--------------|---------------------|---------------|-------------|
| **A** | `PageHero` | `dashboard-hero dashboard-hero--node` on all states (loading, empty, content) | Full hero with subtitle | Same; subtitle may hide via existing `[data-page='portfolio'] .dashboard-hero__sub` rule |
| **B** | `Card` + `Select` + `SegmentedControl` + `DateRangePicker` | `Card` + `portfolio-toolbar` (page-specific layout); inner: `portfolio-toolbar__account`, `portfolio-period-control`, `portfolio-toolbar__range` | Single row: account ~280px, period segment, date range right | Stack: account full width → period (no «3 месяца») → date range full width; no horizontal overflow |
| **C** | `Card` + `StatTile` ×4 overall + period grid | Outer: `dashboard-totals-card`; head: `dashboard-totals-card__head` + `dashboard-panel-title`; overall grid: `portfolio-stats-grid dashboard-summary-grid`; period: `portfolio-stats-grid`; section labels: `portfolio-stats-row-title` | Overall + period **expanded** in one card | Overall 2×2 grid; period inside `CollapsibleSection` `portfolio-stats-period-collapse`, **default closed** |
| **D** | `Card` or `CollapsibleSection` + `Chart` + `Toggle` + legend | Desktop: `dashboard-assets-card`; mobile collapse: `dashboard-assets-collapse`; chart chrome: `portfolio-chart-header`, `portfolio-crosshair-main`, `portfolio-chart-midbar`, `portfolio-legend` | `Card` always visible; height 360px | `CollapsibleSection` default **closed**; `headerEnd` = papers `Toggle`; height 240px |
| **E** | `PortfolioComposition` | `portfolio-collapse portfolio-composition-collapse` | `defaultOpen={true}` | `defaultOpen={false}` |
| **F** | `CollapsibleSection` + `DataTable` | `portfolio-collapse` → migrate title to `dashboard-collapse__label` pattern where feasible; badge: `portfolio-collapse__count` | `defaultOpen={false}`; `maxHeight={420}` | `mobilePrimary` / `mobileDetails` unchanged |
| **G** | `CollapsibleSection` + `DataTable` + sync `Button` | Same collapse classes; sync in `headerEnd` | `defaultOpen={false}` | Same; sync button stays in header (does not collapse section) |

Vertical spacing: use `dashboard-layout` gap (same as dashboard); do not introduce new page-level padding.

---

## Components (mapped to codebase)

| Widget | Primitive | Notes |
|--------|-----------|-------|
| Hero | `PageHero` | `className="dashboard-hero--node"`; no `actions` slot (sync lives in G) |
| Toolbar | `Card`, `Select`, `SegmentedControl`, `DateRangePicker` | Preserve `[R-2]` URL sync on account change |
| Overall KPIs | `StatTile` ×4 in `dashboard-summary-grid` | Labels unchanged: Собственные средства, Текущая стоимость, ROI общий, ROI среднемесячный |
| Period KPIs | `StatTile` ×14 | All labels/values from current `PortfolioPage`; `valueClassName` via `roiClass` / `profitFactorClass` |
| Chart | `Chart`, `Toggle`, `Button` (legend bulk), `Skeleton` | `key` preserves account+range+mode+figis; pan-left period expand unchanged |
| Composition | `PortfolioComposition` | Columns, sort, Bybit path unchanged |
| Snapshots | `CollapsibleSection`, `DataTable` | Row click → `loadPositions(accountId, snapshotId)` |
| Operations | `CollapsibleSection`, `DataTable`, `Button` | Sync wired to existing `handleSyncOperations` |
| Empty / error | `Card`, `RobotIllustration`, `Button` | Reuse `dashboard-error-card`, `dashboard-empty` |
| Loading | `PortfolioSkeleton` | Align with `DashboardSkeleton` card heads + `dashboard-skeleton-card` |
| Feedback | `useToast` | Warning (no token), error (sync fail) |

**Do not use:** `KpiTile` (AnalyticsPage emoji tiles).

---

## Hero copy (resolved)

| Element | Value | Rationale |
|---------|-------|-----------|
| Eyebrow | `ANALYTICS NODE` | Keeps analytics-deep-dive identity; shares «* NODE» family with dashboard `PORTFOLIO NODE` without implying same screen |
| Title | `ПОРТФЕЛЬ` | Unchanged nav label parity |
| Subtitle | `Статистика · позиции · операции` | Scope hint; matches current page |

Apply `dashboard-hero--node` on **portfolio** the same way dashboard scopes it: extend responsive rules from `[data-page='dashboard'] .dashboard-hero--node` to `[data-page='portfolio']` (compact node strip, content alignment). Visual parity is class-driven; copy stays analytics-themed.

---

## Interaction map

| Action | Target | Result |
|--------|--------|--------|
| Select account | Toolbar `Select` | Reload positions + period bundle; `history.replaceState` with `accountId` |
| Period preset | `SegmentedControl` | Updates `fromDate`/`toDate`; reloads snapshots, ops, stats, chart |
| Custom dates | `DateRangePicker` | Sets `period` to 0; reloads period bundle |
| Toggle «Посмотреть бумаги» / «бумаги» | Chart header / collapse `headerEnd` | Switches `chartMode`; mobile opens chart section if collapsed |
| Legend item click | `portfolio-legend-item` | Toggles FIGI in `selectedFigis` |
| «Выделить все» / «Снять все» | `portfolio-chart-midbar` | Select/clear all instrument series |
| Chart crosshair (portfolio mode) | `Chart` | Updates `portfolio-crosshair-main` readout (value, delta, delta %, time) |
| Chart pan left past range | Chart time scale | Expands period preset (existing behavior) |
| Snapshot row click | Snapshots `DataTable` | Loads composition for `snapshot_id` |
| Mobile «Показать состав снимка» | Snapshot `mobileDetails` button | Same as row click |
| **Sync operations** | G `headerEnd` `Button` | See Sync states below |
| Collapsible headers | E, F, G, mobile C-period, mobile D | Keyboard: Enter/Space on `collapsible-section__toggle` |
| Dashboard → account | External | `/portfolio?accountId=` pre-selects account |

**Keyboard (minimal, match dashboard):** focus-visible on all controls; no new global shortcuts required for this redesign.

---

## States

### Initial load (`loading === true`)

- Hero: `PageHero` with `dashboard-hero--node` + current copy (no skeleton on hero text).
- Body: `PortfolioSkeleton` inside `dashboard-layout` with `aria-busy="true"` `aria-label="Загрузка портфеля"`.
- Skeleton blocks: toolbar placeholder → `dashboard-totals-card dashboard-skeleton-card` (4 StatTile-shaped skeletons) → `dashboard-assets-card dashboard-skeleton-card` (chart block).

### No accounts (`accounts.length === 0`)

- Hero + `Card.dashboard-totals-card.dashboard-error-card`.
- `RobotIllustration` `mode="inactive"`, `size={96}`.
- Copy: «Нет счетов портфеля. Запустите робота обновления портфеля (ByBit или T-Invest), чтобы появились снимки.»
- **No** full-page retry (accounts failure is configuration empty, not transient network).

### Section loading (account selected)

| Section | Loading UI |
|---------|------------|
| Stats | In-card skeleton matching overall 4-tile grid; `aria-busy` «Расчет статистики» |
| Chart | `Skeleton` height 360 (desktop) / 240 (mobile) |
| Composition | `PortfolioComposition` internal skeleton |
| Snapshots / ops | Section skeleton ~120px height |

### Section error + retry (stats / chart only)

When `loadStatistics` or `loadChartSeries` fails (data null after error, not merely empty series):

- Replace section body with inline `dashboard-error-card` **inside** the same card/collapse shell (do not unmount toolbar or other sections).
- Copy: «Не удалось загрузить статистику.» / «Не удалось загрузить график.»
- `RobotIllustration` `mode="inactive"`.
- `Button` «Повторить» → re-invokes only that loader (`loadStatistics` / `loadChartSeries`).
- Optional: brief `dashboard-error-card--retrying` + `soft-loading-bar` on retry (mirror dashboard retry animation ~1.8s min on failure).
- Tables (snapshots, ops): keep current silent empty on catch; **no** retry in this pass (SPEC minimal scope).

### Chart empty (success, no series)

- `Card.dashboard-assets-card.dashboard-error-card` (not loading skeleton).
- Copy: «Нет данных графика за выбранный период.»
- No retry (valid empty state).

### Table empty

| Table | `emptyText` |
|-------|-------------|
| Composition | «Нет позиций» |
| Snapshots | «Нет истории» |
| Operations | «Нет операций за период» |

### Sync states (zone G, `[R-10]`)

| State | UI |
|-------|-----|
| Default | `Button` in `CollapsibleSection` `headerEnd`: label **«Синхронизировать»**, `variant="ghost"`, `size="sm"`, class `dashboard-settings-group__bulk` (matches chart «Выделить все» weight) |
| Loading | `loading={true}`, `disabled={true}`; label unchanged (spinner via `Button`) |
| No token | Click → warning toast: «Для выбранного счета не найден tokenId. Обновите портфель.»; button not disabled preemptively |
| Success | Silent; reload operations + extended stats |
| Error | Error toast: «Ошибка синхронизации операций» |
| No account | Button hidden or disabled (edge: should not render in empty-accounts branch) |

`headerEnd` click must not toggle collapse (`CollapsibleSection` existing behavior).

---

## Chart card detail

### Header (desktop)

```text
dashboard-assets-card__head (optional) OR portfolio-chart-header
├── h3.dashboard-panel-title  «Стоимость портфеля»
└── portfolio-chart-header__controls
    └── Toggle  label «Посмотреть бумаги»
```

### Header (mobile)

- Title on collapse: «Стоимость портфеля » (trailing space preserved for badge compatibility).
- `headerEnd`: `Toggle` label «бумаги».

### Crosshair readout (portfolio mode only)

- Placement: **above** chart canvas, below header — `portfolio-crosshair-main` (`mono`).
- Content: formatted total value; signed delta + `(±%)` with `color-up` / `color-down`; time in `portfolio-crosshair-main__time`.
- Hidden when crosshair inactive or instruments mode.

### Instruments mode

- Midbar: «Выделить все» / «Снять все» (`dashboard-settings-group__bulk`).
- Legend row: `portfolio-legend` / `portfolio-legend-item` / `portfolio-legend-color`.
- Crosshair: price lines on axis (existing); no main readout bar.

### Heights

- Desktop: **360px**
- Mobile: **240px**

---

## Typography, spacing, tokens

| Token / class | Usage on portfolio |
|---------------|-------------------|
| `--bg-card`, `--border-subtle` | All `Card` surfaces |
| `--text-primary`, `--text-secondary` | Labels (`portfolio-stat-tile__label`, table muted) |
| `--color-up`, `--color-down` | P&L, ROI, payments; chart deltas |
| `dashboard-panel-title` | Card section titles (stats, chart) |
| `dashboard-empty` | Empty and error body copy |
| `mono` | Money, dates, crosshair |
| `dashboard-layout` | Page stack gap |
| `dashboard-summary-grid` | Overall 4 KPIs — desktop 4-col / mobile 2×2 via existing responsive rules |
| `portfolio-stats-grid` | Period dense grid (multi-column desktop) |

**Spacing:** reuse `--space-*` from `variables.css`; card heads use `dashboard-totals-card__head` / `dashboard-assets-card__head` padding parity with dashboard.

**Themes:** verify dark (default) and light via `data-theme`; chart colors stay theme-branch in page helpers.

---

## CSS: shared vs page-specific

### Prefer shared (`dashboard-*`)

- `dashboard-hero`, `dashboard-hero--node`
- `dashboard-layout`, `dashboard-skeleton`, `dashboard-skeleton-card`
- `dashboard-totals-card`, `dashboard-assets-card`
- `dashboard-totals-card__head`, `dashboard-assets-card__head`
- `dashboard-panel-title`, `dashboard-empty`
- `dashboard-error-card`, `dashboard-error-card__robot`, `dashboard-error-card__actions`, `dashboard-error-card--retrying`
- `dashboard-assets-collapse`, `dashboard-collapse__label` (migrate F/G titles toward dashboard collapse label + icon pattern)
- `dashboard-settings-group__bulk` (sync + legend bulk actions)
- `dashboard-summary-grid` (overall StatTile grid chrome)

### Keep page-specific (`portfolio-*`)

- `portfolio-toolbar`, `portfolio-toolbar__account`, `portfolio-toolbar__range`, `portfolio-period-control`
- `portfolio-stats-rows`, `portfolio-stats-row-title`, `portfolio-stats-grid` (period density)
- `portfolio-stat-tile` (via `StatTile` — shared primitive class name; do not fork)
- `portfolio-chart-header`, `portfolio-chart-header__controls`, `portfolio-crosshair-main`, `portfolio-chart-midbar`
- `portfolio-legend`, `portfolio-legend-item`, `portfolio-legend-color`
- `portfolio-collapse__count`, `portfolio-mobile-split`, `portfolio-mobile-stack`
- `portfolio-stats-period-collapse`, `portfolio-composition-collapse`

### Remove / avoid

- One-off hex card backgrounds fighting `--bg-card`
- Duplicate KPI tile component or Analytics `KpiTile`
- New `portfolio-hero-*` — hero uses dashboard classes only

---

## Copy (labels & messages)

| Context | Russian copy |
|---------|----------------|
| Hero eyebrow | ANALYTICS NODE |
| Hero title | ПОРТФЕЛЬ |
| Hero subtitle | Статистика · позиции · операции |
| Stats card title | Статистика портфеля |
| Stats section «Общее» | Общее |
| Stats section period | Выбранный период |
| Chart title | Стоимость портфеля |
| Composition default title | (from `PortfolioComposition`) |
| Snapshots title | История снимков |
| Operations title | История операций |
| Sync button | Синхронизировать |
| Sync no token toast | Для выбранного счета не найден tokenId. Обновите портфель. |
| Sync error toast | Ошибка синхронизации операций |
| Stats retry | Не удалось загрузить статистику. / Повторить |
| Chart retry | Не удалось загрузить график. / Повторить |
| No accounts | Нет счетов портфеля. Запустите робота обновления портфеля (ByBit или T-Invest), чтобы появились снимки. |
| Chart empty | Нет данных графика за выбранный период. |

All StatTile labels remain as in current `PortfolioPage` (feature parity `[R-5]`).

---

## Out of scope for UI engineer

- Backend / analytics API changes
- Formula or benchmark logic changes
- WebSocket streaming
- Dashboard page behavior changes (except verifying deep-links)
- Full-page retry for accounts summary failure
- Sync progress API / status polling
- Tablet-specific third layout (768–1439 inherits nearest breakpoint)
- Switching to `portfolioService` sync endpoint
- New HTTP paths or renamed API fields

---

## Acceptance checklist (visual)

- [ ] Hero matches dashboard node treatment (`dashboard-hero--node`) in dark + light
- [ ] Toolbar, stats, chart use dashboard card surfaces
- [ ] Overall KPIs: StatTile in `dashboard-summary-grid`, not emoji tiles
- [ ] Sync visible in operations `headerEnd` with loading/disabled/toasts
- [ ] Chart/stats failures show section retry; empty accounts shows robot card without page retry
- [ ] Desktop ≥1440 and mobile ≤767 both accepted: period subset, collapsibles, table mobile rows
- [ ] Feature parity `[R-1]`–`[R-12]` unchanged
