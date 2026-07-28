import React from 'react'
import {
    TESTING_WIZARD_STEPS,
    type TestingWizardStep,
} from '@/pages/testing/refactored/wizard/types'

export type TestingWizardStepperProps = {
    step: TestingWizardStep
    onStepChange: (step: TestingWizardStep) => void
    canGoRun?: boolean
    canGoAnalysis?: boolean
    running?: boolean
}

export function TestingWizardStepper({
    step,
    onStepChange,
    canGoRun = true,
    canGoAnalysis = false,
    running = false,
}: TestingWizardStepperProps) {
    const activeIdx = TESTING_WIZARD_STEPS.findIndex(s => s.id === step)

    return (
        <nav className="testing-wizard-stepper" aria-label="Этапы бэктеста">
            <ol className="testing-wizard-stepper__list">
                {TESTING_WIZARD_STEPS.map((s, idx) => {
                    const isActive = s.id === step
                    const isDone = idx < activeIdx
                    const disabled =
                        s.id === 'run'
                            ? !canGoRun && !running && !isDone && !isActive
                            : s.id === 'analysis'
                              ? !canGoAnalysis && !isActive
                              : false
                    return (
                        <li
                            key={s.id}
                            className={`testing-wizard-stepper__item${isActive ? ' testing-wizard-stepper__item--active' : ''}${isDone ? ' testing-wizard-stepper__item--done' : ''}`}
                        >
                            <button
                                type="button"
                                className="testing-wizard-stepper__btn"
                                disabled={disabled}
                                aria-current={isActive ? 'step' : undefined}
                                onClick={() => {
                                    if (!disabled) onStepChange(s.id)
                                }}
                            >
                                <span className="testing-wizard-stepper__index">{idx + 1}</span>
                                <span className="testing-wizard-stepper__label">{s.label}</span>
                                <span className="testing-wizard-stepper__short">{s.shortLabel}</span>
                            </button>
                            {idx < TESTING_WIZARD_STEPS.length - 1 && (
                                <span className="testing-wizard-stepper__connector" aria-hidden />
                            )}
                        </li>
                    )
                })}
            </ol>
        </nav>
    )
}
