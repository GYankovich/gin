// frontend/src/modules/robots/services/robotService.ts
import { apiFetch } from '../../../core/api';
import type {
    Robot,
    RobotCreate,
    RobotUpdate,
    RobotListResponse,
    RobotTrade,
    RobotLog,
    StrategyInfo,
    AvailableToken,
    RobotLogListResponse
} from '../types';

// Тип для ответа от /api/apikey/data
interface ApiKeyResponse {
    id: number;
    name: string | null;
    key_type: string;
    is_active: boolean;
    created_at: string;
    masked_token: string;
}

interface ApiKeyListResponse {
    keys: ApiKeyResponse[];
    total: number;
    limit: number;
    offset: number;
}

interface RobotListItem {
    id: number;
    name: string;
    token_type: string | null;
    type: number;
    status_name: string;
    last_started: string | null;
    last_error: string | null;
}

interface RobotListResponse {
    total: number;
    items: RobotListItem[];
}

export class RobotService {
    private baseUrl = '/robots';

    /**
     * Получение списка роботов пользователя - POST /api/robots/data
     * @param includeInactive - включать неактивных роботов
     */
    async getRobots(includeInactive = false): Promise<RobotListResponse> {
        const url = `${this.baseUrl}/data`;
        const body = { include_inactive: includeInactive };

        console.log(`🔍 API Request: POST ${url}`, body);

        try {
            const response = await apiFetch<RobotListResponse>(url, {
                method: 'POST',
                body: JSON.stringify(body)
            });
            console.log('📦 API Response:', response);
            return response;
        } catch (error) {
            console.error('❌ API Error in getRobots:', error);
            throw error;
        }
    }

    /**
     * Создание нового робота - POST /api/robots/create
     * @param data - данные для создания
     */
    async createRobot(data: RobotCreate): Promise<Robot> {
        const url = `${this.baseUrl}/create`;
        console.log(`🔍 API Request: POST ${url}`, data);

        try {
            const response = await apiFetch<Robot>(url, {
                method: 'POST',
                body: JSON.stringify(data),
            });
            console.log('📦 API Response:', response);
            return response;
        } catch (error) {
            console.error('❌ API Error in createRobot:', error);
            throw error;
        }
    }

    /**
     * Получение информации о конкретном роботе
     * @param id - ID робота
     */
    async getRobot(id: number): Promise<Robot> {
        const url = `${this.baseUrl}/data/${id}`;
        console.log(`🔍 API Request: GET ${url}`);

        try {
            const response = await apiFetch<Robot>(url, {
                method: 'GET'
            });
            console.log('📦 API Response:', response);
            return response;
        } catch (error) {
            console.error(`❌ API Error in getRobot ${id}:`, error);
            throw error;
        }
    }

    /**
     * Обновление робота - POST /api/robots/update/{id}
     * @param id - ID робота
     * @param data - данные для обновления
     */
    async updateRobot(id: number, data: RobotUpdate): Promise<Robot> {
        const url = `${this.baseUrl}/update/${id}`;
        console.log(`🔍 API Request: POST ${url}`, data);

        try {
            const response = await apiFetch<Robot>(url, {
                method: 'POST',
                body: JSON.stringify(data),
            });
            console.log('📦 API Response:', response);
            return response;
        } catch (error) {
            console.error(`❌ API Error in updateRobot ${id}:`, error);
            throw error;
        }
    }

    /**
     * Удаление (деактивация) робота - POST /api/robots/delete/{id}
     * @param id - ID робота
     */
    async deleteRobot(id: number): Promise<void> {
        const url = `${this.baseUrl}/delete/${id}`;
        console.log(`🔍 API Request: POST ${url}`);

        try {
            await apiFetch<void>(url, {
                method: 'POST',
            });
            console.log(`✅ Robot ${id} deleted successfully`);
        } catch (error) {
            console.error(`❌ API Error in deleteRobot ${id}:`, error);
            throw error;
        }
    }

    // === Управление состоянием ===

    /**
     * Запуск робота - POST /api/robots/{id}/start
     * @param id - ID робота
     */
    async startRobot(id: number): Promise<Robot> {
        const url = `${this.baseUrl}/${id}/start`;
        console.log(`🔍 API Request: POST ${url}`);

        try {
            const response = await apiFetch<Robot>(url, {
                method: 'POST',
            });
            console.log(`✅ Robot ${id} started:`, response);
            return response;
        } catch (error) {
            console.error(`❌ API Error in startRobot ${id}:`, error);
            throw error;
        }
    }

