# Testing Recommendations Rules Spec

Спецификация нормализует идеи из `docs/upg testing.txt` и адаптирует их под текущие данные модуля `recommendations`.

## 1. Цели

- Превратить метрики бэктеста/лайва в конкретные рекомендации по полям конфигурации.
- Давать объяснимые и безопасные советы (с приоритетом риска).
- Поддержать поэтапное внедрение: сначала rule-engine для рекомендаций, затем optimization-engine.

## 2. Scope

### MVP (Phase 1)

- Rule-engine в backend, который:
  - принимает `AnalysisContext`,
  - вычисляет нормализованный snapshot метрик,
  - применяет список правил,
  - возвращает `RecommendationItem[]` в текущем API-формате.
- Категории: `risk`, `performance`, `execution`, `universe`, `market_specific`.
- Приоритеты: `critical`, `warning`, `info`.
- До 3-5 actionable подсказок на запрос (остальные скрываются или понижаются).

### Phase 2

- Расширенные метрики (stop-loss hit rate, take-profit hit rate, commission/slippage attribution, universe size stats, seasonality).
- UI действия `apply / dismiss`.
- История примененных рекомендаций.

### Phase 3

- Optimization-engine (grid + adaptive narrowing + scoring цели).
- Защиты от переоптимизации (walk-forward, min trades, outlier guards).

## 3. Каноническая модель правила

```ts
interface AnalysisRule {
  id: string
  category: 'risk' | 'performance' | 'execution' | 'universe' | 'market_specific'
  priority: 'critical' | 'high' | 'medium' | 'low'
  when: RuleCondition
  recommendations: RecommendationTemplate[]
  description: string
}
```

```ts
interface RuleCondition {
  metric: string // dotted path, например "backtest.maxDrawdown"
  op: '>' | '<' | '>=' | '<=' | '==' | '!='
  value: number | string | boolean
  and?: RuleCondition[]
  or?: RuleCondition[]
}
```

```ts
interface RecommendationTemplate {
  field: string // путь к полю конфига, например "risk.max_position_size_pct"
  operation: 'increase' | 'decrease' | 'set' | 'toggle' | 'suggest'
  value: number | string
  reasoning: string
  expectedImpact: string
  riskLevel: 'low' | 'medium' | 'high'
}
```

## 4. Нормализация метрик (snapshot)

Rule-engine работает не с сырым payload напрямую, а с нормализованным объектом:

- `backtest.totalReturnPct`
- `backtest.maxDrawdownPct`
- `backtest.winRatePct`
- `backtest.tradesTotal`
- `backtest.sharpe`
- `live.totalPnl`
- `live.maxDrawdown`
- `live.fillRatePct`
- `live.signalExecutionRatePct`
- `live.riskEvents7d`
- `risk.maxPositionSizePct`
- `risk.maxDailyLossPct`
- `risk.stopLossPct`
- `risk.takeProfitPct`
- `strategy.name`
- `strategy.interval`

Это позволяет добавлять правила без переписывания остального кода.

## 5. Базовые правила MVP

1. **High drawdown**  
   - Условие: `backtest.maxDrawdownPct > 25`  
   - Рекомендация: снизить `risk.max_position_size_pct` на 30-40%.

2. **Very high drawdown (critical)**  
   - Условие: `backtest.maxDrawdownPct > 30`  
   - Рекомендация: установить `risk.max_position_size_pct = 5`.

3. **Low win rate**  
   - Условие: `backtest.winRatePct < 40 && backtest.tradesTotal >= 10`  
   - Рекомендация: ужесточить входные пороги стратегии (suggest-only).

4. **Low Sharpe with many trades**  
   - Условие: `backtest.sharpe < 1.0 && backtest.tradesTotal > 100`  
   - Рекомендация: снизить частоту сделок (увеличить пороги входа / интервал).

5. **Commission/slippage pressure**  
   - Условие: `live.fillRatePct < 60` или `live.signalExecutionRatePct < 50`  
   - Рекомендация: проверить execution model и ликвидность universe.

6. **Too few trades**  
   - Условие: `backtest.tradesTotal < 10`  
   - Рекомендация: смягчить universe filters / входные пороги.

7. **Negative live PnL with enough closed trades**  
   - Условие: `live.totalPnl < 0` и `closedTrades >= 3` (где доступно)  
   - Рекомендация: снизить агрессию риска.

## 6. Приоритизация и дедупликация

- Порядок: `critical -> warning -> info`.
- Внутри одного поля оставлять самую строгую рекомендацию.
- Ограничение на ответ: максимум 7 рекомендаций, из них:
  - `critical`: без лимита,
  - `warning`: до 4,
  - `info`: до 2.

## 7. Маппинг в текущий API

Каждое сработавшее правило маппится в `RecommendationItem`:

- `id`: стабильный hash от `rule_id + field`.
- `category`: из rule.
- `severity`:
  - `critical/high -> critical|warning`,
  - `medium/low -> info`.
- `title`/`message`: из шаблона с подстановкой метрик.
- `suggested_changes[]`: минимум 1 actionable change, если есть целевое поле.
- `evidence`: срез метрик, приведших к срабатыванию.

## 8. Анти-переоптимизация (для Optimization Engine, не MVP)

- Penalize score при `trades < 10`.
- Penalize при `maxDrawdown > 30`.
- Маркировать подозрительные конфиги:
  - `sharpe > 3`,
  - `winRate > 80`,
  - `return > 100%` за короткий период.
- Ввести минимум one-step forward validation перед автоприменением.

## 9. Совместимость

- Текущий endpoint и фронтовые типы не меняются.
- Rule-engine добавляется поверх текущих эвристик и может включаться флагом.
- Все новые правила должны быть безопасны при отсутствии части метрик (graceful skip).

