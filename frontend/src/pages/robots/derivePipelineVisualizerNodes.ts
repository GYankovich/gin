import type { MarketProfile } from '@/modules/robots/config/resolveProfile'
import type { PipelineVisualizerNode, RobotEditorStage } from '@/pages/robots/components/PipelineVisualizer'

const STAGE_NODES: Record<RobotEditorStage, { icon: string; title: string }> = {
    general: { icon: '⚙️', title: 'Основное' },
    p1: { icon: '📡', title: 'Поиск бумаг' },
    p2: { icon: '🔍', title: 'Отбор бумаг' },
    p3: { icon: '⚡', title: 'Торговая логика' },
    risk: { icon: '🛡️', title: 'Риск' },
}

const CRYPTO_STAGE_NODES: Partial<Record<RobotEditorStage, { icon: string; title: string }>> = {
    p1: { icon: '📡', title: 'Поиск монет' },
    p2: { icon: '🔍', title: 'Отбор монет' },
}

const TRADING_STAGE_ORDER: RobotEditorStage[] = ['p1', 'p2', 'p3', 'risk']

export function derivePipelineVisualizerNodes(opts: {
    robotType: number
    marketProfile?: MarketProfile
    /** @deprecated use marketProfile === 'moex' */
    isMoexType2Tinvest?: boolean
}): PipelineVisualizerNode[] {
    const nodes: PipelineVisualizerNode[] = [
        { id: 'general', ...STAGE_NODES.general },
    ]
    if (Number(opts.robotType) !== 2) return nodes

    const profile =
        opts.marketProfile ??
        (opts.isMoexType2Tinvest === false ? 'crypto' : 'moex')
    if (profile === 'moex') {
        nodes.push({ id: 'p1', ...STAGE_NODES.p1 }, { id: 'p2', ...STAGE_NODES.p2 })
    } else if (profile === 'crypto') {
        nodes.push(
            { id: 'p1', ...CRYPTO_STAGE_NODES.p1! },
            { id: 'p2', ...CRYPTO_STAGE_NODES.p2! },
        )
    }
    nodes.push({ id: 'p3', ...STAGE_NODES.p3 }, { id: 'risk', ...STAGE_NODES.risk })
    return nodes
}

export const STAGE_TITLES: Record<RobotEditorStage, string> = {
    general: 'Основные настройки',
    p1: '1. Поиск бумаг',
    p2: '2. Отбор бумаг',
    p3: '3. Торговая логика',
    risk: 'Риск-менеджмент',
}

const CRYPTO_STAGE_PANEL_TITLES: Partial<Record<RobotEditorStage, string>> = {
    p1: '1. Поиск монет',
    p2: '2. Отбор монет',
    p3: '3. Торговая логика',
    risk: 'Риск-менеджмент',
}

export function stagePanelTitle(stage: RobotEditorStage, profile?: MarketProfile): string {
    if (profile === 'crypto' && CRYPTO_STAGE_PANEL_TITLES[stage]) {
        return CRYPTO_STAGE_PANEL_TITLES[stage]!
    }
    return STAGE_TITLES[stage]
}
