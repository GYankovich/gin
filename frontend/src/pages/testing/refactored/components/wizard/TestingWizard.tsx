import React from 'react'
import { TestingWizardStepper } from '@/pages/testing/refactored/components/wizard/TestingWizardStepper'
import type { TestingWizardStep } from '@/pages/testing/refactored/wizard/types'

export type TestingWizardProps = {
    step: TestingWizardStep
    onStepChange: (step: TestingWizardStep) => void
    running?: boolean
    hasResult?: boolean
    setup: React.ReactNode
    run: React.ReactNode
    analysis: React.ReactNode
    optimize: React.ReactNode
    className?: string
}

/** T3.1 — Setup / Run / Analysis / Optimize wizard shell. */
export function TestingWizard({
    step,
    onStepChange,
    running = false,
    hasResult = false,
    setup,
    run,
    analysis,
    optimize,
    className = '',
}: TestingWizardProps) {
    return (
        <div className={`testing-wizard ${className}`.trim()} data-wizard-step={step}>
            <TestingWizardStepper
                step={step}
                onStepChange={onStepChange}
                running={running}
                canGoRun
                canGoAnalysis={hasResult}
            />
            <div className="testing-wizard__panel">
                {step === 'setup' && <div className="testing-wizard__stage testing-wizard__stage--setup">{setup}</div>}
                {step === 'run' && <div className="testing-wizard__stage testing-wizard__stage--run">{run}</div>}
                {step === 'analysis' && (
                    <div className="testing-wizard__stage testing-wizard__stage--analysis">{analysis}</div>
                )}
                {step === 'optimize' && (
                    <div className="testing-wizard__stage testing-wizard__stage--optimize">{optimize}</div>
                )}
            </div>
        </div>
    )
}