    /**
     * Остановка робота - POST /api/robots/{id}/stop
     * @param id - ID робота
     */
    async stopRobot(id: number): Promise<Robot> {
        const url = `${this.baseUrl}/${id}/stop`;
        console.log(`🔍 API Request: POST ${url}`);

        try {
            const response = await apiFetch<Robot>(url, {
                method: 'POST',
            });
            console.log(`✅ Robot ${id} stopped:`, response);
            return response;
        } catch (error) {
            console.error(`❌ API Error in stopRobot ${id}:`, error);
            throw error;
        }
    }

    // === Стратегии ===

    /**
     * Получение списка доступных стратегий
     */
    async getStrategies(): Promise<StrategyInfo[]> {
        const url = `${this.baseUrl}/strategies`;
        console.log(`🔍 API Request: GET ${url}`);

        try {
            const response = await apiFetch<{ items: StrategyInfo[] } | StrategyInfo[]>(url, {
                method: 'GET',
            });
            console.log('📦 Strategies:', response);
            if (Array.isArray(response)) {
                return response;
            }
            return response?.items || [];
        } catch (error) {
            console.error('❌ API Error in getStrategies:', error);
            return [];
        }
    }

    /**
     * Получение информации о конкретной стратегии
     * @param name - название стратегии
     */
    async getStrategyInfo(name: string): Promise<StrategyInfo> {
        const url = `${this.baseUrl}/strategies/${encodeURIComponent(name)}`;
        console.log(`🔍 API Request: GET ${url}`);

        try {
            const response = await apiFetch<StrategyInfo>(url, {
                method: 'GET'
            });
            console.log('📦 Strategy info:', response);
            return response;
        } catch (error) {
            console.error(`❌ API Error in getStrategyInfo ${name}:`, error);
            throw error;
        }
    }

    // === Токены (через /api/apikey/data) ===

    /**
     * Получение списка доступных токенов через /api/apikey/data
     */
    async getAvailableTokens(): Promise<AvailableToken[]> {
        const url = `/apikey/data`;
        const body = {
            include_inactive: true,
            limit: 100
        };

        console.log(`🔍 API Request: POST ${url}`, body);

        try {
            const response = await apiFetch<ApiKeyListResponse>(url, {
                method: 'POST',
                body: JSON.stringify(body)
            });
            console.log('📦 API Keys response:', response);

            // Преобразуем ответ в формат AvailableToken
            if (response && response.keys) {
                return response.keys.map((key: ApiKeyResponse) => ({
                    id: key.id,
                    token_name: key.name,
                    token_preview: key.masked_token,
                    last_used_at: key.last_used_at
                }));
            }

            return [];
        } catch (error) {
            console.error('❌ API Error in getAvailableTokens:', error);
            return [];
        }
    }

    // === Сделки и логи ===

    /**
     * Получение сделок робота
     * @param robotId - ID робота
     * @param limit - лимит записей
     * @param status - фильтр по статусу
     */
    async getRobotTrades(
        robotId: number,
        limit = 100,
        status?: string
    ): Promise<RobotTrade[]> {
        let url = `${this.baseUrl}/${robotId}/trades?limit=${limit}`;
        if (status) {
            url += `&status=${status}`;
        }
        console.log(`🔍 API Request: GET ${url}`);

        try {
            const response = await apiFetch<RobotTrade[]>(url, {
                method: 'GET'
            });
            console.log(`📦 Trades for robot ${robotId}:`, response);
            return response;
        } catch (error) {
            console.error(`❌ API Error in getRobotTrades ${robotId}:`, error);
            return [];
        }
    }

    /**
     * Получение логов робота
     * @param robotId - ID робота
     * @param limit - лимит записей
     * @param level - фильтр по уровню
     */
    async getRobotLogs(
        robotId: number,
        limit = 100,
        level?: string
    ): Promise<RobotLog[]> {
        let url = `${this.baseUrl}/${robotId}/logs?limit=${limit}`;
        if (level) {
            url += `&level=${level}`;
        }
        console.log(`🔍 API Request: GET ${url}`);

        try {
            const response = await apiFetch<RobotLog[]>(url, {
                method: 'GET'
            });
            console.log(`📦 Logs for robot ${robotId}:`, response);
            return response;
        } catch (error) {
            console.error(`❌ API Error in getRobotLogs ${robotId}:`, error);
            return [];
        }
    }


