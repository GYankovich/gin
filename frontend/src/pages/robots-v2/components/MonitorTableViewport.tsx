import React, { useLayoutEffect, useRef } from 'react'
import { useNestedScrollChain } from '@/hooks/useNestedScrollChain'

type MonitorTableViewportProps = {
    ariaLabel: string
    /** Returns a single <tr>…</tr> for the visible thead. */
    renderHead: () => React.ReactNode
    /** <tr> rows for tbody */
    bodyRows: React.ReactNode
    /** Re-measure columns when data identity changes */
    syncKey?: string | number
}

/**
 * Table viewport where the vertical scrollbar sits beside the body only —
 * thead is outside that scrollport, so the bar never covers the header.
 * Horizontal scroll stays on the body and is mirrored to the head.
 */
export function MonitorTableViewport({
    ariaLabel,
    renderHead,
    bodyRows,
    syncKey,
}: MonitorTableViewportProps) {
    const bodyScrollRef = useNestedScrollChain<HTMLDivElement>()
    const headWrapRef = useRef<HTMLDivElement | null>(null)
    const headTableRef = useRef<HTMLTableElement | null>(null)
    const bodyTableRef = useRef<HTMLTableElement | null>(null)

    useLayoutEffect(() => {
        const headTable = headTableRef.current
        const bodyTable = bodyTableRef.current
        if (!headTable || !bodyTable) return

        const syncWidths = () => {
            const headCells = headTable.querySelectorAll('thead th')
            const bodyRow = bodyTable.querySelector('tbody tr')
            if (!bodyRow || headCells.length === 0) {
                headTable.style.width = ''
                headCells.forEach(th => {
                    ;(th as HTMLElement).style.width = ''
                    ;(th as HTMLElement).style.minWidth = ''
                })
                return
            }
            const bodyCells = bodyRow.querySelectorAll('td')
            const widths: number[] = []
            bodyCells.forEach(td => {
                widths.push((td as HTMLElement).getBoundingClientRect().width)
            })
            let total = 0
            headCells.forEach((th, i) => {
                const w = widths[i]
                if (w == null) return
                const el = th as HTMLElement
                el.style.width = `${w}px`
                el.style.minWidth = `${w}px`
                total += w
            })
            headTable.style.width = `${total}px`
            bodyTable.style.width = `${total}px`
        }

        syncWidths()
        const ro = new ResizeObserver(() => syncWidths())
        ro.observe(bodyTable)
        return () => ro.disconnect()
    }, [syncKey, bodyRows])

    const onBodyScroll = () => {
        const body = bodyScrollRef.current
        const head = headWrapRef.current
        if (!body || !head) return
        head.scrollLeft = body.scrollLeft
    }

    return (
        <div className="robots-monitor-day-trades__viewport">
            <div ref={headWrapRef} className="robots-monitor-day-trades__head">
                <table ref={headTableRef} className="robots-monitor-day-trades__table">
                    <thead>{renderHead()}</thead>
                </table>
            </div>
            <div
                ref={bodyScrollRef}
                className="robots-monitor-day-trades__scroll"
                onScroll={onBodyScroll}
                role="region"
                aria-label={ariaLabel}
            >
                <table
                    ref={bodyTableRef}
                    className="robots-monitor-day-trades__table"
                >
                    <tbody>{bodyRows}</tbody>
                </table>
            </div>
        </div>
    )
}
