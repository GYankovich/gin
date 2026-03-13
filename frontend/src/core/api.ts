import { store } from './store';
import { router } from './router'; // Импортируем router для навигации

interface ApiOptions extends RequestInit {
    token?: string | null;
}

export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
    const { token, ...fetchOptions } = options;

    const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
    };

    const authToken = token || store.getState().token;

    // ОТЛАДКА
    console.log('🔍 apiFetch called:', {
        path,
        method: fetchOptions.method || 'GET',
        hasToken: !!authToken,
        tokenPreview: authToken ? `${authToken.substring(0, 15)}...` : 'none',
        headers: { ...headers, Authorization: authToken ? 'Bearer ***' : 'none' }
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

        console.log('🌐 Fetching:', url);
        console.log('📥 Response status:', response.status);
        console.log('📥 Response headers:', Object.fromEntries(response.headers.entries()));


        let data;
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            data = await response.json();
        } else {
            data = await response.text();
        }

        if (!response.ok) {
            // Обрабатываем разные HTTP статусы
            if (response.status === 401) {
                console.error('🔒 Session expired or unauthorized');

                // Очищаем данные пользователя
                store.setToken(null);
                store.setUser(null);

                // Показываем сообщение пользователю
                const errorMessage = data?.detail || 'Сессия истекла. Пожалуйста, войдите снова';

                // Перенаправляем на страницу логина
                // Используем setTimeout чтобы избежать конфликтов с текущим рендерингом
                setTimeout(() => {
                    window.location.href = '/login';
                }, 100);

                throw new Error(errorMessage);
            }

            if (response.status === 422) {
                const errorMsg = data?.detail?.[0]?.msg || 'Некорректные данные';
                throw new Error(errorMsg);
            }

            if (response.status === 500) {
                throw new Error('Ошибка сервера. Попробуйте позже');
            }

            // Общая ошибка
            const errorMsg = data?.detail || data || 'Произошла ошибка';
            throw new Error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
        }

        return data as T;

    } catch (error: any) {
        // Обрабатываем сетевые ошибки
        if (error.name === 'TypeError' && error.message === 'Failed to fetch') {
            throw new Error('Ошибка сети. Сервер не отвечает');
        }

        // Пробрасываем ошибку дальше
        throw error;
    }
}