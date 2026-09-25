# UX-04: Robots V2 visual alignment with Portfolio / Dashboard

Reference: [UX-01](UX-01-portfolio-dashboard-visual-alignment.md), Portfolio + Dashboard chrome.

## Goal

Unify `/robots` (Robots V2) with the Portfolio family: shared hero subnav, `StatTile` KPIs, `DataTable` / `DateRangePicker` / `Modal` / `SegmentedControl`, section empty/error contracts. No Analytics `KpiTile`. API/WS behavior unchanged.

## Layout rhythm

```text
page[data-page=robots]   /* same attribute as Dashboard/Portfolio hero-node CSS */
  RobotPageChrome (PageHero + Флот/Лайв/Правка/Логи/Бэктест + primary actions)
  dashboard-layout
    [KPI] dashboard-totals-card + StatTile
    [Stage] RobotStageCard (monitor / backtest)
    [Chart] dashboard-assets-card
    [Tables] DataTable in cards / CollapsibleSection / portfolio-history-zone
```

Hero copy/title/actions use shared `[data-page='robots'] .dashboard-hero--node …` rules (with dashboard/portfolio), including `.dashboard-hero__copy`.

## Shared components

| Widget | Path |
|--------|------|
| Subnav chrome | `frontend/src/pages/robots-v2/components/RobotPageChrome.tsx` |
| Confirm modal | `frontend/src/pages/robots-v2/components/RobotConfirmModal.tsx` |
| Stage progress | `frontend/src/pages/robots-v2/components/RobotStageCard.tsx` |
| Formatters / RU status | `frontend/src/pages/robots-v2/formatters.ts` |

## Per-page zones

### Fleet (`robots-v2-fleet`)

- Hero: subtitle + create CTAs
- CollapsibleSection groups (опросники / торговые) with `dashboard-account-stack`
- Empty: `dashboard-empty`; error: `dashboard-error-card` + retry
- Delete / hard stop: `RobotConfirmModal`

### Monitor (`robots-v2-monitor`)

- Chrome + Start / Soft / Hard stop (hard via Modal)
- Day + session `StatTile` in one totals card
- `RobotStageCard` → equity chart → DataTable (orders, positions, scan) → decisions / live stream cards

### Logs (`robots-v2-logs`)

- Full chrome; Export / Refresh in actions
- Source + stream filter: `SegmentedControl`
- Audit tables: `DataTable`; stream: summary row + expand JSON

### Backtest (`robots-v2-backtest`)

- Chrome; Run / Cancel in actions
- Toolbar: period `SegmentedControl` + `DateRangePicker` + capital
- `RobotStageCard` while running; results KPI → chart → trades `DataTable` + collapses

### Wizard (`robots-v2-wizard`)

- Create: `fleetOnly` chrome; Edit: full detail chrome (`active=edit`)
- Restore draft: `RobotConfirmModal` (no `window.confirm`)
- Shell unchanged (steps | form | summary)

## State contract

| State | UI |
|-------|-----|
| loading | Skeleton / «Загрузка…» in section |
| ready | Content |
| empty | `dashboard-empty` |
| error | `dashboard-error-card` + retry where list-scoped |

## Checklist

- [ ] Dark + light `data-theme`
- [ ] Subnav consistent on monitor / logs / backtest / edit
- [ ] No `window.confirm` on fleet / wizard / hard stop
- [ ] Tables use `DataTable` (mobilePrimary where dense)
- [ ] User-facing statuses in RU (`sessionStateLabel`)
- [ ] Mobile ≤767: collapses / DataTable mobile rows
