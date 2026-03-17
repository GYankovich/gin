// frontend/src/modules/robots/components/CreateRobotModal.ts
import { robotService } from '../services/robotService';
import { router } from '../../../core/router';

interface RobotType {
    id: number;
    num_value: number;
    name: string;
    description: string;
}

interface Token {
    id: number;
    token_name: string | null;
    token_preview: string;
}

export class CreateRobotModal {
    private container: HTMLElement;
    private onClose: () => void;
    private onSuccess: () => void;

    private robotTypes: RobotType[] = [];
    private tokens: Token[] = [];
    private loading: boolean = true;

    private formData = {
        name: '',
        type: '',
        token_id: ''
    };

    constructor(container: HTMLElement, onClose: () => void, onSuccess: () => void) {
        this.container = container;
        this.onClose = onClose;
        this.onSuccess = onSuccess;
    }

    async loadData(): Promise<void> {
        this.loading = true;
        this.render();

        try {
            console.log('📡 Fetching robot types...');
            const typesResponse = await fetch('/api/robots/types', {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
                    'Content-Type': 'application/json'
                }
            });

            if (!typesResponse.ok) {
                throw new Error('Failed to load robot types');
            }

            const types = await typesResponse.json();
            this.robotTypes = types.filter((t: RobotType) => !t.hide_from_ui);
            console.log('✅ Robot types loaded:', this.robotTypes);

            console.log('📡 Fetching tokens...');
            const tokensResponse = await fetch('/api/apikey/data', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ limit: 100 })
            });

            if (!tokensResponse.ok) {
                throw new Error('Failed to load tokens');
            }

            const tokensData = await tokensResponse.json();
            this.tokens = tokensData.keys || [];
            console.log('✅ Tokens loaded:', this.tokens);

        } catch (error) {
            console.error('❌ Failed to load data:', error);
            this.showError(error);
        } finally {
            this.loading = false;
            this.render();
        }
    }

    private showError(error: unknown): void {
        this.container.innerHTML = `
            <div class="fixed inset-0 z-50 overflow-y-auto" aria-labelledby="modal-title" role="dialog" aria-modal="true">
                <div class="flex items-end justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
                    <div class="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75 dark:bg-gray-900 dark:bg-opacity-75" aria-hidden="true"></div>
                    <span class="hidden sm:inline-block sm:align-middle sm:h-screen">&#8203;</span>
                    
                    <div class="inline-block w-full max-w-lg overflow-hidden text-left align-bottom transition-all transform bg-white rounded-lg shadow-xl dark:bg-gray-800 sm:my-8 sm:align-middle">
                        <div class="px-4 pt-5 pb-4 bg-white dark:bg-gray-800 sm:p-6 sm:pb-4">
                            <div class="sm:flex sm:items-start">
                                <div class="flex items-center justify-center flex-shrink-0 w-12 h-12 mx-auto bg-red-100 rounded-full dark:bg-red-900 sm:mx-0 sm:h-10 sm:w-10">
                                    <svg class="w-6 h-6 text-red-600 dark:text-red-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                                    </svg>
                                </div>
                                <div class="mt-3 text-center sm:mt-0 sm:ml-4 sm:text-left">
                                    <h3 class="text-lg font-medium leading-6 text-gray-900 dark:text-gray-100" id="modal-title">
                                        Ошибка загрузки
                                    </h3>
                                    <div class="mt-2">
                                        <p class="text-sm text-gray-500 dark:text-gray-400">
                                            ${error instanceof Error ? error.message : 'Не удалось загрузить данные'}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="px-4 py-3 bg-gray-50 dark:bg-gray-700 sm:px-6 sm:flex sm:flex-row-reverse">
                            <button type="button" 
                                class="inline-flex justify-center w-full px-4 py-2 text-base font-medium text-white bg-red-600 border border-transparent rounded-md shadow-sm hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 sm:ml-3 sm:w-auto sm:text-sm"
                                onclick="this.closest('[role=dialog]').remove()">
                                Закрыть
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    private handleInputChange(field: keyof typeof this.formData, value: string): void {
        this.formData[field] = value;
    }

    private async handleSubmit(e: Event): Promise<void> {
        e.preventDefault();

        if (!this.formData.name || !this.formData.type || !this.formData.token_id) {
            alert('Пожалуйста, заполните все поля');
            return;
        }

        const typeValue = parseInt(this.formData.type);
        const status = typeValue === 1 ? 2 : 1;

        const submitData = {
            name: this.formData.name,
            type: typeValue,
            token_id: parseInt(this.formData.token_id),
            status: status
        };

        console.log('📤 Creating robot:', submitData);

        try {
            const response = await fetch('/api/robots/create', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(submitData)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to create robot');
            }

            console.log('✅ Robot created successfully');
            this.onSuccess();
            this.close();

        } catch (error) {
            console.error('❌ Failed to create robot:', error);
            alert(`Ошибка: ${error instanceof Error ? error.message : 'Не удалось создать робота'}`);
        }
    }

    private close(): void {
        this.container.innerHTML = '';
        this.onClose();
    }

    render(): void {
        if (this.loading) {
            this.container.innerHTML = `
            <div class="modal-overlay">
                <div class="modal-container">
                    <div class="modal-content">
                        <div class="modal-loading">
                            <div class="modal-spinner"></div>
                            <div class="modal-loading-text">Загрузка данных...</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
            return;
        }

        this.container.innerHTML = `
        <div class="modal-overlay">
            <div class="modal-container">
                <div class="modal-content">
                    <div class="modal-header">
                        <div>
                            <h3>Создание нового робота</h3>
                            <p>Заполните информацию для создания</p>
                        </div>
                        <button class="close-btn" onclick="this.closest('.modal-overlay').remove()">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                            </svg>
                        </button>
                    </div>

                    <form class="modal-form" id="create-robot-form" autocomplete="off">
                        <div class="form-group">
                            <label for="robot-name">
                                Название робота <span class="required">*</span>
                            </label>
                            <input type="text" id="robot-name" required
                                placeholder="Например: Торговый робот 1"
                                value="${this.formData.name}">
                        </div>

                        <div class="form-group">
                            <label for="robot-type">
                                Тип робота <span class="required">*</span>
                            </label>
                            <select id="robot-type" required>
                                <option value="">Выберите тип робота</option>
                                ${this.robotTypes.map(type => `
                                    <option value="${type.num_value}" ${this.formData.type === type.num_value.toString() ? 'selected' : ''}>
                                        ${type.name}
                                    </option>
                                `).join('')}
                            </select>
                        </div>

                        <div class="form-group">
                            <label for="token-id">
                                Токен доступа <span class="required">*</span>
                            </label>
                            <select id="token-id" required>
                                <option value="">Выберите токен</option>
                                ${this.tokens.map(token => `
                                    <option value="${token.id}" ${this.formData.token_id === token.id.toString() ? 'selected' : ''}>
                                        ${token.token_name || 'Без имени'} (${token.token_preview || '***'})
                                    </option>
                                `).join('')}
                            </select>
                        </div>

                        <div class="modal-actions">
                            <button type="button" class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">
                                Отмена
                            </button>
                            <button type="submit" class="btn btn-primary">
                                Создать робота
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    `;


        setTimeout(() => {
            const form = document.getElementById('create-robot-form');
            const nameInput = document.getElementById('robot-name') as HTMLInputElement;
            const typeSelect = document.getElementById('robot-type') as HTMLSelectElement;
            const tokenSelect = document.getElementById('token-id') as HTMLSelectElement;

            if (nameInput) {
                nameInput.addEventListener('input', (e) => {
                    this.handleInputChange('name', (e.target as HTMLInputElement).value);
                });
            }

            if (typeSelect) {
                typeSelect.addEventListener('change', (e) => {
                    this.handleInputChange('type', (e.target as HTMLSelectElement).value);
                });
            }

            if (tokenSelect) {
                tokenSelect.addEventListener('change', (e) => {
                    this.handleInputChange('token_id', (e.target as HTMLSelectElement).value);
                });
            }

            form?.addEventListener('submit', (e) => this.handleSubmit(e));
        }, 0);
    }
}