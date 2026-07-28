///@EPIC Frontend.ITEM Types.TOPIC FrontendSrcTypesAnalytics [1]
///@ Исходный модуль `frontend/src/types/analytics.ts` — автоматическая разметка для Obsidian Source Scanner.

import type { RobotMetrics, RobotTradeItem } from './robot'

export type { RobotMetrics, RobotTradeItem }

export interface AnalyticsFilters {
    period?: string
    robot_id?: number
    session_id?: number
}
