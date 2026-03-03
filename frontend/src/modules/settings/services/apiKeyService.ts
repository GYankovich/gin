import { apiFetch } from '../../../core/api';
import type {
    ApiKey,
    ApiKeyDetail,
    ApiKeyCreate,
    ApiKeyUpdate,
    ApiKeyListResponse,
    TInvestStatus
} from '../types';

class ApiKeyService {
    private baseUrl = '/apikey';

    async createKey(data: ApiKeyCreate): Promise<ApiKey> {
        try {
            const response = await apiFetch<ApiKey>(`${this.baseUrl}/create`, {
                method: 'POST',
                body: JSON.stringify(data),
            });
            return response;
        } catch (error: any) {
            // Проверяем структуру ошибки
            if (error.response?.data?.code === 'apikey_exists') {
                throw new Error('Токен уже существует');
            }
            throw error;
        }
    }

    // Получение списка ключей
    async getKeys(params?: {
        key_type?: string;
        include_inactive?: boolean;
        limit?: number;
        offset?: number;
    }): Promise<ApiKeyListResponse> {
        console.log('📊 Fetching API keys with params:', params);

        const body: any = {};
        if (params?.key_type !== undefined) body.key_type = params.key_type;
        if (params?.include_inactive !== undefined) body.include_inactive = params.include_inactive;
        if (params?.limit !== undefined) body.limit = params.limit;
        if (params?.offset !== undefined) body.offset = params.offset;

        return apiFetch<ApiKeyListResponse>(`${this.baseUrl}/data`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    // Получение детальной информации о ключе
    async getKeyDetail(keyId: number): Promise<ApiKeyDetail> {
        console.log(`🔍 Fetching key detail for ID: ${keyId}`);
        return apiFetch<ApiKeyDetail>(`${this.baseUrl}/data/${keyId}`);
    }

    // Обновление ключа
    async updateKey(keyId: number, data: ApiKeyUpdate): Promise<ApiKey> {
        console.log(`✏️ Updating key ${keyId} with data:`, data);
        return apiFetch<ApiKey>(`${this.baseUrl}/update/${keyId}`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    // Удаление ключа - ТЕПЕРЬ POST!
    async deleteKey(keyId: number): Promise<{ message: string; success: boolean }> {
        console.log(`🗑️ Deleting key ${keyId} via POST`);
        return apiFetch<{ message: string; success: boolean }>(`${this.baseUrl}/delete/${keyId}`, {
            method: 'POST', // Изменено с DELETE на POST
        });
    }

    // Активация ключа
    async activateKey(keyId: number): Promise<ApiKey> {
        console.log(`✅ Activating key ${keyId}`);
        return apiFetch<ApiKey>(`${this.baseUrl}/activate/${keyId}`, {
            method: 'POST',
        });
    }

    // Деактивация ключа
    async deactivateKey(keyId: number): Promise<ApiKey> {
        console.log(`⛔ Deactivating key ${keyId}`);
        return apiFetch<ApiKey>(`${this.baseUrl}/deactivate/${keyId}`, {
            method: 'POST',
        });
    }

    // Проверка ключа
    async checkKey(keyId: number): Promise<{ valid: boolean; key_type: string; last_checked: string; message: string }> {
        console.log(`🔎 Checking key ${keyId}`);
        return apiFetch(`${this.baseUrl}/check/${keyId}`, {
            method: 'POST',
        });
    }

    // Специфичные методы для T-Invest
    async getTInvestStatus(): Promise<TInvestStatus> {
        console.log('🏦 Getting T-Invest status');
        try {
            const response = await this.getKeys({
                key_type: 'tinvest',
                include_inactive: false,
                limit: 1
            });

            const tinvestKey = response.keys.find(key => key.key_type === 'tinvest' && key.is_active);

            if (tinvestKey) {
                return {
                    has_token: true,
                    key_id: tinvestKey.id,
                    key_name: tinvestKey.name,
                    created_at: tinvestKey.created_at,
                };
            }
            return { has_token: false };
        } catch (error) {
            console.error('Failed to get T-Invest status:', error);
            return { has_token: false };
        }
    }

    // Сохранение T-Invest токена с названием
    async saveTInvestToken(token: string, name?: string): Promise<ApiKey> {
        console.log('💾 Saving T-Invest token with name:', name);
        return this.createKey({
            token,
            key_type: 'tinvest',
            name: name || 'T-Invest API Token',
        });
    }

    async deleteTInvestToken(): Promise<{ message: string; success: boolean }> {
        console.log('🗑️ Deleting T-Invest token via POST');
        const status = await this.getTInvestStatus();
        if (status.key_id) {
            return this.deleteKey(status.key_id);
        }
        throw new Error('T-Invest token not found');
    }
}

export const apiKeyService = new ApiKeyService();