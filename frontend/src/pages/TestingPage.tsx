import React from 'react'
import { TestingPageContent } from '@/pages/testing/TestingPageContent'
import { TestingPageSkeleton } from '@/pages/testing/TestingPageSkeleton'
import { useTestingPage } from '@/pages/testing/hooks/useTestingPage'
import { isTestingLegacyEnabled } from '@/pages/testing/refactored/featureFlag'
import TestingRefactoredPage from '@/pages/testing/refactored/TestingRefactoredPage'

/** @deprecated T6 — monolithic `useTestingPage`; enable via `VITE_TESTING_LEGACY=true`. */
function LegacyTestingPage() {
    const ctx = useTestingPage()

    if (ctx.form.loading) {
        return <TestingPageSkeleton />
    }

    return <TestingPageContent {...ctx} />
}

///@EPIC Backtesting.ITEM TestingPage.TOPIC Robot Form And Run Flow [1]
export default function TestingPage() {
    if (isTestingLegacyEnabled()) {
        return <LegacyTestingPage />
    }
    return <TestingRefactoredPage />
}
