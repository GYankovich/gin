import type {
    RobotCostsConfig,
    RobotRiskConfig,
    RobotStrategyName,
    RobotStrategyParams,
} from '@/types/robot'

export type MoexRefreshSchedule = {
    every_minutes: number
    only_trading_hours: boolean
    daily_at_msk: string | null
}

export type MoexPipelineFilter = {
    type: string
    min?: number
    max_percent?: number
    min_percent?: number
    period?: number
    eq?: string
    direction?: string
    max_steps?: number
    min_ratio?: number
    list?: string[] | null
}

export type MoexHistoricalScreeningConfig = {
    enabled: boolean
    source: 'moex' | 'tinvest'
    board: string
    universe: string
    fixed_tickers: string[]
    interval: string
    lookback_days: number
    filters: MoexPipelineFilter[]
    refresh: MoexRefreshSchedule
}

export type MoexPaperSelectionConfig = {
    enabled: boolean
    input: string
    fixed_tickers: string[]
    mode: 'ALL' | 'ANY'
    filters: MoexPipelineFilter[]
    refresh: MoexRefreshSchedule
}

export type MoexSignalGenerationConfig = {
    strategy: RobotStrategyName
    params: RobotStrategyParams
    data_source: string
    update_interval_seconds: number
    indicator_update_schedule: Record<string, string>
}

/** MOEX trading robot config v3 (`schema_profile=type2_tinvest`). */
export type Type2TinvestConfig = {
    config_version: 3
    schema_profile: 'type2_tinvest'
    instrument_id_type: 'figi'
    broker_type: 'tinvest'
    strategy: RobotStrategyName
    strategy_params: RobotStrategyParams
    allowed_figis: string[]
    universe_mode?: 'fixed' | 'dms_pipeline' | 'tqbr_scan'
    fixed_tickers?: string[]
    universe_refresh_minutes?: number
    update_interval_seconds: number
    indicator_update_schedule: Record<string, string>
    pipeline: {
        mode: 'ALL' | 'ANY'
        filters: MoexPipelineFilter[]
    }
    risk: RobotRiskConfig
    costs: RobotCostsConfig
    historical_screening: MoexHistoricalScreeningConfig
    paper_selection: MoexPaperSelectionConfig
    signal_generation: MoexSignalGenerationConfig
    instrument_map?: Record<string, unknown>
}
