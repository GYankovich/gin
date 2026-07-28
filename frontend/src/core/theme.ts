///@EPIC Frontend.ITEM Core.TOPIC FrontendSrcCoreTheme [1]
///@ Исходный модуль `frontend/src/core/theme.ts` — автоматическая разметка для Obsidian Source Scanner.

export type Theme = 'light' | 'dark';

class ThemeManager {
    private currentTheme: Theme;
    private listeners: Array<(theme: Theme) => void> = [];

    constructor() {
        // Загружаем сохраненную тему или определяем по системным настройкам
        const savedTheme = localStorage.getItem('theme') as Theme | null;
        if (savedTheme && (savedTheme === 'light' || savedTheme === 'dark')) {
            this.currentTheme = savedTheme;
        } else {
            // Проверяем системные настройки
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            this.currentTheme = prefersDark ? 'dark' : 'light';
        }
        this.applyTheme();
    }

    getTheme(): Theme {
        return this.currentTheme;
    }

    toggleTheme(): void {
        this.currentTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        localStorage.setItem('theme', this.currentTheme);
        this.applyTheme();
        this.notify();
    }

    setTheme(theme: Theme): void {
        if (this.currentTheme !== theme) {
            this.currentTheme = theme;
            localStorage.setItem('theme', theme);
            this.applyTheme();
            this.notify();
        }
    }

    private applyTheme(): void {
        document.documentElement.setAttribute('data-theme', this.currentTheme);
    }

    subscribe(listener: (theme: Theme) => void): () => void {
        this.listeners.push(listener);
        return () => {
            this.listeners = this.listeners.filter(l => l !== listener);
        };
    }

    private notify(): void {
        this.listeners.forEach(l => l(this.currentTheme));
    }
}

export const themeManager = new ThemeManager();