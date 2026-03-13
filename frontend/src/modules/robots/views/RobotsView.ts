import { router } from '../../../core/router';
import { store } from '../../../core/store';
import { robotService } from '../services/robotService';
import { RobotCard } from '../components/RobotCard';
import type { Robot } from '../types';

export class RobotsView {
    private container: HTMLElement;
    private robots: Robot[] = [];
    private isLoading = true;
    private filter: 'all' | 'active' | 'stopped' | 'error' = 'all';

    constructor() {
        this.container = document.getElementById('app')!;
    }

    private async loadRobots() {
        try {
            this.isLoading = true;
            this.render();

            const response = await robotService.getRobots(this.filter !== 'all');
            this.robots = response.items;

            this.isLoading = false;
            this.render();
        } catch (error) {
            console.error('Failed to load robots:', error);
            this.isLoading = false;
            this.render();
        }
    }

    private renderRobotsList(): string {
        if (this.isLoading) {
            return '<div class="loading">Загрузка роботов...</div>';
        }

        if (this.robots.length === 0) {
            return `
                <div class="empty-state">
                    <p>У вас пока нет торговых роботов</p>
                    <button class="btn-primary" id="create-first-robot">Создать первого робота</button>
                </div>
            `;
        }

        return `
            <div class="robots-grid">
                ${this.robots.map(robot => {
            const card = new RobotCard(robot);
            return card.render().outerHTML;
        }).join('')}
            </div>
        `;
    }

    render() {
        this.container.innerHTML = `
            <div class="robots-view">
                <div class="view-header">
                    <h1>Торговые роботы</h1>
                    <button class="btn-primary" id="create-robot">+ Создать робота</button>
                </div>
                
                <div class="filters">
                    <button class="filter-btn ${this.filter === 'all' ? 'active' : ''}" data-filter="all">Все</button>
                    <button class="filter-btn ${this.filter === 'active' ? 'active' : ''}" data-filter="active">Активные</button>
                    <button class="filter-btn ${this.filter === 'stopped' ? 'active' : ''}" data-filter="stopped">Остановленные</button>
                    <button class="filter-btn ${this.filter === 'error' ? 'active' : ''}" data-filter="error">Ошибки</button>
                </div>

                ${this.renderRobotsList()}
            </div>
        `;

        // Добавляем обработчики
        document.getElementById('create-robot')?.addEventListener('click', () => {
            router.navigate('/robots/create');
        });

        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const filter = (e.target as HTMLElement).dataset.filter as any;
                if (filter) {
                    this.filter = filter;
                    this.loadRobots();
                }
            });
        });

        // Загружаем роботов
        this.loadRobots();
    }
}