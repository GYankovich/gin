import {
    buildTradingRobotConfigV2,
    type TradingRobotFormSnapshot,
} from '@/pages/testing/buildTradingRobotConfigV2'
import type { Type2TinvestConfig } from '@/modules/robots/config/types/type2-tinvest'

/**
 * Сборка MOEX trading config v3 (`type2_tinvest`) из snapshot формы.
 * Поверх v2-builder добавляет `config_version`, `schema_profile`, `instrument_id_type`.
 */
export function buildMoexConfig(snapshot: TradingRobotFormSnapshot): Type2TinvestConfig {
    const base = buildTradingRobotConfigV2(snapshot)
    return {
        ...(base as Omit<Type2TinvestConfig, 'config_version' | 'schema_profile' | 'instrument_id_type'>),
        config_version: 3,
        schema_profile: 'type2_tinvest',
        instrument_id_type: 'figi',
        broker_type: 'tinvest',
    }
}
