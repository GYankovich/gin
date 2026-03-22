// frontend/src/shared/components/CustomSelect.ts
import { SelectOption, SelectGroup, SelectProps } from '../types/select.types';

export class CustomSelect {
    private container: HTMLElement;
    private props: SelectProps;
    private isOpen: boolean = false;
    private selectedOptions: SelectOption[] = [];
    private searchQuery: string = '';
    private highlightedIndex: number = -1;
    private selectId: string;
    private dropdownId: string;
    private searchInputId: string;

    // Элементы DOM
    private wrapper: HTMLElement | null = null;
    private selectButton: HTMLElement | null = null;
    private dropdown: HTMLElement | null = null;
    private searchInput: HTMLInputElement | null = null;

    // Таймер для debounce поиска
    private searchTimeout: number | null = null;

    // Флаг для блокировки закрытия (только во время ввода)
    private blockCloseUntil: number = 0;

    // Обработчики событий
    private handleClickOutside = (e: MouseEvent) => {
        const target = e.target as HTMLElement;
        const now = Date.now();

        console.log('🖱️ Click outside detected', {
            target: target.className,
            wrapperContains: this.wrapper?.contains(target),
            dropdownContains: this.dropdown?.contains(target),
            blockCloseUntil: this.blockCloseUntil - now,
            isOpen: this.isOpen
        });

        // Если сейчас блокируем закрытие - пропускаем
        if (now < this.blockCloseUntil) {
            console.log('🔵 Blocking close due to blockClose flag');
            return;
        }

        // Если список закрыт - ничего не делаем
        if (!this.isOpen) return;

        // Проверяем, кликнули ли внутри wrapper или dropdown
        const isInside = this.wrapper?.contains(target) || this.dropdown?.contains(target);

        // Если кликнули вне - закрываем
        if (!isInside) {
            console.log('🔴 Closing dropdown - click outside');
            this.closeDropdown();
        } else {
            console.log('🔵 Click inside dropdown/wrapper, keeping open');
        }
    };

