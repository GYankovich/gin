import React, { useRef, useEffect, useState } from 'react'

export interface FeedEvent {
    id: string | number
    type: 'buy' | 'sell' | 'signal' | 'info' | 'error'
    text: string
    time: string
}

interface EventFeedProps {
    events: FeedEvent[]
    maxHeight?: string
}

export function EventFeed({ events, maxHeight = '320px' }: EventFeedProps) {
    const listRef = useRef<HTMLDivElement>(null)
    const [autoScroll, setAutoScroll] = useState(true)

    useEffect(() => {
        if (autoScroll && listRef.current) {
            listRef.current.scrollTop = listRef.current.scrollHeight
        }
    }, [events, autoScroll])

    const onScroll = () => {
        if (!listRef.current) return
        const { scrollTop, scrollHeight, clientHeight } = listRef.current
        setAutoScroll(scrollHeight - scrollTop - clientHeight < 40)
    }

    return (
        <div className="event-feed" ref={listRef} style={{ maxHeight }} onScroll={onScroll}>
            {events.length === 0 && <div className="event-feed__empty">Нет событий</div>}
            {events.map(ev => (
                <div key={ev.id} className={`event-feed__item event-feed__item--${ev.type}`}>
                    <span className="event-feed__time mono">{ev.time}</span>
                    <span className={`event-feed__badge event-feed__badge--${ev.type}`}>
                        {ev.type.toUpperCase()}
                    </span>
                    <span className="event-feed__text">{ev.text}</span>
                </div>
            ))}
        </div>
    )
}
