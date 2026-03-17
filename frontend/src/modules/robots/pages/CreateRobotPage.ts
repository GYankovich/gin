// frontend/src/modules/robots/pages/CreateRobotPage.ts
import { RobotForm } from '../components/RobotForm';
import { robotService } from '../services/robotService';
import { RobotCreate, StrategyInfo, AvailableToken } from '../types';
import { router } from '../../../core/router';

export class CreateRobotPage {
    private strategies: StrategyInfo[] = [];
    private availableTokens: AvailableToken[] = [];
    private loading: boolean = true;
    private form: RobotForm | null = null;
    private container: HTMLElement | null = null;
    private initialized: boolean = false;

    constructor() {
        console.log('🤖 CreateRobotPage constructor called');
        console.log('📍 Current path:', window.location.pathname);
        console.log('🔑 Token present:', !!localStorage.getItem('auth_token'));
    }

    async loadData(): Promise<void> {
        console.log('📊 ===== LOAD CREATE PAGE DATA =====');
        console.log('📊 Loading strategies and tokens...');
        console.log('📊 Current state:', {
            loading: this.loading,
            strategiesCount: this.strategies.length,
            tokensCount: this.availableTokens.length,
            initialized: this.initialized
        });

        this.loading = true;

        // Если контейнер уже есть, обновляем отображение
        if (this.container) {
            console.log('🖼️ Container exists, rendering loading state');
            this.render(this.container);
        } else {
            console.log('⚠️ Container not ready yet');
        }

        try {
            // Проверяем наличие токена авторизации
            const token = localStorage.getItem('auth_token');
            if (!token) {
                console.error('❌ No auth token found!');
                router.navigate('/login');
                return;
            }
            console.log('✅ Auth token present');

            console.log('📡 Fetching strategies from /api/robots/trading/strategies...');
            const strategies = await robotService.getStrategies();
            console.log('✅ Strategies loaded:', strategies);

            console.log('📡 Fetching tokens from /api/apikey/data...');
            const tokens = await robotService.getAvailableTokens();
            console.log('✅ Tokens loaded:', tokens);

            this.strategies = strategies || [];
            this.availableTokens = tokens || [];

            console.log('📊 Data loaded successfully:', {
                strategiesCount: this.strategies.length,
                tokensCount: this.availableTokens.length
            });

        } catch (error) {
            console.error('❌ Failed to load data:', error);
            if (error instanceof Error) {
                console.error('❌ Error name:', error.name);
                console.error('❌ Error message:', error.message);
                console.error('❌ Error stack:', error.stack);
            }
            this.strategies = [];
            this.availableTokens = [];

            if (this.container) {
                this.showError(error);
            }
        } finally {
            this.loading = false;
            console.log('📊 Loading finished, strategies:', this.strategies.length);
            console.log('📊 Loading finished, tokens:', this.availableTokens.length);

            // Всегда перерендериваем после загрузки, если контейнер существует
            if (this.container) {
                console.log('🖼️ Container exists, re-rendering with data');
                this.render(this.container);
            } else {
                console.log('⚠️ Container missing, cannot render');
            }
        }
    }

    private showError(error: unknown): void {
        if (!this.container) {
            console.log('⚠️ Cannot show error - container missing');
            return;
        }

        console.log('❌ Showing error state');
        const errorMessage = error instanceof Error ? error.message : 'Неизвестная ошибка';

        this.container.innerHTML = `
            <div class="create-robot-page">
                <div class="error-container">
                    <div class="error-icon">❌</div>
                    <h2 class="error-title">Ошибка загрузки</h2>
                    <p class="error-message">${errorMessage}</p>
                    <div class="error-actions">
                        <button class="btn-primary" id="retry-load">
                            Повторить
                        </button>
                        <button class="btn-secondary" id="go-back">
                            Назад
                        </button>
                    </div>
                </div>
            </div>
        `;

        setTimeout(() => {
            document.getElementById('retry-load')?.addEventListener('click', () => {
                console.log('🔄 Retry button clicked');
                this.loadData();
            });
            document.getElementById('go-back')?.addEventListener('click', () => {
                console.log('👈 Back button clicked');
                router.navigate('/robots');
            });
        }, 0);
    }

