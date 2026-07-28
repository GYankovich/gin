///@EPIC Frontend.ITEM Shared.TOPIC FrontendSrcSharedComponentsCustomselect [1]
///@ Исходный модуль `frontend/src/shared/components/CustomSelect.ts` — автоматическая разметка для Obsidian Source Scanner.

// frontend/src/shared/components/CustomSelect.ts
import { SelectOption, SelectProps } from '../types/select.types';

export class CustomSelect {
    private container: HTMLElement;
    private props: SelectProps;
    private isOpen: boolean = false;
    private selectedOption: SelectOption | null = null;
    private searchQuery: string = '';
    private wrapper: HTMLElement | null = null;
    private dropdown: HTMLElement | null = null;
    private searchInput: HTMLInputElement | null = null;

    constructor(container: HTMLElement, props: SelectProps) {
        this.container = container;
        this.props = props;
        this.initSelected();
        this.render();
    }

    private initSelected(): void {
        if (this.props.value !== undefined) {
            const allOptions = this.getAllOptions();
            const selected = allOptions.find(opt => opt.value === this.props.value);
            if (selected) {
                this.selectedOption = selected;
            }
        }
    }

    private getAllOptions(): SelectOption[] {
        return this.props.options as SelectOption[];
    }

    private getFilteredOptions(): SelectOption[] {
        const allOptions = this.getAllOptions();
        if (!this.searchQuery.trim()) return allOptions;

        const query = this.searchQuery.toLowerCase();
        return allOptions.filter(opt =>
            opt.label.toLowerCase().includes(query) ||
            (opt.description && opt.description.toLowerCase().includes(query))
        );
    }

    private handleClickOutside = (e: MouseEvent): void => {
        if (!this.wrapper?.contains(e.target as Node)) {
            this.isOpen = false;
            this.searchQuery = '';
            this.render();
        }
    };

    private toggleDropdown = (e: Event): void => {
        e.preventDefault();
        e.stopPropagation();
        if (this.props.disabled) return;

        this.isOpen = !this.isOpen;
        this.render();

        if (this.isOpen && this.props.searchable) {
            setTimeout(() => {
                const searchInput = this.wrapper?.querySelector('.modal-select-search-input') as HTMLInputElement;
                if (searchInput) {
                    searchInput.focus();
                }
            }, 50);
        }

        if (this.isOpen) {
            document.addEventListener('click', this.handleClickOutside);
        } else {
            document.removeEventListener('click', this.handleClickOutside);
        }
    };

    private handleOptionClick = (option: SelectOption): void => {
        if (option.disabled) return;

        this.selectedOption = option;
        this.isOpen = false;
        this.searchQuery = '';
        this.props.onChange(option.value);
        this.render();
        document.removeEventListener('click', this.handleClickOutside);
    };

    private handleSearch = (e: Event): void => {
        const input = e.target as HTMLInputElement;
        this.searchQuery = input.value;
        this.updateOptionsList();
    };

    private updateOptionsList(): void {
        const optionsContainer = this.dropdown?.querySelector('.modal-select-options');
        if (!optionsContainer) return;

        const filteredOptions = this.getFilteredOptions();

        if (filteredOptions.length === 0) {
            optionsContainer.innerHTML = '<div class="modal-select-no-options">Ничего не найдено</div>';
            return;
        }

        optionsContainer.innerHTML = filteredOptions.map(opt => `
            <div class="modal-select-option ${this.selectedOption?.value === opt.value ? 'selected' : ''}" data-value="${opt.value}">
                <div class="modal-select-option-label">${this.escapeHtml(opt.label)}</div>
                ${opt.description ? `<div class="modal-select-option-description">${this.escapeHtml(opt.description)}</div>` : ''}
            </div>
        `).join('');

        // Прикрепляем обработчики
        optionsContainer.querySelectorAll('.modal-select-option').forEach(el => {
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                const value = el.getAttribute('data-value');
                const option = filteredOptions.find(opt => String(opt.value) === value);
                if (option) this.handleOptionClick(option);
            });
        });
    }

    private escapeHtml(str: string): string {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    render(): void {
        const filteredOptions = this.getFilteredOptions();

        this.container.innerHTML = `
            <div class="modal-select-wrapper ${this.isOpen ? 'open' : ''}">
                <button type="button" class="modal-select-button" ${this.props.disabled ? 'disabled' : ''}>
                    <span class="${!this.selectedOption ? 'modal-select-placeholder' : 'modal-select-value'}">
                        ${this.selectedOption ? this.escapeHtml(this.selectedOption.label) : (this.props.placeholder || 'Выберите...')}
                    </span>
                    <span class="modal-select-arrow">▼</span>
                </button>
                
                <div class="modal-select-dropdown">
                    ${this.props.searchable ? `
                        <div class="modal-select-search">
                            <input type="text" 
                                   class="modal-select-search-input" 
                                   placeholder="Поиск..."
                                   value="${this.escapeHtml(this.searchQuery)}"
                                   autocomplete="off">
                        </div>
                    ` : ''}
                    <div class="modal-select-options">
                        ${filteredOptions.length === 0 && this.searchQuery ? `
                            <div class="modal-select-no-options">Ничего не найдено</div>
                        ` : filteredOptions.map(opt => `
                            <div class="modal-select-option ${this.selectedOption?.value === opt.value ? 'selected' : ''}" data-value="${opt.value}">
                                <div class="modal-select-option-label">${this.escapeHtml(opt.label)}</div>
                                ${opt.description ? `<div class="modal-select-option-description">${this.escapeHtml(opt.description)}</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;

        this.attachEvents();
    }

    private attachEvents(): void {
        this.wrapper = this.container.querySelector('.modal-select-wrapper');
        const button = this.container.querySelector('.modal-select-button');
        this.dropdown = this.container.querySelector('.modal-select-dropdown');

        if (button) {
            button.removeEventListener('click', this.toggleDropdown);
            button.addEventListener('click', this.toggleDropdown);
        }

        if (this.dropdown) {
            this.searchInput = this.dropdown.querySelector('.modal-select-search-input');
            if (this.searchInput) {
                this.searchInput.removeEventListener('input', this.handleSearch);
                this.searchInput.addEventListener('input', this.handleSearch);
                this.searchInput.addEventListener('click', (e) => e.stopPropagation());
            }
        }

        // Обновляем список опций при рендере
        this.updateOptionsList();
    }

    public setValue(value: any): void {
        const option = this.getAllOptions().find(opt => opt.value === value);
        if (option) {
            this.selectedOption = option;
            this.render();
        }
    }

    public setOptions(options: SelectOption[]): void {
        this.props.options = options;
        this.render();
    }

    public destroy(): void {
        document.removeEventListener('click', this.handleClickOutside);
        this.container.innerHTML = '';
    }
}