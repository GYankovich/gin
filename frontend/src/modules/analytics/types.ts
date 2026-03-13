export interface AccountSummary {
    id: number;
    account_id: string;
    name: string | null;
    type: string;
    status: string;
    last_snapshot_date: string | null;
    total_value: number;
    currency: string;
    positions_count: number;
}

export interface OverallSummary {
    total_value: number;
    total_daily_yield: number | null;
    total_expected_yield: number | null;
    accounts_count: number;
    accounts: AccountSummary[];
}

export interface HistoryItem {
    snapshot_id: number;
    date: string;
    total_value: number;
    daily_yield: number | null;
    expected_yield: number | null;
}

export interface DistributionItem {
    instrument_type: string;
    value: number;
    percentage: number;
    count: number;
}

export interface AccountDetail {
    account: {
        id: string;
        name: string | null;
        type: string;
        status: string;
    };
    last_snapshot: {
        id: number;
        date: string;
        total_value: number;
        shares_value: number;
        bonds_value: number;
        etf_value: number;
        currencies_value: number;
        expected_yield: number;
        daily_yield: number;
        daily_yield_relative: number;
    } | null;
    history: HistoryItem[];
    distribution: DistributionItem[];
}