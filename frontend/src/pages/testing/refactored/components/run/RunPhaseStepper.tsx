import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import {
    derivePhaseSteps,
    phaseStepIcon,
    type PhaseStepState,
} from '@/pages/testing/refactored/components/run/backtestPhases'

export type RunPhaseStepperProps = {
    runPhase?: string | null
    running: boolean
    hasResult: boolean
    phaseUnitsDone?: number | null
    phaseUnitsTotal?: number | null
    className?: string
}

function itemClass(state: PhaseStepState): string {
    if (state === 'done') return 'testing-phase-stepper__item--done'
    if (state === 'active') return 'testing-phase-stepper__item--active'
    return 'testing-phase-stepper__item--pending'
}

/** T3.3 — 7-phase progress stepper aligned with `backtest_progress.py`. */
export function RunPhaseStepper({
    runPhase,
    running,
    hasResult,
    phaseUnitsDone,
    phaseUnitsTotal,
    className = '',
}: RunPhaseStepperProps) {
    const steps = useMemo(
        () =>
            derivePhaseSteps({
                runPhase,
                running,
                hasResult,
                phaseUnitsDone,
                phaseUnitsTotal,
            }),
        [runPhase, running, hasResult, phaseUnitsDone, phaseUnitsTotal],
    )

    const showStepper = running || hasResult || Boolean(runPhase)
    if (!showStepper) return null

    return (
        <Card
            className={`mb-6 cyber-form-card testing-cyber-card testing-phase-stepper-card ${className}`.trim()}
        >
            <h3 className="card__section-title pipeline-title testing-phase-stepper__title">
                <span className="cyber-bracket">[</span>
                ФАЗЫ ПРОГОНА
                <span className="cyber-bracket">]</span>
            </h3>
            <ol className="testing-phase-stepper" aria-label="Фазы бэктеста">
                {steps.map((step, idx) => (
                    <li
                        key={step.id}
                        className={`testing-phase-stepper__item ${itemClass(step.state)}`}
                        aria-current={step.state === 'active' ? 'step' : undefined}
                    >
                        <span className="testing-phase-stepper__icon" aria-hidden>
                            {phaseStepIcon(step.state)}
                        </span>
                        <div className="testing-phase-stepper__body">
                            <span className="testing-phase-stepper__label">{step.label}</span>
                            <span className="testing-phase-stepper__meta">
                                <span className="testing-phase-stepper__weight">{step.weight}%</span>
                                {step.detail && (
                                    <span className="testing-phase-stepper__detail">{step.detail}</span>
                                )}
                            </span>
                        </div>
                        {idx < steps.length - 1 && (
                            <span className="testing-phase-stepper__connector" aria-hidden />
                        )}
                    </li>
                ))}
            </ol>
        </Card>
    )
}
