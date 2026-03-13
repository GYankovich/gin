import { tradingService } from '../services/tradingService';
import { router } from '../../../core/router';
import { store } from '../../../core/store';
import type { StrategyInfo, ApiToken, TradingRobotCreate } from '../types';

export class TradingCreateView {
    private container: HTMLElement;
    private strategies: StrategyInfo[] = [];
    private tokens: ApiToken[] = [];
    private accounts: any[] = [];
    private loading: boolean = true;
    private loadingTokens: boolean = true;
    private loadingAccounts: boolean = false;
    private error: string | null = null;
    private selectedStrategy: StrategyInfo | null = null;
    private strategyParams: Record<string, any> = {};
    private selectedTokenId: number | null = null;

    // Поля формы
    private formData = {
        name: '',
        strategy_name: '',
        token_id: null as number | null,
        account_id: '',
        max_position_size_percent: 10,
        stop_loss_percent: 5,
        take_profit_percent: null as number | null,
        daily_loss_limit: null as number | null,
        max_trades_per_day: null as number | null,
        schedule_cron: null as string | null,
    };

    constructor(container?: HTMLElement) {
        if (container) this.container = container;
        console.log('📊 TradingCreateView created');

        // Запускаем загрузку сразу в конструкторе
        this.loadStrategies();
        this.loadUserTokens();
    }

    setContainer(container: HTMLElement): void {
        this.container = container;
    }

    private async loadStrategies(): Promise<void> {
        try {
            this.loading = true;
            this.error = null;
            this.render();

            console.log('📡 Загрузка стратегий...');
            const strategies = await tradingService.getStrategies();
            console.log('✅ Загружено стратегий:', strategies);
            this.strategies = strategies;
        } catch (err: any) {
            console.error('❌ Ошибка загрузки стратегий:', err);
            this.error = err.message || 'Не удалось загрузить стратегии';
        } finally {
            this.loading = false;
            this.render();
        }
    }

    private async loadUserTokens(): Promise<void> {
        try {
            this.loadingTokens = true;
            this.error = null;
            this.render();

            console.log('📡 Загрузка токенов...');
            const tokens = await tradingService.getUserTokens();
            console.log('✅ Загружено токенов:', tokens);
            this.tokens = tokens;
        } catch (err: any) {
            console.error('❌ Ошибка загрузки токенов:', err);
            this.error = err.message || 'Не удалось загрузить токены';
        } finally {
            this.loadingTokens = false;
            this.render();
        }
    }

    private async loadTokenAccounts(tokenId: number): Promise<void> {
        try {
            this.loadingAccounts = true;
            this.error = null;
            this.render();

            console.log(`📡 Загрузка счетов для токена ${tokenId}...`);
            const accounts = await tradingService.getTokenAccounts(tokenId);
            console.log('✅ Загружено счетов:', accounts);
            this.accounts = accounts;
        } catch (err: any) {
            console.error('❌ Ошибка загрузки счетов:', err);
            this.error = err.message || 'Не удалось загрузить счета';
        } finally {
            this.loadingAccounts = false;
            this.render();
        }
    }

    private handleStrategyChange(strategyName: string): void {
        this.selectedStrategy = this.strategies.find(s => s.name === strategyName) || null;
        this.formData.strategy_name = strategyName;

        // Сбрасываем параметры стратегии
        this.strategyParams = {};

        // Инициализируем параметры значениями по умолчанию из схемы
        if (this.selectedStrategy?.params_schema) {
            const schema = this.selectedStrategy.params_schema;
            Object.keys(schema).forEach(key => {
                if (schema[key].default !== undefined) {
                    this.strategyParams[key] = schema[key].default;
                }
            });
        }

        this.render();
    }

    private handleTokenChange(tokenId: number): void {
        this.selectedTokenId = tokenId;
        this.formData.token_id = tokenId;
        this.formData.account_id = '';
        this.accounts = [];
        this.loadTokenAccounts(tokenId);
    }

    private handleInputChange(field: string, value: any): void {
        if (field.startsWith('param_')) {
            const paramName = field.replace('param_', '');
            this.strategyParams[paramName] = value;
        } else {
            (this.formData as any)[field] = value;
        }
        this.render();
    }

