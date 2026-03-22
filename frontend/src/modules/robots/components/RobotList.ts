// frontend/src/modules/robots/components/RobotList.ts

import { RobotCard, RobotCardData } from './RobotCard';

export class RobotList {
    private container: HTMLElement;
    private robots: RobotCardData[];
    private onToggle: (id: number, statusCode: number) => void;
    private isLoading: boolean;
    private filter: string;
    private onFilterChange: (filter: string) => void;
    private cards: RobotCard[] = [];

    constructor(
        robots: RobotCardData[],
        onToggle: (id: number, statusCode: number) => void,
        isLoading: boolean = false,
        filter: string = 'all',
        onFilterChange: (filter: string) => void
    ) {
        this.robots = robots;
        this.onToggle = onToggle;
        this.isLoading = isLoading;
        this.filter = filter;
        this.onFilterChange = onFilterChange;
    }

    updateProps(props: {
        robots: RobotCardData[];
        loading: boolean;
        filter: string;
    }): void {
        this.robots = props.robots;
        this.isLoading = props.loading;
        this.filter = props.filter;
        this.render();
    }

    private getFilteredRobots(): RobotCardData[] {
        switch (this.filter) {
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

    render(container?: HTMLElement): void {
        if (container) {
            this.container = container;
        }

        if (!this.container) return;

        const filteredRobots = this.getFilteredRobots();

        this.container.innerHTML = `
            <div class="robots-filters">
                <button class="filter-btn ${this.filter === 'all' ? 'active' : ''}" data-filter="all">
                    Все <span class="filter-count">${this.robots.length}</span>
                </button>
                <button class="filter-btn ${this.filter === 'active' ? 'active' : ''}" data-filter="active">
                    Активные <span class="filter-count">${this.robots.filter(r => r.status === 1).length}</span>
                </button>
                <button class="filter-btn ${this.filter === 'stopped' ? 'active' : ''}" data-filter="stopped">
                    Остановлены <span class="filter-count">${this.robots.filter(r => r.status === 2).length}</span>
                </button>
                <button class="filter-btn ${this.filter === 'error' ? 'active' : ''}" data-filter="error">
                    Ошибка <span class="filter-count">${this.robots.filter(r => r.last_error !== null).length}</span>
                </button>
            </div>
            
            <div class="robots-list" id="robots-list"></div>
        `;

        const list = document.getElementById('robots-list');

        if (list) {
            this.cards.forEach(card => card.destroy());
            this.cards = [];

            if (filteredRobots.length === 0) {
                list.innerHTML = `
                    <div class="no-results">
                        <p>Нет роботов, соответствующих выбранному фильтру</p>
                    </div>
                `;
            } else {
                list.innerHTML = '';

                filteredRobots.forEach(robot => {
                    const cardContainer = document.createElement('div');
                    cardContainer.className = 'robot-card-wrapper';
                    list.appendChild(cardContainer);

                    const card = new RobotCard(
                        cardContainer,
                        robot,
                        this.onToggle,
                        this.isLoading
                    );
                    card.render();
                    this.cards.push(card);
                });
            }
        }

        this.attachFilterEvents();
    }

    private attachFilterEvents(): void {
        const filterBtns = this.container.querySelectorAll('.filter-btn');
        filterBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const target = e.target as HTMLElement;
                const filter = target.dataset.filter;
                if (filter) {
                    this.onFilterChange(filter);
                }
            });
        });
    }

    destroy(): void {
        this.cards.forEach(card => card.destroy());
        this.cards = [];
        this.container.innerHTML = '';
    }
}