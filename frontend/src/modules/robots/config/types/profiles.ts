import type { Type2TinvestConfig } from '@/modules/robots/config/types/type2-tinvest'

export type SchemaProfile =
    | 'type1_tinvest'
    | 'type1_bybit'
    | 'type2_tinvest'
    | 'type2_bybit'

export type Type1TinvestConfig = {
    config_version: 3
    schema_profile: 'type1_tinvest'
    broker_type: 'tinvest'
}

export type Type1BybitConfig = {
    config_version: 3
    schema_profile: 'type1_bybit'
    broker_type: 'bybit'
    bybit: {
        testnet: boolean
        account_type: 'UNIFIED' | 'CONTRACT' | 'SPOT'
    }
}

export type Type2BybitConfig = {
    config_version: 3
    schema_profile: 'type2_bybit'
    broker_type: 'bybit'
    market_profile: 'crypto'
    instrument_id_type: 'symbol'
}

export type RobotConfigProfile =
    | Type1TinvestConfig
    | Type1BybitConfig
    | Type2TinvestConfig
    | Type2BybitConfig

export function isType2TinvestConfig(cfg: { schema_profile?: string }): cfg is Type2TinvestConfig {
    return cfg.schema_profile === 'type2_tinvest'
}

export function isType2BybitConfig(cfg: { schema_profile?: string }): cfg is Type2BybitConfig {
    return cfg.schema_profile === 'type2_bybit'
}
