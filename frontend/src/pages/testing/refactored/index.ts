export { isTestingRefactoredEnabled, isTestingLegacyEnabled } from '@/pages/testing/refactored/featureFlag'
export { default as TestingRefactoredPage } from '@/pages/testing/refactored/TestingRefactoredPage'
export { useTestingRefactoredPage } from '@/pages/testing/refactored/hooks/useTestingRefactoredPage'
export { useTestingConfig } from '@/pages/testing/refactored/hooks/useTestingConfig'
export { useTestingRunner } from '@/pages/testing/refactored/hooks/useTestingRunner'
export { useTestingResults } from '@/pages/testing/refactored/hooks/useTestingResults'
export { validateTestingForm, validateTestingFormOrThrow } from '@/pages/testing/refactored/validation'
export {
    hasBlockingValidationIssues,
    validateTestingFormAsync,
} from '@/pages/testing/refactored/validationAsync'
export { buildBacktestConfigFromForm, buildHistoryBacktestRequest } from '@/pages/testing/refactored/payloadBuilder'
export { MarketSelector } from '@/pages/testing/refactored/components/MarketSelector'
export { BaseConfigPanel } from '@/pages/testing/refactored/components/setup/BaseConfigPanel'
export { MoexExtendedPanel } from '@/pages/testing/refactored/components/setup/MoexExtendedPanel'
export { CryptoExtendedPanel } from '@/pages/testing/refactored/components/setup/CryptoExtendedPanel'
export { StrategyParamsPanel } from '@/pages/testing/refactored/components/setup/StrategyParamsPanel'
export { RiskManagementPanel } from '@/pages/testing/refactored/components/setup/RiskManagementPanel'
export { TestingSetupCollapsible } from '@/pages/testing/refactored/components/setup/TestingSetupCollapsible'
export { AdvancedPanel } from '@/pages/testing/refactored/components/setup/AdvancedPanel'
export { SetupValidateBar } from '@/pages/testing/refactored/components/setup/SetupValidateBar'
export { TestingWizard } from '@/pages/testing/refactored/components/wizard/TestingWizard'
export { TestingWizardStepper } from '@/pages/testing/refactored/components/wizard/TestingWizardStepper'
export { useTestingWizardStep } from '@/pages/testing/refactored/hooks/useTestingWizardStep'
export { TESTING_WIZARD_STEPS, wizardStepSubtitle } from '@/pages/testing/refactored/wizard/types'
export type { TestingWizardStep } from '@/pages/testing/refactored/wizard/types'
export { RunControlPanel } from '@/pages/testing/refactored/components/run/RunControlPanel'
export { RunStatusLog } from '@/pages/testing/refactored/components/run/RunStatusLog'
export {
    deriveRunControlState,
    runControlStateLabel,
    runControlSystemLabel,
} from '@/pages/testing/refactored/components/run/runControlState'
export { RunPhaseStepper } from '@/pages/testing/refactored/components/run/RunPhaseStepper'
export {
    BACKTEST_PHASE_ORDER,
    BACKTEST_PHASE_WEIGHTS,
    BACKTEST_PHASE_LABELS_RU,
    derivePhaseSteps,
    phaseIndex,
} from '@/pages/testing/refactored/components/run/backtestPhases'
export type { BacktestPhaseId, PhaseStepState, PhaseStepView } from '@/pages/testing/refactored/components/run/backtestPhases'
export type { RunControlState } from '@/pages/testing/refactored/components/run/runControlState'
export { TestingAnalysisPanel } from '@/pages/testing/refactored/components/analysis/TestingAnalysisPanel'
export { ResultsDashboard } from '@/pages/testing/refactored/components/analysis/ResultsDashboard'
export { EquityChartPanel } from '@/pages/testing/refactored/components/analysis/EquityChartPanel'
export { ResultDetailsTabs } from '@/pages/testing/refactored/components/analysis/ResultDetailsTabs'
export { ResultExportActions } from '@/pages/testing/refactored/components/analysis/ResultExportActions'
export { RunComparePanel } from '@/pages/testing/refactored/components/analysis/RunComparePanel'
export { HistoryPanel } from '@/pages/testing/refactored/components/analysis/HistoryPanel'
export { resolveResultCurrencyLabel, resolveHistoryRunCurrencyLabel } from '@/pages/testing/refactored/components/analysis/resultCurrency'
export { buildResultKpis } from '@/pages/testing/refactored/components/analysis/resultKpi'
export { formatValidationIssuesForToast, issuesToInvalidFields } from '@/pages/testing/refactored/setupValidation'
export { createDefaultTestingFormState } from '@/pages/testing/refactored/defaults'
export {
    isMoexMarket,
    isCryptoMarket,
    showMoexFields,
    showCryptoFields,
    showBrokerCommission,
    showCryptoExtendedFilters,
    showMoexAdvancedExtras,
} from '@/pages/testing/refactored/visibility'
export { toFormSectionsView } from '@/pages/testing/refactored/formStateViews'
export type {
    TestingFormSectionsView,
    TestingMoexSection,
    TestingCryptoSection,
    TestingRiskSection,
    TestingAdvancedSection,
} from '@/pages/testing/refactored/types/formSections'
export type { TestingFormState, ValidationIssue } from '@/pages/testing/refactored/types/forms'