    private handleSubmit = async (data: RobotCreate): Promise<void> => {
        console.log('📤 Submitting robot creation:', data);

        const submitBtn = document.querySelector('.btn-primary[type="submit"]') as HTMLButtonElement;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Создание...';
        }

        try {
            await robotService.createRobot(data);
            console.log('✅ Robot created successfully');

            this.showNotification('success', 'Робот успешно создан!');

            setTimeout(() => {
                router.navigate('/robots');
            }, 1500);

        } catch (error) {
            console.error('❌ Failed to create robot:', error);

            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Создать робота';
            }

            this.showNotification(
                'error',
                `Не удалось создать робота: ${error instanceof Error ? error.message : 'Неизвестная ошибка'}`
            );
        }
    }

    private showNotification(type: 'success' | 'error', message: string): void {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.innerHTML = `
            <div class="notification-icon">${type === 'success' ? '✅' : '❌'}</div>
            <div class="notification-message">${message}</div>
        `;

        document.body.appendChild(notification);
        setTimeout(() => notification.classList.add('show'), 10);
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    private handleCancel = (): void => {
        console.log('👈 Cancelling, going back to robots list');
        router.navigate('/robots');
    }

    render(container: HTMLElement): void {
        console.log('🎨 ===== RENDER CREATE PAGE =====');

        this.container = container;
        container.className = 'create-robot-page';

        if (this.loading) {
            console.log('⏳ Rendering loading state');
            container.innerHTML = `
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">Загрузка данных для создания робота...</div>
                </div>
            `;

            // Загружаем данные только один раз при первом рендере
            if (!this.initialized) {
                console.log('📊 First render, initializing data load');
                this.initialized = true;
                setTimeout(() => {
                    console.log('⏰ Timeout triggered, calling loadData()');
                    this.loadData();
                }, 100);
            }
            return;
        }

        // Если загрузка завершена, но данных нет
        if (!this.loading && this.strategies.length === 0) {
            console.log('📭 No strategies available, showing empty state');
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📭</div>
                    <h2 class="empty-state-title">Нет доступных стратегий</h2>
                    <p class="empty-state-description">
                        Для создания торгового робота необходимо иметь хотя бы одну стратегию.
                    </p>
                    <button class="btn-secondary" id="go-back">
                        Вернуться к списку
                    </button>
                </div>
            `;

            setTimeout(() => {
                document.getElementById('go-back')?.addEventListener('click', () => {
                    router.navigate('/robots');
                });
            }, 0);
            return;
        }

        // Данные загружены успешно
        console.log('📦 Rendering form with data:', {
            strategies: this.strategies,
            tokens: this.availableTokens
        });

        // Очищаем контейнер
        container.innerHTML = '';

        // Создаем структуру формы
        const formContainer = document.createElement('div');
        formContainer.className = 'create-robot-form-container';

        formContainer.innerHTML = `
            <div class="form-header">
                <h1 class="form-title">Создание нового робота</h1>
                <p class="form-description">
                    Заполните конфигурацию для вашего торгового робота. 
                    Все параметры можно будет изменить позже.
                </p>
            </div>
            <div id="robot-form-placeholder"></div>
        `;

        container.appendChild(formContainer);

        // Создаем форму
        const formPlaceholder = document.getElementById('robot-form-placeholder');
        if (!formPlaceholder) {
            console.error('❌ Form placeholder not found');
            return;
        }

        if (!this.form) {
            console.log('🆕 Creating new RobotForm instance');
            this.form = new RobotForm(
                undefined,
                this.strategies,
                this.availableTokens,
                this.handleSubmit,
                this.handleCancel,
                false
            );
        }

        console.log('🎯 Rendering RobotForm');
        this.form.render(formPlaceholder);
    }

    destroy(): void {
        console.log('🧹 Destroying CreateRobotPage');
        if (this.form) {
            this.form.destroy();
            this.form = null;
        }
        this.container = null;
        this.initialized = false;
    }
}