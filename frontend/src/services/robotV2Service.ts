import { api } from './api'
import type {
    RobotBacktestRunDetails,
    RobotBacktestRunStatus,
    RobotHistoryBacktestQueuedResponse,
    RobotHistoryBacktestResult,
} from '@/types/robot'
import type {
    AuditDataType,
    RobotV2,
    RobotV2AuditResponse,
    RobotV2Status,
    RobotV2UniverseRefresh,
    RobotV2ValidateResponse,
    StrategyArchetypeInfo,
    UniversePreview,
} from '@/types/robotV2'

function normalizeRobot(raw: Record<string, unknown>): RobotV2 {
    return {
        id: Number(raw.id),
        name: String(raw.name ?? ''),
        type: Number(raw.type ?? 2),
        typeName: (raw.typeName ?? raw.type_name ?? null) as string | null,
        type_name: (raw.typeName ?? raw.type_name ?? null) as string | null,
        tokenId: (raw.tokenId ?? raw.token_id ?? null) as number | null,
        token_id: (raw.tokenId ?? raw.token_id ?? null) as number | null,
        status: Number(raw.status ?? 0),
        statusName: (raw.statusName ?? raw.status_name ?? null) as string | null,
        status_name: (raw.statusName ?? raw.status_name ?? null) as string | null,
        configVersion: Number(raw.configVersion ?? raw.config_version ?? 4),
        config_version: Number(raw.configVersion ?? raw.config_version ?? 4),
        config: (raw.config as Record<string, unknown>) || {},
        metadata: (raw.metadata as Record<string, unknown>) || {},
        createdAt: (raw.createdAt ?? raw.created_at) as string | undefined,
        created_at: (raw.createdAt ?? raw.created_at) as string | undefined,
        updatedAt: (raw.updatedAt ?? raw.updated_at ?? null) as string | null,
        updated_at: (raw.updatedAt ?? raw.updated_at ?? null) as string | null,
        lastStarted: (raw.lastStarted ?? raw.last_started ?? null) as string | null,
        last_started: (raw.lastStarted ?? raw.last_started ?? null) as string | null,
        sessionState: (raw.sessionState ?? raw.session_state ?? null) as string | null,
        session_state: (raw.sessionState ?? raw.session_state ?? null) as string | null,
    }
}

/** Client facade for /api/v2/robots. */
export const robotV2Service = {
    /** Lightweight module probe (layout guard — not a full fleet list). */
    async checkModule(): Promise<{ enabled: boolean }> {
        const { data } = await api.get<{ enabled: boolean }>('/v2/robots/module')
        return { enabled: data.enabled !== false }
    },

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
        status?: number
    }): Promise<RobotV2> {
        const { data } = await api.post<Record<string, unknown>>('/v2/robots/create', payload)
        return normalizeRobot(data)
    },

    async changeStatus(
        robotId: number,
        status: number,
        opts: { stopMode?: 'soft' | 'hard' } = {},
    ): Promise<RobotV2> {
        const body: Record<string, unknown> = { robotId, status }
        if (opts.stopMode != null) body.stopMode = opts.stopMode
        const { data } = await api.post<Record<string, unknown>>('/v2/robots/change_status', body)
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
        const body: Record<string, unknown> = {}
        if (payload.virtualCapital != null) body.virtualCapital = payload.virtualCapital
        if (payload.stopMode != null) body.stopMode = payload.stopMode
        const { data } = await api.post<Record<string, unknown>>(`/v2/robots/${robotId}/start`, body)
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

    async refreshUniverse(robotId: number): Promise<RobotV2UniverseRefresh> {
        const { data } = await api.post<RobotV2UniverseRefresh>(`/v2/robots/${robotId}/refresh-universe`)
        return data
    },

    async getStatus(robotId: number): Promise<RobotV2Status> {
        const { data } = await api.get<RobotV2Status>(`/v2/robots/${robotId}/status`)
        return data
    },

    async fetchAudit(payload: {
        robotId: number
        limit?: number
        offset?: number
        sessionId?: string | null
        types?: AuditDataType[]
    }): Promise<RobotV2AuditResponse> {
        const { data } = await api.post<RobotV2AuditResponse>('/v2/robots/audit', {
            robotId: payload.robotId,
            limit: payload.limit ?? 100,
            offset: payload.offset ?? 0,
            sessionId: payload.sessionId ?? undefined,
            types: payload.types,
        })
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
    buildStreamUrl(robotId: number, token?: string): string {
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        const base = `${proto}://${window.location.host}/api/v2/robots/${robotId}/stream`
        if (token) {
            return `${base}?token=${encodeURIComponent(token)}`
        }
        return base
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

    async listBacktestRuns(params: { robotId?: number; limit?: number } = {}): Promise<{
        items: Array<{
            run_id: number
            robot_id?: number | null
            status: string
            requested_from: string
            requested_to: string
            started_at: string
            finished_at?: string | null
            initial_capital: number
            total_return_percent?: number | null
            max_drawdown_percent?: number | null
            final_equity?: number | null
            trades_total: number
            error_message?: string | null
        }>
        total: number
    }> {
        const { data } = await api.get('/v2/robots/backtest/runs', {
            params: { robot_id: params.robotId, limit: params.limit ?? 30 },
        })
        return data
    },

    async compareBacktestRuns(baseRunId: number, compareRunId: number): Promise<{
        base_run_id: number
        compare_run_id: number
        metrics_base: Record<string, number | null>
        metrics_compare: Record<string, number | null>
        metrics_diff: Record<string, number | null>
        config_diff: Record<string, { base: unknown; compare: unknown }>
        base: Record<string, unknown>
        compare: Record<string, unknown>
    }> {
        const { data } = await api.post('/v2/robots/backtest/compare', {
            baseRunId,
            compareRunId,
        })
        return data
    },
}

export type { RobotHistoryBacktestResult }