    private handleEscapeKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape' && this.isOpen) {
            console.log('🔴 Closing due to Escape key');
            this.closeDropdown();
            e.preventDefault();
            e.stopPropagation();
        }
    };

    constructor(container: HTMLElement, props: SelectProps) {
        this.container = container;
        this.props = props;
        this.selectId = props.id || `select-${Math.random().toString(36).substr(2, 9)}`;
        this.dropdownId = `${this.selectId}-dropdown`;
        this.searchInputId = `${this.selectId}-search`;

        this.initSelectedOptions();
        this.render();
    }

    private initSelectedOptions(): void {
        if (this.props.value !== undefined) {
            const allOptions = this.getAllOptions();
            const selected = allOptions.find(opt => opt.value === this.props.value);
            if (selected) {
                this.selectedOptions = [selected];
            }
        }
    }

    private getAllOptions(): SelectOption[] {
        if (!this.props.options.length) return [];

        const firstItem = this.props.options[0];
        if ('group' in firstItem || 'options' in firstItem) {
            return (this.props.options as SelectGroup[]).flatMap(group => group.options);
        } else {
            return this.props.options as SelectOption[];
        }
    }

    private getFilteredOptions(): SelectOption[] {
        const allOptions = this.getAllOptions();

        if (!this.searchQuery.trim()) {
            return allOptions;
        }

        const query = this.searchQuery.toLowerCase();
        return allOptions.filter(opt =>
            opt.label.toLowerCase().includes(query) ||
            (opt.description && opt.description.toLowerCase().includes(query))
        );
    }

    private getGroupedOptions(): SelectGroup[] {
        if (!this.props.options.length) return [];

        const firstItem = this.props.options[0];
        if ('group' in firstItem || 'options' in firstItem) {
            return this.props.options as SelectGroup[];
        }

        const options = this.props.options as SelectOption[];
        const groups: Map<string, SelectOption[]> = new Map();

        options.forEach(opt => {
            const groupName = opt.group || 'Другое';
            if (!groups.has(groupName)) {
                groups.set(groupName, []);
            }
            groups.get(groupName)!.push(opt);
        });

        return Array.from(groups.entries()).map(([label, options]) => ({
            label,
            options
        }));
    }

    private toggleDropdown = (e?: Event): void => {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }

        if (this.props.disabled) return;

        if (this.isOpen) {
            this.closeDropdown();
        } else {
            this.openDropdown();
        }
    };

    private openDropdown(): void {
        console.log('🟢 openDropdown called');

        this.isOpen = true;
        this.highlightedIndex = -1;
        this.blockCloseUntil = 0; // Сбрасываем блокировку

        if (this.selectButton) {
            this.selectButton.setAttribute('aria-expanded', 'true');
        }

        if (this.dropdown) {
            this.dropdown.classList.add('open');
            this.dropdown.style.pointerEvents = 'auto';
        }

        // Добавляем обработчики
        setTimeout(() => {
            document.addEventListener('click', this.handleClickOutside);
            document.addEventListener('keydown', this.handleEscapeKey);
        }, 0);

        if (this.props.searchable) {
            setTimeout(() => {
                this.searchInput?.focus();
            }, 100);
        }
    }

    private closeDropdown(): void {
        if (!this.isOpen) return;

        console.log('🔴 closeDropdown called');

        this.isOpen = false;
        this.blockCloseUntil = 0; // Сбрасываем блокировку

        if (this.selectButton) {
            this.selectButton.setAttribute('aria-expanded', 'false');
        }

        if (this.dropdown) {
            this.dropdown.classList.remove('open');
        }

        // Удаляем обработчики
        document.removeEventListener('click', this.handleClickOutside);
        document.removeEventListener('keydown', this.handleEscapeKey);

        if (this.props.clearSearchOnClose) {
            this.searchQuery = '';
            if (this.searchInput) {
                this.searchInput.value = '';
            }
        }

        // Перерендерим, чтобы обновить UI
        this.render();
    }

    private handleOptionClick = (e: Event, option: SelectOption): void => {
        console.log('🖱️ Option clicked', option);

        e.preventDefault();
        e.stopPropagation();

        if (option.disabled) return;

        if (this.props.multiple) {
            const index = this.selectedOptions.findIndex(opt => opt.value === option.value);
            if (index === -1) {
                this.selectedOptions = [...this.selectedOptions, option];
            } else {
                this.selectedOptions = this.selectedOptions.filter(opt => opt.value !== option.value);
            }

            const value = this.props.multiple
                ? this.selectedOptions.map(opt => opt.value)
                : this.selectedOptions[0]?.value;

            this.props.onChange(value);
            this.render();
        } else {
            this.selectedOptions = [option];

            const value = this.selectedOptions[0]?.value;
            this.props.onChange(value);

            // Закрываем после выбора
            this.closeDropdown();
        }
    };

    private handleSearchInput = (e: Event): void => {
        console.log('🔍 Search input event');

        e.preventDefault();
        e.stopPropagation();

        const input = e.target as HTMLInputElement;
        const newQuery = input.value;

        this.searchQuery = newQuery;
        this.highlightedIndex = -1;

        // Блокируем закрытие на 300мс после последнего ввода
        this.blockCloseUntil = Date.now() + 300;

        // Обновляем только список опций
        this.updateOptionsList();

        if (this.props.onSearch) {
            if (this.searchTimeout) {
                window.clearTimeout(this.searchTimeout);
            }

            this.searchTimeout = window.setTimeout(() => {
                this.props.onSearch?.(newQuery);
                this.searchTimeout = null;
                // Снимаем блокировку после завершения поиска
                this.blockCloseUntil = 0;
            }, 300);
        }
    };

    private updateOptionsList(): void {
        if (!this.dropdown) return;

        const optionsContainer = this.dropdown.querySelector('.select-options');
        if (!optionsContainer) return;

        const filteredOptions = this.getFilteredOptions();

        if (filteredOptions.length === 0) {
            optionsContainer.innerHTML = '<div class="select-no-options">Ничего не найдено</div>';
        } else {
            optionsContainer.innerHTML = filteredOptions.map((opt, idx) => this.renderOption(opt, idx)).join('');
        }
    }

    private handleClear = (e: Event): void => {
        console.log('🧹 Clear clicked');

        e.preventDefault();
        e.stopPropagation();

        this.selectedOptions = [];
        this.props.onChange(this.props.multiple ? [] : undefined);
        this.render();
    };

    private handleKeyDown = (e: KeyboardEvent): void => {
        if (!this.isOpen) return;

        const filteredOptions = this.getFilteredOptions();

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                e.stopPropagation();
                this.highlightedIndex = Math.min(this.highlightedIndex + 1, filteredOptions.length - 1);
                this.scrollToHighlighted();
                break;
            case 'ArrowUp':
                e.preventDefault();
                e.stopPropagation();
                this.highlightedIndex = Math.max(this.highlightedIndex - 1, -1);
                this.scrollToHighlighted();
                break;
            case 'Enter':
                e.preventDefault();
                e.stopPropagation();
                if (this.highlightedIndex >= 0 && filteredOptions[this.highlightedIndex]) {
                    this.handleOptionClick(e, filteredOptions[this.highlightedIndex]);
                }
                break;
            case 'Escape':
                // Обрабатывается в handleEscapeKey
                break;
            case 'Tab':
                this.closeDropdown();
                break;
        }
    };

    private scrollToHighlighted(): void {
        setTimeout(() => {
            if (this.highlightedIndex >= 0 && this.dropdown) {
                const highlightedEl = this.dropdown.querySelector(`[data-index="${this.highlightedIndex}"]`);
                if (highlightedEl) {
                    highlightedEl.scrollIntoView({ block: 'nearest' });
                }
            }
        }, 10);
    }

    private renderSelectedContent(): string {
        if (this.selectedOptions.length === 0) {
            return `<span class="select-placeholder">${this.props.placeholder || 'Выберите...'}</span>`;
        }

        if (this.props.multiple) {
            return `
                <div class="select-multiple-tags">
                    ${this.selectedOptions.map(opt => `
                        <span class="select-tag">
                            ${opt.icon ? `<span class="select-tag-icon">${opt.icon}</span>` : ''}
                            <span class="select-tag-label">${opt.label}</span>
                            <span class="select-tag-remove" data-value="${opt.value}">×</span>
                        </span>
                    `).join('')}
                </div>
            `;
        }

        const selected = this.selectedOptions[0];
        return `
            <div class="select-selected">
                ${selected.icon ? `<span class="select-selected-icon">${selected.icon}</span>` : ''}
                <span class="select-selected-label">${selected.label}</span>
                ${selected.description ? `<span class="select-selected-description">${selected.description}</span>` : ''}
            </div>
        `;
    }

    render(): void {
        const filteredOptions = this.getFilteredOptions();
        const groupedOptions = this.props.groups ? this.getGroupedOptions() : [];

        this.container.innerHTML = `
            <div class="custom-select-wrapper ${this.props.className || ''}" id="${this.selectId}-wrapper">
                ${this.props.label ? `
                    <label class="select-label" for="${this.selectId}">
                        ${this.props.label}
                        ${this.props.required ? '<span class="required">*</span>' : ''}
                    </label>
                ` : ''}
                
                <div class="custom-select-container ${this.isOpen ? 'open' : ''} ${this.props.disabled ? 'disabled' : ''} ${this.props.error ? 'error' : ''}">
                    <button 
                        type="button" 
                        class="custom-select-button" 
                        id="${this.selectId}"
                        aria-haspopup="listbox" 
                        aria-expanded="${this.isOpen}"
                        aria-labelledby="${this.selectId} ${this.selectId}-label"
                        ${this.props.disabled ? 'disabled' : ''}
                    >
                        <div class="select-content">
                            ${this.renderSelectedContent()}
                        </div>
                        
                        <div class="select-indicators">
                            ${this.props.clearable && this.selectedOptions.length > 0 ? `
                                <span class="select-clear-indicator" id="${this.selectId}-clear">×</span>
                            ` : ''}
                            <span class="select-dropdown-indicator">▼</span>
                        </div>
                    </button>
                    
                    <div class="custom-select-dropdown" id="${this.dropdownId}" role="listbox">
                        ${this.props.searchable ? `
                            <div class="select-search">
                                <input 
                                    type="text" 
                                    class="select-search-input" 
                                    id="${this.searchInputId}"
                                    placeholder="Поиск..."
                                    value="${this.searchQuery}"
                                    autocomplete="off"
                                    ${this.isOpen ? '' : 'tabindex="-1"'}
                                >
                                ${this.searchQuery ? `
                                    <button type="button" class="select-search-clear" id="${this.searchInputId}-clear">×</button>
                                ` : ''}
                            </div>
                        ` : ''}
                        
                        <div class="select-options">
                            ${filteredOptions.length === 0 ? `
                                <div class="select-no-options">
                                    ${this.searchQuery ? 'Ничего не найдено' : 'Нет доступных опций'}
                                </div>
                            ` : ''}
                            
                            ${this.props.groups ?
            groupedOptions.map(group => `
                                    <div class="select-option-group">
                                        <div class="select-group-label">${group.label}</div>
                                        ${group.options
                .filter(opt => !this.searchQuery || opt.label.toLowerCase().includes(this.searchQuery.toLowerCase()))
                .map((opt, idx) => this.renderOption(opt, idx))
                .join('')}
                                    </div>
                                `).join('')
            :
            filteredOptions.map((opt, idx) => this.renderOption(opt, idx)).join('')
        }
                        </div>
                        
                        ${this.props.loading ? `
                            <div class="select-loading">
                                <div class="select-loading-spinner"></div>
                                <span>Загрузка...</span>
                            </div>
                        ` : ''}
                    </div>
                </div>
                
                ${this.props.error ? `
                    <div class="select-error">${this.props.error}</div>
                ` : ''}
            </div>
        `;

        this.attachEvents();
    }

    private renderOption(option: SelectOption, index: number): string {
        const isSelected = this.selectedOptions.some(opt => opt.value === option.value);
        const isHighlighted = index === this.highlightedIndex;

        return `
            <div 
                class="select-option ${isSelected ? 'selected' : ''} ${option.disabled ? 'disabled' : ''} ${isHighlighted ? 'highlighted' : ''}"
                role="option"
                aria-selected="${isSelected}"
                data-value="${option.value}"
                data-index="${index}"
                ${option.disabled ? 'aria-disabled="true"' : ''}
            >
                ${option.icon ? `<span class="select-option-icon">${option.icon}</span>` : ''}
                <div class="select-option-content">
                    <div class="select-option-label">${option.label}</div>
                    ${option.description ? `<div class="select-option-description">${option.description}</div>` : ''}
                </div>
                ${isSelected ? '<span class="select-option-checkmark">✓</span>' : ''}
            </div>
        `;
    }

    private attachEvents(): void {
        this.wrapper = document.getElementById(`${this.selectId}-wrapper`);
        this.selectButton = document.getElementById(this.selectId);
        this.dropdown = document.getElementById(this.dropdownId);
        this.searchInput = document.getElementById(this.searchInputId) as HTMLInputElement;

        if (this.selectButton) {
            this.selectButton.addEventListener('click', this.toggleDropdown);
            this.selectButton.addEventListener('mousedown', (e) => e.stopPropagation());
        }

        if (this.searchInput) {
            this.searchInput.addEventListener('input', this.handleSearchInput);
            this.searchInput.addEventListener('keydown', this.handleKeyDown);
            this.searchInput.addEventListener('click', (e) => e.stopPropagation());
            this.searchInput.addEventListener('mousedown', (e) => e.stopPropagation());
        }

        const searchClearBtn = document.getElementById(`${this.searchInputId}-clear`);
        if (searchClearBtn) {
            searchClearBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (this.searchInput) {
                    this.searchInput.value = '';
                    this.searchQuery = '';
                    this.updateOptionsList();

                    if (this.props.onSearch) {
                        this.props.onSearch('');
                    }
                }
            });
        }

        // Обработчик для клика по опциям
        if (this.dropdown) {
            this.dropdown.addEventListener('mousedown', (e) => {
                e.stopPropagation();
            });

            this.dropdown.addEventListener('click', (e) => {
                e.stopPropagation();

                const target = e.target as HTMLElement;
                const optionEl = target.closest('.select-option');

                if (optionEl && !optionEl.classList.contains('disabled')) {
                    const value = optionEl.getAttribute('data-value');
                    const allOptions = this.getAllOptions();
                    const option = allOptions.find(opt => String(opt.value) === value);

                    if (option) {
                        this.handleOptionClick(e, option);
                    }
                }
            });
        }

        const clearBtn = document.getElementById(`${this.selectId}-clear`);
        if (clearBtn) {
            clearBtn.addEventListener('click', this.handleClear);
            clearBtn.addEventListener('mousedown', (e) => e.stopPropagation());
        }

        if (this.selectButton) {
            this.selectButton.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                    e.preventDefault();
                    e.stopPropagation();
                    this.openDropdown();
                }
            });
        }

        if (this.props.multiple) {
            this.dropdown?.addEventListener('click', (e) => {
                e.stopPropagation();

                const target = e.target as HTMLElement;
                if (target.classList.contains('select-tag-remove')) {
                    const value = target.getAttribute('data-value');

                    if (value) {
                        const numValue = isNaN(Number(value)) ? value : Number(value);
                        this.selectedOptions = this.selectedOptions.filter(opt => opt.value !== numValue);

                        const finalValue = this.props.multiple
                            ? this.selectedOptions.map(opt => opt.value)
                            : this.selectedOptions[0]?.value;

                        this.props.onChange(finalValue);
                        this.render();
                    }
                }
            });
        }
    }

    public setValue(value: any): void {
        const allOptions = this.getAllOptions();

        if (this.props.multiple && Array.isArray(value)) {
            this.selectedOptions = allOptions.filter(opt => value.includes(opt.value));
        } else {
            const selected = allOptions.find(opt => opt.value === value);
            this.selectedOptions = selected ? [selected] : [];
        }

        this.render();
    }

    public setOptions(options: SelectOption[] | SelectGroup[]): void {
        this.props.options = options;
        this.render();
    }

    public setLoading(loading: boolean): void {
        this.props.loading = loading;
        this.render();
    }

    public disable(): void {
        this.props.disabled = true;
        this.render();
    }

    public enable(): void {
        this.props.disabled = false;
        this.render();
    }

    public destroy(): void {
        this.closeDropdown();
        this.container.innerHTML = '';
    }
}