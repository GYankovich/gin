import { apiFetch } from '../../../core/api';
import type {
    Robot, RobotCreate, RobotUpdate,
    RobotTrade, RobotLog, RobotStats, AvailableToken
} from '../types';

export class RobotService {
    private baseUrl = '/api/robots';

    // --- Управление роботами ---

    async getRobots(includeInactive: boolean = false, robotType?: string): Promise<{total: number, items: Robot[]}> {
        const params = new URLSearchParams();
        if (includeInactive) params.append('include_inactive', 'true');
        if (robotType) params.append('robot_type', robotType);

        return apiFetch(`${this.baseUrl}?${params.toString()}`);
    }

    async getRobot(id: number): Promise<Robot> {
        return apiFetch(`${this.baseUrl}/${id}`);
    }

    async createRobot(data: RobotCreate): Promise<Robot> {
        return apiFetch(this.baseUrl, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updateRobot(id: number, data: RobotUpdate): Promise<Robot> {
        return apiFetch(`${this.baseUrl}/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    async deleteRobot(id: number): Promise<void> {
        return apiFetch(`${this.baseUrl}/${id}`, {
            method: 'DELETE'
        });
    }

    // --- Управление состоянием ---

    async startRobot(id: number): Promise<Robot> {
        return apiFetch(`${this.baseUrl}/${id}/start`, {
            method: 'POST'
        });
    }

    async stopRobot(id: number): Promise<Robot> {
        return apiFetch(`${this.baseUrl}/${id}/stop`, {
            method: 'POST'
        });
    }

    // --- Сделки и логи ---

    async getRobotTrades(id: number, limit: number = 100): Promise<RobotTrade[]> {
        return apiFetch(`${this.baseUrl}/${id}/trades?limit=${limit}`);
    }

    async getRobotLogs(id: number, level?: string, limit: number = 100): Promise<RobotLog[]> {
        const params = new URLSearchParams();
        if (level) params.append('level', level);
        params.append('limit', limit.toString());

        return apiFetch(`${this.baseUrl}/${id}/logs?${params.toString()}`);
    }

    async getRobotStats(id: number): Promise<RobotStats> {
        return apiFetch(`${this.baseUrl}/${id}/stats`);
    }

    // --- Токены ---

    async getAvailableTokens(): Promise<AvailableToken[]> {
        return apiFetch(`${this.baseUrl}/available-tokens`);
    }
}

export const robotService = new RobotService();