// frontend/src/modules/robots/pages/RobotDetailPage.ts
import { robotService } from '../services/robotService';
import { Robot, RobotTrade, RobotLog, RobotStats } from '../types';
import { router } from '../../../core/router';

export class RobotDetailPage {
    private robotId: number;
    private robot: Robot | null = null;
    private trades: RobotTrade[] = [];
    private logs: RobotLog[] = [];
    private stats: RobotStats | null = null;
    private loading: boolean = true;
    private activeTab: 'info' | 'trades' | 'logs' | 'stats' = 'info';
    private container: HTMLElement | null = null;

    constructor(robotId: number) {
        this.robotId = robotId;
    }

    async loadData(): Promise<void> {
        this.loading = true;
        this.render();

        try {
            const [robot, trades, logs, stats] = await Promise.all([
                robotService.getRobot(this.robotId),
                robotService.getRobotTrades(this.robotId, 50),
                robotService.getRobotLogs(this.robotId, 50),
                robotService.getRobotStats(this.robotId)
            ]);
            this.robot = robot;
            this.trades = trades;
            this.logs = logs;
            this.stats = stats;
        } catch (error) {
            console.error('Failed to load robot details:', error);
        } finally {
            this.loading = false;
            this.render();
        }
    }

    private handleBack = (): void => {
        router.navigate('/robots');
    }

    private handleStart = async (): Promise<void> => {
        if (!this.robot) return;
        try {
            await robotService.startRobot(this.robot.id);
            await this.loadData();
        } catch (error) {
            console.error('Failed to start robot:', error);
            alert('Не удалось запустить робота');
        }
    }

    private handleStop = async (): Promise<void> => {
        if (!this.robot) return;
        try {
            await robotService.stopRobot(this.robot.id);
            await this.loadData();
        } catch (error) {
            console.error('Failed to stop robot:', error);
            alert('Не удалось остановить робота');
        }
    }

    private handleEdit = (): void => {
        router.navigate(`/robots/${this.robotId}/edit`);
    }

    private handleDelete = async (): Promise<void> => {
        if (!confirm('Вы уверены, что хотите удалить этого робота?')) {
            return;
        }
        try {
            await robotService.deleteRobot(this.robotId);
            router.navigate('/robots');
        } catch (error) {
            console.error('Failed to delete robot:', error);
            alert('Не удалось удалить робота');
        }
    }

    private setActiveTab = (tab: 'info' | 'trades' | 'logs' | 'stats'): void => {
        this.activeTab = tab;
        this.render();
    }

    private formatDate(dateStr: string | null): string {
        if (!dateStr) return '—';
        return new Date(dateStr).toLocaleString();
    }

    private formatProfit(profit: number): string {
        const sign = profit >= 0 ? '+' : '';
        return `${sign}${profit.toFixed(2)} ₽`;
    }

