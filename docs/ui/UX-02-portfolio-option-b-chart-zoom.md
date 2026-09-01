# UX-02: Portfolio layout Option B + independent chart zoom

SPEC companion: extend or supersede chart/period parts of `docs/SPEC-01-portfolio-dashboard-visual-alignment.md` when implementing.

**Chosen:** Option **B** — dashboard-style `Сводка | График` grid.  
**Chart:** full observation history always loaded; zoom presets include **Всё**.

---

## Data model (controls)

| Control | Affects | Does not affect |
|---------|---------|-----------------|
| Account select | All account-scoped loads | — |
| Toolbar period + DateRangePicker | Statistics, snapshots, operations (period filter) | Chart series fetch / zoom |
| Chart zoom presets | Visible time range only (`timeScale`) | Stats / ops / snapshots |
| Chart «бумаги» / legend | Instrument series display | Toolbar period |

**Chart fetch:** once per selected account — full history (`from` = earliest available snapshot / open date, `to` = now). Changing toolbar period must **not** refetch chart.

**Zoom presets** (SegmentedControl on chart card header):

| Preset | Visible window |
|--------|----------------|
| День | last 1 calendar day (or last trading day window) |
| Неделя | last 7 days |
| Месяц | last 30 days |
| Год | last 365 days |
| Всё | `fitContent()` — entire loaded series |

Default zoom: **Месяц** (or **Всё** if series shorter than a month — product: prefer Месяц then clamp).

---

## Layout (desktop ≥1440)

```text
+-- PageHero: PORTFOLIO NODE / ПОРТФЕЛЬ ------------------+
|                                                          |
| B  Card.portfolio-toolbar                                |
|    [Счёт] [Период-фильтр] [DateRange]                    |
|    → label intent: «Период данных» (stats / ops / snaps) |
|                                                          |
| C+D  dashboard-currency-row / dashboard-currency-grid    |
|    +----------------------+-----------------------------+|
|    | C Сводка             | D Стоимость портфеля        ||
|    | KPI за период фильтра| [Д|Н|М|Г|Всё] [бумаги]      ||
|    | + period details     | full-history series         ||
|    |   (collapse mobile)  | crosshair / legend          ||
|    +----------------------+-----------------------------+|
|                                                          |
| E  Состав портфеля (CollapsibleSection)                  |
| F  История снимков (period-filtered)                     |
| G  История операций + sync (period-filtered)             |
+----------------------------------------------------------+
```

**Mobile ≤767:** stack toolbar → сводка → chart collapse → composition → snaps → ops. Chart zoom strip stays in chart header (`headerEnd` or midbar). Toolbar omits «3 месяца» as today if still in filter presets.

---

## Zone details

### B — Toolbar (period **filter**)

- Same controls as today: account, SegmentedControl periods, DateRangePicker.
- Copy / aria: treat as **filter for tables & stats**, not chart range.
- Optional microcopy under toolbar (optional, not required for v1): «Период влияет на статистику и историю».

### C — Сводка

- KPI for **selected filter period** (existing overall + period metric set; keep feature parity).
- Surface: `dashboard-totals-card` + shared dashboard metric chrome.
- Stats retry on section error (existing pattern).

### D — График

- Title: «Стоимость портфеля» (keep product name; not «Динамика» from cancelled mockup).
- Header right: zoom `SegmentedControl` (День / Неделя / Месяц / Год / Всё) + papers `Toggle`.
- Body: Lightweight Charts area/lines; load full history; apply preset via visible range.
- Empty / error / retry: existing `dashboard-error-card` language.
- Height: desktop ~360 in grid cell; mobile 240.

### E–G

- Unchanged behavior; E open desktop / closed mobile; F/G default closed; G sync in `headerEnd`.

---

## Interactions

1. Change account → reload positions, period bundle (stats/snaps/ops), **and** full chart history; reset zoom to default (Месяц).
2. Change toolbar period/dates → reload stats + snapshots + operations only.
3. Change zoom preset → no network; set visible range from last point backward (or fitContent for Всё).
4. Pan/zoom by gesture: allowed; may clear active preset highlight to «custom» or leave nearest preset — **recommend:** leave preset selected until user picks another; optional later: deselect when range drifts.
5. Instruments mode / legend / select-all: unchanged; still on full-history series.

---

## Visual language (from `/dashboard`)

- `PageHero` + `dashboard-hero--node`
- Cards: `dashboard-totals-card`, `dashboard-assets-card` (chart)
- Grid: `dashboard-currency-grid` (1fr | 1fr desktop)
- Collapses: `dashboard-accounts-collapse` / `dashboard-assets-collapse`
- Tokens: `--bg-card`, up/down, no new purple/glow theme

---

## Out of scope (this pass)

- code.html 2/3+1/3 composition mockup
- New backend endpoints (unless full-history request needs a sentinel date already supported)
- Changing FIFO / ROI formulas

---

## Open for implementer

- Earliest chart `from_date`: use account first snapshot date from API if available; else far-past constant already used for «Всё время» (e.g. 3650d) on chart-only request.
- Intraday vs daily bars: keep current series granularity from `/analytics/chart_series`.

---

## Acceptance (manual, local)

- [ ] Toolbar period changes stats/ops/snaps without chart refetch
- [ ] Chart shows history beyond toolbar window when zoom = Всё / Год
- [ ] Presets День…Всё change visible range only
- [ ] Desktop: сводка | график side-by-side; mobile stacked
- [ ] Dark + light readable; no auto CI build required for review
