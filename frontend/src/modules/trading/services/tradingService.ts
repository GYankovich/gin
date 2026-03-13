import { apiFetch } from '../../../core/api';
import type {
    StrategyInfo,
    TradingRobot,
    TradingRobotCreate,
    TradingRobotUpdate,
    RobotTrade,
    ApiToken
} from '../types';

class TradingService {
    private baseUrl = '/robots';

    // Стратегии
    async getStrategies(): Promise<StrategyInfo[]> {
        return apiFetch<StrategyInfo[]>(`${this.baseUrl}/strategies`);
    }

    // Роботы - ВАЖНО: здесь токен автоматически подхватится из store
    async getRobots(): Promise<TradingRobot[]> {
        return apiFetch<TradingRobot[]>(`${this.baseUrl}/`);
    }

    async getRobot(id: number): Promise<TradingRobot> {
        return apiFetch<TradingRobot>(`${this.baseUrl}/${id}`);
    }

    async createRobot(data: TradingRobotCreate): Promise<TradingRobot> {
        return apiFetch<TradingRobot>(`${this.baseUrl}/`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    async updateRobot(id: number, data: TradingRobotUpdate): Promise<TradingRobot> {
        return apiFetch<TradingRobot>(`${this.baseUrl}/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    async deleteRobot(id: number): Promise<void> {
        return apiFetch<void>(`${this.baseUrl}/${id}`, {
            method: 'DELETE',
        });
    }

    async runRobotNow(id: number): Promise<void> {
        return apiFetch<void>(`${this.baseUrl}/${id}/run`, {
            method: 'POST',
        });
    }

    // Сделки робота
    async getRobotTrades(robotId: number): Promise<RobotTrade[]> {
        return apiFetch<RobotTrade[]>(`${this.baseUrl}/${robotId}/trades`);
    }

    // Получение токенов пользователя для выпадающего списка
    async getUserTokens(): Promise<ApiToken[]> {
        return apiFetch<ApiToken[]>('/settings/tokens');
    }

    // Получение счетов для выбранного токена
    async getTokenAccounts(tokenId: number): Promise<any[]> {
        return apiFetch<any[]>(`/portfolio/accounts?token_id=${tokenId}`);
    }
}

export const tradingService = new TradingService();