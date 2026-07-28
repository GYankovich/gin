import { useCallback, useRef, useState } from 'react'
import { robotService } from '@/services/robotService'
import type { Robot, RobotListRequest } from '@/types/robot'

export type RobotsListFilters = {
    robot_name?: string
    robot_status?: number[]
    robot_type?: number[]
    sort_by?: string
    sort_order?: 'asc' | 'desc'
}

const DEFAULT_LIMIT = 200

export function useRobotsList() {
    const [robots, setRobots] = useState<Robot[]>([])
    const [total, setTotal] = useState(0)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [filters, setFilters] = useState<RobotsListFilters>({})
    const filtersRef = useRef(filters)
    filtersRef.current = filters
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    const fetchList = useCallback(async (applied: RobotsListFilters, showLoader: boolean) => {
        if (showLoader) setLoading(true)
        setError(null)
        try {
            const body: RobotListRequest = {
                limit: DEFAULT_LIMIT,
                offset: 0,
                sort_by: applied.sort_by ?? 'name',
                sort_order: applied.sort_order ?? 'asc',
            }
            const name = applied.robot_name?.trim()
            if (name) body.robot_name = name
            if (applied.robot_status?.length) body.robot_status = applied.robot_status
            if (applied.robot_type?.length) body.robot_type = applied.robot_type

            const res = await robotService.list(body)
            setRobots(res.items)
            setTotal(res.total)
            return res.items
        } catch {
            setError('Не удалось загрузить роботов')
            return [] as Robot[]
        } finally {
            if (showLoader) setLoading(false)
        }
    }, [])

    const load = useCallback(async (next?: RobotsListFilters, showLoader = true) => {
        const applied = next ?? filtersRef.current
        if (next) {
            setFilters(applied)
            filtersRef.current = applied
        }
        return fetchList(applied, showLoader)
    }, [fetchList])

    /** Update filters immediately; debounce name search network call. */
    const patchFilters = useCallback((patch: Partial<RobotsListFilters>, onLoaded?: (items: Robot[]) => void) => {
        const next = { ...filtersRef.current, ...patch }
        setFilters(next)
        filtersRef.current = next

        const delay = patch.robot_name !== undefined ? 300 : 0
        if (debounceRef.current) clearTimeout(debounceRef.current)
        debounceRef.current = setTimeout(() => {
            void fetchList(next, false).then(items => onLoaded?.(items))
        }, delay)
    }, [fetchList])

    const upsert = useCallback((robot: Robot) => {
        setRobots(prev => {
            const idx = prev.findIndex(r => r.id === robot.id)
            if (idx < 0) return [robot, ...prev]
            const next = [...prev]
            next[idx] = robot
            return next
        })
    }, [])

    const remove = useCallback((robotId: number) => {
        setRobots(prev => prev.filter(r => r.id !== robotId))
        setTotal(t => Math.max(0, t - 1))
    }, [])

    const cancelPending = useCallback(() => {
        if (debounceRef.current) clearTimeout(debounceRef.current)
    }, [])

    return {
        robots,
        total,
        loading,
        error,
        filters,
        setFilters,
        load,
        patchFilters,
        upsert,
        remove,
        setRobots,
        cancelPending,
    }
}
