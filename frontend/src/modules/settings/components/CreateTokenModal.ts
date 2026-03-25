// frontend/src/modules/settings/components/CreateTokenModal.ts

interface TokenType {
    id: number;
    tableName: string;
    columnName: string;
    name: string;
    description: string;
    numericValue: number;
    stringValue: string | null;
}

export class CreateTokenModal {
    private static activeModal: CreateTokenModal | null = null;
    private container: HTMLElement;
    private onClose: () => void;
    private onSuccess: (data: { name: string; token: string; tokenType: number }) => void;

    private tokenTypes: TokenType[] = [];
    private loading: boolean = true;
    private isDataLoaded: boolean = false;
    private isSaving: boolean = false;
    private modalError: string | null = null;

    private formData = {
        name: '',
        token: '',
        tokenType: ''
    };

    private errors = {
        name: false,
        tokenType: false,
        token: false
    };

    private isClosed: boolean = false;
    private openSelect: string | null = null;
    private activeDropdown: HTMLElement | null = null;
    private formContainer: HTMLElement | null = null;

    constructor(
        container: HTMLElement,
        onClose: () => void,
        onSuccess: (data: { name: string; token: string; tokenType: number }) => void
    ) {
        this.container = container;
        this.onClose = onClose;
        this.onSuccess = onSuccess;
        this.isClosed = false;

        if (CreateTokenModal.activeModal) {
            CreateTokenModal.activeModal.close();
        }
        CreateTokenModal.activeModal = this;
    }

