import { robotService } from '../services/robotService';
import { showToast } from '../../../shared/components/Toast';
import type { StrategyInfo, StrategyParam } from '../types';

interface RobotConfig {
    strategy_name?: string;
    strategy_params?: Record<string, any>;
    allowed_instruments?: string[];
    max_daily_loss?: number | null;
    max_position_size?: number | null;
}

interface RobotSettingsFormOptions {
    robotId: number;
    currentConfig: RobotConfig;
    onSave?: () => void;
}

export class RobotSettingsForm {
    private container: HTMLElement;
    private robotId: number;
    private config: RobotConfig;
    private strategies: StrategyInfo[] = [];
    private selectedStrategy: StrategyInfo | null = null;
    private loading = true;
    private saving = false;
    private onSave?: () => void;

    constructor(container: HTMLElement, opts: RobotSettingsFormOptions) {
        this.container = container;
        this.robotId = opts.robotId;
        this.config = { ...opts.currentConfig };
        this.onSave = opts.onSave;
    }

    async init(): Promise<void> {
        this.render();
        try {
            this.strategies = await robotService.getStrategies();
            if (this.config.strategy_name) {
                this.selectedStrategy = this.strategies.find(
                    s => s.name === this.config.strategy_name
                ) || null;
            }
        } catch (err) {
            console.error('Failed to load strategies:', err);
        } finally {
            this.loading = false;
            this.render();
        }
    }

    render(): void {
        if (this.loading) {
            this.container.innerHTML = this.tplSkeleton();
            return;
        }

        this.container.innerHTML = `
        <form class="rsf" id="rsf-form">
            <!-- Strategy selector -->
            <div class="rsf-group">
                <label class="rsf-label">Стратегия</label>
                <select class="rsf-select" id="rsf-strategy">
                    <option value="">-- без стратегии --</option>
                    ${this.strategies.map(s => `
                        <option value="${s.name}" ${s.name === this.config.strategy_name ? 'selected' : ''}>
                            ${this.esc(s.title)}
                        </option>
                    `).join('')}
                </select>
                ${this.selectedStrategy ? `
                    <p class="rsf-hint">${this.esc(this.selectedStrategy.description)}</p>
                ` : ''}
            </div>

            <!-- Dynamic strategy params -->
            ${this.selectedStrategy ? this.renderStrategyParams() : ''}

            <!-- Risk management -->
            <div class="rsf-divider"></div>
            <h4 class="rsf-section-title">Риск-менеджмент</h4>

            <div class="rsf-row">
                <div class="rsf-group">
                    <label class="rsf-label">Макс. дневной убыток, руб</label>
                    <input type="number" class="rsf-input" id="rsf-max-loss"
                           step="100" min="0"
                           value="${this.config.max_daily_loss ?? ''}"
                           placeholder="без ограничения">
                </div>
                <div class="rsf-group">
                    <label class="rsf-label">Макс. размер позиции, руб</label>
                    <input type="number" class="rsf-input" id="rsf-max-pos"
                           step="100" min="0"
                           value="${this.config.max_position_size ?? ''}"
                           placeholder="без ограничения">
                </div>
            </div>

            <!-- Instruments -->
            <div class="rsf-group">
                <label class="rsf-label">Разрешённые инструменты (FIGI через запятую)</label>
                <textarea class="rsf-textarea" id="rsf-instruments" rows="2"
                          placeholder="Оставьте пустым для автоподбора"
                >${(this.config.allowed_instruments || []).join(', ')}</textarea>
                <p class="rsf-hint">Если пусто — робот сам подберёт топ-20 акций по ликвидности</p>
            </div>

            <!-- Actions -->
            <div class="rsf-actions">
                <button type="submit" class="btn btn-primary" id="rsf-save" ${this.saving ? 'disabled' : ''}>
                    ${this.saving ? 'Сохранение...' : 'Сохранить настройки'}
                </button>
            </div>
        </form>`;

        this.attachEvents();
    }

    private renderStrategyParams(): string {
        if (!this.selectedStrategy) return '';
        const schema = this.selectedStrategy.params_schema;
        const params = this.config.strategy_params || {};

        const fields = Object.entries(schema).map(([key, def]) => {
            const value = params[key] ?? def.default ?? '';
            return this.renderParamField(key, def, value);
        });

        return `
            <div class="rsf-divider"></div>
            <h4 class="rsf-section-title">Параметры стратегии: ${this.esc(this.selectedStrategy.title)}</h4>
            <div class="rsf-params-grid">
                ${fields.join('')}
            </div>
        `;
    }

