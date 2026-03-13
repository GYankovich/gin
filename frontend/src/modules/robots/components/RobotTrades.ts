import type { RobotTrade } from '../types';

export class RobotTradesComponent {
    private element: HTMLElement;

    constructor(private trades: RobotTrade[]) {
        this.element = document.createElement('div');
        this.element.className = 'robot-trades';
    }

    private formatProfit(profit: number | null): string {
        if (profit === null) return '—';
        const sign = profit >= 0 ? '+' : '';
        const color = profit >= 0 ? 'green' : 'red';
        return `<span style="color: ${color}">${sign}${profit.toFixed(2)}</span>`;
    }

    render(): HTMLElement {
        this.element.innerHTML = `
            <h3>Последние сделки</h3>
            <table class="trades-table">
                <thead>
                    <tr>
                        <th>Время</th>
                        <th>Инструмент</th>
                        <th>Тип</th>
                        <th>Направление</th>
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
                            <td>${new Date(trade.created_at).toLocaleString()}</td>
                            <td>${trade.ticker || trade.figi}</td>
                            <td>${trade.instrument_type}</td>
                            <td class="trade-${trade.side}">${trade.side === 'buy' ? 'Покупка' : 'Продажа'}</td>
                            <td>${trade.quantity}</td>
                            <td>${trade.price.toFixed(2)} ₽</td>
                            <td>${trade.total_amount.toFixed(2)} ₽</td>
                            <td>${this.formatProfit(trade.profit)} ₽</td>
                            <td>${trade.status === 'open' ? 'Открыта' : trade.status === 'closed' ? 'Закрыта' : 'Отменена'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;

        return this.element;
    }
}