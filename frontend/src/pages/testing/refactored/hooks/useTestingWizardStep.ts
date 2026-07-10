import { useCallback, useEffect, useRef, useState } from 'react'
import type { TestingWizardStep } from '@/pages/testing/refactored/wizard/types'

export type UseTestingWizardStepArgs = {
    running: boolean
    hasResult: boolean
}

/** T3.1 — wizard step state with auto transitions Run → Analysis. */
export function useTestingWizardStep({ running, hasResult }: UseTestingWizardStepArgs) {
    const [step, setStep] = useState<TestingWizardStep>('setup')
    const resumeLatchRef = useRef(false)
    const wasRunningRef = useRef(false)

    useEffect(() => {
        if (resumeLatchRef.current) return
        if (running) {
            resumeLatchRef.current = true
            setStep('run')
        }
    }, [running])

    useEffect(() => {
        if (running) {
            wasRunningRef.current = true
            setStep('run')
            return
        }
        if (wasRunningRef.current && hasResult) {
            setStep('analysis')
        }
    }, [running, hasResult])

    const goSetup = useCallback(() => setStep('setup'), [])
    const goRun = useCallback(() => setStep('run'), [])
    const goAnalysis = useCallback(() => setStep('analysis'), [])
    const goOptimize = useCallback(() => setStep('optimize'), [])

    return {
        step,
        setStep,
        goSetup,
        goRun,
        goAnalysis,
        goOptimize,
    }
}
