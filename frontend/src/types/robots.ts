/** Types for robots v2 greenfield contour. */

export type TradingRobotStatusCode = 0 | 1 | 2 | 3 // draft/stopped/active/error — backend uses int dict

export type TradingRobot = {
    id: number
    name: string
    type: number
    typeName?: string | null
    type_name?: string | null
    tokenId: number | null
    token_id?: number | null
    status: number
    statusName?: string | null
    status_name?: string | null
    configVersion: number
    config_version?: number
    config: Record<string, unknown>
    metadata?: Record<string, unknown>
    createdAt?: string
    created_at?: string
    updatedAt?: string | null
    updated_at?: string | null
    lastStarted?: string | null
    last_started?: string | null
    /** Populated on list for type=2 trading robots when session is in memory */
    sessionState?: string | null
    session_state?: string | null
}

export type TradingRobotTickerScan = {
    ticker: string
    code?: string
    message?: string
    price?: number | null
    metrics?: Record<string, unknown> | null
}

/** Machine source for Monitor Equity/Cash labels (SPEC-04 / UX-06). */
export type TradingRobotBalanceSource = 'session' | 'broker' | 'paper_last'

export type TradingRobotStatus = {
    robotId: number
    robot_id?: number
    status: number
    sessionState?: string | null
    session_state?: string | null
    message?: string | null
    mode?: string | null
    cycleNumber?: number | null
    cycle_number?: number | null
    equity?: number | null
    cash?: number | null
    /** session | broker | paper_last — do not infer labels from mode alone when set */
    balanceSource?: TradingRobotBalanceSource | null
    balance_source?: TradingRobotBalanceSource | null
    /** ISO timestamp for balance freshness */
    balanceAsOf?: string | null
    balance_as_of?: string | null
    /** Paper last capital from metadata (idle display / active echo) */
    lastVirtualCapital?: number | null
    last_virtual_capital?: number | null
    openPositions?: Array<Record<string, unknown>> | null
    open_positions?: Array<Record<string, unknown>> | null
    /** Fleet period closed trades / W/L (optional until /data wires aggregates) */
    tradesCount?: number | null
    trades_count?: number | null
    wins?: number | null
    losses?: number | null
    ownFunds?: number | null
    own_funds?: number | null
    /** Latest portfolio value minus own funds */
    priceDelta?: number | null
    price_delta?: number | null
    /** Equity change over statsPeriod (last curve point minus the first) */
    periodDelta?: number | null
    period_delta?: number | null
    statsPeriod?: 'session' | 'week' | 'month' | 'all' | null
    stats_period?: 'session' | 'week' | 'month' | 'all' | null
    /** session = live ledger; broker = idle snapshot from broker */
    positionsSource?: string | null
    positions_source?: string | null
    universe?: string[] | null
    lastCycleAt?: string | null
    last_cycle_at?: string | null
    positionsUpdatedAt?: string | null
    positions_updated_at?: string | null
    wsHealthy?: boolean | null
    ws_healthy?: boolean | null
    decisions?: Array<Record<string, unknown>> | null
    equityCurve?: Array<{ time?: string; equity?: number; cycle?: number }> | null
    equity_curve?: Array<{ time?: string; equity?: number; cycle?: number }> | null
    cycleStage?: string | null
    cycle_stage?: string | null
    cycleProgress?: number | null
    cycle_progress?: number | null
    cycleDetail?: string | null
    cycle_detail?: string | null
    cycleSkipReason?: string | null
    cycle_skip_reason?: string | null
    lastTriggeredBy?: string | null
    last_triggered_by?: string | null
    tickerScan?: TradingRobotTickerScan[] | null
    ticker_scan?: TradingRobotTickerScan[] | null
    tickerScanAt?: string | null
    ticker_scan_at?: string | null
    openOrders?: Array<Record<string, unknown>> | null
    open_orders?: Array<Record<string, unknown>> | null
    bootstrapReady?: boolean | null
    bootstrap_ready?: boolean | null
    universeRefreshedAt?: string | null
    universe_refreshed_at?: string | null
}

export type TradingRobotUniverseRefresh = {
    robotId: number
    universe: string[]
    added: string[]
    removed: string[]
    reason: string
    keptPrevious?: boolean
    refreshedAt?: string | null
    tickerScan?: TradingRobotTickerScan[] | null
}

export type TradingRobotValidateResponse = {
    valid: boolean
    errors: Array<{ field?: string; message: string; severity?: string }>
    suggestions: string[]
}

export type UniversePreviewAsset = {
    ticker: string
    name?: string | null
    included?: boolean
    price?: number | null
}

