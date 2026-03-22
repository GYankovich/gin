// frontend/src/modules/robots/components/CreateRobotModal.ts
import { CustomSelect } from '../../../shared/components/CustomSelect';
import type { SelectOption } from '../../../shared/types/select.types';

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

    private typeSelect: CustomSelect | null = null;
    private tokenSelect: CustomSelect | null = null;

    private handleOverlayClick = (e: MouseEvent) => {
        const target = e.target as HTMLElement;

        // Проверяем, не кликнули ли мы внутри селекта
        const isSelectClick = target.closest('.custom-select-wrapper') !== null;
        const isDropdownClick = target.closest('.custom-select-dropdown') !== null;

        console.log('🖱️ Modal overlay click', {
            target: target.className,
            isSelectClick,
            isDropdownClick
        });

        // Если клик по overlay и не по селекту - закрываем
        if (target.classList.contains('modal-overlay') && !isSelectClick && !isDropdownClick) {
            console.log('🔴 Closing modal due to overlay click');
            this.close();
        }
    };

    private handleContentClick = (e: MouseEvent) => {
        // Останавливаем всплытие для всех кликов внутри контента
        e.stopPropagation();
    };

    private handleEscapeKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
            const anySelectOpen = document.querySelector('.custom-select-dropdown.open') !== null;

            console.log('🔑 Escape key pressed', { anySelectOpen });

            if (!anySelectOpen) {
                console.log('🔴 Closing modal due to Escape');
                this.close();
            }
        }
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
            <div class="modal-overlay">
                <div class="modal-container">
                    <div class="modal-content">
                        <div class="modal-error">
                            <div class="modal-error-icon">
                                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                                </svg>
                            </div>
                            <h3 class="modal-error-title">Ошибка загрузки</h3>
                            <p class="modal-error-message">${error instanceof Error ? error.message : 'Не удалось загрузить данные'}</p>
                            <button class="btn-create" id="modal-close-error-btn">
                                Закрыть
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        setTimeout(() => {
            const closeBtn = document.getElementById('modal-close-error-btn');
            if (closeBtn) {
                closeBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.close();
                });
            }

            const overlay = this.container.querySelector('.modal-overlay');
            if (overlay) {
                overlay.addEventListener('click', this.handleOverlayClick);
            }

            const content = this.container.querySelector('.modal-content');
            if (content) {
                content.addEventListener('click', this.handleContentClick);
            }

            document.addEventListener('keydown', this.handleEscapeKey);
        }, 0);
    }

    private handleInputChange(field: keyof typeof this.formData, value: string): void {
        this.formData[field] = value;
    }

    private async handleSubmit(e: Event): Promise<void> {
        e.preventDefault();
        e.stopPropagation();

        if (!this.formData.name || !this.formData.type || !this.formData.token_id) {
            alert('Пожалуйста, заполните все поля');
            return;
        }

        const typeValue = parseInt(this.formData.type);


        const submitData = {
            name: this.formData.name,
            type: typeValue,
            token_id: parseInt(this.formData.token_id),
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

            document.removeEventListener('keydown', this.handleEscapeKey);

            this.onSuccess();
            this.close();

        } catch (error) {
            console.error('❌ Failed to create robot:', error);
            alert(`Ошибка: ${error instanceof Error ? error.message : 'Не удалось создать робота'}`);
        }
    }

    private close(): void {
        console.log('🔴 Closing modal');

        document.removeEventListener('keydown', this.handleEscapeKey);

        const overlay = this.container.querySelector('.modal-overlay');
        if (overlay) {
            overlay.removeEventListener('click', this.handleOverlayClick);
        }

        const content = this.container.querySelector('.modal-content');
        if (content) {
            content.removeEventListener('click', this.handleContentClick);
        }

        if (this.typeSelect) {
            this.typeSelect.destroy();
            this.typeSelect = null;
        }
        if (this.tokenSelect) {
            this.tokenSelect.destroy();
            this.tokenSelect = null;
        }

        this.container.innerHTML = '';
        this.onClose();
    }

    private initCustomSelects(): void {
        const typeOptions: SelectOption[] = this.robotTypes.map(type => ({
            value: type.num_value,
            label: type.name,
            description: type.description
        }));

        const typeContainer = document.getElementById('robot-type-select');
        if (typeContainer) {
            typeContainer.innerHTML = '';
            this.typeSelect = new CustomSelect(typeContainer, {
                options: typeOptions,
                placeholder: 'Выберите тип робота',
                label: 'Тип робота',
                required: true,
                searchable: true,
                onChange: (value) => {
                    this.formData.type = value as string;
                }
            });
        }

        const tokenOptions: SelectOption[] = this.tokens.map(token => ({
            value: token.id,
            label: token.token_name || 'Без имени',
            description: token.token_preview
        }));

        const tokenContainer = document.getElementById('token-id-select');
        if (tokenContainer) {
            tokenContainer.innerHTML = '';
            this.tokenSelect = new CustomSelect(tokenContainer, {
                options: tokenOptions,
                placeholder: 'Выберите токен',
                label: 'Токен доступа',
                required: true,
                searchable: true,
                onChange: (value) => {
                    this.formData.token_id = value as string;
                }
            });
        }
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

            setTimeout(() => {
                const overlay = this.container.querySelector('.modal-overlay');
                if (overlay) {
                    overlay.addEventListener('click', this.handleOverlayClick);
                }

                const content = this.container.querySelector('.modal-content');
                if (content) {
                    content.addEventListener('click', this.handleContentClick);
                }

                document.addEventListener('keydown', this.handleEscapeKey);
            }, 0);

            return;
        }

        this.container.innerHTML = `
            <div class="modal-overlay">
                <div class="modal-container">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h3>Создание нового робота</h3>
                            <button class="close-btn" id="modal-close-btn">
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

                            <div class="form-group" id="robot-type-select">
                                <!-- Сюда будет вставлен кастомный селект -->
                            </div>

                            <div class="form-group" id="token-id-select">
                                <!-- Сюда будет вставлен кастомный селект -->
                            </div>

                            <div class="modal-actions">
                                <button type="submit" class="btn-create">
                                    Создать робота
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        `;

        this.initCustomSelects();

        setTimeout(() => {
            const form = document.getElementById('create-robot-form');
            const nameInput = document.getElementById('robot-name') as HTMLInputElement;
            const closeBtn = document.getElementById('modal-close-btn');
            const overlay = this.container.querySelector('.modal-overlay');
            const content = this.container.querySelector('.modal-content');

            if (nameInput) {
                nameInput.addEventListener('input', (e) => {
                    e.stopPropagation();
                    this.handleInputChange('name', (e.target as HTMLInputElement).value);
                });
                nameInput.addEventListener('click', (e) => e.stopPropagation());
                nameInput.addEventListener('mousedown', (e) => e.stopPropagation());
            }

            if (closeBtn) {
                closeBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.close();
                });
                closeBtn.addEventListener('mousedown', (e) => e.stopPropagation());
            }

            if (overlay) {
                overlay.addEventListener('click', this.handleOverlayClick);
            }

            if (content) {
                content.addEventListener('click', this.handleContentClick);
                content.addEventListener('mousedown', (e) => e.stopPropagation());
            }

            form?.addEventListener('submit', (e) => this.handleSubmit(e));

            document.addEventListener('keydown', this.handleEscapeKey);
        }, 0);
    }
}