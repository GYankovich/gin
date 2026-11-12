# UX-10: `/robots/new` — рельс шагов + рабочая карточка

Mockup: [public/ui-fixes/21-robots-new.html](../../public/ui-fixes/21-robots-new.html)#d (shell)  
Nav: [public/ui-fixes/24-wizard-nav-variants.html](../../public/ui-fixes/24-wizard-nav-variants.html)#j — **J** soft select / edge bar  
Related: [UX-04](UX-04-robots-v2-visual-alignment.md) (wizard shell)

## Goal

Создание и правка робота (`/robots/new`, `/robots/edit/:id`) в том же спокойном языке, что флот `/robots`: карточка `radius 16`, hairline, tags/status. Горизонтальные плашки шагов убрать; слева вертикальный рельс прогресса, справа одна рабочая карточка текущего шага.

API, draft storage, validation и save/start — без изменений.

## Layout (zones)

Desktop ≥1440:

```text
page[data-page=robots][data-robots-view=wizard]
  dashboard-layout.robots-v2-wizard-layout
    [optional] robots-v2-banner--error
    .robots-v2-wizard-rail-layout
      aside.robots-v2-wizard-rail          /* ~200px */
        title: «Создание» | «Правка»
        nav steps (vertical)
        meta: kind · mode · draft hint
      Card.robots-v2-wizard-card          /* working pane */
        head: step title + tags + «К списку»
        form: current step only
        footer: Назад | Далее / Сохранить…
```

Mobile (&lt;900): soft-select (J) в отдельной `--bg-card` плашке; карточка шага — sibling того же материала ([23](../../public/ui-fixes/23-wizard-rail-surface.html)#f). Desktop: вертикальный рельс с edge bar у active.

## Components

| Zone | Primitive / class | Notes |
|------|-------------------|--------|
| Rail shell | new `robots-v2-wizard-rail` | Card-like: border, radius 16, `--bg-card` |
| Step item | button in rail | States: `done` (✓), `active` (filled index), `todo` (muted index) |
| Working card | existing `robots-v2-wizard-card` | Keep head hairline, fields, archetype grid, footer |
| Status / tags | — | Removed from working card head |
| Back to list | — | Removed from working card head |
| Local draft | — | Removed; persist only via API save |

Steps (unchanged labels):

- Trading: `Основное` → `Стратегия` → `Активы` → `Риск`
- Portfolio: `Основное` → `Синхрон`

## Interaction map

| Action | Behavior |
|--------|----------|
| Click rail step `i` | Always allowed (no step validation gate) |
| Назад / Далее | Always allowed; footer stays in working card |
| Kind switch (step 0, create only) | Existing type cards; rail rebuilds to 2 or 4 steps |
| Keyboard | Optional: ↑/↓ in rail when focused; Tab order rail → form → footer |
| Save / create | Only on last step; allowed with incomplete config (name + API key). Trading create soft-save → status stopped |
| Start / enable | Last step only; only when all steps validate; API also rejects start/enable on invalid config |
| Rail mark | Always step number (no ✓) |
| Mobile rail title | Hidden |

## Working card head copy

| Mode | Title in card | Rail title |
|------|---------------|------------|
| Create, step 0 | `Новый робот` / `Новый опросник` | `Создание` |
| Create, step ≥1 | Label of current step (e.g. `Стратегия`) | `Создание` |
| Edit | Label of current step; name + `#id` in tags or rail meta | `Правка` |

Tags under title (create): `Черновик` + `Торговый|Опросник` + for trading `Бумага|Боевой` (+ broker short name when token chosen).  
Edit portfolio: keep enabled/disabled pill as today.

Rail meta (below steps):

- Create: `Торговый · Бумага` (or portfolio) + line `Черновик сохраняется локально` when local draft exists / always for create.
- Edit: `Имя · #id` + kind/mode one-liner.

## States

| State | UI |
|-------|-----|
| loading (edit fetch) | Skeleton inside working card; rail shows steps disabled or dimmed |
| field errors | Existing banner above layout + toast; highlight active rail step as current (no new error chrome on rail) |
| empty tokens | Existing hint on step 0 |
| restore draft | `RobotConfirmModal` before form |

## Token notes

- Match fleet card: `var(--bg-card)`, `var(--border-subtle)`, radius 16, no glow.
- Active rail item: `color-mix(in srgb, var(--text-primary) 6%, transparent)` like current step pill.
- Done checkmark: secondary text; active index disc: `--text-primary` on `--bg-page` (or inverse of primary button).
- Draft status: warn tone like fleet `--warn` led, not neon accent.

## Copy

- Rail heading create: `Создание`
- Rail heading edit: `Правка`
- Draft meta: `Черновик сохраняется локально`
- Back: `К списку`
- Step labels: keep existing RU strings

## Out of scope

- Live fleet-card preview (option B)
- Flattening wizard into all-sections page (option C)
- New API / draft schema
- Changing step field inventory
- Mobile-first redesign beyond rail → top tabs

## UI engineer checklist

- [x] Replace horizontal `.robots-v2-steps` with left rail on desktop
- [x] Working card title = current step (after step 0 create)
- [x] Fleet-like draft/status tags in card head
- [x] Preserve `goToStep` / validate / save / portfolio vs trading
- [x] Dark + light `data-theme`
- [x] &lt;900px: horizontal step strip above card
