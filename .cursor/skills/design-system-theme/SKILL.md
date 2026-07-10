---
name: design-system-theme
description: >-
  GIN frontend theme tokens, dark default, Zustand theme store, data-theme
  attribute, and semantic colors for trading (up/down). Use when styling new
  UI, charts, tables, or mockups that must match the existing cyber-trading look.
---

# Design system and theme

## Source of truth

1. **`frontend/src/styles/variables.css`** — spacing scale, z-index, **trading semantics**:
   - `--color-up`, `--color-down`, `--color-warn`
   - Dark surfaces: `--bg-page`, `--bg-card`, `--text-primary`, borders
2. **`frontend/src/shared/styles/theme.css`** — alternate / extended token set (`--color-success`, `--accent`, …). Prefer **one consistent token family per feature**; do not mix conflicting backgrounds in the same card.

Charts read **`data-theme`** in `Chart.tsx`; keep that attribute in sync with the store.

## Runtime theme switch

- **Store**: `frontend/src/stores/themeStore.ts` (`zustand`)
  - Persists to **`localStorage['gin-theme']`**
  - Sets **`document.documentElement.setAttribute('data-theme', t)`** where `t` is `'dark' | 'light'`
- **Default**: `'dark'` if nothing stored.

New root-level UI must **not** assume only CSS `:root`; test with **`data-theme='light'`** when touching global backgrounds.

## Implementation rules

- Prefer **CSS variables** over hardcoded hex in TSX (exceptions: third-party canvases where the API requires hex — still derive from theme branch like `Chart.tsx`).
- **Cards / panels**: `background: var(--bg-card)`, `border: 1px solid var(--border-subtle)` (or `var(--border)` from `theme.css` — match sibling components on the same page).
- **Typography**: `var(--font-sans)`, sizes from `--text-*` in `variables.css`.

## shadcn / Tailwind note

This repo uses **Vite + shared CSS** heavily. If adding Tailwind/shadcn later, **map** utilities to the same CSS variables at the theme layer so charts and legacy CSS stay aligned.

## Checklist for new screens

- [ ] Works in **dark** (default)
- [ ] No unreadable contrast on `--bg-card`
- [ ] P&L uses **semantic** up/down colors consistently
- [ ] Focus rings visible for keyboard users (match existing controls)
