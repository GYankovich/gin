---
name: trading-table-patterns
description: >-
  Dense trading tables: sorting, row actions, MOEX-style up/down coloring,
  optional virtualization, loading and empty states. Use when building
  positions, orders, watchlists, or logs tables on the frontend.
---

# Trading table patterns

## Default component

Use **`frontend/src/components/ui/DataTable.tsx`** unless the user requires virtualization (then add `@tanstack/react-virtual` or similar in a thin wrapper — not in the repo root `package.json` today).

### Props to know

- **`columns`**: `Column<T>` with `key`, `header`, optional `render`, `sortable`, `align`, `width`.
- **`data`**, **`keyField`**: stable row id.
- **`onRowClick`**, **`rowClassName`**: for selection / P&L row tint.
- **`maxHeight`**: scroll body for long lists (desktop dashboards).
- **Mobile**: `mobilePrimary`, `mobileSecondary`, `mobileDetails` exist — **omit or keep minimal** when the task is desktop-first (1440px+).

## States (mandatory)

| State | UI |
|-------|-----|
| Loading | Skeleton rows or shimmer block matching table height |
| Empty | `emptyText` (default already Russian: «Нет данных») — customize per domain |
| Error | Banner above table + retry; do not fail silently |

## MOEX-style semantics

- **Up / profit**: `var(--color-up)` or success token from `variables.css` / `theme.css` — stay consistent within a screen.
- **Down / loss**: `var(--color-down)` or danger token.
- **Neutral**: secondary text color; avoid random greens/reds.

Use **`rowClassName`** for signed P&L columns instead of inline rainbow per cell when possible.

## Performance

- Memoize **`columns`** if defined inline (or extract outside component).
- For **>500 rows** visible scroll: prefer virtualization in a dedicated component; keep sort stable.

## Accessibility

- Header cells for sortable columns should remain **buttons** or have **keyboard** activation if customized.
- Announce bulk errors via existing toast patterns if the page already uses them.
