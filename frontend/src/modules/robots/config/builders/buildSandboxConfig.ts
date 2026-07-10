import { buildMoexConfig } from '@/modules/robots/config/builders/buildMoexConfig'
import type { TradingRobotFormSnapshot } from '@/pages/testing/buildTradingRobotConfigV2'
import type { Type2TinvestConfig } from '@/modules/robots/config/types/type2-tinvest'

/** Sandbox testing broker: v3 type2_tinvest shape with broker_type=sandbox. */
export function buildSandboxConfig(snapshot: TradingRobotFormSnapshot): Type2TinvestConfig {
    const base = buildMoexConfig(snapshot)
    return {
        ...base,
        broker_type: 'sandbox',
    }
}
