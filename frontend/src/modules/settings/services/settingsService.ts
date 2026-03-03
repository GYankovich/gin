import { apiFetch } from '../../../core/api';
import type { TInvestSettingsOut, TInvestSettingsIn } from '../types';

class SettingsService {
    async getTInvestSettings(): Promise<TInvestSettingsOut> {
        return apiFetch<TInvestSettingsOut>('/settings/tinvest', {
            token: localStorage.getItem('auth_token'),
        });
    }

    async saveTInvestToken(token: string): Promise<void> {
        return apiFetch<void>('/settings/tinvest', {
            method: 'POST',
            body: JSON.stringify({ api_token: token } as TInvestSettingsIn),
            token: localStorage.getItem('auth_token'),
        });
    }
}

export const settingsService = new SettingsService();