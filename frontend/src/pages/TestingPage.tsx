import React from 'react'
import { TestingPageContent } from '@/pages/testing/TestingPageContent'
import { TestingPageSkeleton } from '@/pages/testing/TestingPageSkeleton'
import { useTestingPage } from '@/pages/testing/hooks/useTestingPage'

///@EPIC Backtesting.ITEM TestingPage.TOPIC Robot Form And Run Flow [1]
///@ Форма тестирования повторяет параметры робота, позволяет выбрать интервал свечей,
///@ собирает payload для /api/robots/history-backtest и отображает результат прогона:
///@ status stages, метрики, кривая капитала, сделки, сигналы, ордера и история запусков.
export default function TestingPage() {
    const ctx = useTestingPage()

    if (ctx.form.loading) {
        return <TestingPageSkeleton />
    }

    return <TestingPageContent {...ctx} />
}
