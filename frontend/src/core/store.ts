///@EPIC Frontend.ITEM Core.TOPIC FrontendSrcCoreStore [1]
///@ Исходный модуль `frontend/src/core/store.ts` — автоматическая разметка для Obsidian Source Scanner.

interface User {
    id: number;
    login: string;
    email?: string | null;
    phone?: string | null;
}

interface AppState {
    user: User | null;
    token: string | null;
    isLoading: boolean;
}

class Store {
    private state: AppState = {
        user: null,
        token: localStorage.getItem('auth_token'), // ИЗМЕНЕНО: было 'token', стало 'auth_token'
        isLoading: false,
    };

    private listeners: Array<(state: AppState) => void> = [];

    getState(): AppState {
        return { ...this.state };
    }

    setUser(user: User | null): void {
        this.state.user = user;
        this.notify();
    }

    setToken(token: string | null): void {
        this.state.token = token;
        if (token) {
            localStorage.setItem('auth_token', token); // ИЗМЕНЕНО: сохраняем в auth_token
            // Удаляем старый ключ если есть
            localStorage.removeItem('token');
        } else {
            localStorage.removeItem('auth_token');
        }
        this.notify();
    }

    setLoading(loading: boolean): void {
        this.state.isLoading = loading;
        this.notify();
    }

    subscribe(listener: (state: AppState) => void): () => void {
        this.listeners.push(listener);
        return () => {
            this.listeners = this.listeners.filter(l => l !== listener);
        };
    }

    private notify(): void {
        this.listeners.forEach(l => l(this.getState()));
    }
}

export const store = new Store();