export type UniversePreview = {
    assets: UniversePreviewAsset[]
    total: number
    page?: number
    pageSize?: number
    asOf?: string
    rejectedSample?: Array<Record<string, unknown>>
}

export type StrategyArchetypeInfo = {
    archetype: string
    title?: string
    description?: string
    requiredData?: string[]
}

export type TradingRobotFill = {
    id: string
    orderId: string
    robotId: number
    ticker: string
    side: string
    quantity: number
    price: number
    /** @deprecated use ledgerPnl — unreliable on live (ledger bugs) */
    pnl?: number | null
    ledgerPnl?: number | null
    /** FIFO price-based PnL after commission, before tax (SELL legs only) */
    realizedPnl?: number | null
    /** After commission and tax on profit — «в кармане» (SELL legs only) */
    netPnl?: number | null
    /** FIFO avg entry for SELL legs */
    entryPrice?: number | null
    commission?: number | null
    kind: string
    filledAt: string
}

export type TradingRobotOrder = {
    id: string
    cycleId: string
    robotId: number
    ticker: string
    side: string
    kind: string
    quantity: number
    price?: number | null
    status: string
    mode: string
    orderType?: string
    order_type?: string
    brokerOrderId?: string | null
    broker_order_id?: string | null
    rejectReason?: string | null
    reject_reason?: string | null
    submittedAt: string
    submitted_at?: string
    /** Position entry price for exit (SELL) orders */
    entryPrice?: number | null
    entry_price?: number | null
}

export type TradingRobotSession = {
    id: string
    robotId: number
    mode: string
    virtualCapital?: number | null
    accountId?: string | null
    startedAt: string
    endedAt?: string | null
    stopReason?: string | null
}

export type TradingRobotCycle = {
    id: string
    sessionId: string
    robotId: number
    cycleNumber: number
    triggeredBy: string
    startedAt: string
    finishedAt?: string | null
    status: string
    skipReason?: string | null
    equity?: number | null
    stats?: Record<string, unknown>
}

export type TradingRobotDecision = {
    id: string
    cycleId: string
    robotId: number
    stage: string
    outcome: string
    code: string
    message?: string | null
    ticker?: string | null
    context?: Record<string, unknown>
    createdAt: string
}

export type TradingRobotSignal = {
    id: string
    cycleId: string
    robotId: number
    ticker: string
    side: string
    kind: string
    reason?: string | null
    price?: number | null
    /** Avg entry of open position (CLOSE / scale-in); null on flat BUY */
    entryPrice?: number | null
    /** Order-flow delta % at signal time */
    deltaPct?: number | null
    createdAt: string
}

export type TradingRobotRoundTrip = {
    id: string
    ticker: string
    buyAt?: string | null
    buy_at?: string | null
    buyPrice?: number | null
    buy_price?: number | null
    buyQty?: number | null
    buy_qty?: number | null
    sellAt?: string | null
    sell_at?: string | null
    sellListedPrice?: number | null
    sell_listed_price?: number | null
    sellFillPrice?: number | null
    sell_fill_price?: number | null
    sellQty?: number | null
    sell_qty?: number | null
    sellSubmittedAt?: string | null
    sell_submitted_at?: string | null
    status: string
    reason?: string | null
    /** Strategy / entry signal that opened the lot */
    entryReason?: string | null
    entry_reason?: string | null
    /** After commission, before tax */
    realizedPnl?: number | null
    realized_pnl?: number | null
    /** After commission and NDFL — «в кармане» */
    netPnl?: number | null
    net_pnl?: number | null
    /** Round-trip commission (entry + exit), ₽ */
    commission?: number | null
}

export type AuditDataType = 'sessions' | 'fills' | 'cycles' | 'decisions' | 'signals' | 'orders' | 'roundTrips'

export type TradingRobotAuditRequest = {
    robotId: number
    limit?: number
    offset?: number
    sessionId?: string | null
    types?: AuditDataType[]
    from?: string | null
    to?: string | null
}

export type TradingRobotAuditSection<T> = {
    items: T[]
    total: number
}

export type TradingRobotAuditResponse = {
    robotId: number
    sessions?: TradingRobotAuditSection<TradingRobotSession>
    fills?: TradingRobotAuditSection<TradingRobotFill>
    cycles?: TradingRobotAuditSection<TradingRobotCycle>
    decisions?: TradingRobotAuditSection<TradingRobotDecision>
    signals?: TradingRobotAuditSection<TradingRobotSignal>
    orders?: TradingRobotAuditSection<TradingRobotOrder>
    roundTrips?: TradingRobotAuditSection<TradingRobotRoundTrip>
}
