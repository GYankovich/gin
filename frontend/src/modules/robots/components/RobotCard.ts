import { router } from '../../../core/router';
import type { Robot } from '../types';

export class RobotCard {
    private element: HTMLElement;

    constructor(private robot: Robot) {
        this.element = document.createElement('div');
        this.element.className = 'robot-card';
    }

    private getStatusClass(): string {
        switch (this.robot.status) {
            case 'active': return 'status-active';
            case 'error': return 'status-error';
            default: return 'status-stopped';
        }
    }

    private formatProfit(): string {
        const profit = this.robot.total_profit;
        const percent = this.robot.total_profit_percent;
        const sign = profit >= 0 ? '+' : '';
        const color = profit >= 0 ? 'green' : 'red';

        return `<span style="color: ${color}">${sign}${profit.toFixed(2)} ₽ (${sign}${percent.toFixed(2)}%)</span>`;
    }

    render(): HTMLElement {
        const statusClass = this.getStatusClass();

        this.element.innerHTML = `
            <div class="robot-card-header">
                <h3>${this.robot.name}</h3>
                <span class="robot-status ${statusClass}">${this.robot.status}</span>
            </div>
            <div class="robot-card-body">
                <div class="robot-type">Тип: ${this.robot.robot_type}</div>
                <div class="robot-token">
                    Токен: ${this.robot.token?.token_preview || 'Не выбран'}
                </div>
                <div class="robot-stats-preview">
                    <div>Сделок: ${this.robot.total_trades}</div>
                    <div>Прибыль: ${this.formatProfit()}</div>
                </div>
                <div class="robot-description">
                    ${this.robot.description || 'Нет описания'}
                </div>
            </div>
            <div class="robot-card-footer">
                <button class="btn-view" data-id="${this.robot.id}">Подробнее</button>
                <button class="btn-start" data-id="${this.robot.id}" ${this.robot.status === 'active' ? 'disabled' : ''}>
                    ${this.robot.status === 'active' ? 'Запущен' : 'Запустить'}
                </button>
                <button class="btn-stop" data-id="${this.robot.id}" ${this.robot.status !== 'active' ? 'disabled' : ''}>
                    Остановить
                </button>
            </div>
        `;

        // Добавляем обработчики
        const viewBtn = this.element.querySelector('.btn-view');
        viewBtn?.addEventListener('click', () => {
            router.navigate(`/robots/${this.robot.id}`);
        });

        return this.element;
    }
}