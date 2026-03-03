// Типы для запросов и ответов API
export interface LoginRequest {
    login: string;
    password: string;
}

export interface LoginResponse {
    access_token: string;
    token_type: string;
    expires_at: string;
}

export interface User {
    id: number;
    login: string;
    email?: string | null;
    phone?: string | null;
}

export interface AuthState {
    user: User | null;
    token: string | null;
    isLoading: boolean;
    error: string | null;
}