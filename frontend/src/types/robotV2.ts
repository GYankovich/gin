/** Types for robots v2 greenfield contour. */

export type RobotV2StatusCode = 0 | 1 | 2 | 3 // draft/stopped/active/error — backend uses int dict

export type RobotV2 = {
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

export type RobotV2TickerScan = {
    ticker: string
    code?: string
    message?: string
    price?: number | null
    metrics?: Record<string, unknown> | null
}

export type RobotV2Status = {
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
    openPositions?: Array<Record<string, unknown>> | null
    open_positions?: Array<Record<string, unknown>> | null
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
    tickerScan?: RobotV2TickerScan[] | null
    ticker_scan?: RobotV2TickerScan[] | null
    tickerScanAt?: string | null
    ticker_scan_at?: string | null
    openOrders?: Array<Record<string, unknown>> | null
    open_orders?: Array<Record<string, unknown>> | null
    bootstrapReady?: boolean | null
    bootstrap_ready?: boolean | null
    universeRefreshedAt?: string | null
    universe_refreshed_at?: string | null
}

export type RobotV2UniverseRefresh = {
    robotId: number
    universe: string[]
    added: string[]
    removed: string[]
    reason: string
    keptPrevious?: boolean
    refreshedAt?: string | null
    tickerScan?: RobotV2TickerScan[] | null
}

export type RobotV2ValidateResponse = {
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

export type RobotV2Fill = {
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

export type RobotV2Order = {
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

export type RobotV2Session = {
    id: string
    robotId: number
    mode: string
    virtualCapital?: number | null
    accountId?: string | null
    startedAt: string
    endedAt?: string | null
    stopReason?: string | null
}

export type RobotV2Cycle = {
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

export type RobotV2Decision = {
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

export type RobotV2Signal = {
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

export type RobotV2RoundTrip = {
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
    status: string
    reason?: string | null
    /** After commission, before tax */
    realizedPnl?: number | null
    realized_pnl?: number | null
    /** After commission and NDFL — «в кармане» */
    netPnl?: number | null
    net_pnl?: number | null
}

export type AuditDataType = 'sessions' | 'fills' | 'cycles' | 'decisions' | 'signals' | 'orders' | 'roundTrips'

export type RobotV2AuditRequest = {
    robotId: number
    limit?: number
    offset?: number
    sessionId?: string | null
    types?: AuditDataType[]
}

export type RobotV2AuditSection<T> = {
    items: T[]
    total: number
}

export type RobotV2AuditResponse = {
    robotId: number
    sessions?: RobotV2AuditSection<RobotV2Session>
    fills?: RobotV2AuditSection<RobotV2Fill>
    cycles?: RobotV2AuditSection<RobotV2Cycle>
    decisions?: RobotV2AuditSection<RobotV2Decision>
    signals?: RobotV2AuditSection<RobotV2Signal>
    orders?: RobotV2AuditSection<RobotV2Order>
    roundTrips?: RobotV2AuditSection<RobotV2RoundTrip>
}
