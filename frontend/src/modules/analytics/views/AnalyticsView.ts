import { analyticsService } from '../services/analyticsService';
import { router } from '../../../core/router';
import { store } from '../../../core/store';
import { apiFetch } from '../../../core/api';
import Chart from 'chart.js/auto';
import type { OverallSummary, AccountDetail, AccountSummary, HistoryItem } from '../types';

export class AnalyticsView {
    private container: HTMLElement;
    private summary: OverallSummary | null = null;
    private accounts: AccountSummary[] = [];
    private selectedAccountId: number | null = null;
    private accountDetail: AccountDetail | null = null;
    private loading: boolean = false;
    private loadingDetail: boolean = false;
    private refreshing: boolean = false;
    private error: string | null = null;
    private historyDays: number = 30;
    private chart: Chart | null = null;
    private distributionChart: Chart | null = null;
    private initialLoadStarted: boolean = false;

    constructor(container?: HTMLElement) {
        if (container) this.container = container;
        console.log('📊 AnalyticsView created');
    }

    setContainer(container: HTMLElement): void {
        this.container = container;
    }

    private async loadSummary(): Promise<void> {
        // Если уже загружаемся или данные уже есть - выходим
        if (this.loading || this.summary) return;

        try {
            this.loading = true;
            this.error = null;
            this.render();

            console.log('📡 Loading analytics summary...');
            this.summary = await analyticsService.getOverallSummary();
            this.accounts = this.summary.accounts;

            // Сбрасываем loading ПОСЛЕ получения данных, НО перед загрузкой деталей
            this.loading = false;
            this.render();

            if (this.accounts.length > 0 && !this.selectedAccountId) {
                this.selectedAccountId = this.accounts[0].id;
                await this.loadAccountDetail(this.selectedAccountId);
            }
        } catch (err: any) {
            console.error('❌ Failed to load summary:', err);
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

            console.log(`📡 Loading account detail for ID: ${accountId}`);
            this.accountDetail = await analyticsService.getAccountDetail(accountId);

            // После загрузки деталей, если период не 30, перезагружаем историю с нужным периодом
            if (this.historyDays !== 30) {
                await this.loadHistoryForSelectedAccount();
            }
        } catch (err: any) {
            console.error('❌ Failed to load account detail:', err);
            this.error = err.message || 'Не удалось загрузить детали портфеля';
        } finally {
            this.loadingDetail = false;
            this.render(); // Важно: перерендериваем после загрузки деталей
        }
    }

    private async loadAccountDetail(accountId: number): Promise<void> {
        try {
            this.loadingDetail = true;
            this.error = null;
            this.render();

            console.log(`📡 Loading account detail for ID: ${accountId}`);
            this.accountDetail = await analyticsService.getAccountDetail(accountId);

            // После загрузки деталей, если период не 30, перезагружаем историю с нужным периодом
            if (this.historyDays !== 30) {
                await this.loadHistoryForSelectedAccount();
            }
        } catch (err: any) {
            console.error('❌ Failed to load account detail:', err);
            this.error = err.message || 'Не удалось загрузить детали портфеля';
        } finally {
            this.loadingDetail = false;
            this.render();
        }
    }

    private async loadHistoryForSelectedAccount(): Promise<void> {
        if (!this.selectedAccountId || !this.accountDetail) return;

        try {
            console.log(`📡 Loading history for account ${this.selectedAccountId}, days: ${this.historyDays}`);
            const historyData = await analyticsService.getAccountHistory(this.selectedAccountId, this.historyDays);
            this.accountDetail.history = historyData.history;
            this.renderCharts();
        } catch (err: any) {
            console.error('❌ Failed to load history:', err);
        }
    }

    private async handleAccountChange(accountId: number): Promise<void> {
        this.selectedAccountId = accountId;
        this.accountDetail = null; // Сбрасываем детали при смене счета
        await this.loadAccountDetail(accountId);
    }

    private async handleRefreshAll(): Promise<void> {
        try {
            this.refreshing = true;
            this.error = null;
            this.render();

            console.log('🔄 Refreshing all portfolios...');
            await apiFetch('/portfolio/refresh-all', { method: 'POST' });

            // Сбрасываем флаг, чтобы загрузить свежие данные
            this.summary = null;
            this.accounts = [];
            this.accountDetail = null;
            this.initialLoadStarted = false;

            await this.loadSummary();
        } catch (err: any) {
            console.error('❌ Failed to refresh:', err);
            this.error = err.message || 'Ошибка при обновлении';
        } finally {
            this.refreshing = false;
            this.render();
        }
    }

    private async handleDaysChange(days: number): Promise<void> {
        this.historyDays = days;
        await this.loadHistoryForSelectedAccount();
    }

