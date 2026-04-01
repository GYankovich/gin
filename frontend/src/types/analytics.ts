import type { RobotMetrics, RobotTradeItem } from './robot'

export type { RobotMetrics, RobotTradeItem }

export interface AnalyticsFilters {
    period?: string
    robot_id?: number
    session_id?: number
}
