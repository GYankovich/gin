// frontend/src/modules/robots/pages/RobotsPage.ts
import { RobotList } from '../components/RobotList';
import { robotService } from '../services/robotService';
import { Robot } from '../types';
import { router } from '../../../core/router';

export class RobotsPage {
    private robots: Robot[] = [];
    private loading: boolean = true;
    private filter: 'all' | 'active' | 'stopped' | 'error' = 'all';
    private robotList: RobotList | null = null;
    private container: HTMLElement | null = null;
    private initialized: boolean = false;

    constructor() {
        console.log('🤖 RobotsPage constructor called');
        console.log('📍 Current path:', window.location.pathname);
        console.log('🔑 Token present:', !!localStorage.getItem('auth_token'));
    }

    async loadData(): Promise<void> {
        console.log('📊 ===== LOAD DATA CALLED =====');
        console.log('📊 Loading robots data...');
        console.log('📊 Current filter:', this.filter);

        this.loading = true;

        // НЕ вызываем render() здесь, так как container может быть undefined
        // Мы вызовем render после установки container в методе render()

        try {
            // Проверяем наличие токена
            const token = localStorage.getItem('auth_token');
            console.log('🔑 Auth token:', token ? `${token.substring(0, 20)}...` : 'NOT FOUND');

            if (!token) {
                console.error('❌ No auth token found!');
                router.navigate('/login');
                return;
            }

            // Определяем параметры запроса
            const includeInactive = this.filter !== 'all';

            console.log(`🔍 Fetching robots with params:`, {
                includeInactive,
                filter: this.filter
            });

            console.log('📡 Making API request to /robots...');

            const startTime = Date.now();
            const response = await robotService.getRobots(includeInactive);
            const endTime = Date.now();

            console.log(`✅ API request completed in ${endTime - startTime}ms`);
            console.log('📦 API Response:', response);

            // Проверяем структуру ответа
            if (response && Array.isArray(response.items)) {
                console.log(`📊 Received ${response.items.length} robots`);
                this.robots = response.items;
            } else if (Array.isArray(response)) {
                console.log('⚠️ Response is array, wrapping in items');
                this.robots = response;
            } else {
                console.warn('⚠️ Unexpected response format:', response);
                this.robots = [];
            }

        } catch (error) {
            console.error('❌ Failed to load robots:', error);

            // Детальный вывод ошибки
            if (error instanceof Error) {
                console.error('❌ Error name:', error.name);
                console.error('❌ Error message:', error.message);
                console.error('❌ Error stack:', error.stack);
            }

            this.robots = [];

            // Показываем ошибку через render, но только если container уже установлен
            if (this.container) {
                this.showError(error);
            }
        } finally {
            this.loading = false;
            console.log('📊 Loading finished, robots count:', this.robots.length);

            // Перерендериваем после загрузки, но только если container уже установлен
            if (this.container) {
                this.render(this.container);
            }
        }
    }

    private showError(error: unknown): void {
        if (!this.container) return;

        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.innerHTML = `
            <div style="text-align: center; padding: 2rem;">
                <h3 style="color: #f44336; margin-bottom: 1rem;">Ошибка загрузки</h3>
                <p style="color: #666; margin-bottom: 1rem;">${error instanceof Error ? error.message : 'Неизвестная ошибка'}</p>
                <button id="retry-load" style="
                    background: #f44336;
                    color: white;
                    border: none;
                    padding: 0.5rem 2rem;
                    border-radius: 6px;
                    cursor: pointer;
                    margin-right: 1rem;
                ">
                    Повторить
                </button>
                <button id="check-auth" style="
                    background: #666;
                    color: white;
                    border: none;
                    padding: 0.5rem 2rem;
                    border-radius: 6px;
                    cursor: pointer;
                ">
                    Проверить авторизацию
                </button>
            </div>
        `;

        this.container.innerHTML = '';
        this.container.appendChild(errorDiv);

        setTimeout(() => {
            document.getElementById('retry-load')?.addEventListener('click', () => {
                console.log('🔄 Retry button clicked');
                this.loadData();
            });

            document.getElementById('check-auth')?.addEventListener('click', () => {
                console.log('🔍 Checking auth...');
                const token = localStorage.getItem('auth_token');
                const user = localStorage.getItem('user');
                alert(`Token: ${token ? 'есть' : 'нет'}\nUser: ${user ? 'есть' : 'нет'}`);
            });
        }, 0);
    }

    private handleStart = async (id: number): Promise<void> => {
        console.log(`▶️ Starting robot ${id}`);
        try {
            await robotService.startRobot(id);
            console.log(`✅ Robot ${id} started`);
            await this.loadData();
        } catch (error) {
            console.error(`❌ Failed to start robot ${id}:`, error);
            alert(`Не удалось запустить робота`);
        }
    }

