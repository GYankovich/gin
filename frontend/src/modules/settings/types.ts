// Типы для API ключей
export interface ApiKey {
    id: number;
    name?: string | null;
    key_type: string;
    is_active: boolean;
    created_at: string;
    masked_token: string;
    refresh_interval_minutes?: number;
    last_used_at?: string | null;
}

export interface ApiKeyDetail extends ApiKey {
    updated_at?: string | null;
    expires_at?: string | null;
    last_used_at?: string | null;
}

export interface ApiKeyCreate {
    token: string;
    key_type: string;
    name?: string | null;
    refresh_interval_minutes?: number;
}

export interface ApiKeyUpdate {
    name?: string | null;
    is_active?: boolean | null;
    refresh_interval_minutes?: number;
}

export interface ApiKeyListResponse {
    keys: ApiKey[];
    total: number;
    limit: number;
    offset: number;
}

// Для обратной совместимости с T-Invest
export interface TInvestStatus {
    has_token: boolean;
    key_id?: number | null;
    key_name?: string | null;
    created_at?: string | null;
    last_used_at?: string | null;
}

