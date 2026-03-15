import { router } from './router';

interface ApiOptions extends RequestInit {
    token?: string | null;
}

export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
    const { token, ...fetchOptions } = options;

    const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
    };

    const authToken = token || localStorage.getItem('auth_token');

    console.log('🔍 apiFetch called:', {
        path,
        method: fetchOptions.method || 'GET',
        hasToken: !!authToken,
        tokenPreview: authToken ? `${authToken.substring(0, 15)}...` : 'none',
    });

    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }

    try {
        const url = `/api${path}`;
        const response = await fetch(url, {
            ...fetchOptions,
            headers,
        });

        let data;
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            data = await response.json();
        } else {
            data = await response.text();
        }

        if (!response.ok) {
            if (response.status === 401) {
                console.error('🔒 Session expired or unauthorized');

                // SIMPLIFIED: Clear only localStorage
                localStorage.removeItem('auth_token');
                localStorage.removeItem('user');

                const errorMessage = data?.detail || 'Session expired. Please login again';

                setTimeout(() => {
                    window.location.href = '/login';
                }, 100);

                throw new Error(errorMessage);
            }

            if (response.status === 422) {
                const errorMsg = data?.detail?.[0]?.msg || 'Invalid data';
                throw new Error(errorMsg);
            }

            if (response.status === 500) {
                throw new Error('Server error. Try again later');
            }

            const errorMsg = data?.detail || data || 'An error occurred';
            throw new Error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
        }

        return data as T;

    } catch (error: any) {
        if (error.name === 'TypeError' && error.message === 'Failed to fetch') {
            throw new Error('Network error. Server is not responding');
        }
        throw error;
    }
}