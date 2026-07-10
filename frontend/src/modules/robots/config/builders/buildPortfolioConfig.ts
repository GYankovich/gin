import { isCryptoBroker } from '@/modules/robots/config/builders/buildCryptoConfig'
import {
    pollValueToHours,
    type TradingRobotSchedulePatch,
} from '@/pages/testing/buildTradingRobotConfigV2'

export type BybitAccountType = 'UNIFIED' | 'CONTRACT' | 'SPOT'

export type PortfolioFormSnapshot = {
    brokerType: string
    bybitTestnet?: boolean
    bybitAccountType?: BybitAccountType
}

export type PortfolioScheduleSnapshot = {
    pollValue: number
    pollUnit: 'minutes' | 'hours'
    hoursFrom: string
    hoursTo: string
    weekdaysMask: number
}

/** Schedule fields for portfolio updater robots (type=1). */
export function buildPortfolioSchedulePatch(snapshot: PortfolioScheduleSnapshot): TradingRobotSchedulePatch {
    return {
        poll_interval_hours: pollValueToHours(snapshot.pollValue, snapshot.pollUnit),
        trading_hours_start: snapshot.hoursFrom || '10:00',
        trading_hours_end: snapshot.hoursTo || '18:45',
        allowed_weekdays: Number(snapshot.weekdaysMask ?? 31),
    }
}

/** v3 type1_tinvest | type1_bybit config for portfolio updater robots. */
export function buildPortfolioRobotConfig(snapshot: PortfolioFormSnapshot): Record<string, unknown> {
    if (isCryptoBroker(snapshot.brokerType)) {
        const accountType = snapshot.bybitAccountType ?? 'UNIFIED'
        return {
            config_version: 3,
            schema_profile: 'type1_bybit',
            broker_type: 'bybit',
            bybit: {
                testnet: snapshot.bybitTestnet ?? false,
                account_type: accountType,
            },
        }
    }
    return {
        config_version: 3,
        schema_profile: 'type1_tinvest',
        broker_type: 'tinvest',
    }
}

export function portfolioDefaultsFromConfig(cfg: Record<string, unknown>): {
    brokerType: string
    bybitTestnet: boolean
    bybitAccountType: BybitAccountType
} {
    const broker = String(cfg.broker_type ?? 'tinvest').trim().toLowerCase()
    const bybit = (cfg.bybit ?? {}) as Record<string, unknown>
    const rawAccount = String(bybit.account_type ?? 'UNIFIED').trim().toUpperCase()
    const accountType: BybitAccountType =
        rawAccount === 'CONTRACT' || rawAccount === 'SPOT' ? rawAccount : 'UNIFIED'
    return {
        brokerType: broker === 'bybit' ? 'bybit' : 'tinvest',
        bybitTestnet: bybit.testnet === true,
        bybitAccountType: accountType,
    }
}