    // === Логи (общие) ===

    /**
     * Получение общих логов роботов
     * @param robotName - фильтр по имени робота
     * @param limit - лимит записей
     * @param offset - смещение
     */
    async getLogs(
        robotName?: string,
        limit = 100,
        offset = 0
    ): Promise<RobotLogListResponse> {
        let url = `${this.baseUrl}/logs?limit=${limit}&offset=${offset}`;
        if (robotName) {
            url += `&robot_name=${encodeURIComponent(robotName)}`;
        }
        console.log(`🔍 API Request: GET ${url}`);

        try {
            const response = await apiFetch<RobotLogListResponse>(url, {
                method: 'GET'
            });
            console.log('📦 Logs:', response);
            return response;
        } catch (error) {
            console.error('❌ API Error in getLogs:', error);
            return { total: 0, logs: [], limit, offset };
        }
    }

    /**
     * Получение статистики по логам
     */
    async getLogStats(): Promise<any> {
        const url = `${this.baseUrl}/logs/stats`;
        console.log(`🔍 API Request: GET ${url}`);

        try {
            const response = await apiFetch(url, {
                method: 'GET'
            });
            console.log('📦 Log stats:', response);
            return response;
        } catch (error) {
            console.error('❌ API Error in getLogStats:', error);
            return [];
        }
    }

    // === Специальные эндпоинты ===

    /**
     * Ручной запуск обновления портфеля
     * @param tokenId - ID токена (опционально)
     */
    async runPortfolioUpdater(tokenId?: number): Promise<any> {
        let url = `${this.baseUrl}/portfolio-updater/run`;
        if (tokenId) {
            url += `?token_id=${tokenId}`;
        }
        console.log(`🔍 API Request: POST ${url}`);

        try {
            const response = await apiFetch(url, {
                method: 'POST',
                body: JSON.stringify({})
            });
            console.log('📦 Portfolio updater result:', response);
            return response;
        } catch (error) {
            console.error('❌ API Error in runPortfolioUpdater:', error);
            throw error;
        }
    }

    /**
     * Запуск торгового робота (для тестирования)
     * @param robotId - ID робота
     */
    async startTradingRobot(robotId: number): Promise<any> {
        const url = `${this.baseUrl}/trading/start/${robotId}`;
        console.log(`🔍 API Request: POST ${url}`);

        try {
            const response = await apiFetch(url, {
                method: 'POST',
                body: JSON.stringify({})
            });
            console.log(`📦 Trading robot ${robotId} result:`, response);
            return response;
        } catch (error) {
            console.error(`❌ API Error in startTradingRobot ${robotId}:`, error);
            throw error;
        }
    }

    // === Планировщик ===

    /**
     * Получение статуса планировщика
     */
    async getSchedulerStatus(): Promise<{ running: boolean; next_check: string }> {
        const url = `${this.baseUrl}/scheduler/status`;
        console.log(`🔍 API Request: GET ${url}`);

        try {
            const response = await apiFetch<{ running: boolean; next_check: string }>(url, {
                method: 'GET'
            });
            console.log('📦 Scheduler status:', response);
            return response;
        } catch (error) {
            console.error('❌ API Error in getSchedulerStatus:', error);
            throw error;
        }
    }

    /**
     * Принудительный запуск обновления планировщиком
     * @param tokenId - ID токена (опционально)
     */
    async forceSchedulerUpdate(tokenId?: number): Promise<any> {
        let url = `${this.baseUrl}/scheduler/force-update`;
        if (tokenId) {
            url += `?token_id=${tokenId}`;
        }
        console.log(`🔍 API Request: POST ${url}`);

        try {
            const response = await apiFetch(url, {
                method: 'POST',
                body: JSON.stringify({})
            });
            console.log('📦 Force update result:', response);
            return response;
        } catch (error) {
            console.error('❌ API Error in forceSchedulerUpdate:', error);
            throw error;
        }
    }
}

// Создаем и экспортируем единственный экземпляр сервиса
export const robotService = new RobotService();