    private renderParamField(key: string, def: StrategyParam, value: any): string {
        const id = `rsf-param-${key}`;
        let input: string;

        if (def.enum && def.enum.length) {
            input = `
                <select class="rsf-select rsf-param-input" id="${id}" data-param="${key}">
                    ${def.enum.map(v => `<option value="${v}" ${v === String(value) ? 'selected' : ''}>${v}</option>`).join('')}
                </select>`;
        } else if (def.type === 'boolean') {
            input = `
                <label class="rsf-toggle">
                    <input type="checkbox" class="rsf-param-input" id="${id}" data-param="${key}" ${value ? 'checked' : ''}>
                    <span class="rsf-toggle-slider"></span>
                </label>`;
        } else if (def.type === 'integer' || def.type === 'float') {
            const step = def.type === 'float' ? '0.01' : '1';
            const min = def.min != null ? `min="${def.min}"` : '';
            const max = def.max != null ? `max="${def.max}"` : '';
            input = `<input type="number" class="rsf-input rsf-param-input" id="${id}" data-param="${key}"
                        step="${step}" ${min} ${max} value="${value}" placeholder="${def.default ?? ''}">`;
        } else if (def.type === 'array') {
            input = `<input type="text" class="rsf-input rsf-param-input" id="${id}" data-param="${key}"
                        value="${Array.isArray(value) ? value.join(', ') : value}" placeholder="через запятую">`;
        } else {
            input = `<input type="text" class="rsf-input rsf-param-input" id="${id}" data-param="${key}"
                        value="${this.esc(String(value))}" placeholder="${def.default ?? ''}">`;
        }

        return `
        <div class="rsf-group">
            <label class="rsf-label" for="${id}">
                ${this.esc(def.label)}
                ${def.description ? `<span class="rsf-label-info" title="${this.esc(def.description)}">?</span>` : ''}
            </label>
            ${input}
        </div>`;
    }

    private attachEvents(): void {
        const form = document.getElementById('rsf-form');
        form?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleSave();
        });

        document.getElementById('rsf-strategy')?.addEventListener('change', (e) => {
            const name = (e.target as HTMLSelectElement).value;
            this.config.strategy_name = name || undefined;
            this.selectedStrategy = this.strategies.find(s => s.name === name) || null;
            this.config.strategy_params = {};
            if (this.selectedStrategy) {
                for (const [k, def] of Object.entries(this.selectedStrategy.params_schema)) {
                    if (def.default !== undefined) {
                        this.config.strategy_params[k] = def.default;
                    }
                }
            }
            this.render();
        });
    }

    private collectFormData(): RobotConfig {
        const strategyParams: Record<string, any> = {};
        document.querySelectorAll<HTMLInputElement | HTMLSelectElement>('.rsf-param-input').forEach(el => {
            const key = el.dataset.param;
            if (!key) return;

            const schema = this.selectedStrategy?.params_schema[key];
            if (!schema) return;

            if (el instanceof HTMLInputElement && el.type === 'checkbox') {
                strategyParams[key] = el.checked;
            } else if (schema.type === 'integer') {
                strategyParams[key] = el.value ? parseInt(el.value) : schema.default;
            } else if (schema.type === 'float') {
                strategyParams[key] = el.value ? parseFloat(el.value) : schema.default;
            } else if (schema.type === 'array') {
                strategyParams[key] = el.value ? el.value.split(',').map(s => s.trim()).filter(Boolean) : [];
            } else {
                strategyParams[key] = el.value;
            }
        });

        const maxLossEl = document.getElementById('rsf-max-loss') as HTMLInputElement;
        const maxPosEl = document.getElementById('rsf-max-pos') as HTMLInputElement;
        const instrEl = document.getElementById('rsf-instruments') as HTMLTextAreaElement;

        return {
            strategy_name: this.config.strategy_name,
            strategy_params: strategyParams,
            max_daily_loss: maxLossEl?.value ? parseFloat(maxLossEl.value) : null,
            max_position_size: maxPosEl?.value ? parseFloat(maxPosEl.value) : null,
            allowed_instruments: instrEl?.value
                ? instrEl.value.split(',').map(s => s.trim()).filter(Boolean)
                : [],
        };
    }

    private async handleSave(): Promise<void> {
        if (this.saving) return;
        this.saving = true;
        this.render();

        try {
            const data = this.collectFormData();
            await robotService.updateRobot(this.robotId, {
                strategy_params: data.strategy_params,
                max_daily_loss: data.max_daily_loss,
                max_position_size: data.max_position_size,
                allowed_instruments: data.allowed_instruments,
            });
            showToast({ message: 'Настройки сохранены', type: 'success' });
            this.onSave?.();
        } catch (err: any) {
            showToast({ message: err.message || 'Ошибка сохранения', type: 'error' });
        } finally {
            this.saving = false;
            this.render();
        }
    }

    private tplSkeleton(): string {
        return `
        <div class="rsf">
            ${[1, 2, 3, 4].map(() => `
                <div class="rsf-group">
                    <div class="skeleton-pulse" style="width:100px;height:14px;margin-bottom:8px"></div>
                    <div class="skeleton-pulse" style="width:100%;height:40px"></div>
                </div>
            `).join('')}
        </div>`;
    }

    private esc(str: string): string {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }
}
