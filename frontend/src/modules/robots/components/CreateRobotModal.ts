// frontend/src/modules/robots/components/CreateRobotModal.ts

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
    private static activeModal: CreateRobotModal | null = null;
    private container: HTMLElement;
    private onClose: () => void;
    private onSuccess: () => void;

    private robotTypes: RobotType[] = [];
    private tokens: Token[] = [];
    private loading: boolean = true;
    private isDataLoaded: boolean = false;

    private formData = {
        name: '',
        type: '',
        token_id: ''
    };

    private isClosed: boolean = false;
    private openSelect: string | null = null;
    private activeDropdown: HTMLElement | null = null;
    private modalContent: HTMLElement | null = null;
    private formContainer: HTMLElement | null = null;

    constructor(container: HTMLElement, onClose: () => void, onSuccess: () => void) {
        this.container = container;
        this.onClose = onClose;
        this.onSuccess = onSuccess;
        this.isClosed = false;

        if (CreateRobotModal.activeModal) {
            CreateRobotModal.activeModal.close();
        }
        CreateRobotModal.activeModal = this;
    }

    async loadData(): Promise<void> {
        this.loading = true;
        this.render();

        try {
            const token = localStorage.getItem('auth_token');

            const typesResponse = await fetch('/api/robots/types', {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (!typesResponse.ok) {
                throw new Error('Failed to load robot types');
            }

            const types = await typesResponse.json();
            this.robotTypes = types.filter((t: RobotType) => !t.hide_from_ui);

            const tokensResponse = await fetch('/api/apikey/data', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ limit: 100 })
            });

            if (!tokensResponse.ok) {
                throw new Error('Failed to load tokens');
            }

            const tokensData = await tokensResponse.json();
            this.tokens = tokensData.keys || [];

            this.isDataLoaded = true;

            // Бесшовная замена скелетона на форму
            this.replaceSkeletonWithForm();

        } catch (error) {
            console.error('Failed to load data:', error);
            if (!this.isClosed) {
                this.showError(error);
            }
        } finally {
            this.loading = false;
        }
    }

    private replaceSkeletonWithForm(): void {
        if (this.isClosed || !this.formContainer) return;

        const hasType = !!this.formData.type;
        const selectedType = this.robotTypes.find(t => t.num_value.toString() === this.formData.type);
        const typeLabel = selectedType?.name || 'Выберите тип робота';

        const hasToken = !!this.formData.token_id;
        const selectedToken = this.tokens.find(t => t.id.toString() === this.formData.token_id);
        const tokenLabel = selectedToken?.token_name || selectedToken?.token_preview || 'Выберите токен доступа';

        // Заменяем содержимое контейнера на форму
        this.formContainer.innerHTML = `
            <form class="modal-form" id="create-robot-form">
                <div class="modal-form-group">
                    <label for="robot-name">
                        <span>Название робота</span>
                        <span class="required">*</span>
                    </label>
                    <input type="text" id="robot-name" required
                        placeholder="Торговый робот 1"
                        value="${this.formData.name.replace(/"/g, '&quot;')}">
                </div>
                
                <div class="modal-form-group">
                    <label>
                        <span>Тип робота</span>
                        <span class="required">*</span>
                    </label>
                    <div class="modal-select">
                        <button type="button" class="modal-select-button" id="type-select-btn">
                            <span class="${hasType ? 'modal-select-value' : 'modal-select-placeholder'}">${this.escapeHtml(typeLabel)}</span>
                            <span class="modal-select-arrow">▼</span>
                        </button>
                        <div class="modal-select-dropdown" id="type-select-dropdown">
                            <div class="modal-select-search">
                                <input type="text" class="modal-select-search-input" placeholder="Поиск..." autocomplete="off">
                            </div>
                            <div class="modal-select-options">
                                ${this.robotTypes.map(type => `
                                    <div class="modal-select-option ${this.formData.type === type.num_value.toString() ? 'selected' : ''}" 
                                         data-value="${type.num_value}" data-label="${this.escapeHtml(type.name)}">
                                        <div class="modal-select-option-label">${this.escapeHtml(type.name)}</div>
                                        <div class="modal-select-option-description">${this.escapeHtml(type.description)}</div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="modal-form-group">
                    <label>
                        <span>Токен доступа</span>
                        <span class="required">*</span>
                    </label>
                    <div class="modal-select">
                        <button type="button" class="modal-select-button" id="token-select-btn">
                            <span class="${hasToken ? 'modal-select-value' : 'modal-select-placeholder'}">${this.escapeHtml(tokenLabel)}</span>
                            <span class="modal-select-arrow">▼</span>
                        </button>
                        <div class="modal-select-dropdown" id="token-select-dropdown">
                            <div class="modal-select-search">
                                <input type="text" class="modal-select-search-input" placeholder="Поиск..." autocomplete="off">
                            </div>
                            <div class="modal-select-options">
                                ${this.tokens.map(token => `
                                    <div class="modal-select-option ${this.formData.token_id === token.id.toString() ? 'selected' : ''}" 
                                         data-value="${token.id}" data-label="${this.escapeHtml(token.token_name || token.token_preview)}">
                                        <div class="modal-select-option-label">${this.escapeHtml(token.token_name || 'Без имени')}</div>
                                        <div class="modal-select-option-description">${this.escapeHtml(token.token_preview)}</div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="modal-actions">
                    <button type="button" class="modal-btn modal-btn-secondary" id="modal-cancel-btn">
                        Отмена
                    </button>
                    <button type="submit" class="modal-btn modal-btn-primary">
                        Создать робота
                    </button>
                </div>
            </form>
        `;

        // Прикрепляем обработчики после замены
        this.attachFormEvents();
        this.attachSelectEvents();
    }

    private showError(error: unknown): void {
        if (this.isClosed) return;

        if (this.formContainer) {
            this.formContainer.innerHTML = `
                <div class="modal-error">
                    <div class="modal-error-icon">⚠️</div>
                    <h3 class="modal-error-title">Ошибка загрузки</h3>
                    <p class="modal-error-message">${error instanceof Error ? error.message : 'Не удалось загрузить данные'}</p>
                    <button class="modal-btn modal-btn-secondary" id="modal-retry-btn">
                        Повторить
                    </button>
                </div>
            `;

            const retryBtn = document.getElementById('modal-retry-btn');
            if (retryBtn) {
                retryBtn.addEventListener('click', () => this.loadData());
            }
        }
    }

    private handleEscapeKey = (e: KeyboardEvent) => {
        if (this.isClosed) return;
        if (e.key === 'Escape') {
            if (this.openSelect) {
                this.closeSelect();
            } else {
                this.close();
            }
        }
    };

    private closeSelect(): void {
        if (this.openSelect && this.activeDropdown) {
            this.activeDropdown.classList.remove('open');
            this.activeDropdown = null;
            this.openSelect = null;
        }
    }

    private openSelectDropdown(selectType: 'type' | 'token', button: HTMLElement): void {
        if (this.openSelect) {
            this.closeSelect();
        }

        this.openSelect = selectType;
        const dropdown = document.getElementById(`${selectType}-select-dropdown`);

        if (dropdown && button) {
            const rect = button.getBoundingClientRect();
            dropdown.style.top = `${rect.bottom + 4}px`;
            dropdown.style.left = `${rect.left}px`;
            dropdown.style.width = `${rect.width}px`;
            dropdown.classList.add('open');
            this.activeDropdown = dropdown;

            const searchInput = dropdown.querySelector('.modal-select-search-input') as HTMLInputElement;
            if (searchInput) {
                searchInput.value = '';
                searchInput.focus();
                this.filterOptions(dropdown, '');
            }
        }
    }

    private filterOptions(dropdown: HTMLElement, searchValue: string): void {
        const options = dropdown.querySelectorAll('.modal-select-option');
        const query = searchValue.toLowerCase();

        options.forEach(opt => {
            const label = opt.querySelector('.modal-select-option-label')?.textContent?.toLowerCase() || '';
            const desc = opt.querySelector('.modal-select-option-description')?.textContent?.toLowerCase() || '';
            if (label.includes(query) || desc.includes(query)) {
                (opt as HTMLElement).style.display = '';
            } else {
                (opt as HTMLElement).style.display = 'none';
            }
        });
    }

    private selectOption(selectType: 'type' | 'token', value: string, label: string, button: HTMLElement): void {
        const span = button.querySelector('span:first-child');
        if (span) {
            span.textContent = label;
            span.className = 'modal-select-value';
        }

        if (selectType === 'type') {
            this.formData.type = value;
        } else {
            this.formData.token_id = value;
        }

        this.closeSelect();
    }

    private async handleSubmit(e: Event): Promise<void> {
        e.preventDefault();

        if (!this.formData.name || !this.formData.type || !this.formData.token_id) {
            alert('Пожалуйста, заполните все поля');
            return;
        }

        const submitBtn = this.container.querySelector('.modal-btn-primary') as HTMLButtonElement;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Создание...';
        }

        try {
            const token = localStorage.getItem('auth_token');
            const response = await fetch('/api/robots/create', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: this.formData.name,
                    type: parseInt(this.formData.type),
                    token_id: parseInt(this.formData.token_id),
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to create robot');
            }

            this.onSuccess();
            this.close();

        } catch (error) {
            console.error('Failed to create robot:', error);
            alert(`Ошибка: ${error instanceof Error ? error.message : 'Не удалось создать робота'}`);
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Создать робота';
            }
        }
    }

    private close(): void {
        if (this.isClosed) return;
        this.isClosed = true;
        document.removeEventListener('keydown', this.handleEscapeKey);
        this.container.innerHTML = '';
        if (CreateRobotModal.activeModal === this) {
            CreateRobotModal.activeModal = null;
        }
        this.onClose();
    }

    private attachFormEvents(): void {
        const form = document.getElementById('create-robot-form');
        const nameInput = document.getElementById('robot-name') as HTMLInputElement;
        const cancelBtn = document.getElementById('modal-cancel-btn');

        if (nameInput) {
            nameInput.addEventListener('input', (e) => {
                this.formData.name = (e.target as HTMLInputElement).value;
            });
        }

        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.close());
        }

        if (form) {
            form.addEventListener('submit', (e) => this.handleSubmit(e));
        }
    }

    private attachSelectEvents(): void {
        // Селект типа
        const typeBtn = document.getElementById('type-select-btn');
        const typeDropdown = document.getElementById('type-select-dropdown');
        if (typeBtn && typeDropdown) {
            typeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.openSelectDropdown('type', typeBtn);
            });

            const typeSearch = typeDropdown.querySelector('.modal-select-search-input') as HTMLInputElement;
            if (typeSearch) {
                typeSearch.addEventListener('input', (e) => {
                    this.filterOptions(typeDropdown, (e.target as HTMLInputElement).value);
                });
            }

            typeDropdown.querySelectorAll('.modal-select-option').forEach(opt => {
                opt.addEventListener('click', () => {
                    const value = opt.getAttribute('data-value');
                    const label = opt.getAttribute('data-label');
                    if (value && label && typeBtn) {
                        this.selectOption('type', value, label, typeBtn);
                    }
                });
            });
        }

        // Селект токена
        const tokenBtn = document.getElementById('token-select-btn');
        const tokenDropdown = document.getElementById('token-select-dropdown');
        if (tokenBtn && tokenDropdown) {
            tokenBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.openSelectDropdown('token', tokenBtn);
            });

            const tokenSearch = tokenDropdown.querySelector('.modal-select-search-input') as HTMLInputElement;
            if (tokenSearch) {
                tokenSearch.addEventListener('input', (e) => {
                    this.filterOptions(tokenDropdown, (e.target as HTMLInputElement).value);
                });
            }

            tokenDropdown.querySelectorAll('.modal-select-option').forEach(opt => {
                opt.addEventListener('click', () => {
                    const value = opt.getAttribute('data-value');
                    const label = opt.getAttribute('data-label');
                    if (value && label && tokenBtn) {
                        this.selectOption('token', value, label, tokenBtn);
                    }
                });
            });
        }

        // Закрытие селекта при клике вне
        document.addEventListener('click', (e) => {
            if (this.openSelect && this.activeDropdown) {
                const target = e.target as HTMLElement;
                const isSelectBtn = target.closest('#type-select-btn') || target.closest('#token-select-btn');
                const isDropdown = target.closest('.modal-select-dropdown');
                if (!isSelectBtn && !isDropdown) {
                    this.closeSelect();
                }
            }
        });
    }

    private attachModalEvents(): void {
        const closeBtn = document.getElementById('modal-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.close());
        }

        const overlay = this.container.querySelector('.modal-overlay');
        if (overlay) {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) this.close();
            });
        }

        document.addEventListener('keydown', this.handleEscapeKey);
    }

    render(): void {
        if (this.isClosed) return;

        this.container.innerHTML = `
            <div class="modal-overlay">
                <div class="modal-container">
                    <div class="modal-content">
                        <button class="modal-close" id="modal-close-btn">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 6L6 18M6 6l12 12"/>
                            </svg>
                        </button>
                        
                        <div class="modal-header">
                            <div class="modal-header-left">
                                <div class="modal-icon">✨</div>
                            </div>
                            <div class="modal-header-right">
                                <h3>Создание робота</h3>
                                <p class="modal-description">Укажите токен и тип робота. Настроить его можно будет позже</p>
                            </div>
                        </div>
                        
                        <div class="modal-form-container" id="modal-form-container">
                            <div class="modal-skeleton">
                                <div class="modal-form-group">
                                    <label>Название робота</label>
                                    <div class="skeleton-input"></div>
                                </div>
                                <div class="modal-form-group">
                                    <label>Тип робота</label>
                                    <div class="skeleton-input"></div>
                                </div>
                                <div class="modal-form-group">
                                    <label>Токен доступа</label>
                                    <div class="skeleton-input"></div>
                                </div>
                                <div class="modal-actions">
                                    <div class="skeleton-btn"></div>
                                    <div class="skeleton-btn"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.formContainer = document.getElementById('modal-form-container');
        this.attachModalEvents();

        // Если данные уже загружены, сразу показываем форму
        if (this.isDataLoaded) {
            this.replaceSkeletonWithForm();
        }
    }

    private escapeHtml(str: string): string {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}