import React, { useCallback } from 'react'
import { Button } from '@/components/ui/Button'
import type { RobotHistoryBacktestResult } from '@/types/robot'

export type ResultExportActionsProps = {
    result: RobotHistoryBacktestResult
    onCopied?: () => void
    onDownloaded?: () => void
    className?: string
}

function buildExportPayload(result: RobotHistoryBacktestResult) {
    return {
        run_id: result.run_id ?? null,
        exported_at: new Date().toISOString(),
        ...result,
    }
}

/** T4.4 — copy / download result JSON. */
export function ResultExportActions({ result, onCopied, onDownloaded, className = '' }: ResultExportActionsProps) {
    const handleCopy = useCallback(async () => {
        const text = JSON.stringify(buildExportPayload(result), null, 2)
        try {
            await navigator.clipboard.writeText(text)
            onCopied?.()
        } catch {
            const ta = document.createElement('textarea')
            ta.value = text
            document.body.appendChild(ta)
            ta.select()
            document.execCommand('copy')
            document.body.removeChild(ta)
            onCopied?.()
        }
    }, [result, onCopied])

    const handleDownload = useCallback(() => {
        const text = JSON.stringify(buildExportPayload(result), null, 2)
        const blob = new Blob([text], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `backtest-run-${result.run_id ?? 'export'}.json`
        a.click()
        URL.revokeObjectURL(url)
        onDownloaded?.()
    }, [result, onDownloaded])

    return (
        <div className={`testing-result-export ${className}`.trim()}>
            <Button size="sm" variant="ghost" onClick={() => void handleCopy()}>
                Копировать JSON
            </Button>
            <Button size="sm" variant="secondary" onClick={handleDownload}>
                Скачать JSON
            </Button>
        </div>
    )
}
