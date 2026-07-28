import type { MarketProfile } from '@/modules/robots/config/resolveProfile'
import type { PipelineVisualizerNode, RobotEditorStage } from '@/pages/robots/components/PipelineVisualizer'

const STAGE_NODES: Record<RobotEditorStage, { title: string }> = {
    general: { title: 'Основное' },
    p1: { title: 'Поиск и отбор' },
    p2: { title: 'Отбор бумаг' },
    p3: { title: 'Торговая логика' },
    risk: { title: 'Риск' },
}

const CRYPTO_STAGE_NODES: Partial<Record<RobotEditorStage, { title: string }>> = {
    p1: { title: 'Поиск и отбор' },
}

export function derivePipelineVisualizerNodes(opts: {
    robotType: number
    marketProfile?: MarketProfile
    /** @deprecated use marketProfile === 'moex' */
    isMoexType2Tinvest?: boolean
}): PipelineVisualizerNode[] {
    // Type 1 has a single general stage — no pipeline chrome.
    if (Number(opts.robotType) !== 2) return []

    const nodes: PipelineVisualizerNode[] = [
        { id: 'general', ...STAGE_NODES.general },
    ]

    const profile =
        opts.marketProfile ??
        (opts.isMoexType2Tinvest === false ? 'crypto' : 'moex')
    if (profile === 'moex' || profile === 'crypto') {
        // Поиск + отбор в одной вкладке (p1)
        nodes.push({
            id: 'p1',
            ...(profile === 'crypto' ? CRYPTO_STAGE_NODES.p1! : STAGE_NODES.p1),
        })
    }
    nodes.push({ id: 'p3', ...STAGE_NODES.p3 }, { id: 'risk', ...STAGE_NODES.risk })
    return nodes
}

export const STAGE_TITLES: Record<RobotEditorStage, string> = {
    general: 'Основные настройки',
    p1: 'Поиск и отбор бумаг',
    p2: '2. Отбор бумаг',
    p3: 'Торговая логика',
    risk: 'Риск-менеджмент',
}

const CRYPTO_STAGE_PANEL_TITLES: Partial<Record<RobotEditorStage, string>> = {
    p1: 'Поиск и отбор монет',
    p3: 'Торговая логика',
    risk: 'Риск-менеджмент',
}

export function stagePanelTitle(stage: RobotEditorStage, profile?: MarketProfile): string {
    if (profile === 'crypto' && CRYPTO_STAGE_PANEL_TITLES[stage]) {
        return CRYPTO_STAGE_PANEL_TITLES[stage]!
    }
    if (profile === 'moex' && stage === 'p1') {
        return STAGE_TITLES.p1
    }
    return STAGE_TITLES[stage]
}