    private handleStop = async (id: number): Promise<void> => {
        console.log(`⏸️ Stopping robot ${id}`);
        try {
            await robotService.stopRobot(id);
            console.log(`✅ Robot ${id} stopped`);
            await this.loadData();
        } catch (error) {
            console.error(`❌ Failed to stop robot ${id}:`, error);
            alert(`Не удалось остановить робота`);
        }
    }

    private handleEdit = (id: number): void => {
        console.log(`✏️ Editing robot ${id}`);
        router.navigate(`/robots/${id}/edit`);
    }

    private handleDelete = async (id: number): Promise<void> => {
        console.log(`🗑️ Deleting robot ${id}`);
        if (!confirm('Вы уверены, что хотите удалить этого робота?')) {
            return;
        }

        try {
            await robotService.deleteRobot(id);
            console.log(`✅ Robot ${id} deleted`);
            await this.loadData();
        } catch (error) {
            console.error(`❌ Failed to delete robot ${id}:`, error);
            alert(`Не удалось удалить робота`);
        }
    }

    private handleViewDetails = (id: number): void => {
        console.log(`🔍 Viewing robot ${id} details`);
        router.navigate(`/robots/${id}`);
    }

    private handleFilterChange = (filter: string): void => {
        console.log(`🔍 Filter changed to: ${filter}`);
        this.filter = filter as any;
        this.loadData();
    }

    render(container: HTMLElement): void {
        console.log('🎨 ===== RENDER CALLED =====');
        console.log('🎨 Rendering RobotsPage', {
            loading: this.loading,
            robotsCount: this.robots.length,
            containerExists: !!container,
            initialized: this.initialized
        });

        this.container = container;

        // Если грузимся - показываем загрузку
        if (this.loading) {
            console.log('⏳ Showing loading state');
            container.innerHTML = `
                <div class="robots-page">
                    <div class="loading-container" style="text-align: center; padding: 4rem;">
                        <div class="loading-spinner" style="
                            display: inline-block;
                            width: 50px;
                            height: 50px;
                            border: 4px solid #f3f3f3;
                            border-top: 4px solid #3498db;
                            border-radius: 50%;
                            animation: spin 1s linear infinite;
                        "></div>
                        <div style="margin-top: 1rem; color: #666;">
                            Загрузка роботов...
                        </div>
                    </div>
                </div>
                <style>
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            `;

            // Загружаем данные если ещё не загружены
            if (!this.initialized) {
                console.log('📊 First render, triggering data load');
                this.initialized = true;

                // Используем setTimeout, чтобы не блокировать рендер
                setTimeout(() => {
                    console.log('⏰ Timeout triggered, calling loadData');
                    this.loadData();
                }, 100);
            }
            return;
        }

        // Если есть ошибка и robots пустой - показываем сообщение об ошибке
        if (this.robots.length === 0 && !this.loading) {
            console.log('📭 No robots, showing empty state');
            container.innerHTML = `
        <div class="robots-page">
            <!-- Шапка УДАЛЕНА -->
            
            <div style="text-align: center; padding: 4rem; background: #f9f9f9; border-radius: 12px;">
                <div style="font-size: 4rem; margin-bottom: 1rem;">🤖</div>
                <h2>Нет роботов</h2>
                <p style="color: #666; margin-bottom: 2rem;">Создайте своего первого торгового робота</p>
                <button id="create-first-robot" style="
                    background: #3498db;
                    color: white;
                    border: none;
                    padding: 0.75rem 2rem;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 1rem;
                ">
                    + Создать робота
                </button>
            </div>
        </div>
    `;

            // Добавляем обработчик
            setTimeout(() => {
                const createBtn = document.getElementById('create-first-robot');
                if (createBtn) {
                    console.log('➕ Adding click handler to create button');
                    createBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        console.log('➕ Create robot button clicked');
                        router.navigate('/robots/create');
                    });
                }
            }, 0);

            return;
        }

        // Если есть роботы - показываем список
        console.log('📋 Creating RobotList with', this.robots.length, 'robots');

        // Создаем или обновляем RobotList
        if (!this.robotList) {
            console.log('🆕 Creating new RobotList instance');
            this.robotList = new RobotList(
                this.robots,
                this.handleStart,
                this.handleStop,
                this.handleEdit,
                this.handleDelete,
                this.handleViewDetails,
                this.loading,
                this.filter,
                this.handleFilterChange
            );
        } else {
            console.log('🔄 Updating existing RobotList');
            this.robotList.updateProps({
                robots: this.robots,
                loading: this.loading,
                filter: this.filter
            });
        }

        // Очищаем контейнер и рендерим список
        container.innerHTML = '';
        console.log('🎯 Rendering RobotList');
        this.robotList.render(container);
    }

    destroy(): void {
        console.log('🧹 Destroying RobotsPage');
        if (this.robotList) {
            this.robotList.destroy();
            this.robotList = null;
        }
        this.container = null;
        this.initialized = false;
    }
}