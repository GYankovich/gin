///@EPIC Frontend.ITEM Modules.TOPIC FrontendSrcModulesSettingsTypes [1]
///@ Исходный модуль `frontend/src/modules/settings/types.ts` — автоматическая разметка для Obsidian Source Scanner.

// Типы для API ключей

export interface TokenTypeInfo {
    type: number;
    typeName: string;
    typeDesc: string;
}

export interface ApiKey {
    id: number;
    name?: string | null;
    token_type: TokenTypeInfo;
    status: number;
    status_name?: string | null;
    status_description?: string | null;
    created_at: string;
    masked_token: string;
    last_used_at?: string | null;
}

export interface ApiKeyDetail extends ApiKey {
    updated_at?: string | null;
    expires_at?: string | null;
    last_used_at?: string | null;
}

export interface ApiKeyCreate {
    token: string;
    token_type: TokenTypeInfo;
    name?: string | null;
}

export interface ApiKeyUpdate {
    name?: string | null;
    status?: number | null;
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

