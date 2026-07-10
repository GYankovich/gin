import { useMemo } from 'react'
import { isCryptoBroker } from '@/modules/robots/config/builders/buildCryptoConfig'
import type { TestingFormState } from '@/pages/testing/refactored/types/forms'
import { validateTestingForm, type ValidationIssue } from '@/pages/testing/refactored/validation'
import {
    buildBacktestConfigFromForm,
    buildHistoryBacktestRequest,
    formStateToSnapshot,
} from '@/pages/testing/refactored/payloadBuilder'
import { buildPipelineFiltersPayload } from '@/pages/testing/testingPipeline'

export type UseTestingConfigArgs = {
    form: TestingFormState
    robotType?: number | null
}

/** Form validation + payload assembly (T1.2). */
export function useTestingConfig({ form, robotType }: UseTestingConfigArgs) {
    const issues = useMemo(() => validateTestingForm(form, { robotType }), [form, robotType])

    const pipelinePayload = useMemo(
        () => buildPipelineFiltersPayload(form.filters),
        [form.filters],
    )

    const snapshot = useMemo(() => formStateToSnapshot(form), [form])

    const isCrypto = isCryptoBroker(form.brokerType)

    const validate = (): ValidationIssue[] => validateTestingForm(form, { robotType })

    const buildPayload = (extra?: Parameters<typeof buildBacktestConfigFromForm>[1]) =>
        buildBacktestConfigFromForm(form, extra)

    const buildRequest = (opts: {
        selectedRobotId: number | null
        selectedRobotType?: number | null
        tokenId?: number | null
        mergeStrategyParamsFrom?: Record<string, unknown>
    }) =>
        buildHistoryBacktestRequest({
            form,
            ...opts,
        })

    return {
        form,
        issues,
        isCrypto,
        pipelinePayload,
        snapshot,
        validate,
        buildPayload,
        buildRequest,
    }
}
