import { analyticsService } from '../../analytics/services/analyticsService';
import { showToast } from '../../../shared/components/Toast';
import type { RobotMetrics, RobotTradeItem } from '../../analytics/types';

export class RobotAnalyticsPage {
    private container!: HTMLElement;
    private robotId: number;
    private metrics: RobotMetrics | null = null;
    private trades: RobotTradeItem[] = [];
    private error: string | null = null;

    constructor(robotId: number) {
        this.robotId = robotId;
    }

    async render(container: HTMLElement): Promise<void> {
        this.container = container;
        this.container.innerHTML = this.tplLoading();
        await this.loadData();
    }

    private async loadData(): Promise<void> {
        try {
            const resp = await analyticsService.getRobotMetrics(this.robotId);
            this.metrics = resp.metrics;
            this.trades = resp.recent_trades;
        } catch (err: any) {
            this.error = err.message || 'Не удалось загрузить метрики';
            showToast({ message: this.error!, type: 'error' });
        } finally {
            this.container.innerHTML = this.getTemplate();
        }
    }

    private getTemplate(): string {
        if (this.error) return this.tplError();
        if (!this.metrics) return this.tplEmpty();
        return this.tplMain();
    }

    private tplLoading = () => `
        <div class="av-center">
            <div class="skeleton-pulse" style="width:60px;height:60px;border-radius:50%;margin:0 auto 16px"></div>
            <p style="color:var(--text-muted)">Загрузка метрик робота...</p>
        </div>`;

    private tplError = () => `
        <div class="av-center">
            <p style="color:var(--color-danger)">${this.error}</p>
        </div>`;

    private tplEmpty = () => `
        <div class="av-center">
            <p style="color:var(--text-muted)">Нет данных по сделкам робота</p>
        </div>`;

    private tplMain(): string {
        const m = this.metrics!;
        return `
        <div class="av-page">
            <div class="av-header">
                <h1 class="av-title">Робот #${m.robot_id} — Аналитика</h1>
            </div>

            <div class="kpi-grid">
                ${this.kpi('Всего сделок', m.total_trades)}
                ${this.kpi('Открытых', m.open_trades)}
                ${this.kpi('Закрытых', m.closed_trades)}
                ${this.kpi('Win Rate', m.win_rate != null ? m.win_rate + '%' : '—', m.win_rate != null && m.win_rate >= 50 ? 'text-success' : 'text-danger')}
                ${this.kpi('Итого PnL', this.fmt(m.total_pnl), m.total_pnl >= 0 ? 'text-success' : 'text-danger')}
                ${this.kpi('Ср. прибыль', m.avg_profit != null ? this.fmt(m.avg_profit) : '—', 'text-success')}
                ${this.kpi('Ср. убыток', m.avg_loss != null ? this.fmt(m.avg_loss) : '—', 'text-danger')}
                ${this.kpi('Лучшая', m.best_trade != null ? this.fmt(m.best_trade) : '—', 'text-success')}
                ${this.kpi('Худшая', m.worst_trade != null ? this.fmt(m.worst_trade) : '—', 'text-danger')}
                ${this.kpi('Max Drawdown', m.max_drawdown != null ? this.fmt(m.max_drawdown) : '—', 'text-danger')}
                ${this.kpi('Profit Factor', m.profit_factor != null ? m.profit_factor.toFixed(2) : '—')}
                ${this.kpi('Ср. длительность', m.avg_trade_duration_hours != null ? m.avg_trade_duration_hours.toFixed(1) + 'ч' : '—')}
            </div>

            <div class="card" style="margin-top:var(--space-xl);padding:var(--space-lg)">
                <h3 style="margin:0 0 var(--space-md);font-size:1rem;color:var(--text-primary)">Последние сделки</h3>
                ${this.trades.length ? this.renderTradesTable() : '<p class="live-empty">Нет сделок</p>'}
            </div>
        </div>`;
    }

    private kpi(label: string, value: string | number, cls = ''): string {
        return `
        <div class="kpi-tile">
            <span class="kpi-label">${label}</span>
            <span class="kpi-value ${cls}">${value}</span>
        </div>`;
    }

    private renderTradesTable(): string {
        const rows = this.trades.map(t => {
            const sideClass = t.side === 'buy' ? 'badge-success' : 'badge-danger';
            const profitClass = t.profit != null ? (t.profit >= 0 ? 'text-success' : 'text-danger') : '';
            return `
            <tr>
                <td><span class="badge ${sideClass}">${t.side.toUpperCase()}</span></td>
                <td class="text-mono" style="font-size:0.8rem">${t.figi.slice(0, 12)}</td>
                <td class="text-mono">${t.quantity}</td>
                <td class="text-mono">${t.entry_price?.toFixed(2) ?? '—'}</td>
                <td class="text-mono">${t.exit_price?.toFixed(2) ?? '—'}</td>
                <td class="text-mono ${profitClass}">${t.profit != null ? this.fmt(t.profit) : '—'}</td>
                <td><span class="badge ${t.status === 'closed' ? 'badge-info' : t.status === 'open' ? 'badge-success' : 'badge-warning'}">${t.status}</span></td>
                <td style="font-size:0.75rem;color:var(--text-muted)">${t.created_at ? new Date(t.created_at).toLocaleString('ru-RU') : ''}</td>
            </tr>`;
        }).join('');

        return `
        <div style="overflow-x:auto">
            <table class="ra-table">
                <thead>
                    <tr>
                        <th>Side</th><th>FIGI</th><th>Qty</th><th>Entry</th><th>Exit</th><th>Profit</th><th>Status</th><th>Date</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    }

    private fmt(v: number): string {
        return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(v);
    }
}
