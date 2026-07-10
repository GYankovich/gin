import React from 'react'
import { TestingBacktestHistoryCard, type TestingBacktestHistoryCardProps } from '@/pages/testing/TestingBacktestHistoryCard'

/** T4.5 — history table + filters wrapper. */
export function HistoryPanel(props: TestingBacktestHistoryCardProps) {
    return <TestingBacktestHistoryCard {...props} />
}
