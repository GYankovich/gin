import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { WeekdaysMaskField } from '@/components/ui/WeekdaysMaskField'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import { robotService } from '@/services/robotService'
import type { Robot } from '@/types/robot'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/services/api'
import { useSearchParams } from 'react-router-dom'
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { TestingStrategyParamsCard } from '@/pages/testing/TestingStrategyParamsCard'
import { TestingRiskParamsCard } from '@/pages/testing/TestingRiskParamsCard'
import { buildMoexConfig } from '@/modules/robots/config/builders/buildMoexConfig'
import {
    createDefaultCryptoScreeningFilters,
    cryptoFieldsFromFilters,
    cryptoFiltersFromFields,
    ensureCompleteCryptoFilters,
    type CryptoScreeningFilter,
    type CryptoScreeningFilterType,
} from '@/pages/testing/cryptoScreeningPipeline'
import {
    defaultSlippagePct,
    type FundingSimulationMode,
} from '@/pages/testing/executionRiskDefaults'
import {
    buildCryptoTradingRobotConfig,
    cryptoDefaultsFromConfig,
    isCryptoBroker,
} from '@/modules/robots/config/builders/buildCryptoConfig'
import {
    deriveMarketProfileFromDraft,
    isMoexType2TinvestDraft,
    marketProfileLabel,
    resolveSchemaProfileFromDraft,
} from '@/modules/robots/config/resolveProfile'
import {
    collectIssues,
    hasBlockingValidationIssues,
    type ValidationIssue,
} from '@/modules/robots/config/validate/collectIssues'
import {
    buildTradingRobotConfig,
    buildTradingRobotSchedulePatch,
} from '@/pages/testing/buildTradingRobotConfig'
import type { RobotStrategyName, RobotStrategyParams } from '@/types/robot'
import {
    tradingHoursFromSchedule,
    useTradingRobotStrategyForm,
    type TradingRobotStrategyDraft,
} from '@/pages/robots/useTradingRobotStrategyForm'
import { derivePipelineStageStatuses } from '@/pages/robots/pipelineStageStatus'
import {
    GRAIN_SEED_CRYPTO_P3_EXCLUDE_FIELD_KEYS,
    GRAIN_SEED_EXCLUDED_P3_FIELD_KEYS,
} from '@/pages/testing/strategyPresets'
import { PipelineStageBadges } from '@/components/ui/PipelineStageBadges'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { PipelineVisualizer, type RobotEditorStage } from '@/pages/robots/components/PipelineVisualizer'
import { RobotContextPanel } from '@/pages/robots/components/RobotContextPanel'
import { derivePipelineVisualizerNodes, stagePanelTitle } from '@/pages/robots/derivePipelineVisualizerNodes'
import { CryptoBrokerConfigurator } from '@/modules/robots/components/CryptoConfigurator'
import { CryptoCostsCard } from '@/modules/robots/components/CryptoCostsCard'
import { CryptoUniverseConfigurator } from '@/modules/robots/components/CryptoUniverseConfigurator'
import { MOEX_P2_SNAPSHOT_FILTER_PRESETS, type UniverseFilterPresetId } from '@/modules/robots/config/universeFilterPresets'
import { MoexConfigurator } from '@/modules/robots/components/MoexConfigurator'
import {
    buildPortfolioRobotConfig,
    buildPortfolioSchedulePatch,
    portfolioDefaultsFromConfig,
    type BybitAccountType,
} from '@/modules/robots/config/builders/buildPortfolioConfig'
import { brokerFromTokenId, brokerFromTokenType, brokerLabelFromToken } from '@/modules/robots/config/tokenBroker'
import {
    pollMinuteOptionsForRobotType,
    resolvePollMinutesFromRobot,
    snapPollMinutes,
} from '@/modules/robots/config/pollSchedule'
import type { ApiKeyItem } from '@/pages/settings/types'
import {
    DEFAULT_PIPELINE_FILTERS,
    type PipelineFilter,
    type PipelineFilterType,
} from '@/pages/robots/pipelineFilterMeta'
import type { PipelineFilter as TestingPipelineFilter } from '@/pages/testing/testingPipeline'
import {
    formatFixedTickers,
    normalizeUniverseMode,
    normalizeCryptoUniverseMode,
    parseFixedTickersInput,
    TRADING_UNIVERSE_MODE_OPTIONS,
    type CryptoUniverseMode,
    type UniverseMode,
} from '@/utils/universeMode'
import {
    HISTORICAL_FILTER_TYPES,
    formatUniverseJobTime,
    hydrateCandidatePool,
    hydrateHistoricalScreening,
    hydratePaperSelection,
    hydrateUniverseJobsState,
} from '@/utils/robotConfigV2'
import { normalizeSignalInterval } from '@/pages/testing/testingPipeline'
import { formatRobotSessionStatus } from '@/utils/robotSessionStatus'
import {
    BROKER_CHANGE_BLOCKED_MESSAGE,
    brokerTypeLabel,
    isBrokerTypeConflictError,
} from '@/modules/robots/config/brokerImmutability'
import cyberHero from '@/assets/dashboard/cyber-hero.png'

///@EPIC Frontend.ITEM RobotsUI.TOPIC Trading Robot Configuration [1]
///@ Главная форма настройки торгового робота: pipeline-фильтры, риск/costs, расписание,
///@ пресеты и интеграция с robots API для create/update/preview сценариев.
type DraftSnapshot = {
    name: string
    tokenId: number
    robotType: 1 | 2
    pollValue: number
    pollUnit: 'minutes' | 'hours'
    brokerCommissionRate: number
    ndflRate: number
    hoursFrom: string
    hoursTo: string
    weekdaysMask: number
    pipelineMode: 'ALL' | 'ANY'
    universeMode: 'fixed' | 'dms_pipeline' | 'tqbr_scan'
    fixedTickersText: string
    historicalEnabled: boolean
    historicalInterval: string
    historicalLookbackDays: number
    historicalDailyAtMsk: string
    paperRefreshMinutes: number
    strategy: TradingRobotStrategyDraft
    bybitTestnet: boolean
    instrumentCategory: 'spot' | 'linear' | 'inverse'
    leverage: number
    makerFeePct: number
    takerFeePct: number
    fundingMode: FundingSimulationMode
    backtestExecution: 'limit_maker' | 'market_taker'
    backtestFeeModel: 'maker_taker' | 'taker_only' | 'maker_only'
    maintenanceMarginPct: number
    cryptoUniverseMode: CryptoUniverseMode
    cryptoFilters: Array<{ type: CryptoScreeningFilterType; value: number }>
    portfolioBrokerType: string
    portfolioBybitTestnet: boolean
    portfolioBybitAccountType: BybitAccountType
    filters: Array<{
        type: PipelineFilterType
        min?: number
        max_percent?: number
        min_percent?: number
        period?: number
        eq?: string
        direction?: 'BOTH' | 'UP_ONLY' | 'DOWN_ONLY'
        max_steps?: number
        min_ratio?: number
        list?: string[] | null
    }>
}

type PortfolioDirtySnapshot = Pick<
    DraftSnapshot,
    | 'name'
    | 'tokenId'
    | 'robotType'
    | 'pollValue'
    | 'pollUnit'
    | 'hoursFrom'
    | 'hoursTo'
    | 'weekdaysMask'
    | 'portfolioBrokerType'
    | 'portfolioBybitTestnet'
    | 'portfolioBybitAccountType'
>

function dirtySnapshotFromDraft(draft: DraftSnapshot): DraftSnapshot | PortfolioDirtySnapshot {
    if (draft.robotType === 1) {
        return {
            name: draft.name,
            tokenId: draft.tokenId,
            robotType: draft.robotType,
            pollValue: draft.pollValue,
            pollUnit: draft.pollUnit,
            hoursFrom: draft.hoursFrom,
            hoursTo: draft.hoursTo,
            weekdaysMask: draft.weekdaysMask,
            portfolioBrokerType: draft.portfolioBrokerType,
            portfolioBybitTestnet: draft.portfolioBybitTestnet,
            portfolioBybitAccountType: draft.portfolioBybitAccountType,
        }
    }
    return draft
}

function serializeDirtySnapshot(draft: DraftSnapshot | PortfolioDirtySnapshot): string {
    return JSON.stringify(draft)
}

function fieldIssues(issues: ValidationIssue[] | null, field: string): ValidationIssue[] {
    return (issues || []).filter(i => i.field === field)
}

