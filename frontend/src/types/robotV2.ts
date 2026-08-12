/** Types for robots v2 greenfield contour. */

export type RobotV2StatusCode = 0 | 1 | 2 | 3 // draft/stopped/active/error — backend uses int dict

export type RobotV2 = {
    id: number
    name: string
    type: number
    tokenId: number | null
    token_id?: number | null
    status: number
    configVersion: number
    config_version?: number
    config: Record<string, unknown>
    metadata?: Record<string, unknown>
    createdAt?: string
    created_at?: string
    updatedAt?: string | null
    updated_at?: string | null
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
    universe?: string[] | null
    lastCycleAt?: string | null
    last_cycle_at?: string | null
    wsHealthy?: boolean | null
    ws_healthy?: boolean | null
    decisions?: Array<Record<string, unknown>> | null
    equityCurve?: Array<{ time?: string; equity?: number; cycle?: number }> | null
    equity_curve?: Array<{ time?: string; equity?: number; cycle?: number }> | null
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
