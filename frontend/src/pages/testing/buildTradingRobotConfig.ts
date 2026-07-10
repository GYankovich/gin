export {
    buildTradingRobotConfigV2,
    buildStrategyParamsPayload,
    buildTradingRobotSchedulePatch,
    defaultTestingFilters,
    pollValueToHours,
    type TradingRobotFormSnapshot,
    type TradingRobotSchedulePatch,
} from '@/pages/testing/buildTradingRobotConfigV2'

import { buildMoexConfig } from '@/modules/robots/config/builders/buildMoexConfig'
import {
    buildCryptoTradingRobotConfig,
    isCryptoBroker,
} from '@/modules/robots/config/builders/buildCryptoConfig'
import { buildSandboxConfig } from '@/modules/robots/config/builders/buildSandboxConfig'
import type { TradingRobotFormSnapshot } from '@/pages/testing/buildTradingRobotConfigV2'

/** Сборка config для save/backtest: v3 only (type2_tinvest | type2_bybit | sandbox). */
export function buildTradingRobotConfig(snapshot: TradingRobotFormSnapshot): Record<string, unknown> {
    if (isCryptoBroker(snapshot.brokerType)) {
        return buildCryptoTradingRobotConfig(snapshot)
    }
    if (String(snapshot.brokerType || 'tinvest').trim().toLowerCase() === 'sandbox') {
        return buildSandboxConfig(snapshot)
    }
    return buildMoexConfig(snapshot)
}
