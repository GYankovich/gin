import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { Skeleton } from '@/components/ui/Skeleton'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Chart, type IChartApi, type Time } from '@/components/ui/Chart'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import { useToast } from '@/components/ui/Toast'
import { LineSeries } from 'lightweight-charts'
import { robotService } from '@/services/robotService'
import { marketService, type MarketInstrumentRow } from '@/services/marketService'
import { portfolioService } from '@/services/portfolioService'
import type { Robot, RobotHistoryBacktestResult, RobotHistoryBacktestTrade, StrategyParam } from '@/types/robot'
import type { TokenResponse } from '@/types/portfolio'

const MOEX_INTERVAL_OPTIONS = [
    { value: 'CANDLE_INTERVAL_MONTH', label: 'Месяц' },
    { value: 'CANDLE_INTERVAL_WEEK', label: 'Неделя' },
    { value: 'CANDLE_INTERVAL_DAY', label: 'День' },
    { value: 'CANDLE_INTERVAL_HOUR', label: 'Час' },
    { value: 'CANDLE_INTERVAL_10_MIN', label: '10 минут' },
    { value: 'CANDLE_INTERVAL_1_MIN', label: '1 минута' },
]

function toIsoUtc(d: string): string {
    const dt = new Date(d)
    if (Number.isNaN(dt.getTime())) return new Date().toISOString()
    return dt.toISOString()
}

function parsePercentMasked(raw: string): number {
    const digits = raw.replace(/\D/g, '')
    if (!digits) return 0
    if (digits.startsWith('10000')) return 100
    const normalized = digits.slice(0, 4)
    const v = Number.parseInt(normalized, 10) / 100
    if (!Number.isFinite(v)) return 0
    return Math.max(0, Math.min(100, v))
}

function toChartTime(value: any): Time {
    if (typeof value === 'number') return value as Time
    const d = new Date(String(value))
    const ms = d.getTime()
    if (!Number.isFinite(ms)) return 0 as Time
    return Math.floor(ms / 1000) as Time
}

function normalizeSeriesByTime<T extends { time: Time }>(rows: T[]): T[] {
    const map = new Map<string, T>()
    for (const row of rows) map.set(String(row.time), row)
    return Array.from(map.values()).sort((a, b) => Number(a.time) - Number(b.time))
}

