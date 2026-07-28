import React from 'react'
import { TestingPageContent } from '@/pages/testing/TestingPageContent'
import { TestingPageSkeleton } from '@/pages/testing/TestingPageSkeleton'
import { useTestingRefactoredPage } from '@/pages/testing/refactored/hooks/useTestingRefactoredPage'

/** Refactored /testing page (T1): same UI, 3-hook controller under feature flag. */
export default function TestingRefactoredPage() {
    const ctx = useTestingRefactoredPage()

    if (ctx.form.loading) {
        return <TestingPageSkeleton />
    }

    return <TestingPageContent {...ctx} />
}
