---
name: lightweight-charts-setup
description: >-
  TradingView Lightweight Charts v5 usage aligned with this repo: React wrapper,
  dark/light from data-theme, ResizeObserver, candle/line series, performance.
  Use when adding or changing price charts, indicators overlays, or chart UX
  on the frontend.
---

# Lightweight Charts setup

## Canonical wrapper

Use and extend **`frontend/src/components/ui/Chart.tsx`**:

- Reads theme from `document.documentElement.getAttribute('data-theme') === 'dark'` and sets `layout`, `grid`, `crosshair`, scales accordingly.
- Uses **`ResizeObserver`** to call `chart.applyOptions({ width: container.clientWidth })`.
- Exposes optional **`onReady(chart: IChartApi)`** for parent components to add series.

Prefer **composition** (parent adds series in `onReady`) over forking the wrapper unless the change is global (e.g. new default grid).

## Typical parent pattern

```tsx
import { Chart } from '@/components/ui/Chart'
import type { IChartApi, Time } from '@/components/ui/Chart'
import { CandlestickSeries } from 'lightweight-charts'

// In onReady: const series = chart.addSeries(CandlestickSeries, { ... })
// Set data: series.setData(rows) — map backend OHLC to { time, open, high, low, close }
```

Live examples: `LineSeries` / `AreaSeries` / `CandlestickSeries` + `chart.addSeries(...)` in `PortfolioPage.tsx`, `AnalyticsPage.tsx`, `LivePage.tsx`.

Use **`Time`** from the library for bar timestamps (`UTCTimestamp` or `BusinessDay`).

## UX rules

- **Loading**: show `Skeleton` or a sized placeholder **same height** as the chart to avoid layout jump.
- **Empty / error**: short Russian or English copy + retry; do not leave a blank box.
- **Performance**: update series with `setData` / `update` rather than recreating the chart; throttle high-frequency updates.

## Dependencies

- Package: **`lightweight-charts`** (see root `package.json` for this workspace).

## Anti-patterns

- Creating a second ad-hoc `createChart` without `ResizeObserver` or cleanup (`chart.remove()` on unmount).
- Hardcoding colors that contradict `--color-up` / `--color-down` (`skill://design-system-theme`).
