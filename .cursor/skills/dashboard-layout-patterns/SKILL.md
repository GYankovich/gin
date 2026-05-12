---
name: dashboard-layout-patterns
description: >-
  Desktop-first (1440px+) trading dashboard layout patterns: shell, KPI strip,
  main chart + side panels, dense tables, progressive disclosure. Use when
  designing or implementing dashboard pages, mockups, or navigation structure
  for trading UIs in this repo.
---

# Dashboard layout patterns (mockup + implementation)

## Defaults

- **Viewport**: design for **≥1440px** width first; mobile patterns are secondary unless the user says otherwise.
- **Theme**: dark-first; critical numbers readable at a glance.
- **Hierarchy**: P&L / exposure / risk → positions / orders → detail & settings.

## Mockup template (present 2–3 options)

For each option include:

1. **ASCII or bullet layout** (zones A–E).
2. **Key components** (named widgets).
3. **Interactions** (click row → drawer, shortcuts, WS-driven updates).

Example zone map:

```text
+-------- Navbar (robot / account / alerts) --------+
| [KPI] [KPI] [KPI] [KPI]   (equity, day P&L, DD, status) |
+----------+----------------------+------------------+
| Watchlist|    Main chart        | Order / event    |
| (narrow) |    or multi-chart    | feed + actions   |
|          |                      |                  |
+----------+----------------------+------------------+
| Positions / orders table (full width, virtualized) |
+-----------------------------------------------------+
```

## Implementation anchors (this repo)

- **Shell**: `frontend/src/components/layout/PageLayout.tsx` — `Navbar`, `main`, optional tab bar.
- **New pages**: `frontend/src/pages/*.tsx`, register routes in `frontend/src/app/App.tsx`.
- **Reusable chrome**: `frontend/src/components/ui/Card.tsx`, `KpiTile.tsx`, `PageLayout`-consistent padding.

## Checklist

- [ ] KPI strip always visible on dashboard-style pages.
- [ ] Async regions: skeleton while loading, inline error with retry (see `Skeleton.tsx` patterns).
- [ ] Keyboard: document at least **refresh**, **focus search**, **toggle panel** where applicable.
- [ ] Styling: semantic colors via CSS variables (`skill://design-system-theme`).

## What not to do here

- Do not specify backend routes or DB shapes; consume existing API hooks or placeholders only.
