// frontend/src/modules/robots/components/RobotForm.ts
import { Robot, RobotCreate, RobotUpdate, StrategyInfo, AvailableToken } from '../types';
import { StrategyConfig } from './StrategyConfig';
import { router } from '../../../core/router';

export class RobotForm {
    private initialData?: Robot;
    private strategies: StrategyInfo[];
    private availableTokens: AvailableToken[];
    private onSubmit: (data: RobotCreate | RobotUpdate) => void;
    private onCancel: () => void;
    private isEditing: boolean;
    private container: HTMLElement | null = null;

    private selectedStrategy: string;
    private strategyParams: Record<string, any>;
    private formData: {
        name: string;
        display_name: string;
        description: string;
        token_id: number | null;
        max_daily_loss: string;
        max_position_size: string;
    };

    private strategyConfig: StrategyConfig | null = null;

    constructor(
        initialData: Robot | undefined,
        strategies: StrategyInfo[],
        availableTokens: AvailableToken[],
        onSubmit: (data: RobotCreate | RobotUpdate) => void,
        onCancel: () => void,
        isEditing: boolean = false
    ) {
        this.initialData = initialData;
        this.strategies = strategies;
        this.availableTokens = availableTokens;
        this.onSubmit = onSubmit;
        this.onCancel = onCancel;
        this.isEditing = isEditing;

        this.selectedStrategy = initialData?.strategy_name || (strategies[0]?.name || '');
        this.strategyParams = initialData?.strategy_params || {};

        this.formData = {
            name: initialData?.name || '',
            display_name: initialData?.display_name || '',
            description: initialData?.description || '',
            token_id: initialData?.token_id || null,
            max_daily_loss: initialData?.max_daily_loss?.toString() || '',
            max_position_size: initialData?.max_position_size?.toString() || '',
        };
    }

    private getCurrentStrategy(): StrategyInfo | undefined {
        return this.strategies.find(s => s.name === this.selectedStrategy);
    }

    private handleSubmit = (e: Event): void => {
        e.preventDefault();

        const data: any = {
            name: this.formData.name,
            display_name: this.formData.display_name || undefined,
            description: this.formData.description || undefined,
            robot_type: 'trading',
            strategy_name: this.selectedStrategy,
            strategy_params: this.strategyParams,
            token_id: this.formData.token_id || undefined,
        };

        if (this.formData.max_daily_loss) {
            data.max_daily_loss = parseFloat(this.formData.max_daily_loss);
        }
        if (this.formData.max_position_size) {
            data.max_position_size = parseFloat(this.formData.max_position_size);
        }

        this.onSubmit(data);
    };

    private handleStrategyChange = (e: Event): void => {
        const select = e.target as HTMLSelectElement;
        const newStrategy = select.value;
        this.selectedStrategy = newStrategy;
        this.strategyParams = {};
        this.renderForm();
    };

    private handleInputChange = (field: keyof typeof this.formData, value: string): void => {
        this.formData[field] = value as any;
    };

    private handleTokenChange = (e: Event): void => {
        const select = e.target as HTMLSelectElement;
        this.formData.token_id = select.value ? parseInt(select.value) : null;
    };

    private handleStrategyParamsChange = (params: Record<string, any>): void => {
        this.strategyParams = params;
    };

    private renderForm(): void {
        if (!this.container) return;

        const currentStrategy = this.getCurrentStrategy();

        // Создаём или обновляем StrategyConfig
        if (currentStrategy && this.strategyConfig) {
            this.strategyConfig.updateProps({
                params: this.strategyParams,
                schema: currentStrategy.params_schema,
                onChange: this.handleStrategyParamsChange
            });
        }

        // Рендерим только если изменился выбор стратегии
        if (currentStrategy) {
            const strategyContainer = document.getElementById('strategy-config-container');
            if (strategyContainer) {
                if (!this.strategyConfig) {
                    this.strategyConfig = new StrategyConfig(
                        currentStrategy.name,
                        this.strategyParams,
                        currentStrategy.params_schema,
                        this.handleStrategyParamsChange
                    );
                }
                this.strategyConfig.render(strategyContainer);
            }
        }
    }