    private async handleSubmit(): Promise<void> {
        // Валидация
        if (!this.formData.name.trim()) {
            alert('Введите название робота');
            return;
        }

        if (!this.formData.strategy_name) {
            alert('Выберите стратегию');
            return;
        }

        if (!this.formData.token_id) {
            alert('Выберите токен');
            return;
        }

        if (!this.formData.account_id) {
            alert('Выберите счет');
            return;
        }

        if (this.formData.max_position_size_percent <= 0 || this.formData.max_position_size_percent > 100) {
            alert('Размер позиции должен быть от 1 до 100%');
            return;
        }

        if (this.formData.stop_loss_percent <= 0 || this.formData.stop_loss_percent > 50) {
            alert('Стоп-лосс должен быть от 1 до 50%');
            return;
        }

        try {
            const robotData: TradingRobotCreate = {
                name: this.formData.name,
                strategy_name: this.formData.strategy_name,
                token_id: this.formData.token_id!,
                account_id: this.formData.account_id,
                max_position_size_percent: this.formData.max_position_size_percent,
                stop_loss_percent: this.formData.stop_loss_percent,
                take_profit_percent: this.formData.take_profit_percent,
                daily_loss_limit: this.formData.daily_loss_limit,
                max_trades_per_day: this.formData.max_trades_per_day,
                schedule_cron: this.formData.schedule_cron,
                strategy_params: this.strategyParams
            };

            console.log('📤 Создание робота:', robotData);
            await tradingService.createRobot(robotData);
            alert('Робот успешно создан!');
            router.navigate('/trading');
        } catch (err: any) {
            console.error('❌ Ошибка при создании робота:', err);
            alert('Ошибка при создании робота: ' + err.message);
        }
    }

    private goBack(): void {
        router.navigate('/trading');
    }

    render(container?: HTMLElement): void {
        if (container) this.container = container;
        if (!this.container) return;

        console.log('🎨 Rendering TradingCreateView, loading:', this.loading, 'loadingTokens:', this.loadingTokens);

        this.container.innerHTML = this.getTemplate();
        this.attachEvents();
    }

