import { api } from './api'
import type {
    RobotBacktestRunDetails,
    RobotBacktestRunStatus,
    RobotHistoryBacktestQueuedResponse,
    RobotHistoryBacktestResult,
} from '@/types/robot'
import type {
    RobotV2,
    RobotV2Status,
    RobotV2ValidateResponse,
    StrategyArchetypeInfo,
    UniversePreview,
} from '@/types/robotV2'

function normalizeRobot(raw: Record<string, unknown>): RobotV2 {
    return {
        id: Number(raw.id),
        name: String(raw.name ?? ''),
        type: Number(raw.type ?? 2),
        tokenId: (raw.tokenId ?? raw.token_id ?? null) as number | null,
        token_id: (raw.tokenId ?? raw.token_id ?? null) as number | null,
        status: Number(raw.status ?? 0),
        configVersion: Number(raw.configVersion ?? raw.config_version ?? 4),
        config_version: Number(raw.configVersion ?? raw.config_version ?? 4),
        config: (raw.config as Record<string, unknown>) || {},
        metadata: (raw.metadata as Record<string, unknown>) || {},
        createdAt: (raw.createdAt ?? raw.created_at) as string | undefined,
        created_at: (raw.createdAt ?? raw.created_at) as string | undefined,
        updatedAt: (raw.updatedAt ?? raw.updated_at ?? null) as string | null,
        updated_at: (raw.updatedAt ?? raw.updated_at ?? null) as string | null,
    }
}

/** Client facade for /api/v2/robots. */
export const robotV2Service = {
    async list(params: { robot_status?: number[]; robot_type?: number[] } = {}): Promise<{
        items: RobotV2[]
        total: number
    }> {
        const { data } = await api.post<{ items: Record<string, unknown>[]; total: number }>(
            '/v2/robots/data',
            params,
        )
        return {
            items: (data.items || []).map(normalizeRobot),
            total: data.total ?? 0,
        }
    },

    async getById(robotId: number): Promise<RobotV2> {
        const { data } = await api.get<Record<string, unknown>>(`/v2/robots/${robotId}`)
        return normalizeRobot(data)
    },

    async createOrUpdate(payload: {
        id?: number | null
        name: string
        type: number
        tokenId: number
        config: Record<string, unknown>
    }): Promise<RobotV2> {
        const { data } = await api.post<Record<string, unknown>>('/v2/robots/create', payload)
        return normalizeRobot(data)
    },

    async delete(robotId: number): Promise<void> {
        await api.post('/v2/robots/delete', { robotId })
    },

    async clone(robotId: number): Promise<RobotV2> {
        const { data } = await api.post<Record<string, unknown>>(`/v2/robots/${robotId}/clone`)
        return normalizeRobot(data)
    },

    async getLogs(
        robotId: number,
        opts: { limit?: number; eventType?: string } = {},
    ): Promise<{ robotId: number; items: Array<Record<string, unknown>>; total: number }> {
        const { data } = await api.get<{ robotId: number; items: Array<Record<string, unknown>>; total: number }>(
            `/v2/robots/${robotId}/logs`,
            { params: { limit: opts.limit ?? 100, event_type: opts.eventType } },
        )
        return data
    },

    async validate(payload: {
        type: number
        config: Record<string, unknown>
    }): Promise<RobotV2ValidateResponse> {
        const { data } = await api.post<RobotV2ValidateResponse>('/v2/robots/validate', payload)
        return data
    },

    async previewUniverse(payload: {
        tokenId: number
        instrumentType?: string
        universe: Record<string, unknown>
        page?: number
        pageSize?: number
    }): Promise<UniversePreview> {
        const { data } = await api.post<UniversePreview>('/v2/robots/preview-universe', payload)
        return data
    },

    async start(
        robotId: number,
        payload: { virtualCapital?: number; stopMode?: 'soft' | 'hard' } = {},
    ): Promise<RobotV2> {
        const { data } = await api.post<Record<string, unknown>>(`/v2/robots/${robotId}/start`, {
            virtualCapital: payload.virtualCapital,
            stopMode: payload.stopMode,
        })
        return normalizeRobot(data)
    },

    async stop(robotId: number, stopMode: 'soft' | 'hard' = 'soft'): Promise<RobotV2> {
        const { data } = await api.post<Record<string, unknown>>(
            `/v2/robots/${robotId}/stop`,
            null,
            { params: { stop_mode: stopMode } },
        )
        return normalizeRobot(data)
    },

    async getStatus(robotId: number): Promise<RobotV2Status> {
        const { data } = await api.get<RobotV2Status>(`/v2/robots/${robotId}/status`)
        return data
    },

    async listArchetypes(): Promise<StrategyArchetypeInfo[]> {
        const { data } = await api.get<{ items?: StrategyArchetypeInfo[] } | StrategyArchetypeInfo[]>(
            '/v2/strategy/archetypes',
        )
        if (Array.isArray(data)) return data
        return data.items || []
    },

    /** WebSocket URL for robot event stream (same-origin /api proxy). */
    buildStreamUrl(robotId: number): string {
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        return `${proto}://${window.location.host}/api/v2/robots/${robotId}/stream`
    },

    // --- Backtest (Stage 3b) ---

    async runBacktest(payload: {
        config: Record<string, unknown>
        from_date: string
        to_date: string
        initial_capital?: number
        robotId?: number | null
        tokenId?: number | null
        asyncExecution?: boolean
    }): Promise<
        | { status: 200; data: RobotBacktestRunDetails }
        | { status: 202; data: RobotHistoryBacktestQueuedResponse }
    > {
        const body = {
            config: payload.config,
            from_date: payload.from_date,
            to_date: payload.to_date,
            initial_capital: payload.initial_capital,
            robotId: payload.robotId ?? undefined,
            tokenId: payload.tokenId ?? undefined,
            asyncExecution: payload.asyncExecution ?? true,
        }
        const res = await api.post<RobotBacktestRunDetails | RobotHistoryBacktestQueuedResponse>(
            '/v2/robots/backtest',
            body,
        )
        if (res.status === 202) {
            return { status: 202, data: res.data as RobotHistoryBacktestQueuedResponse }
        }
        return { status: 200, data: res.data as RobotBacktestRunDetails }
    },

    async getBacktestRunStatus(runId: number): Promise<RobotBacktestRunStatus> {
        const { data } = await api.get<RobotBacktestRunStatus>(`/v2/robots/backtest/runs/${runId}/status`)
        return data
    },

    async getBacktestRunDetails(runId: number): Promise<RobotBacktestRunDetails> {
        const { data } = await api.get<RobotBacktestRunDetails>(`/v2/robots/backtest/runs/${runId}`)
        return data
    },

    async cancelBacktestRun(runId: number): Promise<{ run_id: number; cancel_requested: boolean }> {
        const { data } = await api.post<{ run_id: number; cancel_requested: boolean }>(
            `/v2/robots/backtest/runs/${runId}/cancel`,
        )
        return data
    },
}

export type { RobotHistoryBacktestResult }