export default function TradingRobotSettingsPage() {
    const [searchParams, setSearchParams] = useSearchParams()
    const toast = useToast()
    const [robots, setRobots] = useState<Robot[]>([])
    const [tokenOptions, setTokenOptions] = useState<Array<{ value: string; label: string }>>([])
    const [tokenCatalog, setTokenCatalog] = useState<ApiKeyItem[]>([])
    const [selectedRobot, setSelectedRobot] = useState<number | null>(() => {
        const raw = searchParams.get('robotId')
        const parsed = raw ? Number(raw) : null
        return parsed && Number.isFinite(parsed) ? parsed : null
    })
    const [isNewRobot, setIsNewRobot] = useState<boolean>(() => !searchParams.get('robotId'))
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [duplicating, setDuplicating] = useState(false)
    const [previewLoading, setPreviewLoading] = useState(false)
    const [preview, setPreview] = useState<{
        total_checked: number
        passed: number
        rejected: number
        sample: any[]
    } | null>(null)
    const [activeStage, setActiveStage] = useState<RobotEditorStage>('general')

    const [pipelineMode, setPipelineMode] = useState<'ALL' | 'ANY'>('ALL')
    const [universeMode, setUniverseMode] = useState<UniverseMode>('dms_pipeline')
    const [fixedTickersText, setFixedTickersText] = useState('')
    const [historicalEnabled, setHistoricalEnabled] = useState(true)
    const [historicalInterval, setHistoricalInterval] = useState('CANDLE_INTERVAL_10_MIN')
    const [historicalLookbackDays, setHistoricalLookbackDays] = useState(14)
    const [historicalDailyAtMsk, setHistoricalDailyAtMsk] = useState('07:00')
    const [paperRefreshMinutes, setPaperRefreshMinutes] = useState(30)
    const [bybitTestnet, setBybitTestnet] = useState(false)
    const [instrumentCategory, setInstrumentCategory] = useState<'spot' | 'linear' | 'inverse'>('linear')
    const [leverage, setLeverage] = useState(5)
    const [makerFeePct, setMakerFeePct] = useState(0.01)
    const [takerFeePct, setTakerFeePct] = useState(0.06)
    const [fundingMode, setFundingMode] = useState<FundingSimulationMode>('historical')
    const [backtestExecution, setBacktestExecution] = useState<'limit_maker' | 'market_taker'>('market_taker')
    const [backtestFeeModel, setBacktestFeeModel] = useState<'maker_taker' | 'taker_only' | 'maker_only'>('maker_taker')
    const [maintenanceMarginPct, setMaintenanceMarginPct] = useState(0.5)
    const [cryptoFilters, setCryptoFilters] = useState<CryptoScreeningFilter[]>(() => createDefaultCryptoScreeningFilters())
    const [cryptoUniverseMode, setCryptoUniverseMode] = useState<CryptoUniverseMode>('fixed')
    const [portfolioBrokerType, setPortfolioBrokerType] = useState('tinvest')
    const [portfolioBybitTestnet, setPortfolioBybitTestnet] = useState(true)
    const [portfolioBybitAccountType, setPortfolioBybitAccountType] = useState<BybitAccountType>('UNIFIED')
    const [candidatePoolTickers, setCandidatePoolTickers] = useState<string[]>([])
    const [candidatePoolAsOf, setCandidatePoolAsOf] = useState<string | null>(null)
    const [allowedFigisCount, setAllowedFigisCount] = useState(0)
    const [lastHistoricalRun, setLastHistoricalRun] = useState<string | null>(null)
    const [lastPaperRun, setLastPaperRun] = useState<string | null>(null)
    const [histJobLoading, setHistJobLoading] = useState(false)
    const [paperJobLoading, setPaperJobLoading] = useState(false)
    const [cryptoScreeningLoading, setCryptoScreeningLoading] = useState(false)
    const [cryptoScreeningPreview, setCryptoScreeningPreview] = useState<{
        symbols: string[]
        accepted: number
        scanned: number
        message?: string | null
    } | null>(null)
    const [migratingV3, setMigratingV3] = useState(false)
    const [pipelineRunning, setPipelineRunning] = useState(false)
    const [checkLoading, setCheckLoading] = useState(false)
    const [checkedIssues, setCheckedIssues] = useState<ValidationIssue[] | null>(null)
    const [filters, setFilters] = useState<PipelineFilter[]>([])
    const [name, setName] = useState('')
    const [tokenId, setTokenId] = useState<number>(0)
    const [robotType, setRobotType] = useState<1 | 2>(2)
    const [pollValue, setPollValue] = useState<number>(5)
    const [pollUnit, setPollUnit] = useState<'minutes' | 'hours'>('minutes')
    const [hoursFrom, setHoursFrom] = useState('10:00')
    const strategyForm = useTradingRobotStrategyForm()
    const [hoursTo, setHoursTo] = useState('18:45')
    const [weekdaysMask, setWeekdaysMask] = useState(31)
    const [baselineDraft, setBaselineDraft] = useState<string>('')
    const [isEditing, setIsEditing] = useState(false)
    const [robotTypeOptions, setRobotTypeOptions] = useState<Array<{ value: string; label: string }>>([
        { value: '1', label: 'Portfolio updater' },
        { value: '2', label: 'Trading robot' },
    ])
    const hydratingDraftRef = useRef(false)
    const isEditingRef = useRef(false)
    const skipNextLoadOneRef = useRef<number | null>(null)
    const tradingDefaultsRef = useRef<{ brokerPct: number; ndflPct: number } | null>(null)

    const selectedRobotEntity = useMemo(
        () => robots.find(r => r.id === selectedRobot) || null,
        [robots, selectedRobot],
    )

    const needsConfigV3Migrate = useMemo(() => {
        if (!selectedRobotEntity?.config) return false
        const v = Number((selectedRobotEntity.config as { config_version?: number }).config_version ?? 0)
        return v < 3
    }, [selectedRobotEntity?.config])

    const isMoexType2Tinvest = useMemo(
        () => isMoexType2TinvestDraft(robotType, strategyForm.brokerType, selectedRobotEntity?.config ?? null),
        [robotType, strategyForm.brokerType, selectedRobotEntity?.config],
    )

    const marketProfile = useMemo(
        () => deriveMarketProfileFromDraft(robotType, strategyForm.brokerType, selectedRobotEntity?.config ?? null),
        [robotType, strategyForm.brokerType, selectedRobotEntity?.config],
    )
    const isCrypto = marketProfile === 'crypto'
    const isPortfolioRobot = robotType === 1

    const syncBrokerFromToken = useCallback((broker: 'tinvest' | 'bybit', userPickedToken = false) => {
        setPortfolioBrokerType(broker)
        strategyForm.setBrokerType(broker)
        if (robotType === 1) {
            if (userPickedToken && isCryptoBroker(broker)) {
                setPortfolioBybitTestnet(true)
                setPortfolioBybitAccountType('UNIFIED')
            }
            return
        }
        if (userPickedToken && isCryptoBroker(broker)) {
            setUniverseMode('fixed')
            setCryptoUniverseMode('fixed')
            setBybitTestnet(false)
            setInstrumentCategory('linear')
            setLeverage(1)
            setMakerFeePct(0.01)
            setTakerFeePct(0.06)
            setFundingMode('historical')
            setCryptoFilters(createDefaultCryptoScreeningFilters())
            strategyForm.setNdflPct(0)
            strategyForm.setMinTradeAmountRub(5)
        }
    }, [strategyForm, robotType])

    const buildDirtySnapshotFromState = useCallback(
        () => dirtySnapshotFromDraft(buildDraftSnapshot()),
        [
            name,
            tokenId,
            robotType,
            pollValue,
            pollUnit,
            strategyForm.brokerCommissionPct,
            strategyForm.ndflPct,
            strategyForm.strategy,
            strategyForm.capital,
            strategyForm.strategyParams,
            strategyForm.interval,
            strategyForm.stopLossPct,
            strategyForm.takeProfitPct,
            strategyForm.maxPositionPct,
            strategyForm.maxPositionRub,
            strategyForm.maxDailyLoss,
            strategyForm.minTradeAmountRub,
            strategyForm.brokerType,
            hoursFrom,
            hoursTo,
            weekdaysMask,
            pipelineMode,
            universeMode,
            fixedTickersText,
            historicalEnabled,
            historicalInterval,
            historicalLookbackDays,
            historicalDailyAtMsk,
            paperRefreshMinutes,
            bybitTestnet,
            instrumentCategory,
            leverage,
            makerFeePct,
            takerFeePct,
            fundingMode,
            backtestExecution,
            backtestFeeModel,
            maintenanceMarginPct,
            cryptoUniverseMode,
            cryptoFilters,
            portfolioBrokerType,
            portfolioBybitTestnet,
            portfolioBybitAccountType,
            filters,
        ],
    )

    const commitBaselineFromForm = useCallback(() => {
        hydratingDraftRef.current = true
        setBaselineDraft(serializeDirtySnapshot(buildDirtySnapshotFromState()))
        setIsEditing(false)
        queueMicrotask(() => {
            hydratingDraftRef.current = false
        })
    }, [buildDirtySnapshotFromState])

    const applyUniverseStatusFromConfig = (cfg: Record<string, unknown>) => {
        const pool = hydrateCandidatePool(cfg)
        setCandidatePoolTickers(pool.tickers)
        setCandidatePoolAsOf(pool.asOf)
        const figis = Array.isArray(cfg.allowed_figis) ? (cfg.allowed_figis as string[]) : []
        setAllowedFigisCount(figis.length)
        const jobs = hydrateUniverseJobsState(cfg)
        setLastHistoricalRun(jobs.lastHistoricalScreeningAt)
        setLastPaperRun(jobs.lastPaperSelectionAt)
    }

    const refreshRobotInList = async (robotId: number) => {
        const refreshed = await robotService.getById(robotId)
        setRobots(prev => prev.map(r => (r.id === refreshed.id ? refreshed : r)))
        const cfg = (refreshed.config || {}) as Record<string, unknown>
        applyUniverseStatusFromConfig(cfg)
        return refreshed
    }

    const runHistoricalScreeningJob = async () => {
        if (!selectedRobot || isNewRobot) return
        setHistJobLoading(true)
        try {
            const res = await robotService.runHistoricalScreening(selectedRobot)
            if (res.skipped) {
                toast.show(res.message || 'П1 пропущен (уже выполнен сегодня или отключён)', 'info')
            } else {
                toast.show(
                    `П1: ${res.passed} из ${res.scanned} → candidate_pool ${res.tickers.length} тикеров`,
                    'success',
                )
            }
            setCandidatePoolTickers(res.tickers.map(t => String(t).toUpperCase()))
            if (res.as_of) setCandidatePoolAsOf(res.as_of)
            await refreshRobotInList(selectedRobot)
        } catch {
            toast.show('Не удалось запустить исторический скрининг (П1)', 'error')
        } finally {
            setHistJobLoading(false)
        }
    }

    const runPaperSelectionJob = async () => {
        if (!selectedRobot || isNewRobot) return
        setPaperJobLoading(true)
        try {
            const res = await robotService.runPaperSelection(selectedRobot)
            toast.show(
                `П2: ${res.accepted_tickers.length} тикеров → ${res.allowed_figis.length} FIGI` +
                    (res.candidate_pool_size ? ` (из пула ${res.candidate_pool_size})` : ''),
                'success',
            )
            setAllowedFigisCount(res.allowed_figis.length)
            await refreshRobotInList(selectedRobot)
        } catch {
            toast.show('Не удалось запустить отбор по снапшоту (П2)', 'error')
        } finally {
            setPaperJobLoading(false)
        }
    }

    const runCryptoScreeningJob = async () => {
        if (!selectedRobot || isNewRobot) return
        setCryptoScreeningLoading(true)
        try {
            const res = await robotService.runCryptoScreening(selectedRobot)
            if (res.skipped) {
                toast.show(res.message || 'Crypto-screening пропущен', 'info')
            } else {
                toast.show(`Crypto: ${res.accepted} из ${res.scanned} символов`, 'success')
            }
            setCryptoScreeningPreview({
                symbols: res.symbols,
                accepted: res.accepted,
                scanned: res.scanned,
                message: res.message,
            })
            if (res.symbols.length > 0) {
                setFixedTickersText(res.symbols.join(', '))
            }
            await refreshRobotInList(selectedRobot)
        } catch {
            toast.show('Не удалось запустить crypto-screening', 'error')
        } finally {
            setCryptoScreeningLoading(false)
        }
    }

    const migrateConfigV3 = async () => {
        if (!selectedRobot || isNewRobot) return
        setMigratingV3(true)
        try {
            const res = await robotService.migrateConfigV3(selectedRobot)
            const item = res.items.find(i => i.robot_id === selectedRobot)
            if (item?.updated) {
                toast.show(`Config v3: обновлён (profile ${item.schema_profile})`, 'success')
            } else {
                toast.show('Config уже v3', 'info')
            }
            await refreshRobotInList(selectedRobot)
        } catch {
            toast.show('Ошибка миграции config v3', 'error')
        } finally {
            setMigratingV3(false)
        }
    }

    const buildDraftSnapshot = (): DraftSnapshot => ({
        name: name.trim(),
        tokenId: Number(tokenId || 0),
        robotType,
        pollValue: Number(pollValue || 1),
        pollUnit,
        brokerCommissionRate: Number(strategyForm.brokerCommissionPct || 0),
        ndflRate: Number(strategyForm.ndflPct || 0),
        hoursFrom,
        hoursTo,
        weekdaysMask: Math.max(0, Math.min(127, Number(weekdaysMask || 0))),
        pipelineMode,
        universeMode,
        fixedTickersText,
        historicalEnabled,
        historicalInterval,
        historicalLookbackDays,
        historicalDailyAtMsk,
        paperRefreshMinutes,
        strategy: strategyForm.getDraft(),
        bybitTestnet,
        instrumentCategory,
        leverage,
        makerFeePct,
        takerFeePct,
        fundingMode,
        backtestExecution,
        backtestFeeModel,
        maintenanceMarginPct,
        cryptoUniverseMode,
        cryptoFilters: cryptoFilters.map(f => ({ type: f.type, value: f.value })),
        portfolioBrokerType,
        portfolioBybitTestnet,
        portfolioBybitAccountType,
        filters: filters.map(f => ({
            type: f.type,
            min: f.min != null ? Number(f.min) : undefined,
            max_percent: f.max_percent != null ? Number(f.max_percent) : undefined,
            min_percent: f.min_percent != null ? Number(f.min_percent) : undefined,
            period: f.period != null ? Number(f.period) : undefined,
            eq: f.eq != null ? String(f.eq) : undefined,
            direction: f.direction,
            max_steps: f.max_steps != null ? Number(f.max_steps) : undefined,
            min_ratio: f.min_ratio != null ? Number(f.min_ratio) : undefined,
            list: Array.isArray(f.list) ? f.list.map(x => String(x).toUpperCase()) : (f.list ?? null),
        })),
    })

    const applyDraft = (draft: DraftSnapshot) => {
        hydratingDraftRef.current = true
        setName(draft.name)
        setTokenId(draft.tokenId)
        setRobotType(draft.robotType)
        setPollValue(draft.pollValue)
        setPollUnit(draft.pollUnit)
        strategyForm.applyDraft(draft.strategy)
        strategyForm.setBrokerCommissionPct(draft.brokerCommissionRate)
        strategyForm.setNdflPct(draft.ndflRate)
        setHoursFrom(draft.hoursFrom)
        setHoursTo(draft.hoursTo)
        setWeekdaysMask(draft.weekdaysMask)
        setPipelineMode(draft.pipelineMode)
        setUniverseMode(draft.universeMode)
        setFixedTickersText(draft.fixedTickersText)
        setHistoricalEnabled(draft.historicalEnabled ?? true)
        setHistoricalInterval(draft.historicalInterval ?? 'CANDLE_INTERVAL_10_MIN')
        setHistoricalLookbackDays(draft.historicalLookbackDays ?? 14)
        setHistoricalDailyAtMsk(draft.historicalDailyAtMsk ?? '07:00')
        setPaperRefreshMinutes(draft.paperRefreshMinutes ?? 30)
        setBybitTestnet(draft.bybitTestnet ?? false)
        setInstrumentCategory(draft.instrumentCategory ?? 'linear')
        setLeverage(draft.leverage ?? 5)
        setMakerFeePct(draft.makerFeePct ?? 0.01)
        setTakerFeePct(draft.takerFeePct ?? 0.06)
        setFundingMode(draft.fundingMode ?? 'historical')
        setBacktestExecution(draft.backtestExecution ?? 'market_taker')
        setBacktestFeeModel(draft.backtestFeeModel ?? 'maker_taker')
        setMaintenanceMarginPct(draft.maintenanceMarginPct ?? 0.5)
        setCryptoUniverseMode(draft.cryptoUniverseMode ?? 'fixed')
        setCryptoFilters(
            ensureCompleteCryptoFilters(
                (draft.cryptoFilters ?? []).map((f, idx) => ({
                    id: `hydrate-${f.type}-${idx}`,
                    type: f.type,
                    value: f.value,
                })),
            ),
        )
        setPortfolioBrokerType(draft.portfolioBrokerType ?? 'tinvest')
        setPortfolioBybitTestnet(draft.portfolioBybitTestnet ?? true)
        setPortfolioBybitAccountType(draft.portfolioBybitAccountType ?? 'UNIFIED')
        setFilters(
            draft.filters.map((f, idx) => ({
                id: `${f.type}-${idx}-${Date.now()}`,
                type: f.type,
                min: f.min,
                max_percent: f.max_percent,
                min_percent: f.min_percent,
                period: f.period,
                eq: f.eq,
                direction: f.direction,
                max_steps: f.max_steps,
                min_ratio: f.min_ratio,
                list: f.list ?? null,
            })),
        )
        setPreview(null)
        setBaselineDraft(serializeDirtySnapshot(dirtySnapshotFromDraft(draft)))
        setIsEditing(false)
        queueMicrotask(() => {
            hydratingDraftRef.current = false
        })
    }

    const loadReferenceData = async () => {
        try {
            const keysResp = await api.post('/apikey/data', {})
            const keys = (keysResp.data?.keys || []) as ApiKeyItem[]
            setTokenCatalog(keys)
            setTokenOptions(
                keys.map(k => ({
                    value: String(k.id),
                    label: `${k.name || `Токен #${k.id}`} (${k.token_type?.typeName || 'TYPE'})`,
                })),
            )
            const robotTypesResp = await api.post('/dictionary/data', { tableName: 'ROBOT', columnName: 'TYPE' })
            const typeOptions = (Array.isArray(robotTypesResp.data) ? robotTypesResp.data : [])
                .map((x: any) => ({
                    value: String(x.numericValue ?? ''),
                    label: String(x.name ?? x.stringValue ?? ''),
                }))
                .filter((x: { value: string }) => x.value !== '')
            if (typeOptions.length > 0) {
                setRobotTypeOptions(typeOptions)
            }
            try {
                const defaults = await robotService.getTradingDefaults()
                tradingDefaultsRef.current = {
                    brokerPct: Number(defaults.broker_commission_rate || 0.0005) * 100,
                    ndflPct: Number(defaults.ndfl_rate || 0.15) * 100,
                }
            } catch {
                // Keep local defaults if endpoint unavailable.
            }
        } catch {
            toast.show('Не удалось загрузить справочники', 'error')
        }
    }

    const loadRobots = async (showLoader = true) => {
        if (showLoader) setLoading(true)
        try {
            const res = await robotService.list(200, 0)
            setRobots(res.items)
            if (!selectedRobot && res.items.length > 0 && !isNewRobot) {
                setSelectedRobot(res.items[0].id)
            }
            return res.items
        } catch {
            toast.show('Не удалось загрузить роботов', 'error')
            return []
        } finally {
            if (showLoader) setLoading(false)
        }
    }

    const openRobotForEdit = (robotId: number) => {
        hydratingDraftRef.current = true
        setIsEditing(false)
        setBaselineDraft('')
        setIsNewRobot(false)
        setSelectedRobot(robotId)
        setSearchParams({ robotId: String(robotId) })
    }

    const startCreateRobot = () => {
        setIsNewRobot(true)
        setSelectedRobot(null)
        setSearchParams({})
        strategyForm.resetToDefaults()
        if (tradingDefaultsRef.current) {
            strategyForm.applyCommissionDefaults(
                tradingDefaultsRef.current.brokerPct,
                tradingDefaultsRef.current.ndflPct,
            )
        }
        applyDraft({
            name: '',
            tokenId: 0,
            robotType: 2,
            pollValue: 5,
            pollUnit: 'minutes',
            hoursFrom: '10:00',
            hoursTo: '18:45',
            brokerCommissionRate: strategyForm.brokerCommissionPct || 0.05,
            ndflRate: strategyForm.ndflPct || 15,
            weekdaysMask: 31,
            pipelineMode: 'ALL',
            universeMode: 'dms_pipeline',
            fixedTickersText: '',
            historicalEnabled: true,
            historicalInterval: 'CANDLE_INTERVAL_10_MIN',
            historicalLookbackDays: 14,
            historicalDailyAtMsk: '07:00',
            paperRefreshMinutes: 30,
            bybitTestnet: false,
            instrumentCategory: 'linear',
            leverage: 1,
            makerFeePct: 0.01,
            takerFeePct: 0.06,
            fundingMode: 'historical',
            backtestExecution: 'market_taker',
            backtestFeeModel: 'maker_taker',
            maintenanceMarginPct: 0.5,
            cryptoUniverseMode: 'fixed',
            cryptoFilters: createDefaultCryptoScreeningFilters().map(f => ({ type: f.type, value: f.value })),
            portfolioBrokerType: 'tinvest',
            portfolioBybitTestnet: true,
            portfolioBybitAccountType: 'UNIFIED',
            strategy: strategyForm.getDraft(),
            filters: DEFAULT_PIPELINE_FILTERS,
        })
        setIsEditing(true)
    }

    const upsertRobotInList = useCallback((robot: Robot) => {
        setRobots(prev => prev.map(r => (r.id === robot.id ? robot : r)))
    }, [])

    const toggleRobotStatus = async (robot: Robot) => {
        const nextStatus = robot.status === 1 ? 2 : 1
        try {
            const updated = await robotService.changeStatus(robot.id, nextStatus)
            upsertRobotInList(updated)
            toast.show(nextStatus === 1 ? 'Робот запущен' : 'Робот остановлен', 'success')
        } catch {
            toast.show('Не удалось изменить статус робота', 'error')
        }
    }

    const deleteRobot = async (robot: Robot) => {
        if (!window.confirm(`Удалить робота «${robot.name}»?`)) return
        try {
            await robotService.deleteRobot(robot.id)
            if (selectedRobot === robot.id) {
                startCreateRobot()
            }
            toast.show('Робот удален', 'success')
            await loadRobots()
        } catch {
            toast.show('Не удалось удалить робота', 'error')
        }
    }

    const duplicateRobot = async () => {
        if (!selectedRobotEntity) return
        const defaultName = `${selectedRobotEntity.name} (copy)`
        const name = window.prompt('Имя копии робота', defaultName)
        if (!name?.trim()) return

        let brokerType: string | undefined
        if (Number(selectedRobotEntity.type) === 2) {
            const currentBroker = String(
                (selectedRobotEntity.config as { broker_type?: string } | null)?.broker_type || 'tinvest',
            ).toLowerCase()
            if (currentBroker === 'tinvest') {
                const migrateCrypto = window.confirm(
                    'Дублировать как ByBit (crypto)?\n\nOK — копия с broker_type=bybit (universe сброшен).\nОтмена — тот же брокер T-Invest.',
                )
                if (migrateCrypto) brokerType = 'bybit'
            } else if (currentBroker === 'bybit') {
                const migrateMoex = window.confirm(
                    'Дублировать как T-Invest (MOEX)?\n\nOK — копия с broker_type=tinvest.\nОтмена — тот же брокер ByBit.',
                )
                if (migrateMoex) brokerType = 'tinvest'
            }
        }

        setDuplicating(true)
        try {
            const created = await robotService.duplicate({
                source_robot_id: selectedRobotEntity.id,
                name: name.trim(),
                broker_type: brokerType,
                token_id: tokenId > 0 ? tokenId : undefined,
            })
            toast.show(`Робот «${created.name}» создан`, 'success')
            await loadRobots(false)
            openRobotForEdit(created.id)
        } catch {
            toast.show('Не удалось дублировать робота', 'error')
        } finally {
            setDuplicating(false)
        }
    }

    useEffect(() => {
        const boot = async () => {
            await Promise.all([
                loadReferenceData(),
                loadRobots(true),
            ])
        }
        boot()
    }, [])

    useEffect(() => {
        const loadOne = async () => {
            if (!selectedRobot || isNewRobot) return
            if (skipNextLoadOneRef.current === selectedRobot) {
                skipNextLoadOneRef.current = null
                return
            }
            try {
                const r = await robotService.getById(selectedRobot)
                const cfg = (r.config || {}) as Record<string, unknown>
                const histState = hydrateHistoricalScreening(cfg)
                const paperState = hydratePaperSelection(cfg)
                const pipeline = (cfg.pipeline || {}) as Record<string, unknown>
                const filters: any[] = [
                    ...histState.filters,
                    ...paperState.filters,
                ]
                if (!filters.length && Array.isArray(pipeline.filters)) {
                    filters.push(...(pipeline.filters as any[]))
                }
                const schedule = (r as any).schedule || null
                const isTradingRobot = Number(r.type) === 2
                const resolvedPoll = resolvePollMinutesFromRobot(
                    schedule,
                    cfg,
                    isTradingRobot ? 2 : 1,
                )
                const startCfg = toTime(String(cfg?.risk?.trading_hours_start || '').replace(' MSK', ''))
                const endCfg = toTime(String(cfg?.risk?.trading_hours_end || '').replace(' MSK', ''))
                const startSch = toTime(schedule?.start_time)
                const endSch = toTime(schedule?.end_time)
                const resolvedStart = startCfg ?? startSch ?? '10:00'
                const resolvedEnd = endCfg ?? endSch ?? '18:45'
                const weekdaysCfg = cfg?.risk?.allowed_weekdays != null ? Number(cfg.risk.allowed_weekdays) : null
                const weekdaysSch = schedule?.weekdays != null ? Number(schedule.weekdays) : null
                const resolvedWeekdays = weekdaysCfg ?? weekdaysSch ?? 31
                const uiUniverseMode =
                    paperState.universeMode === 'dms_pipeline' ? 'tqbr_scan' : paperState.universeMode
                const normalized: Array<DraftSnapshot['filters'][number]> = filters
                    .filter(f => ['security_status', 'trading_status', 'allowed_tickers', 'volume', 'num_trades', 'gap', 'spread', 'atr', 'capitalization', 'min_step_ratio', 'excluded_tickers', 'exclude_tickers', 'turnover', 'gap_retention', 'price_vs_open', 'opening_range'].includes(String(f?.type)))
                    .map((f) => ({
                        type: (f.type === 'exclude_tickers' ? 'excluded_tickers' : f.type) as PipelineFilterType,
                        min: f.min != null ? Number(f.min) : undefined,
                        max_percent: f.max_percent != null ? Number(f.max_percent) : undefined,
                        min_percent: f.min_percent != null ? Number(f.min_percent) : undefined,
                        period: f.period != null ? Number(f.period) : undefined,
                        eq: f.eq != null ? String(f.eq) : undefined,
                        direction: f.direction === 'UP_ONLY' || f.direction === 'DOWN_ONLY' ? f.direction : 'BOTH',
                        max_steps: f.max_steps != null ? Number(f.max_steps) : undefined,
                        min_ratio: f.min_ratio != null ? Number(f.min_ratio) : undefined,
                        list: Array.isArray(f.list) ? f.list.map((x: any) => String(x).toUpperCase()) : f.list ?? null,
                    }))
                const portfolioFields = portfolioDefaultsFromConfig(cfg)
                if (isTradingRobot) {
                    strategyForm.hydrateFromConfig(cfg as Record<string, unknown>)
                }
                const broker = brokerFromTokenType(
                    r.token ? { type: r.token.type, typeName: r.token.typeName } : undefined,
                )
                strategyForm.setBrokerType(broker)
                let cryptoFields: Pick<
                    DraftSnapshot,
                    | 'bybitTestnet'
                    | 'instrumentCategory'
                    | 'leverage'
                    | 'makerFeePct'
                    | 'takerFeePct'
                    | 'fundingMode'
                    | 'backtestExecution'
                    | 'backtestFeeModel'
                    | 'maintenanceMarginPct'
                    | 'cryptoUniverseMode'
                    | 'cryptoFilters'
                > = {
                    bybitTestnet: false,
                    instrumentCategory: 'linear',
                    leverage: 1,
                    makerFeePct: 0.01,
                    takerFeePct: 0.06,
                    fundingMode: 'historical',
                    backtestExecution: 'market_taker',
                    backtestFeeModel: 'maker_taker',
                    maintenanceMarginPct: 0.5,
                    cryptoUniverseMode: 'fixed',
                    cryptoFilters: createDefaultCryptoScreeningFilters().map(f => ({ type: f.type, value: f.value })),
                }
                let resolvedFixedTickers = formatFixedTickers(paperState.fixedTickers)
                if (isCryptoBroker(broker)) {
                    const crypto = cryptoDefaultsFromConfig(cfg)
                    cryptoFields = {
                        bybitTestnet: false,
                        instrumentCategory: crypto.instrumentCategory,
                        leverage: crypto.leverage,
                        makerFeePct: crypto.makerFeePct,
                        takerFeePct: crypto.takerFeePct,
                        fundingMode: crypto.fundingMode,
                        backtestExecution: crypto.backtestExecution ?? 'market_taker',
                        backtestFeeModel: crypto.backtestFeeModel ?? 'maker_taker',
                        maintenanceMarginPct: crypto.maintenanceMarginPct ?? 0.5,
                        cryptoUniverseMode: crypto.cryptoUniverseMode,
                        cryptoFilters: ensureCompleteCryptoFilters(
                            cryptoFiltersFromFields({
                            cryptoMinVolume24hUsd: crypto.cryptoMinVolume24hUsd,
                            cryptoMinLastPrice: crypto.cryptoMinLastPrice,
                            cryptoMaxSpreadBps: crypto.cryptoMaxSpreadBps,
                            cryptoMaxFundingRatePct: crypto.cryptoMaxFundingRatePct,
                            cryptoMinFundingRatePct: crypto.cryptoMinFundingRatePct,
                            cryptoMinOpenInterestUsd: crypto.cryptoMinOpenInterestUsd,
                            cryptoMinLsr: crypto.cryptoMinLsr,
                            cryptoMaxLsr: crypto.cryptoMaxLsr,
                            cryptoMinRvol: crypto.cryptoMinRvol,
                            cryptoMinAtrPercent: crypto.cryptoMinAtrPercent,
                            cryptoMaxAtrPercent: crypto.cryptoMaxAtrPercent,
                            cryptoLookbackDays: crypto.cryptoLookbackDays,
                            cryptoFundingLookbackHours: crypto.cryptoFundingLookbackHours,
                            cryptoRefreshEveryMinutes: crypto.cryptoRefreshEveryMinutes,
                        }),
                        ),
                    }
                    const symbols = Array.isArray(cfg.allowed_symbols)
                        ? (cfg.allowed_symbols as string[])
                        : Array.isArray(cfg.instruments)
                          ? (cfg.instruments as string[])
                          : Array.isArray(cfg.fixed_tickers)
                            ? (cfg.fixed_tickers as string[])
                            : paperState.fixedTickers
                    resolvedFixedTickers = formatFixedTickers(symbols)
                }
                if (isEditingRef.current) {
                    return
                }
                applyDraft({
                    name: r.name || '',
                    tokenId: Number(r.token?.id || 0),
                    robotType: (Number(r.type) === 1 ? 1 : 2) as 1 | 2,
                    pollValue: resolvedPoll,
                    pollUnit: 'minutes',
                    brokerCommissionRate:
                        Number(
                            cfg?.costs?.broker_commission_rate != null
                                ? cfg.costs.broker_commission_rate
                                : strategyForm.brokerCommissionPct / 100 || 0.0005,
                        ) * 100,
                    ndflRate:
                        Number(cfg?.costs?.ndfl_rate != null ? cfg.costs.ndfl_rate : strategyForm.ndflPct / 100 || 0.15) * 100,
                    hoursFrom: resolvedStart,
                    hoursTo: resolvedEnd,
                    weekdaysMask: resolvedWeekdays,
                    pipelineMode: paperState.mode,
                    universeMode: isCryptoBroker(broker) ? normalizeCryptoUniverseMode(cryptoFields.cryptoUniverseMode ?? 'fixed') : uiUniverseMode,
                    fixedTickersText: resolvedFixedTickers,
                    historicalEnabled: uiUniverseMode !== 'fixed' ? true : histState.enabled,
                    historicalInterval: normalizeSignalInterval(histState.interval),
                    historicalLookbackDays: histState.lookbackDays,
                    historicalDailyAtMsk: histState.dailyAtMsk,
                    paperRefreshMinutes: paperState.refreshMinutes,
                    strategy: strategyForm.getDraft(),
                    ...cryptoFields,
                    portfolioBrokerType: broker,
                    portfolioBybitTestnet: isTradingRobot ? true : portfolioFields.bybitTestnet,
                    portfolioBybitAccountType: isTradingRobot ? 'UNIFIED' : portfolioFields.bybitAccountType,
                    filters: normalized.length > 0 ? normalized : DEFAULT_PIPELINE_FILTERS,
                })
                applyUniverseStatusFromConfig(cfg)
            } catch {
                toast.show('Не удалось загрузить настройки выбранного робота', 'error')
            }
        }
        loadOne()
    }, [selectedRobot, isNewRobot])

    useEffect(() => {
        if (!selectedRobotEntity?.config) {
            setCandidatePoolTickers([])
            setCandidatePoolAsOf(null)
            setAllowedFigisCount(0)
            setLastHistoricalRun(null)
            setLastPaperRun(null)
            return
        }
        applyUniverseStatusFromConfig((selectedRobotEntity.config || {}) as Record<string, unknown>)
    }, [selectedRobotEntity?.id, selectedRobotEntity?.config])

    useEffect(() => {
        if (hydratingDraftRef.current) return
        if (!baselineDraft) return
        const current = serializeDirtySnapshot(buildDirtySnapshotFromState())
        setIsEditing(current !== baselineDraft)
    }, [
        buildDirtySnapshotFromState,
        name,
        tokenId,
        robotType,
        pollValue,
        pollUnit,
        strategyForm.brokerCommissionPct,
        strategyForm.ndflPct,
        strategyForm.strategy,
        strategyForm.capital,
        strategyForm.strategyParams,
        hoursFrom,
        hoursTo,
        weekdaysMask,
        pipelineMode,
        universeMode,
        fixedTickersText,
        historicalEnabled,
        historicalInterval,
        historicalLookbackDays,
        historicalDailyAtMsk,
        paperRefreshMinutes,
        bybitTestnet,
        instrumentCategory,
        leverage,
        makerFeePct,
        takerFeePct,
        fundingMode,
        backtestExecution,
        backtestFeeModel,
        maintenanceMarginPct,
        cryptoUniverseMode,
        cryptoFilters,
        portfolioBrokerType,
        portfolioBybitTestnet,
        portfolioBybitAccountType,
        filters,
        baselineDraft,
    ])

    useEffect(() => {
        isEditingRef.current = isEditing
    }, [isEditing])

    useEffect(() => {
        setActiveStage('general')
    }, [selectedRobot, isNewRobot])

    useEffect(() => {
        if (robotType !== 2 && activeStage !== 'general') {
            setActiveStage('general')
        }
        if (!isMoexType2Tinvest && !isCrypto && marketProfile !== 'moex' && (activeStage === 'p1' || activeStage === 'p2')) {
            setActiveStage('p3')
        }
    }, [robotType, isMoexType2Tinvest, isCrypto, marketProfile, activeStage])

    const handleUniverseModeChange = (raw: unknown) => {
        const mode = normalizeUniverseMode(raw)
        const uiMode = mode === 'dms_pipeline' ? 'tqbr_scan' : mode
        setUniverseMode(uiMode)
        setHistoricalEnabled(uiMode !== 'fixed')
    }

    const toTime = (raw: any): string | null => {
        if (!raw) return null
        const s = String(raw)
        const hhmm = s.match(/(\d{2}):(\d{2})/)
        return hhmm ? `${hhmm[1]}:${hhmm[2]}` : null
    }

    const buildTradingFormSnapshot = () => {
        const session = tradingHoursFromSchedule(hoursFrom, hoursTo, weekdaysMask)
        return {
            strategy: strategyForm.strategy,
            strategyParams: strategyForm.strategyParams,
            interval: strategyForm.interval,
            capital: strategyForm.capital,
            brokerType: strategyForm.brokerType,
            stopLossPct: strategyForm.stopLossPct,
            takeProfitPct: strategyForm.takeProfitPct,
            maxPositionPct: strategyForm.maxPositionPct,
            maxPositionRub: strategyForm.maxPositionRub,
            maxDailyLoss: strategyForm.maxDailyLoss,
            minTradeAmountRub: strategyForm.minTradeAmountRub,
            brokerCommissionPct: strategyForm.brokerCommissionPct,
            ndflPct: strategyForm.ndflPct,
            pipelineMode,
            filters: filters as TestingPipelineFilter[],
            universeMode,
            fixedTickers: parseFixedTickersInput(fixedTickersText),
            universeRefreshMinutes: paperRefreshMinutes,
            historicalEnabled,
            historicalInterval,
            historicalLookbackDays,
            historicalDailyAtMsk,
            bybitTestnet: false,
            instrumentCategory,
            leverage,
            makerFeePct,
            takerFeePct,
            fundingMode,
            backtestExecution,
            backtestFeeModel,
            maintenanceMarginPct,
            cryptoUniverseMode,
            slippagePct: defaultSlippagePct('crypto'),
            ...cryptoFieldsFromFilters(cryptoFilters),
            ...session,
        }
    }

    const buildPortfolioFormSnapshot = () => ({
        brokerType: portfolioBrokerType,
        bybitTestnet: portfolioBybitTestnet,
        bybitAccountType: portfolioBybitAccountType,
    })

    const buildFullTradingConfig = () => {
        const cfg = (selectedRobotEntity?.config || {}) as Record<string, unknown>
        const existingFigis = Array.isArray(cfg.allowed_figis) ? (cfg.allowed_figis as string[]) : []
        const snapshot = {
            ...buildTradingFormSnapshot(),
            preserveAllowedFigis: existingFigis,
        }
        const profile = resolveSchemaProfileFromDraft(robotType, strategyForm.brokerType, cfg)
        const patch =
            marketProfile === 'crypto'
                ? buildCryptoTradingRobotConfig(snapshot)
                : profile === 'type2_tinvest'
                  ? buildMoexConfig(snapshot)
                  : buildTradingRobotConfig(snapshot)
        if (cfg.instrument_map) {
            patch.instrument_map = cfg.instrument_map as Record<string, unknown>
        }
        return patch
    }

    const buildSchedulePatch = () =>
        buildTradingRobotSchedulePatch({
            strategy: strategyForm.strategy,
            strategyParams: strategyForm.strategyParams,
            interval: strategyForm.interval,
            capital: strategyForm.capital,
            brokerType: strategyForm.brokerType,
            stopLossPct: strategyForm.stopLossPct,
            takeProfitPct: strategyForm.takeProfitPct,
            maxPositionPct: strategyForm.maxPositionPct,
            maxPositionRub: strategyForm.maxPositionRub,
            maxDailyLoss: strategyForm.maxDailyLoss,
            minTradeAmountRub: strategyForm.minTradeAmountRub,
            brokerCommissionPct: strategyForm.brokerCommissionPct,
            ndflPct: strategyForm.ndflPct,
            pipelineMode,
            filters: filters as TestingPipelineFilter[],
            pollValue,
            pollUnit,
            ...tradingHoursFromSchedule(hoursFrom, hoursTo, weekdaysMask),
        })

    const buildValidationInput = () => ({
        name,
        tokenId,
        robotType,
        hoursFrom,
        hoursTo,
        pollValue,
        pollUnit,
        strategy: strategyForm.strategy as RobotStrategyName,
        strategyParams: strategyForm.strategyParams as RobotStrategyParams,
        interval: strategyForm.interval,
        capital: strategyForm.capital,
        stopLossPct: strategyForm.stopLossPct,
        takeProfitPct: strategyForm.takeProfitPct,
        maxPositionPct: strategyForm.maxPositionPct,
        maxPositionRub: strategyForm.maxPositionRub,
        universeMode,
        fixedTickersText,
        isCrypto,
        cryptoUniverseMode,
    })

    const pipelineStages = useMemo(
        () =>
            derivePipelineStageStatuses({
                robotType,
                universeMode,
                historicalEnabled,
                candidatePoolCount: candidatePoolTickers.length,
                allowedFigisCount,
                lastHistoricalRun,
                lastPaperRun,
                strategy: strategyForm.strategy,
                interval: strategyForm.interval,
                tokenId,
                lastError: selectedRobotEntity?.last_error ?? null,
            }),
        [
            robotType,
            universeMode,
            historicalEnabled,
            candidatePoolTickers.length,
            allowedFigisCount,
            lastHistoricalRun,
            lastPaperRun,
            strategyForm.strategy,
            strategyForm.interval,
            tokenId,
            selectedRobotEntity?.last_error,
        ],
    )

    const allowedFigisPreview = useMemo(() => {
        const cfg = (selectedRobotEntity?.config || {}) as Record<string, unknown>
        const figis = Array.isArray(cfg.allowed_figis) ? (cfg.allowed_figis as string[]) : []
        return figis.map(f => String(f).toUpperCase())
    }, [selectedRobotEntity?.config])

    const allowedSymbolsPreview = useMemo(() => {
        const cfg = (selectedRobotEntity?.config || {}) as Record<string, unknown>
        const symbols = Array.isArray(cfg.allowed_symbols)
            ? (cfg.allowed_symbols as string[])
            : Array.isArray(cfg.instruments)
              ? (cfg.instruments as string[])
              : []
        return symbols.map(s => String(s).toUpperCase())
    }, [selectedRobotEntity?.config])

    const pipelineVisualizerNodes = useMemo(
        () => derivePipelineVisualizerNodes({ robotType, marketProfile }),
        [robotType, marketProfile],
    )

    const save = async (): Promise<boolean> => {
        if (!name.trim()) {
            toast.show('Укажите название робота', 'error')
            return false
        }
        if (!tokenId) {
            toast.show('Выберите токен', 'error')
            return false
        }
        if (robotType === 2 && ((isCrypto && cryptoUniverseMode === 'fixed') || (!isCrypto && universeMode === 'fixed')) && !parseFixedTickersInput(fixedTickersText).length) {
            toast.show(
                isCrypto ? 'Укажите символы ByBit (например BTCUSDT)' : 'Укажите тикеры для режима «Фиксированный список»',
                'error',
            )
            return false
        }
        setSaving(true)
        try {
            let robotId = selectedRobot
            const creatingNew = isNewRobot
            const schedule =
                robotType === 2
                    ? buildSchedulePatch()
                    : buildPortfolioSchedulePatch({
                          pollValue,
                          pollUnit,
                          hoursFrom,
                          hoursTo,
                          weekdaysMask,
                      })
            if (isNewRobot) {
                const created = await robotService.create({
                    name: name.trim(),
                    token_id: tokenId,
                    type: robotType,
                    config:
                        robotType === 2
                            ? buildFullTradingConfig()
                            : buildPortfolioRobotConfig(buildPortfolioFormSnapshot()),
                    ...schedule,
                })
                robotId = created.id
                skipNextLoadOneRef.current = robotId
                setSelectedRobot(robotId)
                setIsNewRobot(false)
                setSearchParams({ robotId: String(robotId) })
                commitBaselineFromForm()
            } else {
                if (!robotId) {
                    throw new Error('robot id missing')
                }
                const patch: Record<string, any> = {
                    name: name.trim(),
                    token_id: tokenId,
                    type: robotType,
                }
                if (robotType === 2) {
                    patch.config = buildFullTradingConfig()
                    Object.assign(patch, schedule)
                } else {
                    patch.config = buildPortfolioRobotConfig(buildPortfolioFormSnapshot())
                    Object.assign(patch, schedule)
                }
                await robotService.updateRobot(robotId, patch)
            }
            if (!robotId) {
                throw new Error('robot id missing')
            }
            toast.show(creatingNew ? 'Робот создан и настроен' : 'Настройки робота сохранены', 'success')
            if (!creatingNew) {
                commitBaselineFromForm()
            }
            setCheckedIssues(null)
            await loadRobots(false)
            return true
        } catch (err: unknown) {
            if (isBrokerTypeConflictError(err)) {
                toast.show(BROKER_CHANGE_BLOCKED_MESSAGE, 'warning')
            } else {
                toast.show('Не удалось сохранить настройки робота', 'error')
            }
            return false
        } finally {
            setSaving(false)
        }
    }

    const runFullPipeline = useCallback(async () => {
        if (!selectedRobot || isNewRobot) return
        setPipelineRunning(true)
        try {
            if (universeMode !== 'fixed' && historicalEnabled) {
                await runHistoricalScreeningJob()
            }
            if (universeMode !== 'fixed') {
                await runPaperSelectionJob()
            }
            toast.show('Полный цикл П1→П2 завершён', 'success')
        } catch {
            toast.show('Ошибка при выполнении полного цикла', 'error')
        } finally {
            setPipelineRunning(false)
        }
    }, [selectedRobot, isNewRobot, universeMode, historicalEnabled])

    const runCheck = async (opts?: { quiet?: boolean }): Promise<boolean> => {
        setCheckLoading(true)
        const issues = collectIssues(buildValidationInput())
        try {
            if (isMoexType2Tinvest && !hasBlockingValidationIssues(issues)) {
                try {
                    const cfg = (selectedRobotEntity?.config || {}) as Record<string, unknown>
                    const existingFigis = Array.isArray(cfg.allowed_figis) ? (cfg.allowed_figis as string[]) : []
                    const config = buildMoexConfig({
                        ...buildTradingFormSnapshot(),
                        preserveAllowedFigis: existingFigis,
                    })
                    await robotService.validateConfig({
                        robot_type: 2,
                        broker_type: 'tinvest',
                        config,
                    })
                } catch (err: unknown) {
                    const ax = err as { response?: { data?: { detail?: unknown } } }
                    const detail = ax.response?.data?.detail ?? 'Ошибка валидации конфига на сервере'
                    issues.push({
                        id: 'server_validate',
                        severity: 'error',
                        field: 'config',
                        message: typeof detail === 'string' ? detail : JSON.stringify(detail),
                    })
                }
            }

            if (isMoexType2Tinvest && !isNewRobot && selectedRobot && universeMode !== 'fixed') {
                setPreviewLoading(true)
                try {
                    const snapshotFilters = filters.filter(f => !HISTORICAL_FILTER_TYPES.has(f.type))
                    const payloadFilters = snapshotFilters.map(f => ({
                        type: f.type,
                        min: f.min,
                        max_percent: f.max_percent,
                        min_percent: f.min_percent,
                        period: f.period,
                        eq: f.eq,
                        direction: f.direction,
                        max_steps: f.max_steps,
                        min_ratio: f.min_ratio,
                        list: f.list,
                    }))
                    const res = await robotService.previewDmsPipeline({
                        robot_id: selectedRobot,
                        board: 'TQBR',
                        filters: payloadFilters,
                        mode: pipelineMode,
                    })
                    setPreview(res)
                } catch {
                    issues.push({
                        id: 'preview_failed',
                        severity: 'error',
                        field: 'pipeline',
                        message: 'Не удалось выполнить тест фильтров П2 (preview)',
                    })
                } finally {
                    setPreviewLoading(false)
                }
            }

            setCheckedIssues(issues)
            const ok = !hasBlockingValidationIssues(issues)
            if (ok) {
                if (!opts?.quiet) {
                    toast.show(
                        issues.some(i => i.severity === 'warning')
                            ? 'Проверка пройдена с предупреждениями'
                            : 'Проверка пройдена',
                        issues.some(i => i.severity === 'warning') ? 'warning' : 'success',
                    )
                }
            } else {
                toast.show('Проверка не пройдена — см. список ошибок', 'error')
            }
            return ok
        } finally {
            setCheckLoading(false)
        }
    }

    const handleRun = async () => {
        if (isNewRobot || !selectedRobot) {
            toast.show('Сначала сохраните робота', 'warning')
            return
        }
        if (isEditing) {
            toast.show('Сначала сохраните изменения кнопкой «Сохранить»', 'warning')
            return
        }
        const ok = await runCheck({ quiet: true })
        if (!ok) return
        if (isMoexType2Tinvest && universeMode !== 'fixed') {
            await runFullPipeline()
        }
        if (selectedRobotEntity && selectedRobotEntity.status !== 1) {
            await toggleRobotStatus(selectedRobotEntity)
        }
    }

    const handleStop = async () => {
        if (!selectedRobotEntity || selectedRobotEntity.status !== 1) return
        await toggleRobotStatus(selectedRobotEntity)
    }

    const applyPreset = (preset: UniverseFilterPresetId) => {
        const config = MOEX_P2_SNAPSHOT_FILTER_PRESETS[preset]
        setPipelineMode(config.mode)
        const hist = filters.filter(f => HISTORICAL_FILTER_TYPES.has(f.type))
        const paper = config.filters.map((f, idx) => ({
            id: `${f.type}-${idx}-${Date.now()}`,
            ...f,
        }))
        setFilters([...hist, ...paper])
        setCheckedIssues(null)
        toast.show(`Пресет П2 «${preset === 'conservative' ? 'Консервативная' : preset === 'moderate' ? 'Умеренная' : 'Агрессивная'}» применён`, 'success')
    }

    const dirtyDraftKey = useMemo(() => {
        if (!isEditing) return ''
        return serializeDirtySnapshot(buildDirtySnapshotFromState())
    }, [
        isEditing,
        buildDirtySnapshotFromState,
        name,
        tokenId,
        robotType,
        pollValue,
        pollUnit,
        strategyForm.brokerCommissionPct,
        strategyForm.ndflPct,
        strategyForm.strategy,
        strategyForm.capital,
        strategyForm.strategyParams,
        strategyForm.interval,
        strategyForm.stopLossPct,
        strategyForm.takeProfitPct,
        strategyForm.maxPositionPct,
        strategyForm.maxPositionRub,
        strategyForm.maxDailyLoss,
        strategyForm.minTradeAmountRub,
        hoursFrom,
        hoursTo,
        weekdaysMask,
        pipelineMode,
        universeMode,
        fixedTickersText,
        historicalEnabled,
        historicalInterval,
        historicalLookbackDays,
        historicalDailyAtMsk,
        paperRefreshMinutes,
        filters,
    ])

    useEffect(() => {
        if (!dirtyDraftKey) return
        setCheckedIssues(null)
    }, [dirtyDraftKey])

    if (loading) {
        return (
            <div className="page" data-page="robots">
                <RobotsHero onCreate={undefined} />
                <div className="dashboard-layout robots-page-layout" aria-busy="true" aria-label="Загрузка роботов">
                    <div className="robots-workspace">
                        <aside className="robots-workspace__sidebar">
                            <Card className="robots-list-card portfolio-panel">
                                <div className="dashboard-totals-card__head">
                                    <h3 className="dashboard-panel-title">Флот</h3>
                                </div>
                                <div className="ops-loader" style={{ minHeight: 120 }}>
                                    <div className="soft-loading-bar" />
                                </div>
                            </Card>
                        </aside>
                        <div className="robots-workspace__main">
                            <Card className="portfolio-panel robots-editor-empty">
                                <div className="ops-loader" style={{ minHeight: 160 }}>
                                    <div className="soft-loading-bar" />
                                </div>
                            </Card>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    const isGrainSeed = strategyForm.strategy === 'grain_seed'
    const pollMinuteOptions = pollMinuteOptionsForRobotType(robotType)
    const pollSelectMinutes = snapPollMinutes(pollValue, pollMinuteOptions)
    const hasEditor = isNewRobot || Boolean(selectedRobot)

    const syncAtrFilterFromParams = (period: number, minPercent: number) => {
        setFilters(prev => {
            if (!prev.some(f => f.type === 'atr')) return prev
            return prev.map(f =>
                f.type === 'atr' ? { ...f, period, min_percent: minPercent } : f,
            )
        })
    }

    return (
        <div className="page" data-page="robots">
            <RobotsHero onCreate={startCreateRobot} />

            <div className="dashboard-layout robots-page-layout">
            <div className="robots-workspace">
                <aside className="robots-workspace__sidebar">
            <Card className="robots-list-card portfolio-panel">
                <div className="dashboard-totals-card__head">
                    <h3 className="dashboard-panel-title">Флот</h3>
                </div>
                {robots.length === 0 ? (
                    <div className="robots-empty-fleet">
                        <RobotIllustration size={96} />
                        <p className="dashboard-empty">Роботов пока нет. Создайте первого.</p>
                        <Button variant="primary" size="sm" onClick={startCreateRobot}>
                            + Создать робота
                        </Button>
                    </div>
                ) : (
                    <div className="robots-list-cards">
                        {robots.map(r => {
                            const hasError = Boolean(r.last_error)
                            const headTone = hasError
                                ? 'error'
                                : r.status === 1
                                  ? 'active'
                                  : 'inactive'
                            return (
                            <div
                                key={r.id}
                                role="button"
                                tabIndex={0}
                                className={`robots-list-item${!isNewRobot && selectedRobot === r.id ? ' robots-list-item--selected' : ''}${hasError ? ' robots-list-item--error' : ''}`}
                                onClick={() => openRobotForEdit(r.id)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                        e.preventDefault()
                                        openRobotForEdit(r.id)
                                    }
                                }}
                            >
                                <div className={`robots-list-item__head robots-list-item__head--${headTone}`}>
                                    <strong>{r.name}</strong>
                                    <span className="robots-list-item__open">Открыт →</span>
                                </div>
                                <div className="robots-list-item__meta mono">
                                    {r.typeName}
                                    {r.statusName ? ` · ${r.statusName}` : ''}
                                </div>
                                {Number(r.type) === 2 && (
                                    <div className="robots-list-item__session" title={r.last_error || undefined}>
                                        {formatRobotSessionStatus(r, { noEmoji: true })}
                                    </div>
                                )}
                            </div>
                            )
                        })}
                    </div>
                )}
                {robots.length > 0 && (
                <Button
                    variant="primary"
                    size="sm"
                    className="robot-create-btn"
                    onClick={startCreateRobot}
                >
                    + Создать робота
                </Button>
                )}
            </Card>
                </aside>

                <div className="robots-workspace__main">
                    {!hasEditor ? (
                        <Card className="portfolio-panel robots-editor-empty">
                            <h3 className="dashboard-panel-title">Редактор</h3>
                            <p className="dashboard-empty">
                                Выберите робота слева или создайте нового, чтобы настроить pipeline и запуск.
                            </p>
                            <Button variant="ghost" size="sm" className="dashboard-hero__cfg" onClick={startCreateRobot}>
                                + Создать
                            </Button>
                        </Card>
                    ) : (
                    <>
                    <PipelineVisualizer
                        nodes={pipelineVisualizerNodes}
                        activeStage={activeStage}
                        onStageChange={setActiveStage}
                    />

                    <div className="step-editor-panel portfolio-panel">
                        <header className="step-editor-panel__header">
                            <h2 className="step-editor-panel__title">
                                <span className="step-editor-panel__title-accent">{stagePanelTitle(activeStage, marketProfile)}</span>
                            </h2>
                            {robotType >= 1 && (
                                <span className="step-editor-panel__meta step-editor-panel__meta--profile">
                                    {marketProfileLabel(marketProfile)}
                                </span>
                            )}
                            {isMoexType2Tinvest && activeStage === 'p2' && universeMode !== 'fixed' && (
                                <span className="step-editor-panel__meta">Universe: MOEX + DMS</span>
                            )}
                            {isCrypto && activeStage === 'p2' && cryptoUniverseMode === 'auto' && (
                                <span className="step-editor-panel__meta">Universe: ByBit screening</span>
                            )}
                        </header>

            {activeStage === 'general' && (
            <>
            <div className="form-group">
                <label className="form-label">Название робота</label>
                <input className="form-input cyber-input" value={name} onChange={e => setName(e.target.value)} />
                {fieldIssues(checkedIssues, 'name').map(issue => (
                    <p key={issue.id} className="field-inline-error">{issue.message}</p>
                ))}
            </div>
            <div className="form-row">
                <div className="form-group">
                    <label className="form-label">Токен</label>
                    <div className="cyber-select-wrap">
                    <Select
                        options={[{ value: '0', label: 'Выберите токен' }, ...tokenOptions]}
                        value={String(tokenId || 0)}
                        onChange={v => {
                            const next = Number(v || 0)
                            setTokenId(next)
                            const broker = brokerFromTokenId(next, tokenCatalog)
                            if (broker) syncBrokerFromToken(broker, true)
                        }}
                    />
                    </div>
                    {fieldIssues(checkedIssues, 'token').map(issue => (
                        <p key={issue.id} className="field-inline-error">{issue.message}</p>
                    ))}
                </div>
                <div className="form-group">
                    <label className="form-label">Брокер</label>
                    <div className="cyber-select-wrap">
                        <div className="gin-select gin-select--readonly" aria-readonly="true">
                            <div className="gin-select__trigger">
                                <span className="gin-select__value">
                                    {brokerLabelFromToken(tokenId, tokenCatalog)}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="step-editor-panel__subsection">
                <h4 className="card__subsection-title">Расписание</h4>
                <WeekdaysMaskField value={weekdaysMask} onChange={setWeekdaysMask} />
                <div className="form-row schedule-subsection__timing">
                    <div className="form-group">
                        <label className="form-label">
                            {robotType === 2 ? 'Цикл робота (мин)' : 'Частота опроса (мин)'}
                            {robotType === 2 && (
                                <FormLabelTooltip text="Как часто робот проверяет рынок и сигналы." />
                            )}
                        </label>
                        <div className="cyber-select-wrap">
                            <Select
                                options={pollMinuteOptions.map(v => ({ value: String(v), label: `${v} мин` }))}
                                value={String(pollSelectMinutes)}
                                onChange={v => setPollValue(Number(v || (isPortfolioRobot ? 60 : 5)))}
                            />
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label">
                            Часы работы
                            <FormLabelTooltip text="Торговая сессия по МСК. Для crypto 24/7 можно оставить 00:00–23:59." />
                        </label>
                        <div className="schedule-hours-range">
                            <input
                                className="form-input cyber-input"
                                type="time"
                                value={hoursFrom}
                                onChange={e => setHoursFrom(e.target.value)}
                                aria-label="Часы работы, начало"
                            />
                            <span className="schedule-hours-range__sep" aria-hidden>
                                —
                            </span>
                            <input
                                className="form-input cyber-input"
                                type="time"
                                value={hoursTo}
                                onChange={e => setHoursTo(e.target.value)}
                                aria-label="Часы работы, окончание"
                            />
                        </div>
                    </div>
                </div>
                {fieldIssues(checkedIssues, 'schedule').map(issue => (
                    <p key={issue.id} className="field-inline-error">{issue.message}</p>
                ))}
            </div>
            </>
            )}

            {activeStage === 'p1' && isCrypto && (
                <CryptoUniverseConfigurator
                    stage="p1"
                    cryptoUniverseMode={cryptoUniverseMode}
                    onCryptoUniverseModeChange={setCryptoUniverseMode}
                    fixedTickersText={fixedTickersText}
                    onFixedTickersTextChange={setFixedTickersText}
                    cryptoFilters={cryptoFilters}
                    onCryptoFiltersChange={setCryptoFilters}
                    universeFieldIssues={checkedIssues ?? undefined}
                    onConfigDirty={() => setIsEditing(true)}
                />
            )}

            {activeStage === 'p1' && isMoexType2Tinvest && (
                <MoexConfigurator
                    stage="p1"
                    universeMode={universeMode}
                    onUniverseModeChange={handleUniverseModeChange}
                    fixedTickersText={fixedTickersText}
                    onFixedTickersTextChange={setFixedTickersText}
                    historicalInterval={historicalInterval}
                    onHistoricalIntervalChange={setHistoricalInterval}
                    historicalLookbackDays={historicalLookbackDays}
                    onHistoricalLookbackDaysChange={setHistoricalLookbackDays}
                    historicalDailyAtMsk={historicalDailyAtMsk}
                    onHistoricalDailyAtMskChange={setHistoricalDailyAtMsk}
                    paperRefreshMinutes={paperRefreshMinutes}
                    onPaperRefreshMinutesChange={setPaperRefreshMinutes}
                    pipelineMode={pipelineMode}
                    onPipelineModeChange={setPipelineMode}
                    onApplyPreset={applyPreset}
                    filters={filters}
                    onFiltersChange={setFilters}
                    isGrainSeed={isGrainSeed}
                    strategyParams={strategyForm.strategyParams}
                    onStrategyParamChange={(key, value) => strategyForm.setStrategyParam(key, value)}
                    onAtrFilterSync={syncAtrFilterFromParams}
                    universeFieldIssues={checkedIssues ?? undefined}
                />
            )}

            {activeStage === 'p2' && isCrypto && (
                <CryptoUniverseConfigurator
                    stage="p2"
                    cryptoUniverseMode={cryptoUniverseMode}
                    onCryptoUniverseModeChange={setCryptoUniverseMode}
                    fixedTickersText={fixedTickersText}
                    onFixedTickersTextChange={setFixedTickersText}
                    cryptoFilters={cryptoFilters}
                    onCryptoFiltersChange={setCryptoFilters}
                    robotId={selectedRobot ?? undefined}
                    cryptoScreeningLoading={cryptoScreeningLoading}
                    onRunCryptoScreening={() => void runCryptoScreeningJob()}
                    screeningPreview={cryptoScreeningPreview}
                    allowedSymbols={allowedSymbolsPreview}
                    universeFieldIssues={checkedIssues ?? undefined}
                    onConfigDirty={() => setIsEditing(true)}
                />
            )}

            {activeStage === 'p2' && isMoexType2Tinvest && (
                <MoexConfigurator
                    stage="p2"
                    universeMode={universeMode}
                    onUniverseModeChange={handleUniverseModeChange}
                    fixedTickersText={fixedTickersText}
                    onFixedTickersTextChange={setFixedTickersText}
                    historicalInterval={historicalInterval}
                    onHistoricalIntervalChange={setHistoricalInterval}
                    historicalLookbackDays={historicalLookbackDays}
                    onHistoricalLookbackDaysChange={setHistoricalLookbackDays}
                    historicalDailyAtMsk={historicalDailyAtMsk}
                    onHistoricalDailyAtMskChange={setHistoricalDailyAtMsk}
                    paperRefreshMinutes={paperRefreshMinutes}
                    onPaperRefreshMinutesChange={setPaperRefreshMinutes}
                    pipelineMode={pipelineMode}
                    onPipelineModeChange={setPipelineMode}
                    onApplyPreset={applyPreset}
                    filters={filters}
                    onFiltersChange={setFilters}
                    isGrainSeed={isGrainSeed}
                    strategyParams={strategyForm.strategyParams}
                    onStrategyParamChange={(key, value) => strategyForm.setStrategyParam(key, value)}
                    onAtrFilterSync={syncAtrFilterFromParams}
                    preview={preview}
                    universeFieldIssues={checkedIssues ?? undefined}
                />
            )}

            {activeStage === 'p3' && robotType === 2 && (
                <>
                    {isCrypto ? (
                        <p className="form-hint">
                            Сигналы на live-свечах ByBit. Пул символов — на этапах отбора; здесь стратегия и фильтры
                            входа (ATR, спред, ADX).
                        </p>
                    ) : (
                        <p className="form-hint">
                            Свечи и индикаторы в реальном времени — T-Invest. Пул тикеров задаётся этапами поиска и
                            отбора.
                        </p>
                    )}
                    {!isCrypto && <PipelineStageBadges stages={pipelineStages.filter(s => s.id === 'p3')} />}
                    <div className="form-row">
                        <div className="form-group">
                            <label className="form-label">Стратегия</label>
                            <div className="cyber-select-wrap">
                                <Select
                                    options={strategyForm.strategyOptions}
                                    value={strategyForm.strategy}
                                    onChange={v => strategyForm.setStrategy(String(v || 'grain_seed'))}
                                />
                            </div>
                            <p className="field-hint-below">Алгоритм генерации торговых сигналов на live-свечах.</p>
                        </div>
                        <div className="form-group">
                            <label className="form-label">Брокер</label>
                            <div className="cyber-select-wrap">
                                <Select
                                    disabled
                                    options={[{ value: strategyForm.brokerType, label: brokerTypeLabel(strategyForm.brokerType) }]}
                                    value={strategyForm.brokerType}
                                    onChange={() => {}}
                                />
                            </div>
                            {!isNewRobot && (
                                <p className="field-hint-below">Брокер задаётся при создании робота и не меняется.</p>
                            )}
                        </div>
                    </div>
                    {fieldIssues(checkedIssues, 'strategy').map(issue => (
                        <p key={issue.id} className="field-inline-error">{issue.message}</p>
                    ))}
                    {isCrypto && (
                        <CollapsibleSection
                            title="Инструмент ByBit"
                            hint="Категория контракта и плечо (live без маржи — 1×)."
                            defaultOpen={false}
                        >
                            <CryptoBrokerConfigurator
                                instrumentCategory={instrumentCategory}
                                onInstrumentCategoryChange={setInstrumentCategory}
                                leverage={leverage}
                                onLeverageChange={setLeverage}
                                fixedTickersText={fixedTickersText}
                                leverageLocked
                                onConfigDirty={() => setIsEditing(true)}
                            />
                        </CollapsibleSection>
                    )}
                    {isCrypto ? (
                        <TestingStrategyParamsCard
                            embedded
                            grouped
                            className="robot-settings-p3-params"
                            sectionTitle="Параметры стратегии"
                            sectionHint="Фильтры входа отсекают шумные символы до генерации сигнала. Подстройте ATR и спред под текущий рынок."
                            market="crypto"
                            strategy={strategyForm.strategy}
                            params={strategyForm.strategyParams}
                            onParamChange={strategyForm.setStrategyParam}
                            onConfigDirty={() => setIsEditing(true)}
                            excludeFieldKeys={isGrainSeed ? GRAIN_SEED_CRYPTO_P3_EXCLUDE_FIELD_KEYS : undefined}
                        />
                    ) : (
                        <CollapsibleSection
                            title="Показать продвинутые настройки"
                            hint="MA fast/slow, Bollinger, интервал свечей T-Invest и прочие параметры стратегии."
                        >
                            <TestingStrategyParamsCard
                                embedded
                                className="robot-settings-p3-params"
                                sectionTitle="Параметры стратегии"
                                sectionHint="Интервал свечей — для WebSocket и расчёта сигналов (отдельно от MOEX на этапе поиска идей)."
                                market="moex"
                                strategy={strategyForm.strategy}
                                params={strategyForm.strategyParams}
                                onParamChange={strategyForm.setStrategyParam}
                                excludeFieldKeys={isGrainSeed ? GRAIN_SEED_EXCLUDED_P3_FIELD_KEYS : undefined}
                            />
                        </CollapsibleSection>
                    )}
                </>
            )}

            {activeStage === 'risk' && robotType === 2 && (
                <>
                    <p className="form-hint">Бюджет, лимиты позиции и защита капитала при исполнении сделок.</p>
                    {fieldIssues(checkedIssues, 'risk').map(issue => (
                        <p key={issue.id} className="field-inline-error">{issue.message}</p>
                    ))}
                    <TestingRiskParamsCard
                        className="cyber-form-card"
                        embedded
                        capital={strategyForm.capital}
                        onCapitalChange={strategyForm.setCapital}
                        brokerCommissionPct={strategyForm.brokerCommissionPct}
                        onBrokerCommissionPctChange={strategyForm.setBrokerCommissionPct}
                        ndflPct={strategyForm.ndflPct}
                        onNdflPctChange={strategyForm.setNdflPct}
                        stopLossPct={strategyForm.stopLossPct}
                        onStopLossPctChange={strategyForm.setStopLossPct}
                        takeProfitPct={strategyForm.takeProfitPct}
                        onTakeProfitPctChange={strategyForm.setTakeProfitPct}
                        maxPositionPct={strategyForm.maxPositionPct}
                        onMaxPositionPctChange={strategyForm.setMaxPositionPct}
                        maxPositionRub={strategyForm.maxPositionRub}
                        onMaxPositionRubChange={strategyForm.setMaxPositionRub}
                        maxDailyLoss={strategyForm.maxDailyLoss}
                        onMaxDailyLossChange={strategyForm.setMaxDailyLoss}
                        showMinTradeAmount
                        minTradeAmountRub={strategyForm.minTradeAmountRub}
                        onMinTradeAmountRubChange={strategyForm.setMinTradeAmountRub}
                        minTradeAmountLabel={isCrypto ? 'Мин. сумма сделки (USDT)' : 'Мин. сумма сделки (₽)'}
                        slippagePct={defaultSlippagePct(isCrypto ? 'crypto' : 'moex')}
                        onSlippagePctChange={() => {}}
                        executionLatencySec={0}
                        onExecutionLatencySecChange={() => {}}
                        maxDrawdownPct={20}
                        onMaxDrawdownPctChange={() => {}}
                        showCosts={!isCrypto}
                        capitalLabel={isCrypto ? 'Бюджет (USDT)' : 'Бюджет (₽)'}
                        maxPositionRubLabel={isCrypto ? 'Макс. позиция (USDT)' : 'Макс. позиция (₽)'}
                        showMinProfitTarget={isGrainSeed && !isCrypto}
                        minProfitTargetPct={
                            isGrainSeed ? Number(strategyForm.strategyParams.min_profit_target_pct ?? 0.35) : null
                        }
                        onMinProfitTargetPctChange={
                            isGrainSeed
                                ? v => strategyForm.setStrategyParam('min_profit_target_pct', v)
                                : undefined
                        }
                    />
                    {isCrypto && (
                        <CryptoCostsCard
                            className="cyber-form-card"
                            instrumentCategory={instrumentCategory}
                            fixedTickersText={fixedTickersText}
                            makerFeePct={makerFeePct}
                            onMakerFeePctChange={setMakerFeePct}
                            takerFeePct={takerFeePct}
                            onTakerFeePctChange={setTakerFeePct}
                            fundingMode={fundingMode}
                            onFundingModeChange={setFundingMode}
                            backtestExecution={backtestExecution}
                            onBacktestExecutionChange={setBacktestExecution}
                            backtestFeeModel={backtestFeeModel}
                            onBacktestFeeModelChange={setBacktestFeeModel}
                            onConfigDirty={() => setIsEditing(true)}
                        />
                    )}
                </>
            )}

                    </div>
                    </>
                    )}
                </div>

                {(isNewRobot || selectedRobot) && (
                    <RobotContextPanel
                        robot={selectedRobotEntity}
                        isNewRobot={isNewRobot}
                        robotType={robotType}
                        marketProfile={marketProfile}
                        universeMode={universeMode}
                        candidatePoolCount={candidatePoolTickers.length}
                        allowedFigisCount={allowedFigisCount}
                        allowedFigis={allowedFigisPreview}
                        lastPaperRun={lastPaperRun}
                        checkedIssues={checkedIssues}
                        preview={preview}
                        saving={saving}
                        checkLoading={checkLoading}
                        previewLoading={previewLoading}
                        pipelineRunning={pipelineRunning || histJobLoading || paperJobLoading}
                        onSave={() => void save()}
                        onRun={() => void handleRun()}
                        onStop={() => void handleStop()}
                        onDelete={() => selectedRobotEntity && void deleteRobot(selectedRobotEntity)}
                        onDuplicate={() => void duplicateRobot()}
                        duplicating={duplicating}
                        needsConfigV3Migrate={needsConfigV3Migrate}
                        onMigrateConfigV3={() => void migrateConfigV3()}
                        migratingV3={migratingV3}
                    />
                )}
            </div>
            </div>
        </div>
    )
}

function RobotsHero({ onCreate }: { onCreate?: () => void }) {
    return (
        <header className="dashboard-hero">
            <div className="dashboard-hero__bg" style={{ backgroundImage: `url(${cyberHero})` }} aria-hidden />
            <div className="dashboard-hero__veil" aria-hidden />
            <div className="dashboard-hero__content">
                <p className="dashboard-hero__eyebrow">GIN // ROBOT NODE</p>
                <h1 className="dashboard-hero__title">
                    <span className="dashboard-hero__title-glitch" data-text="РОБОТЫ">РОБОТЫ</span>
                </h1>
                <p className="dashboard-hero__sub">Флот · pipeline · запуск</p>
            </div>
            {onCreate && (
                <div className="dashboard-hero__actions">
                    <Button variant="ghost" size="sm" className="dashboard-hero__cfg" onClick={onCreate}>
                        + Создать
                    </Button>
                </div>
            )}
        </header>
    )
}
