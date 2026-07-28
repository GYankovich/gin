///@EPIC Frontend.ITEM Modules.TOPIC FrontendSrcModulesSettingsServicesApikeyservice [1]
///@ Исходный модуль `frontend/src/modules/settings/services/apiKeyService.ts` — автоматическая разметка для Obsidian Source Scanner.

// frontend/src/modules/settings/services/apiKeyService.ts

import { apiFetch } from '../../../core/api';
import type { ApiKey, ApiKeyListResponse } from '../types';

class ApiKeyService {
    private baseUrl = '/apikey';

    async createKey(data: { token: string; key_type: string; name: string | null }): Promise<ApiKey> {
        try {
            const response = await apiFetch<ApiKey>(`${this.baseUrl}/create`, {
                method: 'POST',
                body: JSON.stringify(data),
            });
            return response;
        } catch (error: any) {
            if (error.response?.data?.code === 'apikey_exists') {
                throw new Error('Токен уже существует');
            }
            throw error;
        }
    }

    async getKeys(params?: { key_type?: string; limit?: number; offset?: number }): Promise<ApiKeyListResponse> {
        const body: any = {};
        if (params?.key_type !== undefined) body.key_type = params.key_type;
        if (params?.limit !== undefined) body.limit = params.limit;
        if (params?.offset !== undefined) body.offset = params.offset;

        return apiFetch<ApiKeyListResponse>(`${this.baseUrl}/data`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    async deleteKey(keyId: number): Promise<{ message: string; success: boolean }> {
        return apiFetch<{ message: string; success: boolean }>(`${this.baseUrl}/delete/${keyId}`, {
            method: 'POST',
        });
    }
}

export const apiKeyService = new ApiKeyService();