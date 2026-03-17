// frontend/src/modules/robots/components/StrategyConfig.ts
import { StrategyParam } from '../types';

export class StrategyConfig {
    private strategyName: string;
    private params: Record<string, any>;
    private schema: Record<string, StrategyParam>;
    private onChange: (params: Record<string, any>) => void;
    private container: HTMLElement | null = null;

    constructor(
        strategyName: string,
        params: Record<string, any>,
        schema: Record<string, StrategyParam>,
        onChange: (params: Record<string, any>) => void
    ) {
        this.strategyName = strategyName;
        this.params = { ...params };
        this.schema = schema;
        this.onChange = onChange;
    }

    updateProps(props: {
        params?: Record<string, any>;
        schema?: Record<string, StrategyParam>;
        onChange?: (params: Record<string, any>) => void;
    }): void {
        if (props.params !== undefined) this.params = { ...props.params };
        if (props.schema !== undefined) this.schema = props.schema;
        if (props.onChange !== undefined) this.onChange = props.onChange;
        this.renderContent();
    }

    private handleChange = (key: string, value: any): void => {
        this.params[key] = value;
        this.onChange(this.params);
    };

    private renderField(key: string, param: StrategyParam): string {
        const value = this.params[key] !== undefined ? this.params[key] : param.default;

        switch (param.type) {
            case 'integer':
            case 'float':
                return `
                    <div class="strategy-field">
                        <label for="param-${key}">${param.label}</label>
                        <input
                            type="number"
                            id="param-${key}"
                            value="${value || ''}"
                            min="${param.min !== undefined ? param.min : ''}"
                            max="${param.max !== undefined ? param.max : ''}"
                            step="${param.type === 'float' ? '0.1' : '1'}"
                            data-key="${key}"
                        />
                        ${param.description ? `
                            <small class="field-description">${param.description}</small>
                        ` : ''}
                    </div>
                `;

            case 'string':
                if (param.enum) {
                    return `
                        <div class="strategy-field">
                            <label for="param-${key}">${param.label}</label>
                            <select id="param-${key}" data-key="${key}">
                                ${param.enum.map(option => `
                                    <option value="${option}" ${value === option ? 'selected' : ''}>
                                        ${option}
                                    </option>
                                `).join('')}
                            </select>
                            ${param.description ? `
                                <small class="field-description">${param.description}</small>
                            ` : ''}
                        </div>
                    `;
                }
                return `
                    <div class="strategy-field">
                        <label for="param-${key}">${param.label}</label>
                        <input
                            type="text"
                            id="param-${key}"
                            value="${value || ''}"
                            data-key="${key}"
                        />
                        ${param.description ? `
                            <small class="field-description">${param.description}</small>
                        ` : ''}
                    </div>
                `;

            case 'boolean':
                return `
                    <div class="strategy-field checkbox">
                        <label>
                            <input
                                type="checkbox"
                                id="param-${key}"
                                ${value ? 'checked' : ''}
                                data-key="${key}"
                            />
                            ${param.label}
                        </label>
                        ${param.description ? `
                            <small class="field-description">${param.description}</small>
                        ` : ''}
                    </div>
                `;

            case 'array':
                return `
                    <div class="strategy-field">
                        <label>${param.label}</label>
                        <div class="array-input">
                            <textarea
                                id="param-${key}"
                                data-key="${key}"
                                placeholder="Один элемент на строку"
                                rows="5"
                            >${Array.isArray(value) ? value.join('\n') : ''}</textarea>
                        </div>
                        ${param.description ? `
                            <small class="field-description">${param.description}</small>
                        ` : ''}
                    </div>
                `;

            default:
                return '';
        }
    }

    private renderContent(): void {
        if (!this.container) return;

        const fieldsHtml = Object.entries(this.schema)
            .map(([key, param]) => this.renderField(key, param))
            .join('');

        this.container.innerHTML = `
            <div class="strategy-config">
                <h3>Настройки стратегии: ${this.strategyName}</h3>
                <div class="strategy-fields">
                    ${fieldsHtml}
                </div>
            </div>
        `;

        // Добавляем обработчики событий
        setTimeout(() => {
            Object.keys(this.schema).forEach(key => {
                const element = document.getElementById(`param-${key}`);
                if (!element) return;

                const param = this.schema[key];

                if (param.type === 'integer' || param.type === 'float') {
                    element.addEventListener('input', (e) => {
                        const input = e.target as HTMLInputElement;
                        this.handleChange(key, parseFloat(input.value));
                    });
                } else if (param.type === 'string') {
                    if (param.enum) {
                        element.addEventListener('change', (e) => {
                            const select = e.target as HTMLSelectElement;
                            this.handleChange(key, select.value);
                        });
                    } else {
                        element.addEventListener('input', (e) => {
                            const input = e.target as HTMLInputElement;
                            this.handleChange(key, input.value);
                        });
                    }
                } else if (param.type === 'boolean') {
                    element.addEventListener('change', (e) => {
                        const checkbox = e.target as HTMLInputElement;
                        this.handleChange(key, checkbox.checked);
                    });
                } else if (param.type === 'array') {
                    element.addEventListener('input', (e) => {
                        const textarea = e.target as HTMLTextAreaElement;
                        const lines = textarea.value
                            .split('\n')
                            .map(l => l.trim())
                            .filter(l => l.length > 0);
                        this.handleChange(key, lines);
                    });
                }
            });
        }, 0);
    }

    render(container: HTMLElement): void {
        this.container = container;
        this.renderContent();
    }

    destroy(): void {
        this.container = null;
    }
}