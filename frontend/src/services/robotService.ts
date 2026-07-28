import { api } from './api'
import type {
    Robot,
    RobotListRequest,
    RobotListResponse,
    StrategyListResponse,
    StrategyParam,
    GrainSeedConfig,
    RobotTradingDefaults,
    RobotHistoryBacktestResult,
    RobotHistoryBacktestQueuedResponse,
    RobotBacktestCompareResponse,
    RobotBacktestHistoryResponse,
    RobotBacktestRunDetails,
    RobotBacktestRunStatus,
    RobotBacktestCancelResponse,
    RobotHistoricalScreeningResponse,
    RobotPaperSelectionResponse,
    RobotCryptoScreeningResponse,
    RobotCryptoScreeningStatus,
    RobotUniverseActiveCounts,
} from '@/types/robot'

///@EPIC Frontend.ITEM APIClient.TOPIC Robots Service Facade [1]
///@ Клиентский фасад для /robots и связанных endpoints: CRUD, backtest, live snapshot,
///@ DMS preview и вспомогательные методы для экранов настройки/тестирования.
export const robotService = {
    async list(params: RobotListRequest | number = {}, offset = 0): Promise<RobotListResponse> {
        const body: RobotListRequest =
            typeof params === 'number'
                ? { limit: params, offset }
                : {
                      limit: 50,
                      offset: 0,
                      ...params,
                  }
        const { data } = await api.post<RobotListResponse>('/robots/data', body)
        return data
    },

    async create(payload: {
        name: string
        token_id: number
        type?: 1 | 2
        config?: Record<string, unknown>
        poll_interval_hours?: number
        trading_hours_start?: string
        trading_hours_end?: string
        allowed_weekdays?: number
    }): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/create', payload)
        return data
    },

    async duplicate(payload: {
        source_robot_id: number
        name?: string
        broker_type?: string
        token_id?: number
        copy_sections?: string[]
        reset_sections?: string[]
    }): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/duplicate', payload)
        return data
    },

    async getById(robotId: number): Promise<Robot> {
        const { data } = await api.get<Robot>(`/robots/id/${robotId}`)
        return data
    },

    async updateRobot(robotId: number, patch: Partial<{
        name: string
        token_id: number
        type: 1 | 2
        status: number
        config: Record<string, any>
        poll_interval_hours: number
        trading_hours_start: string
        trading_hours_end: string
        allowed_weekdays: number
    }>): Promise<Robot> {
        const normalized: Record<string, any> = { ...patch }
        if (normalized.token_id != null) {
            normalized.token_id = Number(normalized.token_id)
        }
        const { data } = await api.post<Robot>('/robots/update', { robotId, patch: normalized })
        return data
    },

    async changeStatus(robotId: number, status: number): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/change_status', { robotId, status })
        return data
    },

    async deleteRobot(robotId: number): Promise<{ id: number; deleted: boolean }> {
        const { data } = await api.post<{ id: number; deleted: boolean }>('/robots/delete', { robotId })
        return data
    },

    async updateConfig(robotId: number, config: Record<string, unknown>): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/config', { robotId, config })
        return data
    },

    async validateConfig(payload: {
        robot_type: number
        broker_type: string
        config: GrainSeedConfig | Record<string, unknown>
    }): Promise<{ schema_profile: string; normalized_config: Record<string, unknown> }> {
        const { data } = await api.post<{ schema_profile: string; normalized_config: Record<string, unknown> }>(
            '/robots/validate-config',
            payload,
        )
        return data
    },

    async getConfigSchema(schemaProfile: string): Promise<{ schema_profile: string; json_schema: Record<string, unknown> }> {
        const { data } = await api.get<{ schema_profile: string; json_schema: Record<string, unknown> }>(
            `/robots/config-schema/${encodeURIComponent(schemaProfile)}`,
        )
        return data
    },

    async updateSchedule(robotId: number, payload: {
        poll_interval_hours: number
        trading_hours_start: string
        trading_hours_end: string
        allowed_weekdays: number
    }): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/schedule', { robotId, ...payload })
        return data
    },

    async getStrategies(): Promise<StrategyListResponse> {
        const { data } = await api.get<StrategyListResponse>('/robots/strategies')
        return data
    },

    async getTradingDefaults(): Promise<RobotTradingDefaults> {
        const { data } = await api.get<RobotTradingDefaults>('/robots/trading-defaults')
        return data
    },

    async runHistoryBacktest(payload: {
        robot_id?: number | null
        strategy?: string | null
        from_date: string
        to_date: string
        initial_capital?: number
        token_id?: number
        type?: number
        poll_interval_hours?: number
        trading_hours_start?: string
        trading_hours_end?: string
        allowed_weekdays?: number
        config?: Record<string, any>
        async_execution?: boolean
    }): Promise<
        | { status: 200; data: RobotHistoryBacktestResult }
        | { status: 202; data: RobotHistoryBacktestQueuedResponse }
    > {
        const res = await api.post<RobotHistoryBacktestResult | RobotHistoryBacktestQueuedResponse>(
            '/robots/history-backtest',
            payload,
        )
        if (res.status === 202) {
            return { status: 202, data: res.data as RobotHistoryBacktestQueuedResponse }
        }
        return { status: 200, data: res.data as RobotHistoryBacktestResult }
    },

    async listHistoryBacktests(payload: {
        robotId?: number | null
        limit?: number
        only_active?: boolean
        broker_type?: 'tinvest' | 'bybit'
    }): Promise<RobotBacktestHistoryResponse> {
        const { data } = await api.post<RobotBacktestHistoryResponse>('/robots/history-backtest/list', payload)
        return data
    },

    /** Лёгкий опрос прогона и ETA (без signals/orders). */
    async getHistoryBacktestRunStatus(runId: number): Promise<RobotBacktestRunStatus> {
        const { data } = await api.get<RobotBacktestRunStatus>(`/robots/history-backtest/runs/${runId}/status`)
        return data
    },

    /** Полный прогон с артефактами (после завершения или по клику в истории). */
    async getHistoryBacktestRunDetails(runId: number): Promise<RobotBacktestRunDetails> {
        const { data } = await api.get<RobotBacktestRunDetails>(`/robots/history-backtest/runs/${runId}`)
        return data
    },

    /** Активный прогон RUNNING/QUEUED/FETCHING или `null` (лёгкий статус). */
    async getActiveHistoryBacktestRun(): Promise<RobotBacktestRunStatus | null> {
        const { data } = await api.get<RobotBacktestRunStatus | null>('/robots/history-backtest/runs/active')
        return data
    },

    /** §9.1: запрос отмены фонового прогона. */
    async cancelHistoryBacktestRun(runId: number): Promise<RobotBacktestCancelResponse> {
        const { data } = await api.post<RobotBacktestCancelResponse>(
            `/robots/history-backtest/runs/${runId}/cancel`,
        )
        return data
    },

    async compareHistoryBacktestRuns(
        baseRunId: number,
        compareRunId: number,
        name?: string,
    ): Promise<RobotBacktestCompareResponse> {
        const { data } = await api.post<RobotBacktestCompareResponse>('/robots/history-backtest/compare', {
            baseRunId,
            compareRunId,
            name,
        })
        return data
    },

    /** Legacy POST — тот же ответ, что GET …/runs/{id}; предпочтительно `getHistoryBacktestRunDetails`. */
    async getHistoryBacktestRun(runId: number): Promise<RobotBacktestRunDetails> {
        const { data } = await api.post<RobotBacktestRunDetails>('/robots/history-backtest/run', { runId })
        return data
    },

    async syncUniverse(
        robotId: number,
        options?: { force_refresh_snapshot?: boolean; force_recompute_universe?: boolean },
    ): Promise<{
        robot_id: number
        allowed_figis: string[]
        accepted_tickers: string[]
        snapshot_id?: number | null
        analyzer_written_rows: number
        recomputed: boolean
        message?: string | null
    }> {
        const { data } = await api.post('/robots/sync-universe', {
            robotId,
            force_refresh_snapshot: options?.force_refresh_snapshot ?? true,
            force_recompute_universe: options?.force_recompute_universe ?? true,
        })
        return data
    },

    async runHistoricalScreening(robotId: number): Promise<RobotHistoricalScreeningResponse> {
        const { data } = await api.post<RobotHistoricalScreeningResponse>('/robots/jobs/historical-screening', {
            robotId,
        })
        return data
    },

    async runPaperSelection(
        robotId: number,
        options?: { force_refresh_snapshot?: boolean; force_recompute_universe?: boolean },
    ): Promise<RobotPaperSelectionResponse> {
        const { data } = await api.post<RobotPaperSelectionResponse>('/robots/jobs/paper-selection', {
            robotId,
            force_refresh_snapshot: options?.force_refresh_snapshot ?? true,
            force_recompute_universe: options?.force_recompute_universe ?? true,
        })
        return data
    },

    async runCryptoScreening(robotId: number): Promise<RobotCryptoScreeningResponse> {
        const { data } = await api.post<RobotCryptoScreeningResponse>('/robots/jobs/crypto-screening', {
            robotId,
        })
        return data
    },

    async getCryptoScreeningStatus(robotId: number): Promise<RobotCryptoScreeningStatus> {
        const { data } = await api.get<RobotCryptoScreeningStatus>(
            `/robots/${robotId}/crypto-screening/status`,
        )
        return data
    },

    async getUniverseActiveCounts(robotId: number): Promise<RobotUniverseActiveCounts> {
        const { data } = await api.get<RobotUniverseActiveCounts>(`/robots/${robotId}/universe/active-counts`)
        return data
    },

    async getStrategy(name: string): Promise<StrategyParam> {
        const { data } = await api.get<StrategyParam>(`/robots/strategies/${encodeURIComponent(name)}`)
        return data
    },

    async listUniverseDaily(
        robotId: number,
        params?: { trade_date?: string },
    ): Promise<{ total: number; items: any[]; source: string }> {
        const { data } = await api.get(`/robots/${robotId}/universe/daily`, { params: params || {} })
        return data
    },

    async migrateConfigV3(robotId?: number): Promise<{
        total: number
        updated: number
        items: Array<{
            robot_id: number
            config_version: number
            schema_profile?: string | null
            broker_type?: string | null
            updated: boolean
        }>
    }> {
        const { data } = await api.post('/robots/migrate-config-v3', { robotId: robotId ?? null })
        return data
    },

    async migrateConfigV2(robotId?: number): Promise<{
        total: number
        updated: number
        items: Array<{
            robot_id: number
            config_version: number
            universe_mode?: string | null
            historical_enabled?: boolean | null
            paper_input?: string | null
            updated: boolean
        }>
    }> {
        const { data } = await api.post('/robots/migrate-config-v2', { robotId: robotId ?? null })
        return data
    },

    async getLiveSnapshot(robotId: number, opts?: { mode?: 'ops' | 'full' }): Promise<{
        robot_id: number
        status: number
        broker_type: string
        strategy: string
        account_id?: string | null
        active_positions: any[]
        portfolio_positions: any[]
        portfolio_summary: Record<string, any>
        portfolio_fetch_error?: string | null
        portfolio_source?: string | null
        recent_signals: any[]
        recent_orders: any[]
        open_orders?: any[]
        order_history?: any[]
        recent_logs?: any[]
        stream_health: Record<string, any>
        orders_synced_at?: string | null
    }> {
        const { data } = await api.post('/robots/live/snapshot', {
            robotId,
            mode: opts?.mode ?? 'full',
        })
        return data
    },

    async placeManualOrder(payload: {
        robotId: number
        figi: string
        side: 'BUY' | 'SELL'
        price: number
        quantity?: number
        notional?: number
        reduceOnly?: boolean
    }): Promise<{
        order_id: string
        figi: string
        side: string
        quantity: number
        price: number
        status: string
        broker_type: string
        reduce_only: boolean
        notional?: number | null
        size_mode?: string
        event_id?: number | null
    }> {
        const body: Record<string, unknown> = {
            robotId: payload.robotId,
            figi: payload.figi,
            side: payload.side,
            price: payload.price,
            reduceOnly: payload.reduceOnly ?? false,
        }
        if (payload.notional != null && Number(payload.notional) > 0) {
            body.notional = Number(payload.notional)
        } else if (payload.quantity != null && Number(payload.quantity) > 0) {
            body.quantity = Number(payload.quantity)
        }
        const { data } = await api.post('/robots/live/manual-order', body)
        return data
    },

    async syncLiveOrders(robotId: number): Promise<{
        robot_id: number
        updated: number
        imported: number
        upserted: number
        cancelled: number
        history_updated: number
        healed_open?: number
        healed_closed?: number
        open_orders: any[]
        order_history: any[]
    }> {
        const { data } = await api.post('/robots/live/sync-orders', { robotId })
        return data
    },

    async autoSelectInstruments(params: Record<string, any>): Promise<{ items: any[]; total: number }> {
        const { data } = await api.post('/robots/instruments/auto-select', params)
        return data
    },

    async subscribeDms(payload: {
        robot_id: number
        board?: string
        include_candles?: boolean
        candle_interval?: string | null
        candle_depth?: number
        snapshot_hour?: number | null
        ttl_minutes?: number
    }): Promise<any> {
        const { data } = await api.post('/dms/subscribe', payload)
        return data
    },

    async listDmsSubscriptions(): Promise<any[]> {
        const { data } = await api.get('/dms/subscriptions')
        return data
    },

    async listDmsSnapshots(board?: string): Promise<any[]> {
        const { data } = await api.get('/dms/snapshots', { params: board ? { board } : {} })
        return data
    },

    async createDmsSnapshot(payload?: { board?: string; ttl_minutes?: number; is_manual?: boolean }): Promise<any> {
        const { data } = await api.post('/dms/snapshots/create', payload || { board: 'TQBR', ttl_minutes: 5, is_manual: true })
        return data
    },

    async processDmsQueue(): Promise<any> {
        const { data } = await api.post('/dms/process-queue')
        return data
    },

    async listDailyUniverse(params?: { robot_id?: number; trade_date?: string }): Promise<{ total: number; items: any[] }> {
        const { data } = await api.get('/dms/daily-universe', { params: params || {} })
        return data
    },

    async getDmsFilterLog(params?: { robot_id?: number; trade_date?: string; limit?: number }): Promise<{
        total_checked: number
        passed: number
        rejected: number
        items: any[]
    }> {
        const { data } = await api.get('/dms/filter-log', { params: params || {} })
        return data
    },

    async previewDmsPipeline(payload: {
        robot_id: number
        board?: string
        filters: Array<Record<string, any>>
        mode?: 'ALL' | 'ANY'
    }): Promise<{
        total_checked: number
        passed: number
        rejected: number
        sample: Array<Record<string, any>>
    }> {
        const { data } = await api.post('/dms/pipeline/preview', payload)
        return data
    },

}
