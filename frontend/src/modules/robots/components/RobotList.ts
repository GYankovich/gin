// frontend/src/modules/robots/components/RobotList.ts
import { Robot } from '../types';
import { RobotCard } from './RobotCard';

export class RobotList {
    private robots: Robot[];
    private onStart: (id: number) => void;
    private onStop: (id: number) => void;
    private onEdit: (id: number) => void;
    private onDelete: (id: number) => void;
    private onViewDetails: (id: number) => void;
    private loading: boolean;
    private filter: 'all' | 'active' | 'stopped' | 'error';
    private onFilterChange?: (filter: string) => void;
    private container: HTMLElement | null = null;

    private robotCards: Map<number, RobotCard> = new Map();

    constructor(
        robots: Robot[],
        onStart: (id: number) => void,
        onStop: (id: number) => void,
        onEdit: (id: number) => void,
        onDelete: (id: number) => void,
        onViewDetails: (id: number) => void,
        loading: boolean = false,
        filter: 'all' | 'active' | 'stopped' | 'error' = 'all',
        onFilterChange?: (filter: string) => void
    ) {
        this.robots = robots;
        this.onStart = onStart;
        this.onStop = onStop;
        this.onEdit = onEdit;
        this.onDelete = onDelete;
        this.onViewDetails = onViewDetails;
        this.loading = loading;
        this.filter = filter;
        this.onFilterChange = onFilterChange;
    }

    updateProps(props: {
        robots?: Robot[];
        loading?: boolean;
        filter?: 'all' | 'active' | 'stopped' | 'error';
    }): void {
        if (props.robots !== undefined) this.robots = props.robots;
        if (props.loading !== undefined) this.loading = props.loading;
        if (props.filter !== undefined) this.filter = props.filter;
        this.renderContent();
    }

    private getFilteredRobots(): Robot[] {
        return this.robots.filter(robot => {
            if (this.filter === 'all') return true;
            if (this.filter === 'active') return robot.status === 'active';
            if (this.filter === 'stopped') return robot.status === 'stopped';
            if (this.filter === 'error') return robot.status === 'error';
            return true;
        });
    }

    private getStats() {
        return {
            total: this.robots.length,
            active: this.robots.filter(r => r.status === 'active').length,
            stopped: this.robots.filter(r => r.status === 'stopped').length,
            error: this.robots.filter(r => r.status === 'error').length,
            totalProfit: this.robots.reduce((sum, r) => sum + r.total_profit, 0)
        };
    }

    private renderContent(): void {
        if (!this.container) return;

        const filteredRobots = this.getFilteredRobots();
        const stats = this.getStats();
        const statsHtml = `
            <div class="robots-stats">
                <div class="stat-card">
                    <div class="stat-value">${stats.total}</div>
                    <div class="stat-label">Всего роботов</div>
                </div>
                <div class="stat-card active">
                    <div class="stat-value">${stats.active}</div>
                    <div class="stat-label">Активных</div>
                </div>
                <div class="stat-card stopped">
                    <div class="stat-value">${stats.stopped}</div>
                    <div class="stat-label">Остановлено</div>
                </div>
                <div class="stat-card error">
                    <div class="stat-value">${stats.error}</div>
                    <div class="stat-label">С ошибками</div>
                </div>
                <div class="stat-card profit">
                    <div class="stat-value ${stats.totalProfit >= 0 ? 'profit-positive' : 'profit-negative'}">
                        ${stats.totalProfit >= 0 ? '+' : ''}${stats.totalProfit.toFixed(2)} ₽
                    </div>
                    <div class="stat-label">Общая прибыль</div>
                </div>
            </div>
        `;

        const filtersHtml = this.onFilterChange ? `
            <div class="robots-filters">
                <button class="${this.filter === 'all' ? 'active' : ''}" data-filter="all">Все</button>
                <button class="${this.filter === 'active' ? 'active' : ''}" data-filter="active">Активные</button>
                <button class="${this.filter === 'stopped' ? 'active' : ''}" data-filter="stopped">Остановленные</button>
                <button class="${this.filter === 'error' ? 'active' : ''}" data-filter="error">С ошибками</button>
            </div>
        ` : '';

        if (this.loading) {
            this.container.innerHTML = `
                ${statsHtml}
                ${filtersHtml}
                <div class="loading">Загрузка роботов...</div>
            `;
            return;
        }

        if (filteredRobots.length === 0) {
            this.container.innerHTML = `
                ${statsHtml}
                ${filtersHtml}
                <div class="empty-state">
                    <p>Нет роботов для отображения</p>
                    <button id="create-first-robot">Создать первого робота</button>
                </div>
            `;

            setTimeout(() => {
                document.getElementById('create-first-robot')?.addEventListener('click', () => {
                    window.location.href = '/robots/create';
                });
            }, 0);

            return;
        }

        // Очищаем старые карточки
        this.robotCards.clear();

        const robotsGrid = document.createElement('div');
        robotsGrid.className = 'robots-grid';

        filteredRobots.forEach(robot => {
            const cardContainer = document.createElement('div');
            cardContainer.className = 'robot-card-container';

            const card = new RobotCard(
                robot,
                this.onStart,
                this.onStop,
                this.onEdit,
                this.onDelete,
                this.onViewDetails
            );

            card.render(cardContainer);
            this.robotCards.set(robot.id, card);
            robotsGrid.appendChild(cardContainer);
        });

        this.container.innerHTML = `
            ${statsHtml}
            ${filtersHtml}
        `;

        this.container.appendChild(robotsGrid);

        // Добавляем обработчики фильтров
        if (this.onFilterChange) {
            setTimeout(() => {
                document.querySelectorAll('.robots-filters button').forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        const filter = (e.target as HTMLElement).getAttribute('data-filter');
                        if (filter && this.onFilterChange) {
                            this.onFilterChange(filter);
                        }
                    });
                });
            }, 0);
        }
    }

    render(container: HTMLElement): void {
        this.container = container;
        this.renderContent();
    }

    destroy(): void {
        this.robotCards.forEach(card => card.destroy());
        this.robotCards.clear();
        this.container = null;
    }
}