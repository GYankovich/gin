# UX-settings-mobile: Настройки на телефоне

SPEC: текущий `/settings` (`SettingsPage.tsx` + `SettingsPage.css`)  
Preview: `public/settings-mobile.html`  
Chosen option: **A · Stacked sheet** (утверждено пользователем)

## Problem

На desktop настройки читаются как «профиль | тема» + rail брокеров (240px nav + detail). На ≤767px горизонтальный rail и сжатый top grid тесны; нужная мобильная IA — stacked sheet.

## Variants (согласование)

| ID | Name | Статус |
|----|------|--------|
| **A** | Stacked sheet | **выбран** |
| B | Segment tabs | отклонён |
| C | Broker-first | рекомендация была, не выбран |
| D | List / sheet | отклонён |

## Layout (zones) — Option A

```text
+-------- Настройки --------+
| [avatar] gy · email   [✎]  |
+------------------------------+
| ТЕМА                         |
| [ Система | Тёмная | Светлая]|
+------------------------------+
| БРОКЕРЫ                      |
| ▾ T-Invest  · 1 ток · 2 сч.  |
|   Токены / Счета …           |
| ▸ Bybit     · warn           |
| + брокер                     |
| Выйти                        |
+------------------------------+
|······ MobileTabBar ··········|
```

## Components

| Widget | Примитив |
|--------|----------|
| Theme section label | `.settings-section-label` (≤767px) |
| Broker accordion | `BrokerAccordionCard` |
| Token / account lines | существующие |
| Logout | full-width danger ≥48px |
| Desktop | rail без изменений (≥768px) |

## Interaction map

- Tap broker header → expand/collapse (первый открыт по умолчанию).
- Theme tabs → `setPreference`.
- Edit → profile modal.
- Delete → confirm modal.
- Account toggle → visibility API.
- `#tokens` → scroll to brokers.

## Out of scope

- Не менять desktop rail (≥768px).
- Новые HTTP paths не вводить.
