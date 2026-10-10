import React from 'react'
import {
    BACKTEST_PRESETS,
    type BacktestPresetId,
} from '@/pages/robots-v2/backtestGuide'
import { ARCHETYPE_CARDS, type RobotV2WizardDraft } from '@/pages/robots-v2/wizardDraft'

type Props = {
    draft: RobotV2WizardDraft
    activePreset: BacktestPresetId | null
    onApplyPreset: (id: BacktestPresetId) => void
}

const STEPS = [
    ['1', 'Правила', 'готовый набор или свои'],
    ['2', 'Период', 'даты и стартовый капитал'],
    ['3', 'Журнал', 'каждая сделка и причина'],
    ['4', 'Робот', 'сохранить, если правила устраивают'],
] as const

/** First-run path on the Lab «Настроить» tab. Does not start a run. */
export function BacktestStartGuide({ draft, activePreset, onApplyPreset }: Props) {
    const active = BACKTEST_PRESETS.find(p => p.id === activePreset)

    return (
        <div className="robots-v2-bt-guide">
            <ol className="robots-v2-bt-guide__steps">
                {STEPS.map(([n, title, hint]) => (
                    <li key={n} className="robots-v2-bt-guide__step">
                        <strong>{n}. {title}</strong>
                        <span>{hint}</span>
                    </li>
                ))}
            </ol>
            <p className="robots-v2-hint">
                Готовый набор только заполняет форму. Запуск — кнопка «Запустить бэктест».
                Заявки на биржу не отправляются.
            </p>
            <div className="robots-v2-bt-presets" role="group" aria-label="Готовые наборы правил">
                {BACKTEST_PRESETS.map(preset => (
                    <button
                        key={preset.id}
                        type="button"
                        className={
                            activePreset === preset.id
                                ? 'robots-v2-bt-preset robots-v2-bt-preset--on'
                                : 'robots-v2-bt-preset'
                        }
                        onClick={() => onApplyPreset(preset.id)}
                    >
                        <strong>{preset.title}</strong>
                        <span>{preset.blurb}</span>
                    </button>
                ))}
            </div>
            {active ? (
                <p className="robots-v2-hint">{active.rule}</p>
            ) : (
                <p className="robots-v2-hint">
                    Сейчас в форме: {ARCHETYPE_CARDS.find(c => c.id === draft.archetype)?.title || 'правила не выбраны'}
                    {draft.fixedList ? ` · ${draft.fixedList}` : ''}.
                    Сигналы считают встроенные правила по цене и объёму — их можно прочитать в журнале прогона.
                </p>
            )}
        </div>
    )
}