    private getTemplate(): string {
        // Показываем загрузку, пока любой из флагов загрузки активен
        if (this.loading || this.loadingTokens) {
            return `
                <div class="trading-container">
                    <div class="loading-state">
                        <div class="loading-spinner"></div>
                        <p>Загрузка...</p>
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
                        <button class="button button-secondary" id="back-to-list">← К списку</button>
                    </div>
                </div>
            `;
        }

        return `
            <div class="trading-container">
                <div class="trading-header">
                    <h1>Создание торгового робота</h1>
                    <button class="button button-secondary" id="back-to-list">
                        ← К списку
                    </button>
                </div>

                <form class="robot-form" id="robot-form">
                    <div class="form-section">
                        <h2>Основные настройки</h2>
                        
                        <div class="form-group">
                            <label class="form-label">Название робота *</label>
                            <input 
                                type="text" 
                                class="form-input" 
                                id="robot-name"
                                value="${this.formData.name}"
                                placeholder="Например: Мой первый робот"
                                autocomplete="off"
                            />
                        </div>

                        <div class="form-group">
                            <label class="form-label">Стратегия *</label>
                            <select class="form-select" id="strategy-select">
                                <option value="">Выберите стратегию</option>
                                ${this.strategies.map(s => `
                                    <option value="${s.name}" ${this.formData.strategy_name === s.name ? 'selected' : ''}>
                                        ${s.name}
                                    </option>
                                `).join('')}
                            </select>
                            ${this.selectedStrategy ? `
                                <p class="form-hint">${this.selectedStrategy.description}</p>
                            ` : ''}
                        </div>
                    </div>

                    ${this.selectedStrategy ? `
                        <div class="form-section">
                            <h2>Параметры стратегии</h2>
                            ${this.renderStrategyParams()}
                        </div>
                    ` : ''}

                    <div class="form-section">
                        <h2>Подключение</h2>
                        
                        <div class="form-group">
                            <label class="form-label">Токен *</label>
                            <select class="form-select" id="token-select" ${this.tokens.length === 0 ? 'disabled' : ''}>
                                <option value="">Выберите токен</option>
                                ${this.tokens.map(t => `
                                    <option value="${t.id}" ${this.formData.token_id === t.id ? 'selected' : ''}>
                                        ${t.name || t.masked_token}
                                    </option>
                                `).join('')}
                            </select>
                            ${this.tokens.length === 0 ? `
                                <p class="form-error">У вас нет активных токенов. Создайте токен в настройках.</p>
                            ` : ''}
                        </div>

                        ${this.loadingAccounts ? `
                            <div class="loading-spinner small"></div>
                        ` : ''}

                        ${this.accounts.length > 0 ? `
                            <div class="form-group">
                                <label class="form-label">Счет *</label>
                                <select class="form-select" id="account-select">
                                    <option value="">Выберите счет</option>
                                    ${this.accounts.map(a => `
                                        <option value="${a.id}" ${this.formData.account_id === a.id ? 'selected' : ''}>
                                            ${a.name || a.id}
                                        </option>
                                    `).join('')}
                                </select>
                            </div>
                        ` : ''}
                    </div>

                    <div class="form-section">
                        <h2>Риск-менеджмент</h2>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">Размер позиции (%) *</label>
                                <input 
                                    type="number" 
                                    class="form-input" 
                                    id="max-position-size"
                                    value="${this.formData.max_position_size_percent}"
                                    min="1" max="100" step="1"
                                />
                                <span class="form-hint">% от капитала на одну сделку</span>
                            </div>

                            <div class="form-group">
                                <label class="form-label">Стоп-лосс (%) *</label>
                                <input 
                                    type="number" 
                                    class="form-input" 
                                    id="stop-loss"
                                    value="${this.formData.stop_loss_percent}"
                                    min="0.5" max="50" step="0.5"
                                />
                                <span class="form-hint">Максимальный убыток по сделке</span>
                            </div>
                        </div>

                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">Тейк-профит (%)</label>
                                <input 
                                    type="number" 
                                    class="form-input" 
                                    id="take-profit"
                                    value="${this.formData.take_profit_percent || ''}"
                                    min="0.5" max="100" step="0.5"
                                />
                                <span class="form-hint">Опционально</span>
                            </div>

                            <div class="form-group">
                                <label class="form-label">Лимит убытка в день (₽)</label>
                                <input 
                                    type="number" 
                                    class="form-input" 
                                    id="daily-loss-limit"
                                    value="${this.formData.daily_loss_limit || ''}"
                                    min="0" step="100"
                                />
                                <span class="form-hint">Опционально</span>
                            </div>
                        </div>

                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">Макс. сделок в день</label>
                                <input 
                                    type="number" 
                                    class="form-input" 
                                    id="max-trades"
                                    value="${this.formData.max_trades_per_day || ''}"
                                    min="1" max="100" step="1"
                                />
                                <span class="form-hint">Опционально</span>
                            </div>

                            <div class="form-group">
                                <label class="form-label">Расписание (cron)</label>
                                <input 
                                    type="text" 
                                    class="form-input" 
                                    id="schedule-cron"
                                    value="${this.formData.schedule_cron || ''}"
                                    placeholder="*/5 * * * *"
                                />
                                <span class="form-hint">Например: */5 * * * * (каждые 5 минут)</span>
                            </div>
                        </div>
                    </div>

                    <div class="form-actions">
                        <button type="button" class="button button-secondary" id="cancel-create">
                            Отмена
                        </button>
                        <button type="submit" class="button button-primary" id="submit-create">
                            Создать робота
                        </button>
                    </div>
                </form>
            </div>
        `;
    }

    private renderStrategyParams(): string {
        if (!this.selectedStrategy?.params_schema) return '';

        const schema = this.selectedStrategy.params_schema;

        return Object.entries(schema).map(([key, config]: [string, any]) => {
            const value = this.strategyParams[key] !== undefined ? this.strategyParams[key] : config.default || '';

            switch (config.type) {
                case 'integer':
                case 'number':
                    return `
                        <div class="form-group">
                            <label class="form-label">${config.label || key}</label>
                            <input 
                                type="number" 
                                class="form-input" 
                                id="param_${key}"
                                value="${value}"
                                min="${config.min || 0}"
                                max="${config.max || 100}"
                                step="${config.type === 'integer' ? 1 : 0.1}"
                            />
                            <span class="form-hint">${config.description || ''}</span>
                        </div>
                    `;

                case 'string':
                    if (config.enum) {
                        return `
                            <div class="form-group">
                                <label class="form-label">${config.label || key}</label>
                                <select class="form-select" id="param_${key}">
                                    ${config.enum.map((opt: string) => `
                                        <option value="${opt}" ${value === opt ? 'selected' : ''}>
                                            ${opt}
                                        </option>
                                    `).join('')}
                                </select>
                                <span class="form-hint">${config.description || ''}</span>
                            </div>
                        `;
                    }
                    return `
                        <div class="form-group">
                            <label class="form-label">${config.label || key}</label>
                            <input 
                                type="text" 
                                class="form-input" 
                                id="param_${key}"
                                value="${value}"
                            />
                            <span class="form-hint">${config.description || ''}</span>
                        </div>
                    `;

                case 'array':
                    return `
                        <div class="form-group">
                            <label class="form-label">${config.label || key}</label>
                            <input 
                                type="text" 
                                class="form-input" 
                                id="param_${key}"
                                value="${Array.isArray(value) ? value.join(', ') : value}"
                                placeholder="FIGI через запятую"
                            />
                            <span class="form-hint">${config.description || 'FIGI идентификаторы через запятую'}</span>
                        </div>
                    `;

                default:
                    return '';
            }
        }).join('');
    }

