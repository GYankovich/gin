import { create } from 'zustand'
import type { AccountSummary, DashboardDataResponse } from '@/types/api'
import type { RobotV2 } from '@/types/robotV2'

export type PortfolioAccountsCache = {
    accounts: AccountSummary[]
    selectedAccountId: number | null
}

export type RobotsFleetCache = {
    robots: RobotV2[]
    hasBrokerAccounts: boolean
}

export type RobotsModuleCache = {
    disabled: boolean
}

type PageCacheState = {
    dashboard: DashboardDataResponse | null
    portfolioAccounts: PortfolioAccountsCache | null
    robotsFleet: RobotsFleetCache | null
    robotsModule: RobotsModuleCache | null
    setDashboard: (data: DashboardDataResponse | null) => void
    setPortfolioAccounts: (data: PortfolioAccountsCache | null) => void
    setRobotsFleet: (data: RobotsFleetCache | null) => void
    setRobotsModule: (data: RobotsModuleCache | null) => void
    clear: () => void
}

const empty = {
    dashboard: null as DashboardDataResponse | null,
    portfolioAccounts: null as PortfolioAccountsCache | null,
    robotsFleet: null as RobotsFleetCache | null,
    robotsModule: null as RobotsModuleCache | null,
}

/** In-memory stale-while-revalidate cache for main cabin tabs. Cleared on logout. */
export const usePageCacheStore = create<PageCacheState>((set) => ({
    ...empty,
    setDashboard: (dashboard) => set({ dashboard }),
    setPortfolioAccounts: (portfolioAccounts) => set({ portfolioAccounts }),
    setRobotsFleet: (robotsFleet) => set({ robotsFleet }),
    setRobotsModule: (robotsModule) => set({ robotsModule }),
    clear: () => set({ ...empty }),
}))
