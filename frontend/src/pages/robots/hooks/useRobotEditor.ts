import { useCallback, useRef, useState } from 'react'
import { robotService } from '@/services/robotService'
import type { Robot } from '@/types/robot'
import {
    BROKER_CHANGE_BLOCKED_MESSAGE,
    isBrokerTypeConflictError,
} from '@/modules/robots/config/brokerImmutability'

type SchedulePatch = {
    poll_interval_hours: number
    trading_hours_start: string
    trading_hours_end: string
    allowed_weekdays: number
}

type SaveArgs = {
    isNew: boolean
    robotId: number | null
    name: string
    tokenId: number
    robotType: 1 | 2
    config: Record<string, unknown>
    schedule: SchedulePatch
}

/**
 * Persist robot via contract endpoints:
 * create → POST /robots/create
 * update → POST /robots/update (base) + /robots/config + /robots/schedule
 */
export function useRobotEditorSave() {
    const [saving, setSaving] = useState(false)
    const skipNextLoadRef = useRef<number | null>(null)

    const consumeSkipLoad = useCallback((robotId: number) => {
        if (skipNextLoadRef.current === robotId) {
            skipNextLoadRef.current = null
            return true
        }
        return false
    }, [])

    const markSkipLoad = useCallback((robotId: number) => {
        skipNextLoadRef.current = robotId
    }, [])

    const saveRobot = useCallback(async (args: SaveArgs): Promise<{ robot: Robot; created: boolean }> => {
        setSaving(true)
        try {
            if (args.isNew) {
                const created = await robotService.create({
                    name: args.name.trim(),
                    token_id: args.tokenId,
                    type: args.robotType,
                    config: args.config,
                    ...args.schedule,
                })
                markSkipLoad(created.id)
                return { robot: created, created: true }
            }
            if (!args.robotId) {
                throw new Error('robot id missing')
            }
            await robotService.updateRobot(args.robotId, {
                name: args.name.trim(),
                token_id: args.tokenId,
                type: args.robotType,
            })
            await robotService.updateConfig(args.robotId, args.config)
            const updated = await robotService.updateSchedule(args.robotId, args.schedule)
            return { robot: updated, created: false }
        } catch (err) {
            if (isBrokerTypeConflictError(err)) {
                throw new Error(BROKER_CHANGE_BLOCKED_MESSAGE)
            }
            throw err
        } finally {
            setSaving(false)
        }
    }, [markSkipLoad])

    return { saving, setSaving, saveRobot, consumeSkipLoad, markSkipLoad, skipNextLoadRef }
}
