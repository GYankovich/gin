import { apiFetch } from '../../../core/api';
import type {
    LoginCredentials,
    RegisterData,
    AuthResponse,
    User
} from '../types';

export class AuthService {
    private baseUrl = '/auth';

    // --- Login ---
    async login(credentials: LoginCredentials): Promise<AuthResponse> {
        const response = await apiFetch<AuthResponse>(`${this.baseUrl}/login`, {
            method: 'POST',
            body: JSON.stringify(credentials)
        });

        // SIMPLIFIED: Save only to localStorage
        if (response.token) {
            localStorage.setItem('auth_token', response.token);
            localStorage.setItem('user', JSON.stringify(response.user));
        }

        return response;
    }

    // --- Register ---
    async register(data: RegisterData): Promise<AuthResponse> {
        const response = await apiFetch<AuthResponse>(`${this.baseUrl}/register`, {
            method: 'POST',
            body: JSON.stringify(data)
        });

        // Save to localStorage if auto-login after registration
        if (response.token) {
            localStorage.setItem('auth_token', response.token);
            localStorage.setItem('user', JSON.stringify(response.user));
        }

        return response;
    }

    // --- Logout ---
    async logout(): Promise<void> {
        try {
            // Optional: notify backend about logout
            await apiFetch(`${this.baseUrl}/logout`, {
                method: 'POST'
            });
        } catch (error) {
            console.warn('Logout API error:', error);
        } finally {
            // SIMPLIFIED: Clear only localStorage
            this.clearLocalStorage();

            // Redirect to login page
            window.location.href = '/login';
        }
    }

    // --- Refresh token ---
    async refreshToken(): Promise<AuthResponse> {
        const response = await apiFetch<AuthResponse>(`${this.baseUrl}/refresh`, {
            method: 'POST'
        });

        // Update token in localStorage
        if (response.token) {
            localStorage.setItem('auth_token', response.token);
            // Update user if returned
            if (response.user) {
                localStorage.setItem('user', JSON.stringify(response.user));
            }
        }

        return response;
    }

    // --- Check if user is authenticated ---
    isAuthenticated(): boolean {
        return !!this.getToken();
    }

    // --- Get current user from localStorage ---
    getCurrentUser(): User | null {
        const userStr = localStorage.getItem('user');
        if (!userStr) return null;

        try {
            return JSON.parse(userStr) as User;
        } catch {
            return null;
        }
    }

    // --- Get token from localStorage ---
    getToken(): string | null {
        return localStorage.getItem('auth_token');
    }

    // --- Update user data (after profile update) ---
    updateUserData(user: User): void {
        localStorage.setItem('user', JSON.stringify(user));
    }

    // --- Clear all auth data ---
    private clearLocalStorage(): void {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
    }

    // --- Change password ---
    async changePassword(currentPassword: string, newPassword: string): Promise<void> {
        await apiFetch(`${this.baseUrl}/change-password`, {
            method: 'POST',
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });
    }

    // --- Request password reset ---
    async requestPasswordReset(email: string): Promise<void> {
        await apiFetch(`${this.baseUrl}/reset-password`, {
            method: 'POST',
            body: JSON.stringify({ email })
        });
    }

    // --- Confirm password reset ---
    async confirmPasswordReset(token: string, newPassword: string): Promise<void> {
        await apiFetch(`${this.baseUrl}/reset-password/confirm`, {
            method: 'POST',
            body: JSON.stringify({
                token,
                new_password: newPassword
            })
        });
    }
}

// Create and export a singleton instance
export const authService = new AuthService();