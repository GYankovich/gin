import React from 'react'
import { Skeleton } from '@/components/ui/Skeleton'

export function TestingPageSkeleton() {
    return (
        <div className="page" data-page="testing">
            <h1 className="page__title">Тестирование</h1>
            <Skeleton height="48px" count={4} />
        </div>
    )
}