    private renderCharts(): void {
        if (!this.accountDetail) return;

        // Даём время DOM обновиться
        setTimeout(() => {
            // График истории стоимости
            const historyCtx = document.getElementById('history-chart') as HTMLCanvasElement;
            if (historyCtx && this.accountDetail!.history.length > 0) {
                if (this.chart) this.chart.destroy();

                const dates = this.accountDetail!.history.map(h => new Date(h.date).toLocaleDateString());
                const values = this.accountDetail!.history.map(h => h.total_value);

                this.chart = new Chart(historyCtx, {
                    type: 'line',
                    data: {
                        labels: dates,
                        datasets: [{
                            label: 'Стоимость портфеля',
                            data: values,
                            borderColor: 'rgb(249, 115, 22)',
                            backgroundColor: 'rgba(249, 115, 22, 0.1)',
                            tension: 0.1,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: (context) => {
                                        let value = context.raw as number;
                                        return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB' }).format(value);
                                    }
                                }
                            }
                        },
                        scales: {
                            y: {
                                ticks: {
                                    callback: (value) => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', notation: 'compact' }).format(value as number)
                                }
                            }
                        }
                    }
                });
            }

            // Круговая диаграмма распределения
            const distCtx = document.getElementById('distribution-chart') as HTMLCanvasElement;
            if (distCtx && this.accountDetail!.distribution.length > 0) {
                if (this.distributionChart) this.distributionChart.destroy();

                const labels = this.accountDetail!.distribution.map(d => {
                    const map: Record<string, string> = {
                        'share': 'Акции',
                        'bond': 'Облигации',
                        'etf': 'Фонды',
                        'currency': 'Валюта',
                        'future': 'Фьючерсы',
                        'option': 'Опционы'
                    };
                    return map[d.instrument_type] || d.instrument_type;
                });
                const data = this.accountDetail!.distribution.map(d => d.value);
                const percentages = this.accountDetail!.distribution.map(d => d.percentage);

                this.distributionChart = new Chart(distCtx, {
                    type: 'doughnut',
                    data: {
                        labels,
                        datasets: [{
                            data,
                            backgroundColor: [
                                'rgba(249, 115, 22, 0.8)',
                                'rgba(16, 185, 129, 0.8)',
                                'rgba(59, 130, 246, 0.8)',
                                'rgba(139, 92, 246, 0.8)',
                                'rgba(236, 72, 153, 0.8)',
                                'rgba(245, 158, 11, 0.8)'
                            ]
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'bottom' },
                            tooltip: {
                                callbacks: {
                                    label: (context) => {
                                        const label = context.label || '';
                                        const value = context.raw as number;
                                        const percentage = percentages[context.dataIndex] * 100;
                                        return `${label}: ${new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB' }).format(value)} (${percentage.toFixed(1)}%)`;
                                    }
                                }
                            }
                        }
                    }
                });
            }
        }, 0);
    }

    private formatMoney(value: number, currency: string = 'RUB'): string {
        return new Intl.NumberFormat('ru-RU', { style: 'currency', currency }).format(value);
    }

    private formatPercent(value: number): string {
        return `${(value * 100).toFixed(2)}%`;
    }

    private getTemplate(): string {
        // Проверяем авторизацию
        console.log('🎨 Rendering template with state:', {
            loading: this.loading,
            loadingDetail: this.loadingDetail,
            summary: !!this.summary,
            accountsCount: this.accounts.length,
            error: this.error
        });
        const authToken = store.getState().token;
        if (!authToken) {
            return `
        <div class="analytics-container">
          <div class="no-auth-state">
            <p>Необходимо авторизоваться</p>
            <button class="button button-primary" id="go-to-login">Перейти к входу</button>
          </div>
        </div>
      `;
        }

        if (this.loading) {
            return `
        <div class="analytics-container">
          <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Загрузка данных...</p>
          </div>
        </div>
      `;
        }

        if (this.error) {
            return `
        <div class="analytics-container">
          <div class="error-state">
            <p class="error-message">${this.error}</p>
            <button class="button button-primary" id="retry-load">Повторить</button>
            <button class="button button-secondary" id="refresh-all">Обновить всё</button>
          </div>
        </div>
      `;
        }

        if (!this.summary || this.accounts.length === 0) {
            return `
        <div class="analytics-container">
          <div class="empty-state">
            <p>Нет данных по портфелям. Нажмите "Обновить всё", чтобы загрузить данные из Т-Инвестиций.</p>
            <button class="button button-primary" id="refresh-all" ${this.refreshing ? 'disabled' : ''}>
              <span class="refresh-icon">🔄</span>
              ${this.refreshing ? 'Обновление...' : 'Обновить всё'}
            </button>
          </div>
        </div>
      `;
        }

        const selectedAccount = this.accounts.find(a => a.id === this.selectedAccountId);
        const accountDetail = this.accountDetail;
        const lastSnapshot = accountDetail?.last_snapshot;

        return `
      <div class="analytics-container">
        <div class="analytics-header">
          <h1>Аналитика портфелей</h1>
          <div class="header-controls">
            <select id="account-select" class="account-select">
              ${this.accounts.map(a => `
                <option value="${a.id}" ${a.id === this.selectedAccountId ? 'selected' : ''}>
                  ${a.name || a.account_id}
                </option>
              `).join('')}
            </select>
            <button class="button button-primary" id="refresh-all" ${this.refreshing ? 'disabled' : ''}>
              <span class="refresh-icon">🔄</span>
              ${this.refreshing ? 'Обновление...' : 'Обновить всё'}
            </button>
          </div>
        </div>

        <!-- Общая сводка -->
        <div class="summary-cards">
          <div class="summary-card">
            <div class="summary-label">Всего портфелей</div>
            <div class="summary-value">${this.summary.accounts_count}</div>
          </div>
          <div class="summary-card">
            <div class="summary-label">Общая стоимость</div>
            <div class="summary-value">${this.formatMoney(this.summary.total_value)}</div>
          </div>
          <div class="summary-card">
            <div class="summary-label">Общая доходность</div>
            <div class="summary-value ${this.summary.total_expected_yield && this.summary.total_expected_yield >= 0 ? 'positive' : 'negative'}">
              ${this.summary.total_expected_yield ? this.formatPercent(this.summary.total_expected_yield) : '—'}
            </div>
          </div>
        </div>

        ${this.loadingDetail ? `
          <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Загрузка деталей портфеля...</p>
          </div>
        ` : ''}

        ${accountDetail ? `
          <div class="portfolio-detail">
            <h2>${selectedAccount?.name || selectedAccount?.account_id || 'Портфель'}</h2>
            ${lastSnapshot ? `
              <div class="snapshot-info">
                <div class="snapshot-date">Последнее обновление: ${new Date(lastSnapshot.date).toLocaleString()}</div>
                <div class="snapshot-stats">
                  <div class="stat-item">
                    <span class="stat-label">Общая стоимость</span>
                    <span class="stat-value">${this.formatMoney(lastSnapshot.total_value)}</span>
                  </div>
                  <div class="stat-item">
                    <span class="stat-label">Акции</span>
                    <span class="stat-value">${this.formatMoney(lastSnapshot.shares_value)}</span>
                  </div>
                  <div class="stat-item">
                    <span class="stat-label">Облигации</span>
                    <span class="stat-value">${this.formatMoney(lastSnapshot.bonds_value)}</span>
                  </div>
                  <div class="stat-item">
                    <span class="stat-label">Фонды</span>
                    <span class="stat-value">${this.formatMoney(lastSnapshot.etf_value)}</span>
                  </div>
                  <div class="stat-item">
                    <span class="stat-label">Валюта</span>
                    <span class="stat-value">${this.formatMoney(lastSnapshot.currencies_value)}</span>
                  </div>
                </div>
              </div>
            ` : ''}

            <div class="chart-header">
              <h3>История стоимости</h3>
              <select id="days-select" class="days-select">
                <option value="7" ${this.historyDays === 7 ? 'selected' : ''}>7 дней</option>
                <option value="30" ${this.historyDays === 30 ? 'selected' : ''}>30 дней</option>
                <option value="90" ${this.historyDays === 90 ? 'selected' : ''}>3 месяца</option>
                <option value="365" ${this.historyDays === 365 ? 'selected' : ''}>год</option>
              </select>
            </div>
            <div class="chart-container">
              <canvas id="history-chart"></canvas>
            </div>

            ${accountDetail.distribution.length > 0 ? `
              <h3>Распределение активов</h3>
              <div class="chart-container small">
                <canvas id="distribution-chart"></canvas>
              </div>
            ` : ''}
          </div>
        ` : ''}
      </div>
    `;
    }

    private attachEvents(): void {
        const accountSelect = document.getElementById('account-select') as HTMLSelectElement;
        accountSelect?.addEventListener('change', (e) => {
            const id = parseInt((e.target as HTMLSelectElement).value);
            this.handleAccountChange(id);
        });

        const refreshBtn = document.getElementById('refresh-all');
        refreshBtn?.addEventListener('click', () => this.handleRefreshAll());

        const daysSelect = document.getElementById('days-select') as HTMLSelectElement;
        daysSelect?.addEventListener('change', (e) => {
            const days = parseInt((e.target as HTMLSelectElement).value);
            this.handleDaysChange(days);
        });

        const retryBtn = document.getElementById('retry-load');
        retryBtn?.addEventListener('click', () => this.loadSummary());

        const loginBtn = document.getElementById('go-to-login');
        loginBtn?.addEventListener('click', () => router.navigate('/login'));
    }

    render(container?: HTMLElement): void {
        if (container) this.container = container;
        if (!this.container) return;

        // Загружаем данные только если ещё не начали и нет данных
        if (!this.initialLoadStarted && !this.summary && !this.loading && !this.error) {
            this.initialLoadStarted = true;
            this.loadSummary();
        }

        // Рендерим соответствующий шаблон
        this.container.innerHTML = this.getTemplate();
        this.attachEvents();

        // Рисуем графики после того, как DOM обновился
        if (this.accountDetail) {
            this.renderCharts();
        }
    }
}