    private attachEvents(): void {
        const form = document.getElementById('robot-form');
        form?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleSubmit();
        });

        const backBtn = document.getElementById('back-to-list');
        backBtn?.addEventListener('click', () => {
            this.goBack();
        });

        const cancelBtn = document.getElementById('cancel-create');
        cancelBtn?.addEventListener('click', () => {
            this.goBack();
        });

        const retryBtn = document.getElementById('retry-load');
        retryBtn?.addEventListener('click', () => {
            this.loadStrategies();
            this.loadUserTokens();
        });

        const strategySelect = document.getElementById('strategy-select') as HTMLSelectElement;
        strategySelect?.addEventListener('change', (e) => {
            this.handleStrategyChange((e.target as HTMLSelectElement).value);
        });

        const tokenSelect = document.getElementById('token-select') as HTMLSelectElement;
        tokenSelect?.addEventListener('change', (e) => {
            const tokenId = parseInt((e.target as HTMLSelectElement).value);
            if (!isNaN(tokenId)) {
                this.handleTokenChange(tokenId);
            }
        });

        const nameInput = document.getElementById('robot-name') as HTMLInputElement;
        nameInput?.addEventListener('input', (e) => {
            this.handleInputChange('name', (e.target as HTMLInputElement).value);
        });

        const maxPositionInput = document.getElementById('max-position-size') as HTMLInputElement;
        maxPositionInput?.addEventListener('input', (e) => {
            this.handleInputChange('max_position_size_percent', parseFloat((e.target as HTMLInputElement).value));
        });

        const stopLossInput = document.getElementById('stop-loss') as HTMLInputElement;
        stopLossInput?.addEventListener('input', (e) => {
            this.handleInputChange('stop_loss_percent', parseFloat((e.target as HTMLInputElement).value));
        });

        const takeProfitInput = document.getElementById('take-profit') as HTMLInputElement;
        takeProfitInput?.addEventListener('input', (e) => {
            const val = (e.target as HTMLInputElement).value;
            this.handleInputChange('take_profit_percent', val ? parseFloat(val) : null);
        });

        const dailyLossInput = document.getElementById('daily-loss-limit') as HTMLInputElement;
        dailyLossInput?.addEventListener('input', (e) => {
            const val = (e.target as HTMLInputElement).value;
            this.handleInputChange('daily_loss_limit', val ? parseFloat(val) : null);
        });

        const maxTradesInput = document.getElementById('max-trades') as HTMLInputElement;
        maxTradesInput?.addEventListener('input', (e) => {
            const val = (e.target as HTMLInputElement).value;
            this.handleInputChange('max_trades_per_day', val ? parseInt(val) : null);
        });

        const cronInput = document.getElementById('schedule-cron') as HTMLInputElement;
        cronInput?.addEventListener('input', (e) => {
            const val = (e.target as HTMLInputElement).value;
            this.handleInputChange('schedule_cron', val || null);
        });

        const accountSelect = document.getElementById('account-select') as HTMLSelectElement;
        accountSelect?.addEventListener('change', (e) => {
            this.handleInputChange('account_id', (e.target as HTMLSelectElement).value);
        });

        // Обработчики для параметров стратегии
        if (this.selectedStrategy?.params_schema) {
            Object.keys(this.selectedStrategy.params_schema).forEach(key => {
                const element = document.getElementById(`param_${key}`) as HTMLInputElement | HTMLSelectElement;
                if (element) {
                    element.addEventListener('input', (e) => {
                        let value: any = (e.target as HTMLInputElement).value;
                        const schema = this.selectedStrategy!.params_schema[key];

                        if (schema.type === 'integer' || schema.type === 'number') {
                            value = parseFloat(value);
                        } else if (schema.type === 'array') {
                            value = value.split(',').map((s: string) => s.trim()).filter((s: string) => s);
                        }

                        this.handleInputChange(`param_${key}`, value);
                    });
                }
            });
        }
    }
}