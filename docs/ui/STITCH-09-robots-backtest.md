# Stitch: GIN · Robots & Backtest

**Project:** `projects/4086468344801354302` — **GIN · Robots & Backtest**  
**Design system:** `assets/15099879158102398196` — **GIN Robots Ops**

## Product lock

**[UX-09](UX-09-robots-node-loop.md)** — robot node loop (VIEW · CONFIG · BACKTEST LAUNCH).  
Stitch = visual refs; UX-09 = IA, zones, acceptance. Quiet chrome: no KPI tile strips.

## Visual bar (user approved)

| Screen | Stitch id | Role |
|--------|-----------|------|
| **GIN Флот роботов (Компактный)** | `2b549ecb241945c08366a15d4aa016f3` | `/robots` |
| **GIN Бэктест (Спокойный)** | `6815d6ce55d649cd960d837f0dae258f` | results language |

## Node loop (UX-09 Stitch)

| Screen | Stitch id | Role |
|--------|-----------|------|
| **GIN Node · Лайв** | `f49f35a415024976ac668f456527ad08` | VIEW `/monitor` |
| **GIN Node · Правка** | `22327ea5a7e042688456bf0aad88bccb` | CONFIG `/edit/:id` |
| **GIN Node · Бэктест запуск** | `2d77d03852ed4498b7ce79f07ce685a4` | BACKTEST LAUNCH |

## Also aligned

| Screen | Stitch id | Role |
|--------|-----------|------|
| Аудит (Компактный) | `148f3dc4fc394f88a2623b7ab6bd1d79` | `/logs` |
| Бэктест Лаборатория | `21dd11a600b24eca9febc97ca12a7040` | `/robots/backtest` |
| Создание робота | `212eb45a5c32454fa7f9bf6fed255e7e` | `/robots/new` |

Ignore older noisy drafts.

## Next

Approve UX-09 → UI engineer implements `frontend/src/pages/robots-v2/**` against existing APIs.
