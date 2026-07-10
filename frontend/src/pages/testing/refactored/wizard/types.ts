export type TestingWizardStep = 'setup' | 'run' | 'analysis' | 'optimize'

export const TESTING_WIZARD_STEPS: Array<{
    id: TestingWizardStep
    label: string
    shortLabel: string
}> = [
    { id: 'setup', label: 'Настройка', shortLabel: 'Setup' },
    { id: 'run', label: 'Запуск', shortLabel: 'Run' },
    { id: 'analysis', label: 'Анализ', shortLabel: 'Analysis' },
    { id: 'optimize', label: 'Оптимизация', shortLabel: 'Opt' },
]

export function wizardStepSubtitle(step: TestingWizardStep): string {
    if (step === 'setup') return 'Параметры стратегии, отбор инструментов и риск'
    if (step === 'run') return 'Подготовка и расчёт бэктеста'
    if (step === 'analysis') return 'Результаты текущего прогона'
    return 'История прогонов, ранжирование и сетка параметров'
}
