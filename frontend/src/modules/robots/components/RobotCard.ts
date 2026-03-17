// frontend/src/modules/robots/components/RobotCard.ts
import { Robot } from '../types';

export class RobotCard {
    private robot: Robot;
    private onStart: (id: number) => void;
    private onStop: (id: number) => void;
    private onEdit: (id: number) => void;
    private onDelete: (id: number) => void;
    private onViewDetails: (id: number) => void;
    private container: HTMLElement | null = null;

    constructor(
        robot: Robot,
        onStart: (id: number) => void,
        onStop: (id: number) => void,
        onEdit: (id: number) => void,
        onDelete: (id: number) => void,
        onViewDetails: (id: number) => void
    ) {
        this.robot = robot;
        this.onStart = onStart;
        this.onStop = onStop;
        this.onEdit = onEdit;
        this.onDelete = onDelete;
        this.onViewDetails = onViewDetails;
    }

    private getStatusIcon(): string {
        switch (this.robot.status) {
            case 'active': return '🟢';
            case 'stopped': return '⏸️';
            case 'error': return '🔴';
            default: return '⚪';
        }
    }

    private getStatusText(): string {
        switch (this.robot.status) {
            case 'active': return 'Активен';
            case 'stopped': return 'Остановлен';
            case 'error': return `Ошибка${this.robot.last_error ? ': ' + this.robot.last_error.substring(0, 50) + '...' : ''}`;
            default: return 'Неизвестно';
        }
    }

    private formatProfit(profit: number): string {
        const sign = profit >= 0 ? '+' : '';
        return `${sign}${profit.toFixed(2)} ₽`;
    }

    private formatDate(dateStr: string | null): string {
        if (!dateStr) return '—';
        return new Date(dateStr).toLocaleString();
    }

    render(container: HTMLElement): void {
        this.container = container;
        const profitClass = this.robot.total_profit >= 0 ? 'profit-positive' : 'profit-negative';

        container.innerHTML = `
            <div class="robot-card ${this.robot.status}" data-robot-id="${this.robot.id}">
                <div class="robot-card-header">
                    <div class="robot-title">
                        <span class="status-icon">${this.getStatusIcon()}</span>
                        <h3>${this.robot.display_name || this.robot.name}</h3>
                    </div>
                    <div class="robot-type">
                        ${this.robot.robot_type === 'trading' ? 'Торговый' : 'Обновление портфеля'}
                    </div>
                </div>

                <div class="robot-card-body">
                    <div class="robot-status" title="${this.robot.last_error || ''}">
                        ${this.getStatusText()}
                    </div>

                    ${this.robot.robot_type === 'trading' ? `
                        <div class="robot-stats">
                            <div class="stat">
                                <span class="stat-label">Сделок:</span>
                                <span class="stat-value">${this.robot.total_trades}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Успешных:</span>
                                <span class="stat-value">${this.robot.successful_trades}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Прибыль:</span>
                                <span class="stat-value ${profitClass}">
                                    ${this.formatProfit(this.robot.total_profit)}
                                </span>
                            </div>
                        </div>
                    ` : ''}

                    <div class="robot-times">
                        <div class="time">
                            <span>Создан:</span>
                            ${this.formatDate(this.robot.created_at)}
                        </div>
                        ${this.robot.last_heartbeat_at ? `
                            <div class="time">
                                <span>Последняя активность:</span>
                                ${this.formatDate(this.robot.last_heartbeat_at)}
                            </div>
                        ` : ''}
                    </div>
                </div>

                <div class="robot-card-actions">
                    ${this.robot.status === 'active' ? `
                        <button class="btn-stop" data-action="stop" title="Остановить">⏸️</button>
                    ` : `
                        <button class="btn-start" data-action="start" title="Запустить" ${!this.robot.token_id ? 'disabled' : ''}>
                            ▶️
                        </button>
                    `}
                    <button class="btn-edit" data-action="edit" title="Редактировать">✏️</button>
                    <button class="btn-delete" data-action="delete" title="Удалить">🗑️</button>
                </div>

                ${!this.robot.token_id ? `
                    <div class="robot-warning">Нет токена доступа</div>
                ` : ''}
            </div>
        `;

        // Добавляем обработчики событий
        setTimeout(() => {
            const card = container.querySelector('.robot-card');
            const startBtn = container.querySelector('[data-action="start"]');
            const stopBtn = container.querySelector('[data-action="stop"]');
            const editBtn = container.querySelector('[data-action="edit"]');
            const deleteBtn = container.querySelector('[data-action="delete"]');

            card?.addEventListener('click', (e) => {
                // Не открываем детали при клике на кнопки
                const target = e.target as HTMLElement;
                if (target.closest('button')) return;
                this.onViewDetails(this.robot.id);
            });

            startBtn?.addEventListener('click', (e) => {
                e.stopPropagation();
                this.onStart(this.robot.id);
            });

            stopBtn?.addEventListener('click', (e) => {
                e.stopPropagation();
                this.onStop(this.robot.id);
            });

            editBtn?.addEventListener('click', (e) => {
                e.stopPropagation();
                this.onEdit(this.robot.id);
            });

            deleteBtn?.addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm('Вы уверены, что хотите удалить этого робота?')) {
                    this.onDelete(this.robot.id);
                }
            });
        }, 0);
    }

    destroy(): void {
        this.container = null;
    }
}