export default function TestingPage() {
    const [mode, setMode] = useState<'robot' | 'builder'>('builder')
    const [robots, setRobots] = useState<Robot[]>([])
    const [robotId, setRobotId] = useState<number | null>(null)
    const [marketRows, setMarketRows] = useState<MarketInstrumentRow[]>([])
    const [strategies, setStrategies] = useState<StrategyParam[]>([])
    const [tokens, setTokens] = useState<TokenResponse[]>([])

    const [figi, setFigi] = useState('')
    const [customTicker, setCustomTicker] = useState('')
    const [instrumentInput, setInstrumentInput] = useState('')
    const [instrumentOpen, setInstrumentOpen] = useState(false)
    const instrumentRef = useRef<HTMLDivElement>(null)
    const [quoteMode, setQuoteMode] = useState<'candles'>('candles')
    const [candleInterval, setCandleInterval] = useState('CANDLE_INTERVAL_DAY')
    const [strategy, setStrategy] = useState('ma_cross')
    const [strategyParams, setStrategyParams] = useState<Record<string, any>>({})
    const [stopLoss, setStopLoss] = useState(2)
    const [takeProfit, setTakeProfit] = useState(3)
    const [maxPosPct, setMaxPosPct] = useState(10)
    const [maxPosRub, setMaxPosRub] = useState(50000)
    const [commPct, setCommPct] = useState(0.05)
    const [ndflPct, setNdflPct] = useState(15)
    const [capital, setCapital] = useState(1_000_000)
    const [sessionInterval, setSessionInterval] = useState('10:00-18:45')
    const [syncTokenId, setSyncTokenId] = useState<number | null>(null)
    const [fromDate, setFromDate] = useState('')
    const [toDate, setToDate] = useState('')

    const [loading, setLoading] = useState(true)
    const [running, setRunning] = useState(false)
    const [statusWindow, setStatusWindow] = useState<string[]>([])
    const [result, setResult] = useState<RobotHistoryBacktestResult | null>(null)
    const [priceCurve, setPriceCurve] = useState<Array<{ time: Time; value: number }>>([])
    const [chartLegend, setChartLegend] = useState<{ time: string; equity?: number; price?: number }>({ time: '' })
    const [error, setError] = useState<string | null>(null)
    const [invalid, setInvalid] = useState<Record<string, boolean>>({})
    const toast = useToast()

    useEffect(() => {
        Promise.all([
            robotService.list(100, 0),
            marketService.listInstruments().catch(() => []),
            robotService.getStrategies().catch(() => ({ items: [] })),
            portfolioService.getTokens().catch(() => []),
        ]).then(([r, m, s, t]) => {
            setRobots(r.items)
            if (r.items.length > 0) setRobotId(r.items[0].id)
            setMarketRows(m)
            setStrategies(s.items ?? [])
            setTokens(Array.isArray(t) ? t : [])
        }).finally(() => setLoading(false))
    }, [])

    const selectedStrategy = useMemo(() => strategies.find(s => s.name === strategy), [strategies, strategy])
    const selectedRobot = useMemo(() => robots.find(r => r.id === robotId) ?? null, [robots, robotId])

    useEffect(() => {
        if (mode !== 'robot' || !selectedRobot) return
        const cfg = selectedRobot.config ?? {}
        const sp = { ...(cfg.strategy_params ?? {}) }
        const selected = String(cfg.strategy ?? strategy)
        setStrategy(selected)
        setStrategyParams(sp)
        const figis = (cfg.allowed_figis ?? sp.figis ?? []) as string[]
        if (figis.length > 0) setFigi(String(figis[0]))
        if (sp.interval) setCandleInterval(String(sp.interval))
        setStopLoss(Number(cfg.risk?.stop_loss_percent ?? 2))
        setTakeProfit(Number(cfg.risk?.take_profit_percent ?? 3))
        setMaxPosPct(Number(cfg.risk?.max_position_percent ?? 10))
        setMaxPosRub(Number(cfg.risk?.max_position_rub ?? 50000))
        setCommPct(Number(((cfg.costs?.broker_commission_rate ?? 0.0005) * 100).toFixed(6)))
        setNdflPct(Number(((cfg.costs?.ndfl_rate ?? 0.15) * 100).toFixed(4)))
    }, [mode, selectedRobot])

    useEffect(() => {
        const schema = selectedStrategy?.params_schema ?? {}
        const next: Record<string, any> = { ...strategyParams }
        for (const [key, cfg] of Object.entries(schema)) {
            if (key in next) continue
            if (key === 'figis') next[key] = figi ? [figi] : []
            else if (key === 'interval') next[key] = candleInterval
            else if ((cfg as any).default !== undefined) next[key] = (cfg as any).default
        }
        setStrategyParams(next)
    }, [selectedStrategy, figi, candleInterval])

    useEffect(() => {
        const onClickOutside = (e: MouseEvent) => {
            if (!instrumentRef.current?.contains(e.target as Node)) {
                setInstrumentOpen(false)
            }
        }
        document.addEventListener('mousedown', onClickOutside)
        return () => document.removeEventListener('mousedown', onClickOutside)
    }, [])

    const tickerOptions = useMemo(() => {
        const byTicker = new Map<string, MarketInstrumentRow>()
        for (const row of marketRows) {
            if (!row.ticker) continue
            if (!byTicker.has(row.ticker)) byTicker.set(row.ticker, row)
        }
        return Array.from(byTicker.values()).map(row => ({ figi: row.figi, ticker: row.ticker as string }))
    }, [marketRows])
    const filteredTickers = useMemo(
        () => tickerOptions.filter(x => x.ticker.toLowerCase().includes(instrumentInput.trim().toLowerCase())).slice(0, 12),
        [tickerOptions, instrumentInput],
    )
    const hasExactTicker = useMemo(
        () => tickerOptions.some(x => x.ticker.toLowerCase() === instrumentInput.trim().toLowerCase()),
        [tickerOptions, instrumentInput],
    )

    const ensureInstrument = async (tickerOrFigi: string): Promise<string> => {
        const res = await marketService.ensureCandles({
            figi: tickerOrFigi.toUpperCase(),
            ticker: tickerOrFigi.toUpperCase(),
            candle_interval: candleInterval,
            from_date: toIsoUtc(fromDate),
            to_date: toIsoUtc(toDate),
            data_source: 'moex',
            token_id: syncTokenId ?? undefined,
        })
        setStatusWindow(res.stages ?? [])
        const prices = (res.candles ?? []).map((c: any) => {
            const t = toChartTime(c.time)
            const q = c.close ?? { units: 0, nano: 0 }
            const close = Number(q.units ?? 0) + Number(q.nano ?? 0) / 1_000_000_000
            return { time: t, value: close }
        }).filter((x: any) => Number(x.time) > 0 && Number.isFinite(x.value))
        setPriceCurve(normalizeSeriesByTime(prices))
        return res.figi
    }

    const runBacktest = async () => {
        setRunning(true)
        setError(null)
        setResult(null)
        setStatusWindow(['Подготавливаемся к тесту...'])
        try {
            const nextInvalid: Record<string, boolean> = {}
            const typedTicker = (customTicker || instrumentInput).trim()
            if (!figi && !typedTicker) nextInvalid.instrument = true
            if (!fromDate || !toDate) nextInvalid.period = true
            if (Object.keys(nextInvalid).length > 0) {
                setInvalid(nextInvalid)
                toast.show('Заполните обязательные поля', 'error', 4000)
                setStatusWindow([])
                setRunning(false)
                return
            }
            setInvalid({})
            let effectiveFigi = figi
            if (!effectiveFigi) {
                const t = typedTicker
                if (!t) throw new Error('Укажите тикер')
                effectiveFigi = await ensureInstrument(t)
                setFigi(effectiveFigi)
                setCustomTicker(t.toUpperCase())
            } else {
                effectiveFigi = await ensureInstrument(effectiveFigi)
            }
            setStatusWindow(['Тестируем...'])
            const payload: Record<string, unknown> = {
                figi: effectiveFigi,
                ticker: (customTicker || instrumentInput).trim().toUpperCase() || undefined,
                candle_interval: candleInterval,
                strategy,
                strategy_params: { ...strategyParams, figis: [effectiveFigi], interval: candleInterval, market_data: { mode: quoteMode } },
                risk: {
                    stop_loss_percent: stopLoss,
                    take_profit_percent: takeProfit,
                    max_position_percent: maxPosPct,
                    max_position_rub: maxPosRub,
                },
                costs: {
                    broker_commission_rate: commPct / 100,
                    ndfl_rate: ndflPct / 100,
                },
                from_date: toIsoUtc(fromDate),
                to_date: toIsoUtc(toDate),
                initial_capital: capital,
                token_id: syncTokenId ?? undefined,
                data_source: 'moex',
                fetch_if_missing: false,
                session_interval: sessionInterval,
            }
            const bt = await marketService.runBacktest(payload)
            setStatusWindow([])
            setResult(bt)
            setChartLegend({ time: '' })
        } catch (e: any) {
            const msg = fmtErr(e)
            setError(msg)
            toast.show(msg, 'error', 4000)
            setStatusWindow([])
        }
        setRunning(false)
    }

    const onChartReady = useCallback((chart: IChartApi) => {
        if (!result?.equity_curve?.length) return
        const isIntraday = candleInterval.includes('MIN') || candleInterval.includes('HOUR')
        chart.applyOptions({
            timeScale: {
                timeVisible: isIntraday,
                secondsVisible: false,
            },
        } as any)
        const formatLegendTime = (t: Time | number | string): string => {
            const sec = typeof t === 'number' ? t : Number(t)
            if (!Number.isFinite(sec)) return ''
            const d = new Date(sec * 1000)
            const date = d.toLocaleDateString('ru-RU')
            if (!isIntraday) return date
            const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
            return `${date} ${time}`
        }
        const start = new Date(fromDate)
        const eqDataRaw = result.equity_curve.map((p, i) => {
            const pTime = (p as any).time
            if (pTime) return { time: toChartTime(pTime), value: p.equity }
            const d = new Date(start)
            d.setUTCDate(d.getUTCDate() + i)
            return { time: toChartTime(d.toISOString()), value: p.equity }
        })
        const eqData = normalizeSeriesByTime(eqDataRaw)
        const eqSeries = chart.addSeries(LineSeries, { color: '#0066cc', lineWidth: 2 })
        eqSeries.setData(eqData)

        const priceSeries = chart.addSeries(LineSeries, { color: '#9b7cff', lineWidth: 1, priceScaleId: 'left' as any })
        priceSeries.setData(normalizeSeriesByTime(priceCurve))

        // Dot series to guarantee visible trade points on price chart.
        const buyPointsSeries = chart.addSeries(LineSeries, {
            color: '#00aa66',
            lineVisible: false,
            pointMarkersVisible: true,
            pointMarkersRadius: 4,
            crosshairMarkerVisible: true,
            crosshairMarkerRadius: 5,
            priceScaleId: 'left' as any,
        } as any)
        const sellPointsSeries = chart.addSeries(LineSeries, {
            color: '#cc3333',
            lineVisible: false,
            pointMarkersVisible: true,
            pointMarkersRadius: 4,
            crosshairMarkerVisible: true,
            crosshairMarkerRadius: 5,
            priceScaleId: 'left' as any,
        } as any)
        const buyPoints = (result.trades || []).filter(t => t.side === 'buy' && !!t.bar_time).map(t => ({ time: toChartTime(t.bar_time), value: t.price }))
        const sellPoints = (result.trades || []).filter(t => t.side !== 'buy' && !!t.bar_time).map(t => ({ time: toChartTime(t.bar_time), value: t.price }))
        buyPointsSeries.setData(normalizeSeriesByTime(buyPoints as any))
        sellPointsSeries.setData(normalizeSeriesByTime(sellPoints as any))

        const markers = (result.trades || [])
            .filter(t => !!t.bar_time)
            .map(t => ({
                time: toChartTime(t.bar_time),
                position: t.side === 'buy' ? 'belowBar' : 'aboveBar',
                color: t.side === 'buy' ? '#00aa66' : '#cc3333',
                shape: t.side === 'buy' ? 'arrowUp' : 'arrowDown',
                text: `${t.side.toUpperCase()} ${t.quantity} @ ${t.price.toFixed(2)}`,
            }))
        ;(priceSeries as any).setMarkers?.(markers)

        const tooltip = document.createElement('div')
        tooltip.className = 'chart-trade-tooltip'
        tooltip.style.display = 'none'
        tooltip.style.whiteSpace = 'pre-line'
        const container = document.querySelector('.chart-container')
        if (container) container.appendChild(tooltip)
        const toDayKeyFromSec = (sec: number): string => {
            const d = new Date(sec * 1000)
            const y = d.getUTCFullYear()
            const m = String(d.getUTCMonth() + 1).padStart(2, '0')
            const day = String(d.getUTCDate()).padStart(2, '0')
            return `${y}-${m}-${day}`
        }
        const tradesBySecond = new Map<string, RobotHistoryBacktestTrade[]>()
        const tradesByDay = new Map<string, RobotHistoryBacktestTrade[]>()
        for (const t of result.trades || []) {
            if (!t.bar_time) continue
            const sec = Number(toChartTime(t.bar_time))
            const sk = String(sec)
            const dk = toDayKeyFromSec(sec)
            const a = tradesBySecond.get(sk) ?? []
            a.push(t)
            tradesBySecond.set(sk, a)
            const b = tradesByDay.get(dk) ?? []
            b.push(t)
            tradesByDay.set(dk, b)
        }
        chart.subscribeCrosshairMove((param: any) => {
            if (!param?.time || !param?.point || !container) {
                tooltip.style.display = 'none'
                setChartLegend(prev => ({ ...prev, time: '' }))
                return
            }
            const keySec = typeof param.time === 'number' ? String(param.time) : ''
            const keyDay = typeof param.time === 'object' && param.time
                ? `${param.time.year}-${String(param.time.month).padStart(2, '0')}-${String(param.time.day).padStart(2, '0')}`
                : (typeof param.time === 'number' ? toDayKeyFromSec(param.time) : '')
            const seriesData = param.seriesData
            const eqPoint = seriesData?.get?.(eqSeries)
            const pxPoint = seriesData?.get?.(priceSeries)
            const equity = eqPoint?.value != null ? Number(eqPoint.value) : undefined
            const price = pxPoint?.value != null ? Number(pxPoint.value) : undefined
            setChartLegend({ time: formatLegendTime(param.time), equity, price })
            const buyPoint = seriesData?.get?.(buyPointsSeries)
            const sellPoint = seriesData?.get?.(sellPointsSeries)
            const sideHint: 'buy' | 'sell' | null = buyPoint?.value != null ? 'buy' : sellPoint?.value != null ? 'sell' : null
            const candidates = (tradesBySecond.get(keySec) ?? tradesByDay.get(keyDay) ?? []).filter(t => !sideHint || t.side === sideHint)
            const trade = candidates[0]
            if (!trade) {
                tooltip.style.display = 'none'
                return
            }
            tooltip.style.display = 'block'
            const yOnPrice = (priceSeries as any).priceToCoordinate?.(trade.price)
            const tx = param.point.x + 12
            const ty = Number.isFinite(yOnPrice) ? Number(yOnPrice) - 18 : param.point.y + 12
            tooltip.style.left = `${tx}px`
            tooltip.style.top = `${ty}px`
            const total = trade.price * trade.quantity
            tooltip.textContent =
                `${trade.side.toUpperCase()} ${formatLegendTime(param.time)}\n` +
                `Объём: ${trade.quantity} шт\n` +
                `Цена/ед: ${trade.price.toFixed(2)}\n` +
                `Сумма: ${total.toFixed(2)}`
        })
        chart.timeScale().fitContent()
    }, [result, fromDate, priceCurve, candleInterval])

    const tradeColumns: Column<RobotHistoryBacktestTrade>[] = [
        { key: 'bar_time', header: 'Бар', render: r => r.bar_time ?? '—' },
        { key: 'figi', header: 'FIGI' },
        { key: 'side', header: 'Сторона', render: r => r.side.toUpperCase() },
        { key: 'price', header: 'Цена', align: 'right', render: r => r.price.toLocaleString('ru-RU', { maximumFractionDigits: 4 }) },
        { key: 'quantity', header: 'Лоты', align: 'right' },
        { key: 'commission', header: 'Комиссия', align: 'right', render: r => r.commission.toFixed(2) },
    ]

    const parseNum = (raw: string, allowDecimal: boolean, min?: number, max?: number): number => {
        const cleaned = allowDecimal ? raw.replace(/[^0-9.,-]/g, '').replace(',', '.') : raw.replace(/[^0-9-]/g, '')
        let normalized = cleaned.replace(/^(-?)0+(\d)/, '$1$2')
        if (normalized === '' || normalized === '-' || normalized === '.') normalized = '0'
        let n = Number(normalized)
        if (!Number.isFinite(n)) n = 0
        if (min != null && n < min) n = min
        if (max != null && n > max) n = max
        return n
    }

    if (loading) return <div className="page" data-page="testing"><h1 className="page__title">Тестирование</h1><Skeleton height="48px" count={4} /></div>

    return (
        <div className="page" data-page="testing">
            <h1 className="page__title">Тестирование</h1>

            <Card className="mb-6">
                <h3 className="card__section-title">Блок инструментов</h3>
                <div className="form-row testing-top-row" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 'var(--space-4)' }}>
                    <div className="form-group" ref={instrumentRef} style={{ marginBottom: 0 }}>
                        <label className="form-label">Инструмент</label>
                        <div style={{ position: 'relative' }}>
                            <input
                                className="form-input"
                                style={invalid.instrument ? { borderColor: 'var(--color-down)' } : undefined}
                                value={instrumentInput}
                                onChange={e => { setInstrumentInput(e.target.value.toUpperCase()); setInstrumentOpen(true); setFigi('') }}
                                onFocus={() => setInstrumentOpen(true)}
                                placeholder="Введите тикер"
                            />
                            {instrumentOpen && (
                                <div className="gin-select__dropdown" style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0 }}>
                                    <div className="gin-select__options">
                                        {filteredTickers.map(item => (
                                            <div
                                                key={item.figi}
                                                className="gin-select__option"
                                                onClick={() => { setFigi(item.figi); setCustomTicker(item.ticker); setInstrumentInput(item.ticker); setInstrumentOpen(false) }}
                                            >
                                                {item.ticker}
                                            </div>
                                        ))}
                                        {!!instrumentInput.trim() && !hasExactTicker && (
                                            <div
                                                className="gin-select__option"
                                                onClick={() => { setCustomTicker(instrumentInput.trim().toUpperCase()); setFigi(''); setInstrumentOpen(false) }}
                                            >
                                                Добавить "{instrumentInput.trim()}"
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label">Тип данных MOEX</label>
                        <Select options={[{ value: 'candles', label: 'Свечи' }]} value={quoteMode} onChange={v => setQuoteMode((v as 'candles') || 'candles')} />
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label">Интервал свечей</label>
                        <Select options={MOEX_INTERVAL_OPTIONS} value={candleInterval} onChange={setCandleInterval} />
                    </div>
                </div>
                <div style={invalid.period ? { border: '1px solid var(--color-down)', borderRadius: 'var(--radius-md)', padding: 6 } : undefined}>
                    <DateRangePicker fromValue={fromDate} toValue={toDate} onFromChange={setFromDate} onToChange={setToDate} fromLabel="Интервал с" toLabel="по" />
                </div>
            </Card>

            <Card className="mb-6">
                <h3 className="card__section-title">Режим теста</h3>
                <div className="ios-segment mb-6">
                    <button type="button" className={`ios-segment__item ${mode === 'builder' ? 'ios-segment__item--active' : ''}`} onClick={() => setMode('builder')}>Конструктор</button>
                    <button type="button" className={`ios-segment__item ${mode === 'robot' ? 'ios-segment__item--active' : ''}`} onClick={() => setMode('robot')}>Робот</button>
                </div>
                {mode === 'robot' && (
                    <div className="form-group">
                        <label className="form-label">Робот</label>
                        <Select options={robots.map(r => ({ value: String(r.id), label: r.name }))} value={robotId != null ? String(robotId) : ''} onChange={v => setRobotId(v ? Number(v) : null)} />
                    </div>
                )}
                <div className="form-group">
                    <label className="form-label">Стратегия</label>
                    <Select options={strategies.map(s => ({ value: s.name, label: s.title }))} value={strategy} onChange={setStrategy} />
                </div>
                {Object.entries(selectedStrategy?.params_schema ?? {}).map(([key, schema]: [string, any]) => {
                    if (key === 'figis' || key === 'interval') return null
                    const label = `${schema.label || schema.title || key}${schema.required || schema.default === undefined ? ' *' : ''}`
                    if (schema.enum) return <div className="form-group" key={key}><label className="form-label">{label}</label><Select options={schema.enum.map((x: string) => ({ value: x, label: x }))} value={String(strategyParams[key] ?? schema.default ?? '')} onChange={v => setStrategyParams({ ...strategyParams, [key]: v })} /></div>
                    if (schema.type === 'array') return <div className="form-group" key={key}><label className="form-label">{label}</label><input className="form-input" value={Array.isArray(strategyParams[key]) ? strategyParams[key].join(',') : ''} onChange={e => setStrategyParams({ ...strategyParams, [key]: e.target.value.split(',').map(x => x.trim()).filter(Boolean) })} /></div>
                    const isNumeric = schema.type === 'integer' || schema.type === 'number'
                    return (
                        <div className="form-group" key={key}>
                            <label className="form-label">{label}</label>
                            <input
                                className="form-input"
                                type="text"
                                value={strategyParams[key] ?? schema.default ?? ''}
                                onChange={e => {
                                    if (!isNumeric) {
                                        setStrategyParams({ ...strategyParams, [key]: e.target.value })
                                        return
                                    }
                                    const allowDecimal = schema.type === 'number'
                                    const min = typeof schema.min === 'number' ? schema.min : 0
                                    const max = typeof schema.max === 'number' ? schema.max : undefined
                                    const num = parseNum(e.target.value, allowDecimal, min, max)
                                    setStrategyParams({ ...strategyParams, [key]: num })
                                }}
                            />
                        </div>
                    )
                })}
                <div className="form-row" style={{ flexWrap: 'wrap' }}>
                    <div className="form-group"><label className="form-label">Стоп-лосс %</label><input className="form-input" type="text" value={Number(stopLoss).toFixed(2)} onChange={e => setStopLoss(parsePercentMasked(e.target.value))} /></div>
                    <div className="form-group"><label className="form-label">Тейк-профит %</label><input className="form-input" type="text" value={Number(takeProfit).toFixed(2)} onChange={e => setTakeProfit(parsePercentMasked(e.target.value))} /></div>
                    <div className="form-group"><label className="form-label">Макс. позиция %</label><input className="form-input" type="text" value={Number(maxPosPct).toFixed(2)} onChange={e => setMaxPosPct(parsePercentMasked(e.target.value))} /></div>
                    <div className="form-group"><label className="form-label">Макс. ₽ на сделку</label><input className="form-input" type="text" value={String(maxPosRub)} onChange={e => setMaxPosRub(parseNum(e.target.value, true, 0))} /></div>
                </div>
            </Card>

            <Card className="mb-6">
                <h3 className="card__section-title">Настройки брокера</h3>
                <div className="form-row" style={{ flexWrap: 'wrap' }}>
                    <div className="form-group"><label className="form-label">Комиссия %</label><input className="form-input" type="text" value={Number(commPct).toFixed(2)} onChange={e => setCommPct(parsePercentMasked(e.target.value))} /></div>
                    <div className="form-group"><label className="form-label">НДФЛ %</label><input className="form-input" type="text" value={Number(ndflPct).toFixed(2)} onChange={e => setNdflPct(parsePercentMasked(e.target.value))} /></div>
                    <div className="form-group"><label className="form-label">Бюджет (₽)</label><input className="form-input" type="text" value={String(capital)} onChange={e => setCapital(parseNum(e.target.value, true, 0))} /></div>
                    <div className="form-group"><label className="form-label">Интервал торговой сессии</label><input className="form-input" value={sessionInterval} onChange={e => setSessionInterval(e.target.value)} placeholder="10:00-18:45" /></div>
                </div>
            </Card>

            <div className="mb-6" style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Button onClick={runBacktest} loading={running}>Запустить бэктест</Button>
            </div>

            {statusWindow.length > 0 && (
                <Card className="mb-6">
                    <h3 className="card__section-title">Статус подготовки/теста</h3>
                    <div className="form-hint">{statusWindow.map((s, i) => <div key={`${s}-${i}`}>• {s}</div>)}</div>
                </Card>
            )}

            {result && (
                <>
                    <div className="grid-kpi mb-6">
                        <div className="kpi-tile"><span className="kpi-tile__label">Доходность</span><span className={`kpi-tile__value mono ${result.total_return_percent >= 0 ? 'color-up' : 'color-down'}`}>{result.total_return_percent.toFixed(2)}%</span></div>
                        <div className="kpi-tile"><span className="kpi-tile__label">Итоговый капитал</span><span className="kpi-tile__value mono">{result.final_equity.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽</span></div>
                        <div className="kpi-tile"><span className="kpi-tile__label">Max drawdown</span><span className="kpi-tile__value mono">{result.max_drawdown_percent != null ? `${result.max_drawdown_percent.toFixed(2)}%` : '—'}</span></div>
                        <div className="kpi-tile"><span className="kpi-tile__label">Сделок</span><span className="kpi-tile__value mono">{result.trades.length}</span></div>
                    </div>
                    <Card className="mb-6">
                        <h3 className="card__section-title">Кривая капитала и цена актива</h3>
                        <div className="form-hint" style={{ marginBottom: 8 }}>
                            <span style={{ color: '#0066cc', marginRight: 12 }}>■ Капитал</span>
                            <span style={{ color: '#9b7cff', marginRight: 12 }}>■ Цена актива</span>
                            <span style={{ color: '#00aa66', marginRight: 12 }}>● Покупка</span>
                            <span style={{ color: '#cc3333', marginRight: 12 }}>● Продажа</span>
                            {chartLegend.time && (
                                <span style={{ marginLeft: 12 }}>
                                    {chartLegend.time}
                                    {chartLegend.equity != null ? ` | Капитал: ${chartLegend.equity.toFixed(2)}` : ''}
                                    {chartLegend.price != null ? ` | Цена: ${chartLegend.price.toFixed(2)}` : ''}
                                </span>
                            )}
                        </div>
                        <Chart height={320} onReady={onChartReady} key={`bt-${result.final_equity}-${result.equity_curve.length}-${priceCurve.length}`} />
                    </Card>
                    <Card><h3 className="card__section-title">Сделки</h3><DataTable columns={tradeColumns} data={result.trades} keyField="id" emptyText="Нет сделок" /></Card>
                </>
            )}
        </div>
    )
}

function fmtErr(e: any): string {
    const d = e?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: any) => x.msg ?? JSON.stringify(x)).join('; ')
    if (d && typeof d === 'object') return JSON.stringify(d)
    return e?.message ?? String(e)
}