    render(container: HTMLElement): void {
        this.container = container;
        const currentStrategy = this.getCurrentStrategy();

        container.innerHTML = `
            <form class="robot-form" id="robot-form">
                <h2>${this.isEditing ? 'Редактировать робота' : 'Создать нового робота'}</h2>

                <div class="form-group">
                    <label for="name">Название *</label>
                    <input
                        type="text"
                        id="name"
                        value="${this.formData.name}"
                        required
                        minlength="3"
                        maxlength="100"
                    />
                </div>

                <div class="form-group">
                    <label for="display_name">Отображаемое имя</label>
                    <input
                        type="text"
                        id="display_name"
                        value="${this.formData.display_name}"
                    />
                    <small>Будет использоваться в логах для удобства</small>
                </div>

                <div class="form-group">
                    <label for="description">Описание</label>
                    <textarea
                        id="description"
                        rows="3"
                    >${this.formData.description}</textarea>
                </div>

                <div class="form-group">
                    <label for="token_id">Токен доступа</label>
                    <select id="token_id">
                        <option value="">Без токена</option>
                        ${this.availableTokens.map(token => `
                            <option value="${token.id}" ${this.formData.token_id === token.id ? 'selected' : ''}>
                                ${token.token_name || 'Без имени'} (${token.token_preview})
                            </option>
                        `).join('')}
                    </select>
                </div>

                <div class="form-group">
                    <label for="strategy">Торговая стратегия *</label>
                    <select id="strategy" required>
                        <option value="">Выберите стратегию</option>
                        ${this.strategies.map(strategy => `
                            <option value="${strategy.name}" ${this.selectedStrategy === strategy.name ? 'selected' : ''}>
                                ${strategy.title}
                            </option>
                        `).join('')}
                    </select>
                    ${currentStrategy ? `
                        <small class="strategy-description">${currentStrategy.description}</small>
                    ` : ''}
                </div>

                <div id="strategy-config-container" class="strategy-config-container"></div>

                <div class="risk-settings">
                    <h3>Риск-менеджмент</h3>
                    
                    <div class="form-group">
                        <label for="max_daily_loss">Максимальный дневной убыток (%)</label>
                        <input
                            type="number"
                            id="max_daily_loss"
                            min="0"
                            max="100"
                            step="0.1"
                            value="${this.formData.max_daily_loss}"
                        />
                    </div>

                    <div class="form-group">
                        <label for="max_position_size">Максимальный размер позиции (руб)</label>
                        <input
                            type="number"
                            id="max_position_size"
                            min="0"
                            step="100"
                            value="${this.formData.max_position_size}"
                        />
                    </div>
                </div>

                <div class="form-actions">
                    <button type="button" class="btn-secondary" id="cancel-button">
                        Отмена
                    </button>
                    <button type="submit" class="btn-primary" id="submit-button">
                        ${this.isEditing ? 'Сохранить' : 'Создать'}
                    </button>
                </div>
            </form>
        `;

        // Инициализируем StrategyConfig если есть стратегия
        if (currentStrategy) {
            const strategyContainer = document.getElementById('strategy-config-container');
            if (strategyContainer) {
                this.strategyConfig = new StrategyConfig(
                    currentStrategy.name,
                    this.strategyParams,
                    currentStrategy.params_schema,
                    this.handleStrategyParamsChange
                );
                this.strategyConfig.render(strategyContainer);
            }
        }

        // Добавляем обработчики событий
        setTimeout(() => {
            const form = document.getElementById('robot-form') as HTMLFormElement;
            const nameInput = document.getElementById('name') as HTMLInputElement;
            const displayNameInput = document.getElementById('display_name') as HTMLInputElement;
            const descriptionInput = document.getElementById('description') as HTMLTextAreaElement;
            const tokenSelect = document.getElementById('token_id') as HTMLSelectElement;
            const strategySelect = document.getElementById('strategy') as HTMLSelectElement;
            const maxDailyLossInput = document.getElementById('max_daily_loss') as HTMLInputElement;
            const maxPositionSizeInput = document.getElementById('max_position_size') as HTMLInputElement;
            const cancelButton = document.getElementById('cancel-button');
            const submitButton = document.getElementById('submit-button');

            // Обработчики изменений
            nameInput.addEventListener('input', (e) => {
                this.handleInputChange('name', (e.target as HTMLInputElement).value);
            });

            displayNameInput.addEventListener('input', (e) => {
                this.handleInputChange('display_name', (e.target as HTMLInputElement).value);
            });

            descriptionInput.addEventListener('input', (e) => {
                this.handleInputChange('description', (e.target as HTMLTextAreaElement).value);
            });

            tokenSelect.addEventListener('change', this.handleTokenChange);

            strategySelect.addEventListener('change', this.handleStrategyChange);

            maxDailyLossInput.addEventListener('input', (e) => {
                this.handleInputChange('max_daily_loss', (e.target as HTMLInputElement).value);
            });

            maxPositionSizeInput.addEventListener('input', (e) => {
                this.handleInputChange('max_position_size', (e.target as HTMLInputElement).value);
            });

            // Обработчики кнопок
            form.addEventListener('submit', this.handleSubmit);
            cancelButton?.addEventListener('click', this.onCancel);
        }, 0);
    }

    destroy(): void {
        if (this.strategyConfig) {
            this.strategyConfig.destroy();
            this.strategyConfig = null;
        }
        this.container = null;
    }
}