# UX-05: Glass-box backtest results (vertical story + drawer)

SPEC: docs/SPEC-03-glass-box-backtest-observability.md  
Chosen option: **B** (vertical story + slide-over / sheet inspector)  
Surface: `/robots/:id/backtest` — redesign `BacktestResultsPanel`; keep launch toolbar, `RobotStageCard`, `BacktestHistoryCard` / compare placement  
Viewport: desktop-first **≥1440**; **mobile is a real priority** for this option (natural stack + full-screen inspector sheet)

**Status:** P0 shipped · P1 addendum in this file · **P2 addendum below — await product approval before UI implements P2**

---

## Layout (zones)

P0 zones in detail; P1 **M / L / K** in [P1 addendum](#p1-addendum--universe-holdings-costs); P2 **N / O / P** in [P2 addendum](#p2-addendum--price-overlay-lifecycle-narrative). Launch / progress / history stay outside the redesigned results composition but keep current page order.

```text
RobotPageChrome (unchanged)
Launch toolbar (period / capital) — unchanged
[Running] RobotStageCard — unchanged

=== BacktestResultsPanel (SUCCESS / partial completed) ===

A  Honesty banner          ← always visible, never collapsed
B  KPI StatTiles           ← scoreboard (dashboard-totals-card)
C  Run anatomy strip         stages / history_stats / funding hint if any
D  Equity timeline + trade markers (full width Chart)
E  Reject lens (top 8)     ← always visible under chart, not in CollapsibleSection
--- tables (secondary beat) ---
H  Trades DataTable        ← open by default
G  Signals CollapsibleSection (+ pagination when >5k)
I  Daily rhythm CollapsibleSection
   Orders: keep CollapsibleSection, de-emphasized (not glass-box primary)

=== page tail (unchanged placement) ===
J  BacktestHistoryCard + KPI/config compare
   Optimization card stays as today if present
```

### Desktop (≥1440)

```text
+-- A honesty banner (full width) --------------------------------------+
| B KPI StatTiles                                                       |
| C anatomy chips / caption                                             |
+-----------------------------------------------------------------------+
| D Equity + markers                                                    |
| E Reject lens chips (top 8) + compact status_counts                    |
+-----------------------------------------------------------------------+
| H Trades                                                              |
| G Signals (collapse)                                                  |
| I Daily (collapse)                                                    |
|   Orders (collapse, secondary)                                        |
+-----------------------------------------------------------------------+
| J History + compare                                                   |
+-----------------------------------------------------------------------+
          >>> F Decision inspector = right slide-over drawer
              (overlays content; does not push chart narrower)
```

### Mobile (must not break)

```text
A → B → C → D → E → H → G → I → J   (single column stack)
F = full-screen sheet (not a narrow side drawer)
Tables: keep CollapsibleSection / DataTable mobilePrimary patterns
No horizontal overflow; chart height may shrink (~220–260) but stays readable
```

### Glass-box clarity constraint (despite drawer)

- **A** and **E** must be above-the-fold on desktop results (banner + KPI + anatomy + chart + reject lens before any collapsed block).
- **P1:** only a single compact **M** StatTile row may sit between **C** and **D**; **L**/**K** stay collapsed-by-default below **E**.
- **P2:** price/scrubber (**N**) is a **submode of D** that appears only after a decision is selected — not a permanent tall block that pushes **E** off the first paint. Narrative (**P**) is collapsed below the tables. Intent lifecycle (**O**) lives inside **F**, not in the main column.
- First click on equity **marker**, **trade row**, or **signal row** opens **F** immediately (no intermediate confirm / expand).
- Empty **F** (desktop drawer open-from-affordance optional; preferred: drawer closed until first selection) shows short RU hint when opened without selection, or a one-line caption under **E**: selecting a marker/row shows the engine decision.

### Phase hooks

| Phase | Placement (Option B) |
|-------|----------------------|
| P0 | **A–J** as above (shipped) |
| P1 | **M** compact costs under **C**; **L** holdings after **E**; **K** universe after **I** — see [P1 addendum](#p1-addendum--universe-holdings-costs) |
| P2 | **N** price+scrubber as **D** submode on selection; **O** intent↔fill inside **F**; **P** narrative CollapsibleSection after **K** — see [P2 addendum](#p2-addendum--price-overlay-lifecycle-narrative) |

---

## Components (named → existing primitives)

| Zone | Widget | Map to |
|------|--------|--------|
| A | Execution honesty + truncation / partial / cancel banners | `robots-v2-banner` variants (`--error` / warn tone); copy from `observability.execution_model` + truncation flags |
| B | KPI strip | `Card` `dashboard-totals-card` + `StatTile` (same grid as today): капитал, equity, доходность, Max DD, win rate, Sharpe, Sortino, Calmar, сделки |
| C | Run anatomy | Compact caption / chip row under KPIs (today’s `stages.join` pattern); include warmup, traded bars, skipped schedule; **funding hint only if** `funding_charges_total ≠ 0` or funding events present |
| D | Equity timeline | `Card` `dashboard-assets-card robots-v2-monitor-chart` + `Chart` LineSeries; **trade markers** (buy/sell / PnL tint) clickable |
| E | Reject lens | Horizontal chip / compact list — top **8** from `observability.reject_reason_counts`; show count; use `tradeReasonLabel` / RU reject labels; compact `status_counts` (filled / rejected / deferred) beside or under chips. Density like `MonitorDecisionsCard`, not a live dump |
| F | Decision inspector | **Desktop:** right slide-over panel (`Card` / drawer shell, focus trap). **Mobile:** full-screen sheet. Content = decision packet fields from SPEC §3.2 |
| H | Trades table | `DataTable` (open card, as today) + `onRowClick` → F; PnL via `robots-v2-pnl--up/down` |
| G | Signals / decisions table | `CollapsibleSection` + `DataTable`; filters sync from E; pagination UI when total > 5k (offset/limit from SPEC); row → F |
| I | Daily rhythm | `CollapsibleSection` + `DataTable` on `daily_summary` (keep columns accept/reject/defer/trades) |
| — | Orders | Existing `CollapsibleSection` + `DataTable`; secondary; row may open F if `cycle_id` present |
| J | History + compare | `BacktestHistoryCard` unchanged placement and KPI-only compare |
| Labels | Strategy / reject codes | `tradeReasonLabels` (+ extend missing reject RU); unknown → raw code |
| Shell | Page | `RobotPageChrome`, `dashboard-layout`, launch toolbar, `RobotStageCard` — unchanged |

Inspector body (F) fields — use SPEC names, no parallel vocabulary:

- `cycle_id`, `signal_time` / `bar_time`, `ticker`/`figi`, `kind`, `side`, `status`
- `strategy_reason` (+ RU label), `reject_reason` (+ RU label)
- `quantity`, `price`, `pnl_net`
- `linked_trade_ids`, `execution_note` (e.g. «исполнение на открытии следующего бара»)
- Optional config/risk excerpt if available from cycle bundle

---

## Interaction map (clicks, keyboard)

| Action | Result |
|--------|--------|
| Click equity trade marker | Open **F** for that trade’s `cycle_id` (fetch cycle bundle if signals paginated / sparse) |
| Click trade row (H) | Same → **F** |
| Click signal row (G) | Same → **F** |
| Click reject chip (E) | Filter **G** by `reject_reason`; expand **G** if collapsed; do **not** require opening F; if a single obvious match is already selected, keep F in sync |
| Clear reject filter | Chip toggle off / «Все» control |
| Close inspector | Esc, overlay click (desktop), sheet close control (mobile) |
| History row open (J) | Load that run’s full glass-box results (as today); compare remains KPI + `config_diff` only — no dual inspector |
| Running / queued | No fake markers; optional honesty line on stage that fills finalize after complete (nice-to-have) |

**Keyboard (desktop, when results focused):**

| Key | Behavior |
|-----|----------|
| `Esc` | Close **F** |
| `j` / `k` | Next / previous trade row when **F** open (update inspector) |
| `←` / `→` | Optional: step trade markers on timeline when **F** open |
| `/` | Focus signals filter / ticker filter if present (nice-to-have) |

**Time-to-answer target:** ≤ 2 clicks from completed results to “why” — first click on marker/row is sufficient.

---

## States (loading / empty / error / stale)

| State | Behavior |
|-------|----------|
| Loading details | Skeleton for **B** / **D** / **E**; **A** may show `run_id` if known |
| Running / queued | `RobotStageCard` only for results body; no fabricated trades/markers |
| SUCCESS | Full A–I composition |
| Empty trades, signals present | **D** curve ok, markers empty; **E**/**G** explain reject-dominated run |
| Empty reject lens | **E** shows «Отказов по риску не зафиксировано» (or equivalent); still visible |
| Truncated signals | Persistent banner in **A**; **E** caption «по залогированному окну» when `signals_truncated` |
| Cancelled / partial | Banner in **A**; KPIs for available interval; glass box over available artifacts only |
| Error | Inline `dashboard-error-card` + retry; **J** history still usable |
| Inspector empty | Short RU hint (see Copy) |
| Inspector missing cycle | Show available packet fields + «Связь с циклом недоступна» if `cycle_id` absent `[GAP if stamp missing on old runs]` |
| Signals > 5k | Paginate **G**; details may omit full `signals[]` — inspector uses cycle endpoint / filtered page |
| Mobile | Stack A→J; **F** = full-screen sheet |

WS / realtime stale: **N/A** for P0–P1 results (poll status only).

---

## Token notes (up/down, density)

- Dark-first; honor `data-theme` light as well (`variables.css` / chart theme via `Chart`).
- P&L / return / equity vs capital: `--color-up` / `--color-down` (`color-up` / `robots-v2-pnl--*`).
- Honesty / truncation: warn tone (`--color-warn` / existing banner warn), not success green.
- Reject chips: neutral surface + border; active filter = accent/selected state already used on robots-v2 chips — no new palette.
- Markers: buy/entry up-tint, sell/exit down-tint or side-consistent; avoid decorative glow.
- Density: trading-dashboard — tight StatTile grid, chart ~280–360 desktop / ~220–260 mobile; table `maxHeight` as today (~320–360).
- Drawer/sheet z-index: match existing modal/overlay scale; focus ring visible.

---

## Copy (labels, empty-state text)

| Place | RU copy |
|-------|---------|
| A execution | «Исполнение на открытии следующего бара · без look-ahead» (from `observability.execution_model.label`; do not show bare `BAR_CLOSE` as fill model) |
| A truncation | «Журнал сигналов обрезан (лимит {cap}). Статистика отказов — по залогированному окну.» |
| A partial / cancel | «Прогон частичный / отменён — метрики и решения только по доступному интервалу.» |
| F empty | «Выберите сделку на графике или строку в таблице — покажем решение движка: вход, выход, отказ или отложение.» |
| E empty | «Отказов по риску не зафиксировано» |
| E header | «Почему не вошли» / «Отказы (топ-8)» |
| D empty curve | «Нет точек equity за выбранный период» (keep) |
| H empty | «Сделок не было — проверьте период, расписание и сигналы стратегии» (keep) |
| G empty | «Нет сигналов за период» / filtered: «Нет сигналов с этим кодом отказа» |
| C funding hint | «Funding: {amount}» only when events / total ≠ 0 |
| Status chips | Исполнено / Отказ / Отложено (`status_counts`) |

Reason cells: always `tradeReasonLabel(code)`; show raw code as secondary mono if useful in **F**.

---

## Out of scope for UI engineer

- New HTTP path design (consume SPEC-03 contracts as implemented by backend).
- Deep glass-box compare / dual inspectors / dual equity markers (**R-15** P0 out; P1 may optionally enrich compare metrics only — see addendum).
- Dual-run glass compare / narrative diff (still out unless product revisits).
- Fill-model rewrite; billing/auth.
- Live monitor wiring (label reuse only).
- Production styling inventing a new product skin — extend `BacktestResultsPanel` chrome.
- P1/P2 details: see addenda (not “hooks only” anymore).

### Backend dependency (from SPEC — not UI paths)

**P0 (shipped expectation):** details/`observability` + flattened decision fields + `cycle_id` on trades/signals; paginated signals when >5k; optional cycle bundle when client join is insufficient.

**P1:** see [API fields UI needs (P1)](#api-fields-ui-needs-p1).

**P2:** see [API fields UI needs (P2)](#api-fields-ui-needs-p2).

P0 soft-degrades still apply for old runs:

- `[GAP: cycle_id on historical runs before persist stamp]` — soft-degrade in F

---

## Implementation checklist (UI) — P0

- [x] Zones **A–E** visible without opening collapses; **A** + **E** not buried
- [x] Markers + trade/signal rows open **F** on first click
- [x] Desktop drawer / mobile full-screen sheet
- [x] Reject lens top 8; chip → filter signals
- [x] Signals pagination when total > 5k
- [x] Funding hint in anatomy only when events/total
- [x] `tradeReasonLabels` (+ reject RU fallbacks)
- [x] Truncation + execution honesty always when applicable
- [x] History/compare (**J**) unchanged KPI-only
- [x] Dark + light; no horizontal breakage on mobile

---

## P1 addendum — universe, holdings, costs

**Refs:** `[R-9]` universe · `[R-10]` holdings · `[R-11]` costs/funding strip  
**Layout rule:** Option B unchanged (vertical story + desktop drawer / mobile sheet). **A** and **E** stay above-the-fold; P1 must not insert tall blocks between **A** and **E**.

### P1 zone order (results body)

```text
A  Honesty banner                         ← P0, above fold
B  KPI StatTiles                          ← P0
C  Run anatomy                            ← P0; funding *hint* remains if M hidden
M  Costs / funding strip                  ← P1 [R-11] compact StatTiles; hide if all-zero/absent
D  Equity + trade markers                 ← P0
E  Reject lens (top 8)                    ← P0, still above fold
--- below-fold / progressive disclosure OK ---
L  Holdings at sample time                ← P1 [R-10] CollapsibleSection (or open when time pinned)
H  Trades
G  Signals
I  Daily rhythm
K  Universe membership over time          ← P1 [R-9] CollapsibleSection
   Orders (secondary)
J  History + compare
F  Inspector drawer/sheet (P0; optional L snapshot line when time pinned)
```

**Desktop**

```text
+-- A · B · C ----------------------------------------------------------+
| M  [Комиссия] [Funding] [Funding #] [Налог?]     ← one StatTile row  |
+-----------------------------------------------------------------------+
| D  Equity + markers                                                   |
| E  Reject lens                                                        |
+-----------------------------------------------------------------------+
| L  Позиции на {sample_time}   (CollapsibleSection)                    |
| H / G / I / K / Orders                                                |
+-----------------------------------------------------------------------+
| J  History                                                            |
+-----------------------------------------------------------------------+
```

**Mobile stack:** `A → B → C → M → D → E → L → H → G → I → K → J` · **F** = full-screen sheet · no horizontal scroll on **M** (wrap StatTiles) or **K** day chips (horizontal scroll *inside* the section only, page itself does not overflow).

### Why this placement

| Zone | Where | Why |
|------|-------|-----|
| **M** | Directly under **C** | Costs are scoreboard-adjacent; one compact row does not bury **E**. When `fee_summary` exists, it **supersedes** repeating the P0 funding hint in **C** (keep anatomy process facts; drop duplicate funding line). |
| **L** | After **E**, before **H** | Holdings are secondary to reject clarity; default collapsed so fold stays clean. |
| **K** | After **I** | Universe is run-anatomy depth, not first-click “why trade”; collapsed by default. |

### P1 components → primitives

| Zone | Widget | Primitive / pattern |
|------|--------|---------------------|
| **M** | Costs strip | `Card` or inline row under anatomy + `StatTile`: `commission_total`, `funding_total`, `funding_events`, optional `tax_total`. Signed/neutral money via `fmtMoney`; funding/commission use neutral or warn if material — not fake “up” green |
| **L** | Holdings at sample | `CollapsibleSection` + `DataTable` columns: ticker/`figi`, `side`, `qty`, `avg_entry`, `mark` (optional notional = qty×mark). Empty → RU empty copy |
| **L** | Sample-time control | Compact control in **L** header (and optional cue under **D**): «У маркера» (nearest snapshot to selected trade/marker) · «Начало» · «Середина» · «Конец» run — **not** full P2 bar scrubber |
| **K** | Universe over time | `CollapsibleSection` + either (1) day `DataTable` (date, size, adds, drops) with row expand / second table of tickers, or (2) day chip strip + ticker list. Prefer table-first for desktop density |
| **J** (optional P1) | History truncation badge | Small badge on history row when `signals_truncated` / `history_stats.signals_truncated` |
| **J** (optional P1) | Compare fee / reject | If compare payload gains fields: show commission/funding totals + top reject counts in existing compare `StatTile` block — **no** dual inspector |

### P1 interaction map

| Action | Result |
|--------|--------|
| Load completed run with `fee_summary` | Show **M**; hide duplicate funding hint in **C** |
| No `fee_summary` / all zeros | Hide **M** entirely; keep P0 **C** funding hint rules |
| Select trade marker / open **F** | Pin **L** sample time to nearest `portfolio_snapshots[].time` (or snapshot timestamp field as shipped); badge «у маркера»; do not auto-expand **L** on mobile |
| Change **L** sample (начало / середина / конец / у маркера) | Reload holdings table from nearest snapshot; if none, empty state |
| Expand **K** | Fetch/show universe membership (details embed or universe endpoint); default range = run period |
| Pick day in **K** | Show tickers for that `trade_date`; optional highlight adds/drops vs previous day if API returns sparse diff |
| Click ticker in **K** | Optional: filter **G** signals by ticker (nice-to-have); do not navigate away |
| Compare two runs (optional) | KPI + config_diff as P0; if present, also fee totals / reject_reason_counts — still no glass deep-compare |

**Keyboard:** P0 shortcuts unchanged. No new required shortcuts for P1; **L** sample segmented control is pointer/focusable like existing `SegmentedControl`.

### P1 states

| State | Behavior |
|-------|----------|
| Loading P1 artifacts | Skeleton row for **M** only if details promise fees; **L**/**K** skeleton inside section when expanded |
| **M** absent | Zone omitted (no empty card) |
| **L** no rich positions (count-only legacy) | Section visible with «Детализация позиций недоступна для этого прогона» — `[GAP: rich positions on old runs]` |
| **L** snapshot empty at sample | «На этот момент позиций не было» |
| **K** empty / not persisted | Collapse header badge «нет данных»; body empty copy — `[GAP: universe membership for run]` |
| **K** large day×ticker | Prefer paginated/day-scoped fetch (`from`/`to` or single day); do not dump full matrix into DOM |
| Partial / cancelled run | **M**/**L**/**K** over available artifacts only; same honesty banner **A** |
| Mobile | Stack; **M** wraps; **K** internal horizontal chip scroll OK; **L**/**K** default collapsed |

### P1 token / density notes

- Same theme tokens as P0; **M** uses same `StatTile` density as **B** (one row, 3–4 tiles).
- Adds in **K**: subtle up/neutral; drops: down/warn — membership change ≠ PnL; prefer neutral + labels «+»/«−» over strong green/red.
- Holdings PnL mark vs avg_entry: optional small delta with `--color-up` / `--color-down` only when both present.

### P1 copy (RU)

| Place | Copy |
|-------|------|
| **M** labels | «Комиссия» · «Funding» · «События funding» · «Налог» (hide tax tile if `tax_total` null/absent) |
| **M** title (optional) | «Издержки» |
| **L** title | «Позиции на {datetime}» |
| **L** empty | «На этот момент позиций не было» |
| **L** legacy | «Детализация позиций недоступна для этого прогона» |
| **L** sample | «У маркера» · «Начало» · «Середина» · «Конец» |
| **K** title | «Вселенная» |
| **K** empty | «Нет данных о составе вселенной за прогон» |
| **K** day row | «{date} · {n} тикеров» · «+{adds} / −{drops}» when diff known |
| History badge (optional) | «сигналы обрезаны» |

### API fields UI needs (P1)

Do not invent paths; consume SPEC-03 §5.3 / §6.3 field names:

| Need | Fields / source |
|------|-----------------|
| Costs strip **M** `[R-11]` | `fee_summary.commission_total`, `fee_summary.funding_total`, `fee_summary.funding_events`, optional `fee_summary.tax_total` on details / `result_payload` / `metrics_summary` |
| Holdings **L** `[R-10]` | `portfolio_snapshots[]` with time + `positions: [{ ticker, qty, side, avg_entry, mark }]` (not position **count** only). Sampling ≤500 as SPEC |
| Universe **K** `[R-9]` | Membership rows: `trade_date`, `ticker` (+ optional `source`, `filter_result`, `reject_reason`); and/or sparse adds/drops. Range via `from`/`to` query on universe read |
| Optional compare | `reject_reason_counts` + fee fields on both sides of compare payload |
| Optional history | truncation flag for list badge (`signals_truncated` / `history_stats.signals_truncated`) |

Gaps until backend lands:

- `[GAP: needs API for fee_summary on run details]`
- `[GAP: needs API for portfolio_snapshots[].positions array]`
- `[GAP: needs API for universe membership (or universe_by_day) for run]`

### P1 out of scope

- Dual-run glass compare
- Changing reject-lens or honesty placement
- New visual skin
- P2 features — see [P2 addendum](#p2-addendum--price-overlay-lifecycle-narrative)

### P1 implementation checklist (UI) — after approval

- [ ] **M** under **C**; hidden when no fees; no duplicate funding in **C** when **M** shown
- [ ] **A** + **E** remain above fold on ≥1440 with **M** visible
- [ ] **L** after **E**; sample time sync from marker/selection; DataTable of rich positions
- [ ] **K** after **I**; day → tickers; collapsed by default
- [ ] Mobile stack without page-level horizontal breakage
- [ ] Soft empty/legacy states for old runs
- [ ] Optional: history truncation badge; compare fee/reject if API provides

---

## P2 addendum — price overlay, lifecycle, narrative

**Refs:** `[R-12]` bar scrubber + price overlay · `[R-13]` intent↔fill lifecycle · `[R-14]` in-product narrative (RU end-user voice — locked)  
**Layout rule:** Option B unchanged (vertical story + desktop drawer / mobile sheet). **A** + **E** stay above-the-fold on first paint. P2 must not add always-visible tall zones between **A** and **E**.

### P2 zone order (results body)

```text
A  Honesty                                          ← P0, above fold
B  KPI
C  Anatomy
M  Costs                                            ← P1, compact
D  Equity + markers                                 ← P0
   N  Price window + scrubber (D submode)            ← P2 [R-12] only when decision/ticker selected
E  Reject lens                                      ← P0, first paint without N expanded
--- below fold / progressive disclosure ---
L  Holdings                                         ← P1
H  Trades
G  Signals
I  Daily
K  Universe                                         ← P1
P  Narrative stream                                 ← P2 [R-14] CollapsibleSection, default collapsed
   Orders (secondary)
J  History + compare
F  Inspector drawer/sheet
   └ O Intent ↔ fill lifecycle                      ← P2 [R-13] first-class block inside F
```

**Desktop (selection active)**

```text
+-- A · B · C · M ------------------------------------------------------+
| D  Equity curve + trade markers                                       |
|    [scrubber playhead synced to around]                               |
|    N  Цена {ticker}  Candlestick/OHLC window (height-capped)          |
| E  Reject lens                                                        |
+-----------------------------------------------------------------------+
| L · H · G · I · K                                                     |
| P  История прогона (narrative)   ← collapsed                          |
+-----------------------------------------------------------------------+
| J  History                                                            |
+-----------------------------------------------------------------------+
          >>> F Decision inspector
              packet (P0) + O lifecycle steps (deferred→fill/reject/drop)
```

**Idle (no selection):** **D** shows equity only — same fold as P0/P1; **N** absent.

**Mobile stack:** `A → B → C → M → D(N if active) → E → L → H → G → I → K → P → J`  
**F** = full-screen sheet: packet → **O** lifecycle → optional compact price peek (same window as **N**, or link «к графику» scrolling to **D**). Prefer **one** primary price chart: desktop **N** in **D**; mobile price may render inside **F** below **O** to avoid stacked tall charts when sheet is open. Page must not horizontally overflow; scrubber is full-width under chart.

### Why this placement

| Zone | Where | Why |
|------|-------|-----|
| **N** | Submode of **D**, gated on selection | Price context answers “what did the bar look like?” next to the equity story without a permanent second hero chart burying **E** |
| **O** | Inside **F** | Lifecycle is per-`cycle_id`; belongs with the decision packet, not a main-column table competing with trades |
| **P** | After **K**, collapsed | Run story is demoware / education; must not steal first-click glass-box path |

### P2 components → primitives

| Zone | Widget | Primitive / pattern |
|------|--------|---------------------|
| **N** | Price window | Second series area in **D** `Card`: `Chart` + `CandlestickSeries` (or OHLC) from read-time candles — **not** stored on the run. Header: ticker + window label |
| **N** | Bar scrubber | Range control under charts (native range input or lightweight scrubber): sets `around` (and optional bar index). Sync playhead marker on equity + price charts. Reuse `SegmentedControl` only for window size presets (e.g. ±20 / ±50 / ±100 bars) if helpful |
| **O** | Intent↔fill lifecycle | Inside **F**: vertical step list (same density as `MonitorDecisionsCard` / compact `DataTable`) ordered by time — statuses: deferred → filled / rejected / dropped (use API status strings; RU labels) |
| **P** | Narrative stream | `CollapsibleSection` + scrollable list of steps: `section`, `step`, `text`, `ts` — RU end-user prose as returned; do not rewrite voice in UI |
| **D↔F sync** | Selection bridge | Selecting marker/row opens **F** (P0) **and** activates **N** for packet `ticker`/`figi` around `signal_time` or fill `bar_time` |

### P2 interaction map

| Action | Result |
|--------|--------|
| Click marker / trade / signal row | Open **F** + load **O** for `cycle_id` + activate **N** (`ticker`, `around` = signal or fill time per packet; prefer fill `bar_time` when status=filled, else `signal_time`) |
| Scrub **N** / drag playhead | Update `around`; refetch price-window if outside loaded buffer; sync **L** sample to nearest snapshot (P1); highlight nearest narrative step in **P** if expanded |
| Change window preset (±bars) | Refetch price-window with new `bars` |
| Close **F** / clear selection | Collapse **N** back to equity-only **D** (optional keep last ticker until next selection — prefer collapse for fold clarity) |
| Expand **P** | Fetch/show narrative steps for run; empty → RU empty copy |
| Click narrative step | If `cycle_id` / trade link present → open **F** + **O** + **N**; else scrub playhead to `ts` only |
| Click lifecycle step in **O** | Scrub **N** to that event’s time; keep **F** open |
| Reject chip (E) | Unchanged (filters **G**); does **not** auto-open **N** |

**Keyboard (desktop, extends P0):**

| Key | Behavior |
|-----|----------|
| `Esc` | Close **F**; collapse **N** to equity-only |
| `j` / `k` | Next/prev trade (P0) — refresh **O** + **N** |
| `[` / `]` | Nudge scrubber one bar left/right when **N** active |
| `Esc` on narrative focus | Collapse **P** only if **F** already closed |

### P2 states

| State | Behavior |
|-------|----------|
| No selection | **N** hidden; **O** not shown; **P** collapsed |
| Loading price-window | Skeleton in **N** pane (fixed height); keep last candles if refetching scrub |
| Price-window error | Inline error + retry in **N**; equity remains |
| Loading execution-events | Skeleton steps in **O** |
| Lifecycle empty / legacy run | **O** shows «Цепочка намерение→исполнение недоступна для этого прогона» — `[GAP: execution-events for old runs]` |
| Narrative empty | **P** badge «нет»; body «Нет текстовой истории для этого прогона» |
| Narrative loading | Skeleton lines inside **P** when expanded |
| Partial / cancelled | **N**/**O**/**P** over available artifacts; honesty **A** unchanged |
| Mobile sheet | **F** scrolls: packet → **O** → optional price; avoid locking body scroll under sheet |
| Truncated signals | Unrelated to **N** candles; keep **A** truncation banner |

### P2 token / density notes

- Candles: theme via `Chart` / `data-theme`; up/down wick/body from `--color-up` / `--color-down` (same as live charts).
- Lifecycle: deferred = warn/neutral; filled = up/neutral; rejected/dropped = down/warn — labels over color alone.
- **N** desktop height cap ~180–240px under equity so **E** remains reachable without a long scroll after selection.
- Narrative typography: body text `var(--text-*)`, timestamps `mono`; no marketing cards.

### P2 copy (RU)

| Place | Copy |
|-------|------|
| **N** title | «Цена · {ticker}» |
| **N** empty/idle | (hidden — no idle copy in main column) |
| **N** error | «Не удалось загрузить свечи. Повторить» |
| Scrubber | «Окно» · «±{n} баров» |
| **O** title | «Намерение → исполнение» |
| **O** empty | «Цепочка намерение→исполнение недоступна для этого прогона» |
| **O** statuses | «Отложено» · «Исполнено» · «Отказ» · «Сброшено» (map from API codes) |
| **P** title | «Как проходил прогон» |
| **P** empty | «Нет текстовой истории для этого прогона» |
| **P** voice | Display API `text` as-is (RU end-user); UI chrome only around it |

### API fields UI needs (P2)

Do not invent paths; consume SPEC-03 §5.4 / §6.4 concepts and field names:

| Need | Fields / source |
|------|-----------------|
| Price window **N** `[R-12]` | Read-time candles by `ticker` + `around` + `bars` (OHLC). **No** full candle dump on the run blob |
| Lifecycle **O** `[R-13]` | Execution events for `cycle_id`: `intent_id`, `status` timeline, times, link to fill/reject/drop (ordered steps) |
| Narrative **P** `[R-14]` | Steps: `section`, `step`, `text`, `ts` (+ optional `cycle_id` / ticker for deep-link). RU end-user voice from backend |
| Selection bridge | Existing decision packet: `ticker`/`figi`, `signal_time`, `bar_time`, `cycle_id`, `status` |

Gaps until backend lands:

- `[GAP: needs API for price-window candles by ticker+around+bars]`
- `[GAP: needs API for execution-events (intent↔fill) by cycle_id]`
- `[GAP: needs API for narrative steps on run]`

### P2 out of scope

- Dual-run timeline / narrative diff
- Storing candles on `backtest_runs`
- Changing fill realism / look-ahead model (observe only)
- Replacing equity chart entirely with price as the only view
- Always-on price chart before selection (would bury **E**)
- New product skin

### P2 implementation checklist (UI) — after approval

- [ ] **N** activates only with ticker selection; height-capped; equity remains
- [ ] Scrubber updates `around`, refetches window, syncs playhead (+ **L** if P1 present)
- [ ] **O** first-class block in **F** with RU status labels
- [ ] **P** CollapsibleSection after **K**, default collapsed; RU text as shipped
- [ ] Narrative / lifecycle step → scrub / open cycle
- [ ] **A** + **E** above fold on first paint (no idle **N**/**P** expansion)
- [ ] Mobile: sheet hosts **O** (+ price if needed); no page horizontal breakage
- [ ] Soft empty/legacy states when P2 APIs absent
