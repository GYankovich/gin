// frontend/src/modules/robots/pages/RobotsPage.ts
import { robotService } from '../services/robotService';
import { Robot } from '../types';
import { router } from '../../../core/router';
import { CreateRobotModal } from '../components/CreateRobotModal';
import { RobotList } from '../components/RobotList';
import { RobotCardData } from '../components/RobotCard';
import { apiFetch } from '../../../core/api';

export class RobotsPage {
    private loading: boolean = true;
    private refreshing: boolean = false;
    private filter: 'all' | 'active' | 'stopped' | 'error' = 'all';
    private robotList: RobotList | null = null;
    private container: HTMLElement | null = null;
    private initialized: boolean = false;
    private loadError: Error | null = null;
    private robots: RobotCardData[] = [];

    constructor() {
        console.log('🤖 RobotsPage constructor called');
        console.log('📍 Current path:', window.location.pathname);
        console.log('🔑 Token present:', !!localStorage.getItem('auth_token'));
    }

    async loadData(showRefreshing: boolean = false): Promise<void> {
        console.log('📊 ===== LOAD DATA CALLED =====');
        console.log('📊 Loading robots data...');
        console.log('📊 Current filter:', this.filter);

        if (showRefreshing) {
            this.refreshing = true;
        } else {
            this.loading = true;
        }
        this.loadError = null;

        if (this.container) {
            this.render(this.container);
        }

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

            const startTime = Date.now();
            const response = await robotService.getRobots(includeInactive);
            const endTime = Date.now();

            console.log(`✅ API request completed in ${endTime - startTime}ms`);
            console.log('📦 API Response:', response);


            if (response && Array.isArray(response.items)) {
                console.log(`📊 Received ${response.items.length} robots`);
                // Преобразуем данные в формат RobotCardData
                this.robots = response.items.map((item: any) => ({
                    id: item.id,
                    name: item.name,
                    token: {
                        id: item.token?.id,
                        name: item.token?.name,
                        status: item.token?.status,
                        type: item.token?.type,
                        typeName: item.token?.typeName
                    },
                    type: item.type,
                    typeName: item.typeName,
                    status: item.status,
                    statusName: item.statusName,
                    last_started: item.last_started,
                    last_error: item.last_error,
                    last_error_at: item.last_error_at,
                    last_stopped: item.last_stopped
                }));
            }

        } catch (error) {
            console.error('❌ Failed to load robots:', error);
            this.loadError = error instanceof Error ? error : new Error('Неизвестная ошибка');
            this.robots = [];
        } finally {
            this.loading = false;
            this.refreshing = false;

            if (this.container) {
                this.render(this.container);
            }
        }
    }

    private handleRefresh = (): void => {
        console.log('🔄 Manual refresh triggered');
        this.loadData(true);
    }

    private openCreateModal(): void {
        const modalContainer = document.createElement('div');
        modalContainer.id = 'robot-modal-container';
        modalContainer.style.position = 'fixed';
        modalContainer.style.top = '0';
        modalContainer.style.left = '0';
        modalContainer.style.right = '0';
        modalContainer.style.bottom = '0';
        modalContainer.style.zIndex = '9999';

        document.body.appendChild(modalContainer);

        const modal = new CreateRobotModal(
            modalContainer,
            () => {
                modalContainer.remove();
            },
            () => {
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
            await this.loadData(true);
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
            await this.loadData(true);
        } catch (error) {
            console.error(`❌ Failed to stop robot ${id}:`, error);
            alert('Не удалось остановить робота');
        }
    }

    private handleEdit = (id: number): void => {
        console.log(`✏️ Editing robot ${id}`);
        router.navigate(`/robots/${id}/edit`);
    }


    private handleToggle = async (id: number, statusCode: number): Promise<void> => {
        console.log(`🔄 Changing robot ${id} status to code: ${statusCode}`);

        try {
            await apiFetch('/robots/change_status', {
                method: 'POST',
                body: JSON.stringify({
                    robotId: id,
                    status: statusCode
                })
            });
            console.log(`✅ Robot ${id} status changed successfully`);
            await this.loadData(true);
        } catch (error) {
            console.error(`❌ Failed to change robot ${id} status:`, error);
            alert('Не удалось изменить состояние робота');
        }
    }


    private handleDelete = async (id: number): Promise<void> => {
        console.log(`🗑️ Deleting robot ${id}`);
        try {
            await robotService.deleteRobot(id);
            console.log(`✅ Robot ${id} deleted`);
            await this.loadData(true);
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
            refreshing: this.refreshing,
            robotsCount: this.robots.length,
            hasError: !!this.loadError,
            filter: this.filter
        });

        this.container = container;
        container.className = 'robots-page main-content';

        // Состояние загрузки (первая загрузка)
        if (this.loading) {
            container.innerHTML = `
            <div class="empty-state-wrapper loading-state">
                <div class="loading-animation">
                    <div class="loading-dot"></div>
                    <div class="loading-dot"></div>
                    <div class="loading-dot"></div>
                </div>
                <h2 class="empty-state-title">Загружаем роботов</h2>
                <p class="empty-state-description">
                    Подождите немного, мы собираем данные о ваших роботах
                </p>
            </div>
        `;

            if (!this.initialized) {
                this.initialized = true;
                setTimeout(() => this.loadData(), 100);
            }
            return;
        }

        // Состояние ошибки - грустный робот
        if (this.loadError) {
            container.innerHTML = `
            <div class="empty-state-wrapper error-state">
                <div class="error-robot-illustration">
                    <div class="robot-illustration sad">
                        <div class="robot-head">
                            <div class="robot-eye left happpy"></div>
                            <div class="robot-eye right sad"></div>
                            <div class="robot-antenna"></div>
                        </div>
                        <div class="robot-body">
                            <div class="robot-heart broken">💔</div>
                        </div>
                        <div class="robot-arm left happy"></div>
                        <div class="robot-arm right happy"></div>
                    </div>
                </div>
                
                <h2 class="empty-state-title">Ой, что-то пошло не так</h2>
                <p class="empty-state-description">
                    ${this.loadError.message}
                </p>
                
                <button class="error-retry-btn" id="retry-load">
                    <span class="refresh-icon">↻</span>
                    Попробовать снова
                </button>
            </div>
        `;

            setTimeout(() => {
                const retryBtn = document.getElementById('retry-load');
                if (retryBtn) {
                    retryBtn.addEventListener('click', () => this.loadData());
                }
            }, 0);
            return;
        }

        // Пустое состояние - счастливый робот
        if (this.robots.length === 0) {
            container.innerHTML = `
            <div class="empty-state-wrapper">
                <div class="empty-state-illustration">
                    <div class="robot-illustration happy">
                        <div class="robot-head">
                            <div class="robot-eye left happy"></div>
                            <div class="robot-eye right happy"></div>
                            <div class="robot-antenna"></div>
                        </div>
                        <div class="robot-body">
                            <div class="robot-heart">❤️</div>
                        </div>
                        <div class="robot-arm left happy"></div>
                        <div class="robot-arm right happy"></div>
                    </div>
                </div>
                
                <h2 class="empty-state-title">У вас пока нет роботов</h2>
                <p class="empty-state-description">
                    Создайте своего первого торгового робота и начните автоматизировать торговлю
                </p>

                <button class="btn-create-robot" id="create-first-robot">
                    Создать первого робота
                    <span class="btn-icon">🚀</span>
                </button>
            </div>
        `;

            setTimeout(() => {
                const createFirstBtn = document.getElementById('create-first-robot');
                if (createFirstBtn) {
                    createFirstBtn.addEventListener('click', () => this.openCreateModal());
                }
            }, 0);
            return;
        }

        if (!this.robotList) {
            this.robotList = new RobotList(
                this.robots,
                this.handleToggle,  // Передаем новый метод
                this.refreshing,
                this.filter,
                this.handleFilterChange
            );
        } else {
            this.robotList.updateProps({
                robots: this.robots,
                loading: this.refreshing,
                filter: this.filter
            });
        }

        container.innerHTML = `
        <div class="robots-with-create">
            <div class="robots-list-container"></div>
            <div class="create-robot-fab" id="create-robot-fab" title="Создать нового робота">
                <span class="plus-icon">+</span>
            </div>
        </div>
    `;

        const listContainer = container.querySelector('.robots-list-container');
        if (listContainer) {
            this.robotList.render(listContainer as HTMLElement);
        }

        setTimeout(() => {
            const fabBtn = document.getElementById('create-robot-fab');
            if (fabBtn) {
                fabBtn.addEventListener('click', () => this.openCreateModal());
            }
        }, 0);
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