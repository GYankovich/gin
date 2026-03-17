// frontend/src/modules/robots/pages/RobotsPage.ts
import { RobotList } from '../components/RobotList';
import { robotService } from '../services/robotService';
import { Robot } from '../types';
import { router } from '../../../core/router';
import { CreateRobotModal } from '../components/CreateRobotModal';

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

        try {
            const token = localStorage.getItem('auth_token');
            console.log('🔑 Auth token:', token ? `${token.substring(0, 20)}...` : 'NOT FOUND');

            if (!token) {
                console.error('❌ No auth token found!');
                router.navigate('/login');
                return;
            }

            const includeInactive = this.filter !== 'all';

            console.log(`🔍 Fetching robots with params:`, {
                includeInactive,
                filter: this.filter
            });

            console.log('📡 Making API request to /robots/data...');

            const startTime = Date.now();
            const response = await robotService.getRobots(includeInactive);
            const endTime = Date.now();

            console.log(`✅ API request completed in ${endTime - startTime}ms`);
            console.log('📦 API Response:', response);

            if (response && Array.isArray(response.items)) {
                console.log(`📊 Received ${response.items.length} robots`);
                this.robots = response.items;
            } else {
                console.warn('⚠️ Unexpected response format:', response);
                this.robots = [];
            }

        } catch (error) {
            console.error('❌ Failed to load robots:', error);

            if (error instanceof Error) {
                console.error('❌ Error name:', error.name);
                console.error('❌ Error message:', error.message);
                console.error('❌ Error stack:', error.stack);
            }

            this.robots = [];

            if (this.container) {
                this.showError(error);
            }
        } finally {
            this.loading = false;
            console.log('📊 Loading finished, robots count:', this.robots.length);

            if (this.container) {
                this.render(this.container);
            }
        }
    }

    private showError(error: unknown): void {
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="robots-page">
                <div class="error-state">
                    <div class="error-icon">❌</div>
                    <h2 class="error-title">Ошибка загрузки</h2>
                    <p class="error-message">${error instanceof Error ? error.message : 'Неизвестная ошибка'}</p>
                    <div class="error-actions">
                        <button class="btn-primary" id="retry-load">Повторить</button>
                        <button class="btn-secondary" id="check-auth">Проверить авторизацию</button>
                    </div>
                </div>
            </div>
        `;

        setTimeout(() => {
            document.getElementById('retry-load')?.addEventListener('click', () => {
                this.loadData();
            });

            document.getElementById('check-auth')?.addEventListener('click', () => {
                const token = localStorage.getItem('auth_token');
                const user = localStorage.getItem('user');
                alert(`Token: ${token ? 'есть' : 'нет'}\nUser: ${user ? 'есть' : 'нет'}`);
            });
        }, 0);
    }

    private openCreateModal(): void {
        // Создаем контейнер для модального окна
        const modalContainer = document.createElement('div');
        modalContainer.id = 'robot-modal-container';
        modalContainer.style.position = 'fixed';
        modalContainer.style.top = '0';
        modalContainer.style.left = '0';
        modalContainer.style.right = '0';
        modalContainer.style.bottom = '0';
        modalContainer.style.zIndex = '9999';
        // Убираем pointer-events: none - это блокировало клики

        document.body.appendChild(modalContainer);

        const modal = new CreateRobotModal(
            modalContainer,
            () => {
                // При закрытии удаляем контейнер
                modalContainer.remove();
            },
            () => {
                // При успешном создании удаляем контейнер и перезагружаем список
                modalContainer.remove();
                this.loadData();
            }
        );

        modal.loadData();
    }

    private handleStart = async (id: number): Promise<void> => {
        console.log(`▶️ Starting robot ${id}`);
        try {
            await robotService.startRobot(id);
            console.log(`✅ Robot ${id} started`);
            await this.loadData();
        } catch (error) {
            console.error(`❌ Failed to start robot ${id}:`, error);
            alert('Не удалось запустить робота');
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
            alert('Не удалось остановить робота');
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
            alert('Не удалось удалить робота');
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
            initialized: this.initialized
        });

        this.container = container;
        container.className = 'robots-page';

        if (this.loading) {
            container.innerHTML = `
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">Загрузка роботов...</div>
                </div>
            `;

            if (!this.initialized) {
                this.initialized = true;
                setTimeout(() => {
                    this.loadData();
                }, 100);
            }
            return;
        }

        if (this.robots.length === 0 && !this.loading) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🤖</div>
                    <h2 class="empty-state-title">У вас пока нет роботов</h2>
                    <p class="empty-state-description">
                        Создайте своего первого торгового робота и начните автоматизировать торговлю
                    </p>
                    <button class="btn-primary" id="create-first-robot">
                        <span style="font-size: 1.2rem; margin-right: 0.3rem;">✨</span>
                        Создать первого робота
                        <span style="font-size: 1.2rem; margin-left: 0.3rem;">🚀</span>
                    </button>
                </div>
            `;

            setTimeout(() => {
                const createBtn = document.getElementById('create-first-robot');
                if (createBtn) {
                    createBtn.addEventListener('click', () => {
                        this.openCreateModal();
                    });
                }
            }, 0);

            return;
        }

        if (!this.robotList) {
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
            this.robotList.updateProps({
                robots: this.robots,
                loading: this.loading,
                filter: this.filter
            });
        }

        container.innerHTML = '';
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