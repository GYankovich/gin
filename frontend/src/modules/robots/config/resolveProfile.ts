import type { Robot } from '@/types/robot'
import type { SchemaProfile } from '@/modules/robots/config/types/profiles'

export type MarketProfile = 'portfolio' | 'moex' | 'crypto'

type ConfigLike = {
    schema_profile?: string
    broker_type?: string
    config_version?: number
    market_profile?: string
}

export function deriveMarketProfile(robot: Pick<Robot, 'type' | 'config'>): MarketProfile {
    const cfg = (robot.config ?? {}) as ConfigLike
    if (Number(robot.type) === 1) return 'portfolio'

    const broker = String(cfg.broker_type || 'tinvest').trim().toLowerCase()
    if (broker === 'bybit' || cfg.market_profile === 'crypto') return 'crypto'
    return 'moex'
}

export function deriveMarketProfileFromDraft(
    robotType: 1 | 2,
    brokerType: string,
    config?: ConfigLike | null,
): MarketProfile {
    if (robotType === 1) return 'portfolio'

    const cfg = config ?? {}
    const broker = String(brokerType || cfg.broker_type || 'tinvest').trim().toLowerCase()
    if (broker === 'bybit' || cfg.market_profile === 'crypto') return 'crypto'
    return 'moex'
}

export function resolveSchemaProfile(robot: Pick<Robot, 'type' | 'config'>): SchemaProfile | null {
    const cfg = (robot.config ?? {}) as ConfigLike
    const explicit = String(cfg.schema_profile || '').trim()
    if (explicit === 'type2_tinvest') return 'type2_tinvest'

    const broker = String(cfg.broker_type || 'tinvest').trim().toLowerCase()
    if (Number(robot.type) === 2 && broker === 'tinvest') {
        return 'type2_tinvest'
    }
    return null
}

export function resolveSchemaProfileFromDraft(
    robotType: 1 | 2,
    brokerType: string,
    config?: ConfigLike | null,
): SchemaProfile | null {
    const cfg = config ?? {}
    const explicit = String(cfg.schema_profile || '').trim()
    if (explicit === 'type2_tinvest') return 'type2_tinvest'

    const broker = String(brokerType || cfg.broker_type || 'tinvest').trim().toLowerCase()
    if (robotType === 2 && broker === 'tinvest') {
        return 'type2_tinvest'
    }
    return null
}

/** MOEX trading UI (П1/П2/DMS) — только type=2 + tinvest + schema_profile type2_tinvest. */
export function isMoexType2TinvestDraft(
    robotType: 1 | 2,
    brokerType: string,
    config?: ConfigLike | null,
): boolean {
    return (
        deriveMarketProfileFromDraft(robotType, brokerType, config) === 'moex' &&
        resolveSchemaProfileFromDraft(robotType, brokerType, config) === 'type2_tinvest'
    )
}

export function marketProfileLabel(profile: MarketProfile): string {
    if (profile === 'portfolio') return 'Портфель'
    if (profile === 'crypto') return 'Монеты · ByBit'
    return 'Ценные бумаги · MOEX'
}

/** Testnet/Mainnet для bybit-робота; null если не crypto. */
export function resolveBybitEnvironment(
    config?: { broker_type?: string; bybit?: { testnet?: boolean } } | null,
): 'testnet' | 'mainnet' | null {
    const broker = String(config?.broker_type || '').trim().toLowerCase()
    if (broker !== 'bybit') return null
    return 'mainnet'
}
