import { analyticsService } from '../services/analyticsService';
import { router } from '../../../core/router';
import { store } from '../../../core/store';
import { apiFetch } from '../../../core/api';
import { createChart, AreaSeries, IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import type { OverallSummary, AccountDetail, AccountSummary } from '../types';

export class AnalyticsView {
    private container!: HTMLElement;
    private summary: OverallSummary | null = null;
    private accounts: AccountSummary[] = [];
    private selectedAccountId: number | null = null;
    private accountDetail: AccountDetail | null = null;
    private loading = false;
    private loadingDetail = false;
    private refreshing = false;
    private error: string | null = null;
    private historyDays = 30;

    private lwChart: IChartApi | null = null;
    private areaSeries: ISeriesApi<'Area'> | null = null as any;
    private resizeObserver: ResizeObserver | null = null;
    private initialLoadStarted = false;

    render(container?: HTMLElement): void {
        if (container) this.container = container;
        if (!this.container) return;

        if (!this.initialLoadStarted && !this.summary && !this.loading && !this.error) {
            this.initialLoadStarted = true;
            this.loadSummary();
        }

        this.container.innerHTML = this.getTemplate();
        this.attachEvents();

        if (this.accountDetail) {
            requestAnimationFrame(() => this.renderLWChart());
        }
    }

    /* ---- data ---- */

    private async loadSummary(): Promise<void> {
        if (this.loading || this.summary) return;
        try {
            this.loading = true;
            this.error = null;
            this.render();

            this.summary = await analyticsService.getOverallSummary();
            this.accounts = this.summary.accounts;
            this.loading = false;
            this.render();

            if (this.accounts.length > 0 && !this.selectedAccountId) {
                this.selectedAccountId = this.accounts[0].id;
                await this.loadAccountDetail(this.selectedAccountId);
            }
        } catch (err: any) {
            this.error = err.message || 'Не удалось загрузить данные';
            this.loading = false;
            this.render();
        }
    }

    private async loadAccountDetail(accountId: number): Promise<void> {
        try {
            this.loadingDetail = true;
            this.error = null;
            this.render();
            this.accountDetail = await analyticsService.getAccountDetail(accountId);
            if (this.historyDays !== 30) await this.loadHistory();
        } catch (err: any) {
            this.error = err.message || 'Не удалось загрузить детали портфеля';
        } finally {
            this.loadingDetail = false;
            this.render();
        }
    }

    private async loadHistory(): Promise<void> {
        if (!this.selectedAccountId || !this.accountDetail) return;
        try {
            const d = await analyticsService.getAccountHistory(this.selectedAccountId, this.historyDays);
            this.accountDetail.history = d.history;
            this.renderLWChart();
        } catch {}
    }

    private async handleRefreshAll(): Promise<void> {
        try {
            this.refreshing = true;
            this.render();
            await apiFetch('/portfolio/refresh-all', { method: 'POST' });
            this.summary = null;
            this.accounts = [];
            this.accountDetail = null;
            this.initialLoadStarted = false;
            await this.loadSummary();
        } catch (err: any) {
            this.error = err.message || 'Ошибка при обновлении';
        } finally {
            this.refreshing = false;
            this.render();
        }
    }

    /* ---- chart ---- */

    private renderLWChart(): void {
        if (!this.accountDetail?.history?.length) return;
        const wrapper = document.getElementById('lw-chart-wrapper');
        if (!wrapper) return;

        this.destroyChart();

        const isDark = document.documentElement.getAttribute('data-theme') !== 'light';

        this.lwChart = createChart(wrapper, {
            width: wrapper.clientWidth,
            height: 320,
            layout: {
                background: { color: 'transparent' },
                textColor: isDark ? '#94a3b8' : '#64748b',
                fontFamily: 'Inter, sans-serif',
            },
            grid: {
                vertLines: { color: isDark ? '#1e293b' : '#e2e8f0' },
                horzLines: { color: isDark ? '#1e293b' : '#e2e8f0' },
            },
            rightPriceScale: {
                borderColor: isDark ? '#1e293b' : '#e2e8f0',
            },
            timeScale: {
                borderColor: isDark ? '#1e293b' : '#e2e8f0',
                timeVisible: false,
            },
            crosshair: {
                horzLine: { color: '#f97316', labelBackgroundColor: '#f97316' },
                vertLine: { color: '#f97316', labelBackgroundColor: '#f97316' },
            },
        });

        this.areaSeries = this.lwChart.addSeries(AreaSeries, {
            topColor: 'rgba(249, 115, 22, 0.28)',
            bottomColor: 'rgba(249, 115, 22, 0.02)',
            lineColor: '#f97316',
            lineWidth: 2,
        });

        // Дедупликация: берём последний снапшот за каждый день
        const byDay = new Map<string, number>();
        for (const h of this.accountDetail.history) {
            const day = String(h.date).split('T')[0];
            byDay.set(day, h.total_value);
        }
        const data = Array.from(byDay.entries())
            .sort((a, b) => a[0].localeCompare(b[0]))
            .map(([time, value]) => ({ time: time as Time, value }));

        if (data.length === 0) return;
        this.areaSeries.setData(data);
        this.lwChart.timeScale().fitContent();

        this.resizeObserver = new ResizeObserver(entries => {
            if (this.lwChart && entries[0]) {
                this.lwChart.applyOptions({ width: entries[0].contentRect.width });
            }
        });
        this.resizeObserver.observe(wrapper);
    }

    private destroyChart(): void {
        this.resizeObserver?.disconnect();
        this.resizeObserver = null;
        if (this.lwChart) {
            this.lwChart.remove();
            this.lwChart = null;
            this.areaSeries = null;
        }
    }

    /* ---- helpers ---- */

    private fmt(value: number, currency = 'RUB'): string {
        return new Intl.NumberFormat('ru-RU', { style: 'currency', currency, maximumFractionDigits: 0 }).format(value);
    }

    private pct(value: number | null): string {
        if (value == null) return '—';
        return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`;
    }

    private signClass(v: number | null | undefined): string {
        if (v == null) return '';
        return v >= 0 ? 'text-success' : 'text-danger';
    }

    /* ---- template ---- */

    private getTemplate(): string {
        const token = store.getState().token;
        if (!token) return this.tplNoAuth();
        if (this.loading) return this.tplLoading();
        if (this.error) return this.tplError();
        if (!this.summary || !this.accounts.length) return this.tplEmpty();
        return this.tplMain();
    }

    private tplNoAuth = () => `
        <div class="av-center">
            <p>Необходимо авторизоваться</p>
            <button class="btn btn-primary" id="go-to-login">Перейти к входу</button>
        </div>`;

    private tplLoading = () => `
        <div class="av-center">
            <div class="skeleton-pulse" style="width:60px;height:60px;border-radius:50%;margin:0 auto 16px"></div>
            <p style="color:var(--text-muted)">Загрузка данных...</p>
        </div>`;

    private tplError = () => `
        <div class="av-center">
            <p style="color:var(--color-danger);margin-bottom:12px">${this.error}</p>
            <button class="btn btn-primary" id="retry-load">Повторить</button>
        </div>`;

    private tplEmpty = () => `
        <div class="av-center">
            <p style="color:var(--text-muted);margin-bottom:12px">Нет данных по портфелям.</p>
            <button class="btn btn-primary" id="refresh-all" ${this.refreshing ? 'disabled' : ''}>
                ${this.refreshing ? 'Обновление...' : 'Обновить всё'}
            </button>
        </div>`;

    private tplMain(): string {
        const s = this.summary!;
        const snap = this.accountDetail?.last_snapshot;
        const dist = this.accountDetail?.distribution || [];
        const totalDist = dist.reduce((acc, d) => acc + d.value, 0);

        return `
        <div class="av-page">
            <!-- Header -->
            <div class="av-header">
                <h1 class="av-title">Аналитика</h1>
                <div class="av-controls">
                    <select id="account-select" class="av-select">
                        ${this.accounts.map(a => `
                            <option value="${a.id}" ${a.id === this.selectedAccountId ? 'selected' : ''}>
                                ${a.name || a.account_id}
                            </option>
                        `).join('')}
                    </select>
                    <button class="btn btn-ghost" id="refresh-all" ${this.refreshing ? 'disabled' : ''}>
                        ${this.refreshing ? '...' : '\u21BB Обновить'}
                    </button>
                </div>
            </div>

            <!-- KPI tiles -->
            <div class="kpi-grid">
                <div class="kpi-tile">
                    <span class="kpi-label">Портфелей</span>
                    <span class="kpi-value">${s.accounts_count}</span>
                </div>
                <div class="kpi-tile">
                    <span class="kpi-label">Общая стоимость</span>
                    <span class="kpi-value">${this.fmt(s.total_value)}</span>
                </div>
                <div class="kpi-tile">
                    <span class="kpi-label">Дневная доходность</span>
                    <span class="kpi-value ${this.signClass(s.total_daily_yield)}">
                        ${s.total_daily_yield != null ? this.fmt(s.total_daily_yield) : '—'}
                    </span>
                </div>
                <div class="kpi-tile">
                    <span class="kpi-label">Ожидаемая доходность</span>
                    <span class="kpi-value ${this.signClass(s.total_expected_yield)}">
                        ${this.pct(s.total_expected_yield)}
                    </span>
                </div>
            </div>

            ${this.loadingDetail ? `
                <div class="av-center" style="padding:2rem 0">
                    <div class="skeleton-pulse" style="width:40px;height:40px;border-radius:50%;margin:0 auto 12px"></div>
                    <p style="color:var(--text-muted)">Загрузка деталей...</p>
                </div>
            ` : ''}

            ${this.accountDetail ? `
                <!-- Snapshot KPIs -->
                ${snap ? `
                <div class="kpi-grid" style="margin-top:var(--space-lg)">
                    <div class="kpi-tile"><span class="kpi-label">Акции</span><span class="kpi-value">${this.fmt(snap.shares_value)}</span></div>
                    <div class="kpi-tile"><span class="kpi-label">Облигации</span><span class="kpi-value">${this.fmt(snap.bonds_value)}</span></div>
                    <div class="kpi-tile"><span class="kpi-label">Фонды</span><span class="kpi-value">${this.fmt(snap.etf_value)}</span></div>
                    <div class="kpi-tile"><span class="kpi-label">Валюта</span><span class="kpi-value">${this.fmt(snap.currencies_value)}</span></div>
                </div>
                ` : ''}

                <!-- Chart -->
                <div class="card" style="margin-top:var(--space-lg);padding:var(--space-lg)">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-md)">
                        <h3 style="margin:0;font-size:1rem;color:var(--text-primary)">История стоимости</h3>
                        <select id="days-select" class="av-select av-select-sm">
                            <option value="7" ${this.historyDays === 7 ? 'selected' : ''}>7д</option>
                            <option value="30" ${this.historyDays === 30 ? 'selected' : ''}>30д</option>
                            <option value="90" ${this.historyDays === 90 ? 'selected' : ''}>3м</option>
                            <option value="365" ${this.historyDays === 365 ? 'selected' : ''}>1г</option>
                        </select>
                    </div>
                    <div id="lw-chart-wrapper" style="width:100%;height:320px"></div>
                </div>

                <!-- Distribution -->
                ${dist.length > 0 ? `
                <div class="card" style="margin-top:var(--space-lg);padding:var(--space-lg)">
                    <h3 style="margin:0 0 var(--space-md);font-size:1rem;color:var(--text-primary)">Распределение активов</h3>
                    <div class="av-dist-list">
                        ${dist.map(d => {
                            const pct = totalDist > 0 ? (d.value / totalDist * 100) : 0;
                            const typeNames: Record<string, string> = { share: 'Акции', bond: 'Облигации', etf: 'Фонды', currency: 'Валюта', future: 'Фьючерсы', option: 'Опционы' };
                            const name = typeNames[d.instrument_type] || d.instrument_type;
                            return `
                            <div class="av-dist-row">
                                <div class="av-dist-bar-wrap">
                                    <div class="av-dist-bar" style="width:${pct}%"></div>
                                </div>
                                <span class="av-dist-label">${name}</span>
                                <span class="av-dist-value">${this.fmt(d.value)}</span>
                                <span class="av-dist-pct">${pct.toFixed(1)}%</span>
                            </div>`;
                        }).join('')}
                    </div>
                </div>
                ` : ''}
            ` : ''}
        </div>`;
    }

    /* ---- events ---- */

    private attachEvents(): void {
        document.getElementById('account-select')?.addEventListener('change', (e) => {
            const id = parseInt((e.target as HTMLSelectElement).value);
            this.selectedAccountId = id;
            this.accountDetail = null;
            this.loadAccountDetail(id);
        });
        document.getElementById('refresh-all')?.addEventListener('click', () => this.handleRefreshAll());
        document.getElementById('days-select')?.addEventListener('change', (e) => {
            this.historyDays = parseInt((e.target as HTMLSelectElement).value);
            this.loadHistory();
        });
        document.getElementById('retry-load')?.addEventListener('click', () => {
            this.summary = null;
            this.initialLoadStarted = false;
            this.loadSummary();
        });
        document.getElementById('go-to-login')?.addEventListener('click', () => router.navigate('/login'));
    }

    destroy(): void {
        this.destroyChart();
    }
}