    private renderInfo(): string {
        if (!this.robot) return '';

        return `
            <div class="robot-info-grid">
                <div class="info-group">
                    <label>Название</label>
                    <div class="info-value">${this.robot.display_name || this.robot.name}</div>
                </div>
                <div class="info-group">
                    <label>Тип</label>
                    <div class="info-value">${this.robot.robot_type === 'trading' ? 'Торговый' : 'Обновление портфеля'}</div>
                </div>
                <div class="info-group">
                    <label>Статус</label>
                    <div class="info-value status-${this.robot.status}">
                        ${this.robot.status === 'active' ? 'Активен' :
            this.robot.status === 'stopped' ? 'Остановлен' :
                this.robot.status === 'error' ? 'Ошибка' : 'Неизвестно'}
                    </div>
                </div>
                <div class="info-group">
                    <label>Создан</label>
                    <div class="info-value">${this.formatDate(this.robot.created_at)}</div>
                </div>
                ${this.robot.started_at ? `
                    <div class="info-group">
                        <label>Запущен</label>
                        <div class="info-value">${this.formatDate(this.robot.started_at)}</div>
                    </div>
                ` : ''}
                ${this.robot.last_error ? `
                    <div class="info-group">
                        <label>Последняя ошибка</label>
                        <div class="info-value error-message">${this.robot.last_error}</div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    private renderTrades(): string {
        if (!this.trades.length) {
            return '<div class="empty-state">Нет сделок</div>';
        }

        return `
            <table class="trades-table">
                <thead>
                    <tr>
                        <th>Время</th>
                        <th>Инструмент</th>
                        <th>Тип</th>
                        <th>Количество</th>
                        <th>Цена</th>
                        <th>Сумма</th>
                        <th>Прибыль</th>
                        <th>Статус</th>
                    </tr>
                </thead>
                <tbody>
                    ${this.trades.map(trade => `
                        <tr class="trade-${trade.status}">
                            <td>${this.formatDate(trade.created_at)}</td>
                            <td>${trade.ticker || trade.figi}</td>
                            <td>${trade.side === 'buy' ? 'Покупка' : 'Продажа'}</td>
                            <td>${trade.quantity}</td>
                            <td>${trade.price.toFixed(2)} ₽</td>
                            <td>${trade.total_amount.toFixed(2)} ₽</td>
                            <td class="${trade.profit && trade.profit >= 0 ? 'profit-positive' : 'profit-negative'}">
                                ${trade.profit ? this.formatProfit(trade.profit) : '—'}
                            </td>
                            <td>${trade.status === 'open' ? 'Открыта' :
            trade.status === 'closed' ? 'Закрыта' : 'Отменена'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    }

    private renderLogs(): string {
        if (!this.logs.length) {
            return '<div class="empty-state">Нет логов</div>';
        }

        return `
            <div class="logs-list">
                ${this.logs.map(log => `
                    <div class="log-entry log-${log.success ? 'success' : 'error'}">
                        <div class="log-header">
                            <span class="log-time">${this.formatDate(log.started_at)}</span>
                            <span class="log-status">${log.success ? '✅' : '❌'}</span>
                            ${log.duration_ms ? `<span class="log-duration">${log.duration_ms}ms</span>` : ''}
                        </div>
                        ${log.error_message ? `
                            <div class="log-error">${log.error_message}</div>
                        ` : ''}
                    </div>
                `).join('')}
            </div>
        `;
    }

    private renderStats(): string {
        if (!this.stats) return '<div class="empty-state">Нет статистики</div>';

        return `
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">${this.stats.total_trades}</div>
                    <div class="stat-label">Всего сделок</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${this.stats.successful_trades}</div>
                    <div class="stat-label">Успешных</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${this.stats.failed_trades}</div>
                    <div class="stat-label">Убыточных</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${this.stats.success_rate.toFixed(1)}%</div>
                    <div class="stat-label">Успешность</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value ${this.stats.total_profit >= 0 ? 'profit-positive' : 'profit-negative'}">
                        ${this.formatProfit(this.stats.total_profit)}
                    </div>
                    <div class="stat-label">Общая прибыль</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${this.stats.average_profit_per_trade.toFixed(2)} ₽</div>
                    <div class="stat-label">Средняя прибыль</div>
                </div>
            </div>

            ${this.stats.trades_by_day.length ? `
                <h3>Сделки по дням</h3>
                <div class="trades-by-day">
                    ${this.stats.trades_by_day.map(day => `
                        <div class="day-stats">
                            <span class="day">${day.date}</span>
                            <span class="count">${day.count} сделок</span>
                            <span class="profit ${day.profit >= 0 ? 'profit-positive' : 'profit-negative'}">
                                ${this.formatProfit(day.profit)}
                            </span>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        `;
    }

    render(container: HTMLElement): void {
        this.container = container;

        if (this.loading) {
            container.innerHTML = '<div class="loading">Загрузка...</div>';
            return;
        }

        if (!this.robot) {
            container.innerHTML = `
                <div class="error-state">
                    <p>Робот не найден</p>
                    <button onclick="router.navigate('/robots')">Вернуться к списку</button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="robot-detail">
                <div class="detail-header">
                    <button class="back-button" id="back-button">← Назад</button>
                    <h1>${this.robot.display_name || this.robot.name}</h1>
                    <div class="header-actions">
                        ${this.robot.status === 'active' ? `
                            <button class="btn-stop" id="stop-button">⏸️ Остановить</button>
                        ` : `
                            <button class="btn-start" id="start-button" ${!this.robot.token_id ? 'disabled' : ''}>
                                ▶️ Запустить
                            </button>
                        `}
                        <button class="btn-edit" id="edit-button">✏️ Редактировать</button>
                        <button class="btn-delete" id="delete-button">🗑️ Удалить</button>
                    </div>
                </div>

                <div class="detail-tabs">
                    <button class="tab ${this.activeTab === 'info' ? 'active' : ''}" data-tab="info">
                        Информация
                    </button>
                    <button class="tab ${this.activeTab === 'trades' ? 'active' : ''}" data-tab="trades">
                        Сделки (${this.trades.length})
                    </button>
                    <button class="tab ${this.activeTab === 'logs' ? 'active' : ''}" data-tab="logs">
                        Логи (${this.logs.length})
                    </button>
                    <button class="tab ${this.activeTab === 'stats' ? 'active' : ''}" data-tab="stats">
                        Статистика
                    </button>
                </div>

                <div class="tab-content">
                    ${this.activeTab === 'info' ? this.renderInfo() : ''}
                    ${this.activeTab === 'trades' ? this.renderTrades() : ''}
                    ${this.activeTab === 'logs' ? this.renderLogs() : ''}
                    ${this.activeTab === 'stats' ? this.renderStats() : ''}
                </div>
            </div>
        `;

        // Добавляем обработчики
        setTimeout(() => {
            document.getElementById('back-button')?.addEventListener('click', this.handleBack);
            document.getElementById('start-button')?.addEventListener('click', this.handleStart);
            document.getElementById('stop-button')?.addEventListener('click', this.handleStop);
            document.getElementById('edit-button')?.addEventListener('click', this.handleEdit);
            document.getElementById('delete-button')?.addEventListener('click', this.handleDelete);

            document.querySelectorAll('.tab').forEach(tab => {
                tab.addEventListener('click', (e) => {
                    const tabName = (e.target as HTMLElement).getAttribute('data-tab') as any;
                    if (tabName) {
                        this.setActiveTab(tabName);
                    }
                });
            });
        }, 0);
    }

    destroy(): void {
        this.container = null;
    }
}