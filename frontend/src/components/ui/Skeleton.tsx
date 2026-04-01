import React from 'react'

interface SkeletonProps {
    width?: string
    height?: string
    borderRadius?: string
    count?: number
}

export function Skeleton({ width = '100%', height = '20px', borderRadius, count = 1 }: SkeletonProps) {
    return (
        <>
            {Array.from({ length: count }).map((_, i) => (
                <div
                    key={i}
                    className="skeleton"
                    style={{ width, height, borderRadius, marginBottom: count > 1 ? 'var(--space-2)' : undefined }}
                />
            ))}
        </>
    )
}
