import type { RobotStats } from '../types';

export class RobotStatsComponent {
    private element: HTMLElement;

    constructor(private stats: RobotStats) {
        this.element = document.createElement('div');
        this.element.className = 'robot-stats';
    }

    render(): HTMLElement {
        const successRate = this.stats.success_rate.toFixed(1);
        const profitColor = this.stats.total_profit >= 0 ? 'green' : 'red';

        this.element.innerHTML = `
            <h3>Статистика</h3>
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-label">Всего сделок</div>
                    <div class="stat-value">${this.stats.total_trades}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Успешных</div>
                    <div class="stat-value">${this.stats.successful_trades}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Успешность</div>
                    <div class="stat-value">${successRate}%</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Общая прибыль</div>
                    <div class="stat-value" style="color: ${profitColor}">
                        ${this.stats.total_profit.toFixed(2)} ₽
                    </div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Средняя прибыль</div>
                    <div class="stat-value">${this.stats.average_profit_per_trade.toFixed(2)} ₽</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Макс. прибыль</div>
                    <div class="stat-value" style="color: green">
                        ${this.stats.biggest_win.toFixed(2)} ₽
                    </div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Макс. убыток</div>
                    <div class="stat-value" style="color: red">
                        ${this.stats.biggest_loss.toFixed(2)} ₽
                    </div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Последняя сделка</div>
                    <div class="stat-value">
                        ${this.stats.last_trade_at ? new Date(this.stats.last_trade_at).toLocaleString() : 'Нет'}
                    </div>
                </div>
            </div>
            
            <h4>Прибыль по дням</h4>
            <div class="daily-chart">
                ${this.stats.trades_by_day.map(day => `
                    <div class="daily-item">
                        <div class="daily-date">${day.date}</div>
                        <div class="daily-profit ${day.profit >= 0 ? 'positive' : 'negative'}">
                            ${day.profit.toFixed(2)} ₽
                        </div>
                        <div class="daily-count">${day.count} сделок</div>
                    </div>
                `).join('')}
            </div>
        `;

        return this.element;
    }
}