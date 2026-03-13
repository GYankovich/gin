import { tradingService } from '../services/tradingService';
import { router } from '../../../core/router';
import { store } from '../../../core/store';
import type { TradingRobot } from '../types';

export class TradingView {  // ИСПРАВЛЕНО: было TradingCreateView
    private container: HTMLElement;
    private robots: TradingRobot[] = [];
    private loading: boolean = false;
    private error: string | null = null;
    private initialLoadDone: boolean = false;

    constructor(container?: HTMLElement) {
        if (container) this.container = container;
        console.log('📊 TradingView created');
    }

    setContainer(container: HTMLElement): void {
        this.container = container;
    }

    private async loadRobots(): Promise<void> {
        if (this.loading) return;

        try {
            this.loading = true;
            this.error = null;
            this.render();

            console.log('📡 Загрузка списка роботов...');
            const robots = await tradingService.getRobots();
            console.log('✅ Загружено роботов:', robots);
            this.robots = robots;
        } catch (err: any) {
            console.error('❌ Ошибка загрузки роботов:', err);
            this.error = err.message || 'Не удалось загрузить роботов';
        } finally {
            this.loading = false;
            this.initialLoadDone = true;
            this.render();
        }
    }

    private async handleToggleRobot(robot: TradingRobot): Promise<void> {
        try {
            await tradingService.updateRobot(robot.id, { is_active: !robot.is_active });
            await this.loadRobots();
        } catch (err: any) {
            alert('Ошибка при изменении статуса: ' + err.message);
        }
    }

    private async handleDeleteRobot(id: number): Promise<void> {
        if (!confirm('Вы уверены, что хотите удалить робота?')) return;

        try {
            await tradingService.deleteRobot(id);
            await this.loadRobots();
        } catch (err: any) {
            alert('Ошибка при удалении: ' + err.message);
        }
    }

    private async handleRunRobot(id: number): Promise<void> {
        try {
            await tradingService.runRobotNow(id);
            alert('Робот запущен');
            await this.loadRobots();
        } catch (err: any) {
            alert('Ошибка при запуске: ' + err.message);
        }
    }

    private formatProfit(profit: number): string {
        const sign = profit >= 0 ? '+' : '';
        return `${sign}${profit.toFixed(2)} ₽`;
    }

    private formatDate(date: string | null): string {
        if (!date) return 'никогда';
        return new Date(date).toLocaleString('ru-RU');
    }

    render(container?: HTMLElement): void {
        if (container) this.container = container;
        if (!this.container) return;

        // Загружаем данные при первом рендере
        if (!this.initialLoadDone && !this.loading && !this.error) {
            this.initialLoadDone = true;
            this.loadRobots();
        }

        this.container.innerHTML = this.getTemplate();
        this.attachEvents();
    }

    private getTemplate(): string {
        if (this.loading) {
            return `
                <div class="trading-container">
                    <div class="loading-state">
                        <div class="loading-spinner"></div>
                        <p>Загрузка роботов...</p>
                    </div>
                </div>
            `;
        }

        if (this.error) {
            return `
                <div class="trading-container">
                    <div class="error-state">
                        <p class="error-message">${this.error}</p>
                        <button class="button button-primary" id="retry-load">Повторить</button>
                    </div>
                </div>
            `;
        }

        return `
            <div class="trading-container">
                <div class="trading-header">
                    <h1>Торговые роботы</h1>
                    <button class="button button-primary" id="create-robot">
                        <span class="plus-icon">+</span> Создать робота
                    </button>
                </div>

                ${this.robots.length === 0 ? `
                    <div class="empty-state">
                        <p>У вас ещё нет торговых роботов. Создайте первого!</p>
                    </div>
                ` : `
                    <div class="robots-grid">
                        ${this.robots.map(robot => `
                            <div class="robot-card ${robot.is_active ? 'active' : 'inactive'}">
                                <div class="robot-card-header">
                                    <h3>${robot.name}</h3>
                                    <div class="robot-status">
                                        <span class="status-badge ${robot.is_active ? 'active' : 'inactive'}">
                                            ${robot.is_active ? 'Активен' : 'Остановлен'}
                                        </span>
                                    </div>
                                </div>
                                
                                <div class="robot-card-body">
                                    <div class="robot-info">
                                        <div class="info-row">
                                            <span class="info-label">Стратегия:</span>
                                            <span class="info-value">${robot.strategy_name}</span>
                                        </div>
                                        <div class="info-row">
                                            <span class="info-label">Сделок:</span>
                                            <span class="info-value">${robot.total_trades}</span>
                                        </div>
                                        <div class="info-row">
                                            <span class="info-label">Прибыль:</span>
                                            <span class="info-value ${robot.total_profit >= 0 ? 'positive' : 'negative'}">
                                                ${this.formatProfit(robot.total_profit)}
                                            </span>
                                        </div>
                                        <div class="info-row">
                                            <span class="info-label">Последний запуск:</span>
                                            <span class="info-value">${this.formatDate(robot.last_run_at)}</span>
                                        </div>
                                    </div>

                                    <div class="robot-params">
                                        <div class="param-item">
                                            <span class="param-label">Размер позиции</span>
                                            <span class="param-value">${robot.max_position_size_percent}%</span>
                                        </div>
                                        <div class="param-item">
                                            <span class="param-label">Стоп-лосс</span>
                                            <span class="param-value">${robot.stop_loss_percent}%</span>
                                        </div>
                                        ${robot.schedule_cron ? `
                                            <div class="param-item">
                                                <span class="param-label">Расписание</span>
                                                <span class="param-value">${robot.schedule_cron}</span>
                                            </div>
                                        ` : ''}
                                    </div>
                                </div>

                                <div class="robot-card-footer">
                                    <button class="button button-outline" data-run-id="${robot.id}">
                                        ▶ Запустить
                                    </button>
                                    <button class="button button-outline" data-view-id="${robot.id}">
                                        👁 Детали
                                    </button>
                                    <button class="button button-outline" data-toggle-id="${robot.id}">
                                        ${robot.is_active ? '⏸ Остановить' : '▶ Запустить'}
                                    </button>
                                    <button class="button button-danger" data-delete-id="${robot.id}">
                                        🗑
                                    </button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `}
            </div>
        `;
    }

    private attachEvents(): void {
        const createBtn = document.getElementById('create-robot');
        createBtn?.addEventListener('click', () => {
            router.navigate('/trading/create');
        });

        document.querySelectorAll('[data-run-id]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const id = (e.currentTarget as HTMLElement).dataset.runId;
                if (id) {
                    await this.handleRunRobot(parseInt(id));
                }
            });
        });

        document.querySelectorAll('[data-view-id]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = (e.currentTarget as HTMLElement).dataset.viewId;
                if (id) {
                    router.navigate(`/trading/${id}`);
                }
            });
        });

        document.querySelectorAll('[data-toggle-id]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const id = (e.currentTarget as HTMLElement).dataset.toggleId;
                if (id) {
                    const robot = this.robots.find(r => r.id === parseInt(id));
                    if (robot) await this.handleToggleRobot(robot);
                }
            });
        });

        document.querySelectorAll('[data-delete-id]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const id = (e.currentTarget as HTMLElement).dataset.deleteId;
                if (id) await this.handleDeleteRobot(parseInt(id));
            });
        });

        const retryBtn = document.getElementById('retry-load');
        retryBtn?.addEventListener('click', () => {
            this.initialLoadDone = false;
            this.loadRobots();
        });
    }
}