import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from 'react'
import { portfolioService } from '@/services/portfolioService'
import { robotService } from '@/services/robotService'
import type { Robot } from '@/types/robot'
import {
    buildTradingRobotConfig,
    buildTradingRobotSchedulePatch,
    type TradingRobotFormSnapshot,
} from '@/pages/testing/buildTradingRobotConfig'
import { fmtErr } from '@/pages/testing/testingUtils'

type ToastLike = {
    show: (message: string, variant?: 'success' | 'error' | 'info' | 'warning', durationMs?: number) => void
}

export function useTestingCreateRobot(
    snapshot: TradingRobotFormSnapshot & { pollValue: number; pollUnit: 'minutes' | 'hours' },
    setRobots: Dispatch<SetStateAction<Robot[]>>,
    setRobotId: (id: number | null) => void,
    toast: ToastLike,
) {
    const [createName, setCreateName] = useState('')
    const [createTokenId, setCreateTokenId] = useState<number | null>(null)
    const [tokenOptions, setTokenOptions] = useState<Array<{ value: string; label: string }>>([])
    const [creating, setCreating] = useState(false)

    useEffect(() => {
        portfolioService
            .getTokens()
            .then(tokens => {
                const active = (tokens || []).filter(t => Number((t as any).status) === 1)
                setTokenOptions(
                    active.map(t => ({
                        value: String(t.id),
                        label: (t as any).token_name ? `${(t as any).token_name} (#${t.id})` : `Токен #${t.id}`,
                    })),
                )
                if (active.length === 1) {
                    setCreateTokenId(Number(active[0].id))
                }
            })
            .catch(() => setTokenOptions([]))
    }, [])

    const createTradingRobot = useCallback(async () => {
        const name = createName.trim()
        if (!name) {
            toast.show('Укажите название нового робота', 'error', 4000)
            return
        }
        if (!createTokenId) {
            toast.show('Выберите токен T-Invest', 'error', 4000)
            return
        }
        setCreating(true)
        try {
            const config = buildTradingRobotConfig(snapshot)
            const schedule = buildTradingRobotSchedulePatch(snapshot)
            const created = await robotService.create({
                name,
                token_id: createTokenId,
                type: 2,
                config,
                ...schedule,
            })
            setRobots(prev => {
                const exists = prev.some(r => r.id === created.id)
                return exists ? prev.map(r => (r.id === created.id ? created : r)) : [created, ...prev]
            })
            setRobotId(created.id)
            setCreateName('')
            toast.show(
                `Робот «${created.name}» создан. Включите его в настройках — universe подберётся по выбранному режиму.`,
                'success',
                7000,
            )
        } catch (e: unknown) {
            toast.show(fmtErr(e), 'error', 5000)
        } finally {
            setCreating(false)
        }
    }, [createName, createTokenId, snapshot, setRobots, setRobotId, toast])

    return {
        createName,
        setCreateName,
        createTokenId,
        setCreateTokenId,
        tokenOptions,
        creating,
        createTradingRobot,
    }
}
