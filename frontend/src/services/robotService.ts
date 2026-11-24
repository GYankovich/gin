import { api } from './api'
import type {
    BacktestCycleBundleResponse,
    BacktestExecutionEventsResponse,
    BacktestNarrativeResponse,
    BacktestPriceWindowResponse,
    BacktestUniverseResponse,
    RobotBacktestRunDetails,
    RobotBacktestRunStatus,
    RobotHistoryBacktestQueuedResponse,
    RobotHistoryBacktestResult,
} from '@/types/robot'
import type {
    AuditDataType,
    TradingRobot,
    TradingRobotAuditResponse,
    TradingRobotStatus,
    TradingRobotUniverseRefresh,
    TradingRobotValidateResponse,
    StrategyArchetypeInfo,
    UniversePreview,
} from '@/types/robots'

function normalizeRobot(raw: Record<string, unknown>): TradingRobot {
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

export type TradingRobotFleetLive = {
    sessionState?: string | null
    session_state?: string | null
    equity?: number | null
    equityCurve?: Array<Record<string, unknown>> | null
    equity_curve?: Array<Record<string, unknown>> | null
    openPositionsCount?: number | null
    open_positions_count?: number | null
    tradesCount?: number | null
    trades_count?: number | null
    wins?: number | null
    losses?: number | null
    ownFunds?: number | null
    own_funds?: number | null
    priceDelta?: number | null
    price_delta?: number | null
    periodDelta?: number | null
    period_delta?: number | null
    statsPeriod?: 'session' | 'week' | 'month' | 'all' | null
    stats_period?: 'session' | 'week' | 'month' | 'all' | null
    lastCycleAt?: string | null
    last_cycle_at?: string | null
    message?: string | null
}

export type TradingRobotFleetAccount = {
    accountId?: string | null
    account_id?: string | null
    accountName?: string | null
    account_name?: string | null
}

export type TradingRobotFleetItem = TradingRobot & {
    accounts?: TradingRobotFleetAccount[]
    broker?: string | null
    brokerLabel?: string | null
    broker_label?: string | null
    live?: TradingRobotFleetLive | null
}

export type TradingRobotFleetResponse = {
    items: TradingRobotFleetItem[]
    total: number
    hasBrokerAccounts: boolean
}

/** Client facade for /api/robots. */
export const robotService = {
    async list(params: {
        robot_status?: number[]
        robot_type?: number[]
        broker?: Array<'tinvest' | 'bybit' | string>
    } = {}): Promise<TradingRobotFleetResponse> {
        const { data } = await api.post<{
            items: Array<Record<string, unknown>>
            total: number
            hasBrokerAccounts?: boolean
            has_broker_accounts?: boolean
        }>('/robots/data', params)
        const items = (data.items || []).map(raw => {
            const robot = normalizeRobot(raw) as TradingRobotFleetItem
            const accountsRaw = raw.accounts
            robot.accounts = Array.isArray(accountsRaw)
                ? (accountsRaw as TradingRobotFleetAccount[])
                : []
            robot.broker = (raw.broker ?? null) as string | null
            robot.brokerLabel = (raw.brokerLabel ?? raw.broker_label ?? null) as string | null
            robot.live = (raw.live ?? null) as TradingRobotFleetLive | null
            return robot
        })
        return {
            items,
            total: data.total ?? 0,
            hasBrokerAccounts: Boolean(data.hasBrokerAccounts ?? data.has_broker_accounts),
        }
    },

    async getById(robotId: number): Promise<TradingRobot> {
        const { data } = await api.get<Record<string, unknown>>(`/robots/${robotId}`)
        return normalizeRobot(data)
    },

    async createOrUpdate(payload: {
        id?: number | null
        name: string
        type: number
        tokenId: number
        config: Record<string, unknown>
        status?: number
    }): Promise<TradingRobot> {
        const { data } = await api.post<Record<string, unknown>>('/robots/create', payload)
        return normalizeRobot(data)
    },

    async changeStatus(
        robotId: number,
        status: number,
        opts: { stopMode?: 'soft' | 'hard' } = {},
    ): Promise<TradingRobot> {
        const body: Record<string, unknown> = { robotId, status }
        if (opts.stopMode != null) body.stopMode = opts.stopMode
        const { data } = await api.post<Record<string, unknown>>('/robots/change_status', body)
        return normalizeRobot(data)
    },

    async delete(robotId: number): Promise<void> {
        await api.post('/robots/delete', { robotId })
    },

    async clone(robotId: number): Promise<TradingRobot> {
        const { data } = await api.post<Record<string, unknown>>(`/robots/${robotId}/clone`)
        return normalizeRobot(data)
    },

    async getLogs(
        robotId: number,
        opts: { limit?: number; eventType?: string } = {},
    ): Promise<{ robotId: number; items: Array<Record<string, unknown>>; total: number }> {
        const { data } = await api.get<{ robotId: number; items: Array<Record<string, unknown>>; total: number }>(
            `/robots/${robotId}/logs`,
            { params: { limit: opts.limit ?? 100, event_type: opts.eventType } },
        )
        return data
    },

    async validate(payload: {
        type: number
        config: Record<string, unknown>
    }): Promise<TradingRobotValidateResponse> {
        const { data } = await api.post<TradingRobotValidateResponse>('/robots/validate', payload)
        return data
    },

    async previewUniverse(payload: {
        tokenId: number
        instrumentType?: string
        universe: Record<string, unknown>
        page?: number
        pageSize?: number
    }): Promise<UniversePreview> {
        const { data } = await api.post<UniversePreview>('/robots/preview-universe', payload)
        return data
    },

    async start(
        robotId: number,
        payload: { virtualCapital?: number; stopMode?: 'soft' | 'hard' } = {},
    ): Promise<TradingRobot> {
        const body: Record<string, unknown> = {}
        if (payload.virtualCapital != null) body.virtualCapital = payload.virtualCapital
        if (payload.stopMode != null) body.stopMode = payload.stopMode
        const { data } = await api.post<Record<string, unknown>>(`/robots/${robotId}/start`, body)
        return normalizeRobot(data)
    },

    async stop(robotId: number, stopMode: 'soft' | 'hard' = 'soft'): Promise<TradingRobot> {
        const { data } = await api.post<Record<string, unknown>>(
            `/robots/${robotId}/stop`,
            null,
            { params: { stop_mode: stopMode } },
        )
        return normalizeRobot(data)
    },

    async refreshUniverse(robotId: number): Promise<TradingRobotUniverseRefresh> {
        const { data } = await api.post<TradingRobotUniverseRefresh>(`/robots/${robotId}/refresh-universe`)
        return data
    },

    async getStatus(robotId: number): Promise<TradingRobotStatus> {
        const { data } = await api.get<TradingRobotStatus>(`/robots/${robotId}/status`)
        return data
    },

    async fetchAudit(payload: {
        robotId: number
        limit?: number
        offset?: number
        sessionId?: string | null
        types?: AuditDataType[]
        /** Inclusive UTC start. */
        from?: string | null
        /** Exclusive UTC end. */
        to?: string | null
    }): Promise<TradingRobotAuditResponse> {
        const { data } = await api.post<TradingRobotAuditResponse>('/robots/audit', {
            robotId: payload.robotId,
            limit: payload.limit ?? 100,
            offset: payload.offset ?? 0,
            sessionId: payload.sessionId ?? undefined,
            types: payload.types,
            from: payload.from ?? undefined,
            to: payload.to ?? undefined,
        })
        return data
    },

    async listArchetypes(): Promise<StrategyArchetypeInfo[]> {
        const { data } = await api.get<{ items?: StrategyArchetypeInfo[] } | StrategyArchetypeInfo[]>(
            '/strategy/archetypes',
        )
        if (Array.isArray(data)) return data
        return data.items || []
    },

    /** WebSocket URL for robot event stream (same-origin /api proxy). */
    buildStreamUrl(robotId: number, token?: string): string {
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        const base = `${proto}://${window.location.host}/api/robots/${robotId}/stream`
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
        const body: Record<string, unknown> = {
            config: payload.config,
            from_date: payload.from_date,
            to_date: payload.to_date,
            initial_capital: payload.initial_capital,
            asyncExecution: payload.asyncExecution ?? true,
        }
        // Soft-bind: omit robotId for Lab-native (orphan) runs; never send fake 0.
        if (payload.robotId != null && Number.isFinite(payload.robotId) && payload.robotId > 0) {
            body.robotId = payload.robotId
        }
        if (payload.tokenId != null && Number.isFinite(payload.tokenId) && payload.tokenId > 0) {
            body.tokenId = payload.tokenId
        }
        const res = await api.post<RobotBacktestRunDetails | RobotHistoryBacktestQueuedResponse>(
            '/robots/backtest',
            body,
        )
        if (res.status === 202) {
            return { status: 202, data: res.data as RobotHistoryBacktestQueuedResponse }
        }
        return { status: 200, data: res.data as RobotBacktestRunDetails }
    },

    async getBacktestRunStatus(runId: number): Promise<RobotBacktestRunStatus> {
        const { data } = await api.get<RobotBacktestRunStatus>(`/robots/backtest/runs/${runId}/status`)
        return data
    },

    async getBacktestRunDetails(
        runId: number,
        params?: {
            signalsLimit?: number
            signalsOffset?: number
            signalsStatus?: string
            rejectReason?: string
        },
    ): Promise<RobotBacktestRunDetails> {
        const { data } = await api.get<RobotBacktestRunDetails>(`/robots/backtest/runs/${runId}`, {
            params: {
                signals_limit: params?.signalsLimit,
                signals_offset: params?.signalsOffset,
                signals_status: params?.signalsStatus,
                reject_reason: params?.rejectReason,
            },
        })
        return data
    },

    /** SPEC-03 P0 paginated signals — soft-fail if backend not shipped yet. */
    async listBacktestSignals(
        runId: number,
        params: {
            limit?: number
            offset?: number
            status?: string
            rejectReason?: string
            ticker?: string
            cycleId?: string
        } = {},
    ): Promise<{ items: Array<Record<string, unknown>>; total: number; truncated_run?: boolean } | null> {
        try {
            const { data } = await api.get(`/robots/backtest/runs/${runId}/signals`, {
                params: {
                    limit: params.limit ?? 200,
                    offset: params.offset ?? 0,
                    status: params.status,
                    reject_reason: params.rejectReason,
                    ticker: params.ticker,
                    cycle_id: params.cycleId,
                },
            })
            return data
        } catch {
            return null
        }
    },

    /** SPEC-03 optional cycle inspector bundle — soft-fail if missing. */
    async getBacktestCycle(
        runId: number,
        cycleId: string,
    ): Promise<BacktestCycleBundleResponse | null> {
        try {
            const { data } = await api.get<BacktestCycleBundleResponse>(
                `/robots/backtest/runs/${runId}/cycles/${encodeURIComponent(cycleId)}`,
            )
            return data
        } catch {
            return null
        }
    },

    /** SPEC-03 P1 universe membership — soft-fail for old runs without membership table. */
    async getBacktestUniverse(
        runId: number,
        params: { from?: string; to?: string } = {},
    ): Promise<BacktestUniverseResponse | null> {
        try {
            const { data } = await api.get<BacktestUniverseResponse>(
                `/robots/backtest/runs/${runId}/universe`,
                {
                    params: {
                        from: params.from || undefined,
                        to: params.to || undefined,
                    },
                },
            )
            return data
        } catch {
            return null
        }
    },

    /** SPEC-03 P2 price overlay — soft-fail if candles unavailable. */
    async getBacktestPriceWindow(
        runId: number,
        params: { ticker: string; around: string; bars?: number },
    ): Promise<BacktestPriceWindowResponse | null> {
        try {
            const { data } = await api.get<BacktestPriceWindowResponse>(
                `/robots/backtest/runs/${runId}/price-window`,
                {
                    params: {
                        ticker: params.ticker,
                        around: params.around,
                        bars: params.bars ?? 50,
                    },
                },
            )
            return data
        } catch {
            return null
        }
    },

    /** SPEC-03 P2 intent↔fill lifecycle — soft-fail for legacy runs. */
    async getBacktestExecutionEvents(
        runId: number,
        params: { cycleId?: string; limit?: number } = {},
    ): Promise<BacktestExecutionEventsResponse | null> {
        try {
            const { data } = await api.get<BacktestExecutionEventsResponse>(
                `/robots/backtest/runs/${runId}/execution-events`,
                {
                    params: {
                        cycle_id: params.cycleId,
                        limit: params.limit ?? 500,
                    },
                },
            )
            return data
        } catch {
            return null
        }
    },

    /** SPEC-03 P2 narrative steps — soft-fail if missing. */
    async getBacktestNarrative(runId: number): Promise<BacktestNarrativeResponse | null> {
        try {
            const { data } = await api.get<BacktestNarrativeResponse>(
                `/robots/backtest/runs/${runId}/narrative`,
            )
            return data
        } catch {
            return null
        }
    },

    async cancelBacktestRun(runId: number): Promise<{ run_id: number; cancel_requested: boolean }> {
        const { data } = await api.post<{ run_id: number; cancel_requested: boolean }>(
            `/robots/backtest/runs/${runId}/cancel`,
        )
        return data
    },

    async listBacktestRuns(params: { robotId?: number; limit?: number } = {}): Promise<{
        items: Array<{
            run_id: number
            robot_id?: number | null
            /** Derived server-side when available; UI falls back to robot_id != null */
            bound?: boolean | null
            config_label?: string | null
            display_name?: string | null
            status: string
            requested_from: string
            requested_to: string
            started_at: string
            finished_at?: string | null
            initial_capital: number
            total_return_percent?: number | null
            max_drawdown_percent?: number | null
            sharpe_ratio?: number | null
            final_equity?: number | null
            trades_total: number
            signals_logged?: number
            signals_truncated?: boolean
            error_message?: string | null
        }>
        total: number
    }> {
        const { data } = await api.get('/robots/backtest/runs', {
            params: {
                ...(params.robotId != null ? { robot_id: params.robotId } : {}),
                limit: params.limit ?? 30,
            },
        })
        return data
    },

    async saveBacktestRunAsRobot(
        runId: number,
        body: { name: string; tokenId: number; attachRun?: boolean },
    ): Promise<{ robotId: number; runId: number }> {
        const { data } = await api.post<{
            robotId?: number
            runId?: number
            robot_id?: number
            run_id?: number
        }>(
            `/robots/backtest/runs/${runId}/save-as-robot`,
            {
                name: body.name,
                tokenId: body.tokenId,
                attachRun: body.attachRun ?? true,
            },
        )
        const robotId = Number(data.robotId ?? data.robot_id)
        const outRunId = Number(data.runId ?? data.run_id ?? runId)
        return { robotId, runId: outRunId }
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
        const { data } = await api.post('/robots/backtest/compare', {
            baseRunId,
            compareRunId,
        })
        return data
    },
}

export type { RobotHistoryBacktestResult }
