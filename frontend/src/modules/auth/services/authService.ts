import { apiFetch } from '../../../core/api';
import type { LoginRequest, LoginResponse, User } from '../types';

class AuthService {
    private tokenKey = 'auth_token';

    async login(credentials: LoginRequest): Promise<LoginResponse> {
        try {
            const response = await apiFetch<LoginResponse>('/auth/login', {
                method: 'POST',
                body: JSON.stringify(credentials),
            });

            this.setToken(response.access_token);
            return response;
        } catch (error: any) {
            // Пробрасываем ошибку с понятным сообщением
            if (error.message) {
                throw new Error(error.message);
            }
            throw new Error('Ошибка подключения к серверу');
        }
    }

    async getCurrentUser(): Promise<User> {
        return apiFetch<User>('/auth/me', {
            token: this.getToken(),
        });
    }

    async logout(): Promise<void> {
        try {
            await apiFetch('/auth/logout', {
                method: 'POST',
                token: this.getToken(),
            });
        } finally {
            this.removeToken();
        }
    }

    setToken(token: string): void {
        localStorage.setItem(this.tokenKey, token);
    }

    getToken(): string | null {
        return localStorage.getItem(this.tokenKey);
    }

    removeToken(): void {
        localStorage.removeItem(this.tokenKey);
    }

    isAuthenticated(): boolean {
        return !!this.getToken();
    }
}

export const authService = new AuthService();