    async loadData(): Promise<void> {
        this.loading = true;
        this.render();

        try {
            const authToken = localStorage.getItem('auth_token');

            // Загружаем типы токенов
            const typesResponse = await fetch('/api/dictionary/data', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ tableName: "TOKEN", columnName: "TYPE" })
            });

            if (!typesResponse.ok) {
                throw new Error('Failed to load token types');
            }

            this.tokenTypes = await typesResponse.json();
            console.log('Loaded token types:', this.tokenTypes);

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

    private validateForm(): boolean {
        let isValid = true;

        // Валидация названия
        if (!this.formData.name.trim()) {
            this.errors.name = true;
            isValid = false;
        } else {
            this.errors.name = false;
        }

        // Валидация типа токена
        if (!this.formData.tokenType) {
            this.errors.tokenType = true;
            isValid = false;
        } else {
            this.errors.tokenType = false;
        }

        // Валидация значения токена
        if (!this.formData.token.trim()) {
            this.errors.token = true;
            isValid = false;
        } else {
            this.errors.token = false;
        }

        return isValid;
    }

    private clearFieldError(field: keyof typeof this.errors): void {
        this.errors[field] = false;
        this.updateFieldErrorStyle(field);
    }

    private updateFieldErrorStyle(field: keyof typeof this.errors): void {
        const element = document.getElementById(`field-${field}`);
        if (element) {
            if (this.errors[field]) {
                element.classList.add('error');
            } else {
                element.classList.remove('error');
            }
        }
    }

    private updateAllFieldErrors(): void {
        this.updateFieldErrorStyle('name');
        this.updateFieldErrorStyle('tokenType');
        this.updateFieldErrorStyle('token');
    }

    private replaceSkeletonWithForm(): void {
        if (this.isClosed || !this.formContainer) return;

        const hasTokenType = !!this.formData.tokenType;
        const selectedType = this.tokenTypes.find(t => t.numericValue.toString() === this.formData.tokenType);
        const typeLabel = selectedType?.name || 'Выберите тип токена';

        this.formContainer.innerHTML = `
            <form class="modal-form" id="create-token-form">
                <div class="modal-form-group" id="field-name">
                    <label for="token-name">
                        <span>Название токена</span>
                        <span class="required">*</span>
                    </label>
                    <input type="text" id="token-name" class="form-input" 
                        placeholder="Например: Основной токен"
                        autocomplete="off"
                        value="">
                    <div class="field-error-message">Пожалуйста, укажите название токена</div>
                </div>
                
                <div class="modal-form-group" id="field-tokenType">
                    <label>
                        <span>Тип токена</span>
                        <span class="required">*</span>
                    </label>
                    <div class="modal-select">
                        <button type="button" class="modal-select-button" id="type-select-btn">
                            <span class="${hasTokenType ? 'modal-select-value' : 'modal-select-placeholder'}">${this.escapeHtml(typeLabel)}</span>
                            <span class="modal-select-arrow">▼</span>
                        </button>
                        <div class="modal-select-dropdown" id="type-select-dropdown">
                            <div class="modal-select-search">
                                <input type="text" class="modal-select-search-input" placeholder="Поиск..." autocomplete="off">
                            </div>
                            <div class="modal-select-options">
                                ${this.tokenTypes.map(type => `
                                    <div class="modal-select-option ${this.formData.tokenType === type.numericValue.toString() ? 'selected' : ''}" 
                                         data-value="${type.numericValue}" 
                                         data-label="${this.escapeHtml(type.name)}"
                                         data-description="${this.escapeHtml(type.description)}">
                                        <div class="modal-select-option-label">${this.escapeHtml(type.name)}</div>
                                        <div class="modal-select-option-description">${this.escapeHtml(type.description)}</div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                    <div class="field-error-message">Пожалуйста, выберите тип токена</div>
                </div>
                
                <div class="modal-form-group" id="field-token">
                    <label for="token-value">
                        <span>Токен доступа</span>
                        <span class="required">*</span>
                    </label>
                    <input 
                        type="text" 
                        id="token-value" 
                        class="form-input" 
                        placeholder="t.xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                        autocomplete="off"
                        value="">
                    <div class="field-error-message">Пожалуйста, введите токен доступа</div>
                </div>

                ${this.modalError ? `
                    <div class="modal-error">
                        <span class="error-icon">⚠️</span>
                        <span>${this.escapeHtml(this.modalError)}</span>
                    </div>
                ` : ''}
                
                <div class="modal-actions">
                    <button type="button" class="modal-btn modal-btn-secondary" id="modal-cancel-btn">
                        Отмена
                    </button>
                    <button type="submit" class="modal-btn modal-btn-primary" ${this.isSaving ? 'disabled' : ''}>
                        ${this.isSaving ? 'Добавление...' : 'Добавить'}
                    </button>
                </div>
            </form>
        `;

        // Прикрепляем обработчики после замены
        this.attachFormEvents();
        this.attachSelectEvents();
        this.updateAllFieldErrors();
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

    private openSelectDropdown(button: HTMLElement): void {
        if (this.openSelect) {
            this.closeSelect();
        }

        this.openSelect = 'type';
        const dropdown = document.getElementById('type-select-dropdown');

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

    private selectOption(value: string, label: string, button: HTMLElement): void {
        const span = button.querySelector('span:first-child');
        if (span) {
            span.textContent = label;
            span.className = 'modal-select-value';
        }

        this.formData.tokenType = value;
        this.clearFieldError('tokenType');
        this.closeSelect();
    }

    private async handleSubmit(e: Event): Promise<void> {
        e.preventDefault();

        // Валидация
        if (!this.validateForm()) {
            this.updateAllFieldErrors();
            return;
        }

        // Дополнительная валидация формата токена для T-Invest
        const selectedType = this.tokenTypes.find(t => t.numericValue.toString() === this.formData.tokenType);
        if (selectedType?.stringValue === 'T-Invest' && !this.formData.token.startsWith('t.')) {
            this.modalError = 'Токен T-Invest должен начинаться с t.';
            this.render();
            return;
        }

        this.isSaving = true;
        this.render();

        try {
            await this.onSuccess({
                name: this.formData.name.trim(),
                token: this.formData.token.trim(),
                tokenType: parseInt(this.formData.tokenType)
            });

            this.close();
        } catch (error: any) {
            this.modalError = error.message || 'Ошибка при добавлении токена';
            this.isSaving = false;
            this.render();
        }
    }

    private close(): void {
        if (this.isClosed) return;
        this.isClosed = true;
        document.removeEventListener('keydown', this.handleEscapeKey);
        this.container.innerHTML = '';
        if (CreateTokenModal.activeModal === this) {
            CreateTokenModal.activeModal = null;
        }
        this.onClose();
    }

    private attachFormEvents(): void {
        const form = document.getElementById('create-token-form');
        const nameInput = document.getElementById('token-name') as HTMLInputElement;
        const tokenInput = document.getElementById('token-value') as HTMLInputElement;
        const cancelBtn = document.getElementById('modal-cancel-btn');

        if (nameInput) {
            nameInput.addEventListener('input', (e) => {
                this.formData.name = (e.target as HTMLInputElement).value;
                this.clearFieldError('name');
                this.modalError = null;
            });
        }

        if (tokenInput) {
            tokenInput.addEventListener('input', (e) => {
                this.formData.token = (e.target as HTMLInputElement).value;
                this.clearFieldError('token');
                this.modalError = null;
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
        const typeBtn = document.getElementById('type-select-btn');
        const typeDropdown = document.getElementById('type-select-dropdown');

        if (typeBtn && typeDropdown) {
            typeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.openSelectDropdown(typeBtn);
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
                        this.selectOption(value, label, typeBtn);
                    }
                });
            });
        }

        // Закрытие селекта при клике вне
        document.addEventListener('click', (e) => {
            if (this.openSelect && this.activeDropdown) {
                const target = e.target as HTMLElement;
                const isSelectBtn = target.closest('#type-select-btn');
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
                                <div class="modal-icon">🔑</div>
                            </div>
                            <div class="modal-header-right">
                                <h3>Добавить токен</h3>
                                <p class="modal-description">Укажите название, тип и значение токена доступа</p>
                            </div>
                        </div>
                        
                        <div class="modal-form-container" id="modal-form-container">
                            <div class="modal-skeleton">
                                <div class="modal-form-group">
                                    <label>Название токена</label>
                                    <div class="skeleton-input"></div>
                                </div>
                                <div class="modal-form-group">
                                    <label>Тип токена</label>
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