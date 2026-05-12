///@EPIC Frontend.ITEM Shared.TOPIC FrontendSrcSharedTypesSelectTypes [1]
///@ Исходный модуль `frontend/src/shared/types/select.types.ts` — автоматическая разметка для Obsidian Source Scanner.

// frontend/src/shared/types/select.types.ts
export interface SelectOption {
    value: string | number;
    label: string;
    description?: string;
    icon?: string;
    disabled?: boolean;
    group?: string;
}

export interface SelectGroup {
    label: string;
    options: SelectOption[];
}

export interface SelectProps {
    options: SelectOption[] | SelectGroup[];
    value?: string | number;
    placeholder?: string;
    label?: string;
    required?: boolean;
    disabled?: boolean;
    error?: string;
    searchable?: boolean;
    clearable?: boolean;
    multiple?: boolean;
    groups?: boolean;
    loading?: boolean;
    clearSearchOnClose?: boolean; // Очищать ли поиск при закрытии
    onChange: (value: any) => void;
    onSearch?: (query: string) => void; // Колбэк для серверного поиска
    onBlur?: () => void;
    onFocus?: () => void;
    className?: string;
    id?: string;
    name?: string;
}