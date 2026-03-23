// frontend/src/modules/robots/pages/RobotsPage.ts
import { robotService } from '../services/robotService';
import { apiFetch } from '../../../core/api';
import { router } from '../../../core/router';
import { CreateRobotModal } from '../components/CreateRobotModal';
import { RobotCard, RobotCardData } from '../components/RobotCard';

export class RobotsPage {
    private robots: RobotCardData[] = [];
    private loading: boolean = true;
    private loadingMore: boolean = false;
    private hasMore: boolean = true;
    private offset: number = 0;
    private limit: number = 12;
    private totalCount: number = 0;
    private searchQuery: string = '';
    private searchTimeout: number | null = null;
    private container: HTMLElement | null = null;
    private initialized: boolean = false;
    private loadError: Error | null = null;
    private scrollHandler: (() => void) | null = null;
    private currentFilter: string = 'all';
    private cards: Map<number, RobotCard> = new Map();
    private lastScrollTop: number = 0;
    private isLoadingInProgress: boolean = false;
    private loadMoreTimeout: number | null = null;
    private loadingMoreDelay: number | null = null;
    private isModalOpening: boolean = false;

    constructor() {
        console.log('🤖 RobotsPage constructor called');
    }

    async loadData(reset: boolean = true): Promise<void> {
        if (this.isLoadingInProgress) {
            console.log('⏭️ Skipping - already loading');
            return;
        }

        if (!reset && (this.loadingMore || !this.hasMore)) {
            console.log('⏭️ Skipping - loading more in progress or no more data');
            return;
        }

        this.isLoadingInProgress = true;

        if (reset) {
            this.loading = true;
            this.offset = 0;
            this.hasMore = true;
            this.totalCount = 0;
            this.robots = [];
            this.cards.clear();

            if (this.container) {
                this.renderHeaderAndFilters();
                this.renderSkeletonList();
            }
        } else {
            this.loadingMore = true;
            this.loadingMoreDelay = window.setTimeout(() => {
                this.showLoadingMore();
            }, 300);
        }
        this.loadError = null;

        const startTime = Date.now();

        try {
            const token = localStorage.getItem('auth_token');
            if (!token) {
                router.navigate('/login');
                return;
            }

            const body: any = {
                offset: reset ? 0 : this.offset,
                limit: this.limit
            };

            if (this.searchQuery && this.searchQuery.trim()) {
                body.robot_name = this.searchQuery;
            }

            console.log(`🔍 Fetching robots with offset: ${body.offset}, limit: ${body.limit}`);

            const response = await apiFetch('/robots/data', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            });

            if (response && Array.isArray(response.items)) {
                this.totalCount = response.total || 0;

                const newRobots = response.items.map((item: any) => ({
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
                    last_stopped: item.last_stopped,
                    date_creation: item.date_creation
                }));

                if (reset) {
                    this.robots = newRobots;
                } else {
                    this.robots = [...this.robots, ...newRobots];
                }

                this.offset = this.robots.length;
                this.hasMore = this.robots.length < this.totalCount;

                console.log(`📊 Loaded: ${newRobots.length}, Total: ${this.totalCount}, Current: ${this.robots.length}, HasMore: ${this.hasMore}`);
            } else {
                console.warn('⚠️ Unexpected response format:', response);
                if (reset) {
                    this.robots = [];
                }
                this.hasMore = false;
            }
        } catch (error) {
            console.error('❌ Failed to load robots:', error);
            this.loadError = error instanceof Error ? error : new Error('Неизвестная ошибка');
            if (reset) {
                this.robots = [];
            }
        } finally {
            const elapsed = Date.now() - startTime;
            const minDelay = 800;

            if (elapsed < minDelay) {
                await new Promise(resolve => setTimeout(resolve, minDelay - elapsed));
            }

            if (this.loadingMoreDelay) {
                clearTimeout(this.loadingMoreDelay);
                this.loadingMoreDelay = null;
            }

            this.loading = false;
            this.loadingMore = false;
            this.isLoadingInProgress = false;
            this.hideLoadingMore();

            if (this.container) {
                this.renderListContainer();
            }
        }
    }

    private showLoadingMore(): void {
        const loadingMoreEl = document.getElementById('loading-more');
        if (loadingMoreEl) {
            loadingMoreEl.style.display = 'flex';
        }
    }

    private hideLoadingMore(): void {
        const loadingMoreEl = document.getElementById('loading-more');
        if (loadingMoreEl) {
            loadingMoreEl.style.display = 'none';
        }
    }

    private getFilteredRobots(): RobotCardData[] {
        switch (this.currentFilter) {
            case 'active':
                return this.robots.filter(r => r.status === 1);
            case 'stopped':
                return this.robots.filter(r => r.status === 2);
            case 'error':
                return this.robots.filter(r => r.last_error !== null);
            default:
                return this.robots;
        }
    }

    private loadMore = async (): Promise<void> => {
        if (this.loadMoreTimeout) {
            clearTimeout(this.loadMoreTimeout);
        }

        if (this.loadingMore || !this.hasMore || this.loading || this.isLoadingInProgress) {
            return;
        }

        this.loadMoreTimeout = window.setTimeout(async () => {
            console.log('📊 Loading more robots, current offset:', this.offset, 'total:', this.totalCount);
            await this.loadData(false);
            this.loadMoreTimeout = null;
        }, 100);
    }

    private setupInfiniteScroll(): void {
        if (this.scrollHandler) {
            window.removeEventListener('scroll', this.scrollHandler);
        }

        this.scrollHandler = () => {
            const isRobotsPage = window.location.pathname === '/robots';
            if (!isRobotsPage) return;

            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            const windowHeight = window.innerHeight;
            const documentHeight = document.documentElement.scrollHeight;
            const distanceToBottom = documentHeight - (scrollTop + windowHeight);

            const isScrollingDown = scrollTop > this.lastScrollTop;
            this.lastScrollTop = scrollTop;

            if (isScrollingDown && distanceToBottom < 300) {
                if (!this.loadingMore && this.hasMore && !this.loading && !this.isLoadingInProgress) {
                    console.log('📊 Triggering loadMore, distance to bottom:', distanceToBottom);
                    this.loadMore();
                }
            }
        };

        window.addEventListener('scroll', this.scrollHandler);
    }

    private handleSearch = (e: Event): void => {
        const target = e.target as HTMLInputElement;
        const value = target.value;

        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }

        this.searchTimeout = window.setTimeout(() => {
            this.searchQuery = value;
            this.currentFilter = 'all';
            this.offset = 0;
            this.hasMore = true;
            this.loadData(true);
        }, 500);
    }

    private handleFilterChange = (filter: string): void => {
        this.currentFilter = filter;

        const filterBtns = this.container?.querySelectorAll('.filter-btn');
        if (filterBtns) {
            filterBtns.forEach(btn => {
                const btnFilter = btn.getAttribute('data-filter');
                if (btnFilter === filter) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        }

        this.renderRobotsList();
    }

    private handleToggle = async (id: number, statusCode: number): Promise<boolean> => {
        try {
            const token = localStorage.getItem('auth_token');

            await apiFetch('/robots/change_status', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    robotId: id,
                    status: statusCode
                })
            });

            const robot = this.robots.find(r => r.id === id);
            if (robot) {
                robot.status = statusCode === 1 ? 1 : 2;
                robot.statusName = statusCode === 1 ? 'Включен' : 'Выключен';
            }

            // Обновляем счетчики в фильтрах после изменения статуса
            this.updateFilterCounts();

            return true;
        } catch (error) {
            console.error('Failed to change robot status:', error);
            alert('Не удалось изменить состояние робота');
            return false;
        }
    }

    private updateFilterCounts(): void {
        if (!this.container) return;

        const activeCount = this.robots.filter(r => r.status === 1).length;
        const stoppedCount = this.robots.filter(r => r.status === 2).length;
        const errorCount = this.robots.filter(r => r.last_error !== null).length;

        const allBtn = this.container.querySelector('.filter-btn[data-filter="all"] .filter-count');
        const activeBtn = this.container.querySelector('.filter-btn[data-filter="active"] .filter-count');
        const stoppedBtn = this.container.querySelector('.filter-btn[data-filter="stopped"] .filter-count');
        const errorBtn = this.container.querySelector('.filter-btn[data-filter="error"] .filter-count');

        if (allBtn) allBtn.textContent = String(this.robots.length);
        if (activeBtn) activeBtn.textContent = String(activeCount);
        if (stoppedBtn) stoppedBtn.textContent = String(stoppedCount);
        if (errorBtn) errorBtn.textContent = String(errorCount);
    }

    private attachSearchEvents(): void {
        const searchInput = document.getElementById('search-robots') as HTMLInputElement;
        if (searchInput) {
            searchInput.removeEventListener('input', this.handleSearch);
            searchInput.addEventListener('input', this.handleSearch);
        }
    }

    private attachFilterEvents(): void {
        const filterBtns = document.querySelectorAll('.filter-btn');
        filterBtns.forEach(btn => {
            btn.removeEventListener('click', this.handleFilterClick);
            btn.addEventListener('click', this.handleFilterClick);
        });
    }

    private handleFilterClick = (e: Event): void => {
        const target = e.target as HTMLElement;
        const filterBtn = target.closest('.filter-btn') as HTMLElement;
        if (filterBtn && filterBtn.dataset.filter) {
            const filter = filterBtn.dataset.filter;
            console.log('📊 Filter button clicked:', filter);
            this.handleFilterChange(filter);
        }
    }

    private renderHeaderAndFilters(): void {
        if (!this.container) return;

        const activeCount = this.robots.filter(r => r.status === 1).length;
        const stoppedCount = this.robots.filter(r => r.status === 2).length;
        const errorCount = this.robots.filter(r => r.last_error !== null).length;

        const headerHtml = `
            <div class="robots-header">
                <div class="search-wrapper">
                    <input type="text" 
                           class="search-input" 
                           id="search-robots"
                           placeholder="Поиск"
                           value="${this.escapeHtml(this.searchQuery)}">
                </div>
            </div>

            <div class="robots-filters">
                <button class="filter-btn ${this.currentFilter === 'all' ? 'active' : ''}" data-filter="all">
                    Все <span class="filter-count">${this.robots.length}</span>
                </button>
                <button class="filter-btn ${this.currentFilter === 'active' ? 'active' : ''}" data-filter="active">
                    Активные <span class="filter-count">${activeCount}</span>
                </button>
                <button class="filter-btn ${this.currentFilter === 'stopped' ? 'active' : ''}" data-filter="stopped">
                    Остановлены <span class="filter-count">${stoppedCount}</span>
                </button>
                <button class="filter-btn ${this.currentFilter === 'error' ? 'active' : ''}" data-filter="error">
                    Ошибка <span class="filter-count">${errorCount}</span>
                </button>
            </div>

            <div class="robots-list" id="robots-list"></div>
            
            <div id="loading-more" style="display: none;" class="loading-more">
                <div class="loading-spinner-small"></div>
                <span>Загрузка...</span>
            </div>
            
            <div class="create-robot-fab" id="create-robot-fab" title="Создать нового робота">
                <span class="plus-icon">+</span>
            </div>
        `;

        const existingHeader = this.container.querySelector('.robots-header');
        const existingFilters = this.container.querySelector('.robots-filters');
        const existingFab = this.container.querySelector('.create-robot-fab');

        if (!existingHeader) {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = headerHtml;

            const header = tempDiv.querySelector('.robots-header');
            const filters = tempDiv.querySelector('.robots-filters');
            const fab = tempDiv.querySelector('.create-robot-fab');

            if (header) this.container.appendChild(header);
            if (filters) this.container.appendChild(filters);

            const listContainer = document.createElement('div');
            listContainer.className = 'robots-list';
            listContainer.id = 'robots-list';
            this.container.appendChild(listContainer);

            const loadingMore = document.createElement('div');
            loadingMore.id = 'loading-more';
            loadingMore.className = 'loading-more';
            loadingMore.style.display = 'none';
            loadingMore.innerHTML = '<div class="loading-spinner-small"></div><span>Загрузка...</span>';
            this.container.appendChild(loadingMore);

            if (fab) this.container.appendChild(fab);
        }
    }

    private renderSkeletonList(): void {
        const listContainer = this.container?.querySelector('#robots-list');
        if (!listContainer) return;

        listContainer.innerHTML = `
            <div class="skeleton-grid">
                ${Array(1).fill(0).map(() => `
                    <div class="robots-page-card skeleton-card">
                        <div class="robots-page-card-content">
                            <div class="skeleton-title"></div>
                            <div class="skeleton-robot"></div>
                            <div class="skeleton-line"></div>
                            <div class="skeleton-stats">
                                <div class="skeleton-stat"></div>
                                <div class="skeleton-stat"></div>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    private renderRobotsList(): void {
        const listContainer = this.container?.querySelector('#robots-list');
        if (!listContainer) return;

        const filteredRobots = this.getFilteredRobots();
        listContainer.innerHTML = '';

        if (filteredRobots.length === 0 && !this.loading) {
            listContainer.innerHTML = `
                <div class="empty-state-mini">
                    <p>Нет роботов для отображения</p>
                </div>
            `;
            return;
        }

        const listWrapper = document.createElement('div');
        listWrapper.className = 'robots-list-grid';

        filteredRobots.forEach(robot => {
            const cardContainer = document.createElement('div');
            cardContainer.className = 'robot-card-wrapper';
            listWrapper.appendChild(cardContainer);

            const card = new RobotCard(cardContainer, robot, this.handleToggle);
            card.render();
            this.cards.set(robot.id, card);
        });

        listContainer.appendChild(listWrapper);
    }

    private renderListContainer(): void {
        if (!this.container) return;

        // Обновляем счетчики в фильтрах
        this.updateFilterCounts();

        // Обновляем активный фильтр
        const filterBtns = this.container.querySelectorAll('.filter-btn');
        filterBtns.forEach(btn => {
            const filter = btn.getAttribute('data-filter');
            if (filter === this.currentFilter) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        // Рендерим список роботов
        if (this.loadError) {
            this.renderErrorState();
        } else if (this.robots.length === 0 && !this.loading) {
            this.renderEmptyState();
        } else {
            this.renderRobotsList();
        }

        this.attachSearchEvents();
        this.attachFilterEvents();
        this.setupInfiniteScroll();

    }

    private attachFabEvents(): void {
        const fabBtn = document.getElementById('create-robot-fab');
        if (fabBtn) {
            // Удаляем старый обработчик, если есть
            fabBtn.removeEventListener('click', this.openCreateModal);
            fabBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.openCreateModal();
            });
        }

        const createFirstBtn = document.getElementById('create-first-robot');
        if (createFirstBtn) {
            createFirstBtn.removeEventListener('click', this.openCreateModal);
            createFirstBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.openCreateModal();
            });
        }
    }

    render(container: HTMLElement): void {
        this.container = container;
        container.className = 'robots-page';
        container.innerHTML = '';

        this.renderHeaderAndFilters();

        if (this.loading) {
            this.renderSkeletonList();
        } else if (this.loadError) {
            this.renderErrorState();
        } else if (this.robots.length === 0) {
            this.renderEmptyState();
        } else {
            this.renderRobotsList();
        }

        this.attachSearchEvents();
        this.attachFilterEvents();
        this.setupInfiniteScroll();

        // Прикрепляем обработчик на FAB кнопку
        this.attachFabEvents();

        if (!this.initialized) {
            this.initialized = true;
            setTimeout(() => this.loadData(true), 100);
        }
    }

    private renderErrorState(): void {
        const listContainer = this.container?.querySelector('#robots-list');
        if (!listContainer) return;

        listContainer.innerHTML = `
            <div class="empty-state-wrapper" style="width: 100%; max-width: 100%; margin: 0; padding: 48px 32px;">
                <div class="error-robot-illustration">
                    <div class="robot-illustration sad">
                        <div class="robot-head">
                            <div class="robot-eye left sad"></div>
                            <div class="robot-eye right sad"></div>
                            <div class="robot-antenna"></div>
                        </div>
                        <div class="robot-body">
                            <div class="robot-heart broken">💔</div>
                        </div>
                        <div class="robot-arm left sad"></div>
                        <div class="robot-arm right sad"></div>
                    </div>
                </div>
                
                <h2 class="empty-state-title">Ой, что-то пошло не так</h2>
                <p class="empty-state-description">
                    ${this.escapeHtml(this.loadError?.message || 'Неизвестная ошибка')}
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
                retryBtn.addEventListener('click', () => this.loadData(true));
            }
        }, 0);
    }

    private renderEmptyState(): void {
        const listContainer = this.container?.querySelector('#robots-list');
        if (!listContainer) return;

        listContainer.innerHTML = `
            <div class="empty-state-wrapper" style="width: 100%; max-width: 100%; margin: 0; padding: 48px 32px;">
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
                
                <h2 class="empty-state-title">
                    ${this.searchQuery ? 'Ничего не найдено' : 'У вас пока нет роботов'}
                </h2>
                <p class="empty-state-description">
                    ${this.searchQuery
            ? `По запросу "${this.escapeHtml(this.searchQuery)}" ничего не найдено. Попробуйте другой запрос.`
            : 'Создайте своего первого торгового робота и начните автоматизировать торговлю'}
                </p>

                ${!this.searchQuery ? `
                    <button class="btn-create-robot" id="create-first-robot">
                        Создать робота
                        <span class="btn-icon">🚀</span>
                    </button>
                ` : ''}
            </div>
        `;

        setTimeout(() => {
            const createFirstBtn = document.getElementById('create-first-robot');
            if (createFirstBtn) {
                createFirstBtn.addEventListener('click', () => this.openCreateModal());
            }
        }, 0);
    }

    render(container: HTMLElement): void {
        this.container = container;
        container.className = 'robots-page';
        container.innerHTML = '';

        this.renderHeaderAndFilters();

        if (this.loading) {
            this.renderSkeletonList();
        } else if (this.loadError) {
            this.renderErrorState();
        } else if (this.robots.length === 0) {
            this.renderEmptyState();
        } else {
            this.renderRobotsList();
        }

        this.attachSearchEvents();
        this.attachFilterEvents();
        this.setupInfiniteScroll();


        const fabBtn = document.getElementById('create-robot-fab');
        if (fabBtn && !fabBtn.hasAttribute('data-listener-attached')) {
            fabBtn.setAttribute('data-listener-attached', 'true');
            fabBtn.addEventListener('click', this.openCreateModal);
        }

        const createFirstBtn = document.getElementById('create-first-robot');
        if (createFirstBtn && !createFirstBtn.hasAttribute('data-listener-attached')) {
            createFirstBtn.setAttribute('data-listener-attached', 'true');
            createFirstBtn.addEventListener('click', this.openCreateModal);
        }

        if (!this.initialized) {
            this.initialized = true;
            setTimeout(() => this.loadData(true), 100);
        }
    }


    private openCreateModal = (): void => {
        // Проверяем, не открывается ли уже модалка
        if (this.isModalOpening) {
            console.log('⚠️ Modal is already opening, skipping');
            return;
        }

        // Проверяем, не открыто ли уже модальное окно
        const existingModal = document.getElementById('robot-modal-container');
        if (existingModal) {
            console.log('⚠️ Modal already exists, skipping');
            return;
        }

        console.log('🔵 Opening create robot modal');
        this.isModalOpening = true;

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
                // onClose - удаляем контейнер и сбрасываем флаг
                const container = document.getElementById('robot-modal-container');
                if (container) {
                    container.remove();
                }
                console.log('🔴 Modal closed');
                this.isModalOpening = false;
            },
            () => {
                // onSuccess - удаляем контейнер, сбрасываем флаг и перезагружаем данные
                const container = document.getElementById('robot-modal-container');
                if (container) {
                    container.remove();
                }
                console.log('✅ Robot created, reloading data');
                this.isModalOpening = false;
                this.offset = 0;
                this.hasMore = true;
                this.loadData(true);
            }
        );

        modal.loadData();
    }

    private escapeHtml(str: string): string {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    destroy(): void {
        console.log('🧹 Destroying RobotsPage');
        if (this.scrollHandler) {
            window.removeEventListener('scroll', this.scrollHandler);
            this.scrollHandler = null;
        }
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }
        if (this.loadMoreTimeout) {
            clearTimeout(this.loadMoreTimeout);
        }
        if (this.loadingMoreDelay) {
            clearTimeout(this.loadingMoreDelay);
        }
        this.cards.forEach(card => card.destroy());
        this.cards.clear();
        this.container = null;
        this.initialized = false;
        this.lastScrollTop = 0;
        this.isLoadingInProgress = false;
    }
}