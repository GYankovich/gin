// frontend/src/modules/robots/components/RobotCard.ts

export interface RobotCardData {
    id: number;
    name: string;
    token: {
        id: number;
        name: string | null;
        status: number;
        type: number;
        typeName: string;
    };
    type: number;
    typeName: string;
    status: number;
    statusName: string;
    last_started: string | null;
    last_error: string | null;
    last_error_at: string | null;
    last_stopped: string | null;
}

export class RobotCard {
    private container: HTMLElement;
    private robot: RobotCardData;
    private onToggle: (id: number, statusCode: number) => void;
    private isRefreshing: boolean;

    constructor(
        container: HTMLElement,
        robot: RobotCardData,
        onToggle: (id: number, statusCode: number) => void,
        isRefreshing: boolean = false
    ) {
        this.container = container;
        this.robot = robot;
        this.onToggle = onToggle;
        this.isRefreshing = isRefreshing;
    }

    private getStatusCode(): number {
        // 1 - Включить, 2 - Выключить
        return this.robot.status === 1 ? 2 : 1;
    }

    private getNextStatusName(): string {
        return this.robot.status === 1 ? 'Выключить' : 'Включить';
    }

    private formatDate(dateString: string | null): string {
        if (!dateString) return 'никогда';

        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'только что';
        if (diffMins < 60) return `${diffMins} мин назад`;
        if (diffHours < 24) return `${diffHours} ч назад`;
        if (diffDays < 7) return `${diffDays} дн назад`;

        return date.toLocaleDateString('ru-RU', {
            day: 'numeric',
            month: 'short'
        });
    }

    private shouldShowError(): boolean {
        if (!this.robot.last_error || !this.robot.last_error_at) return false;
        if (!this.robot.last_started) return true;

        const errorDate = new Date(this.robot.last_error_at).getTime();
        const startedDate = new Date(this.robot.last_started).getTime();

        return errorDate > startedDate;
    }

    private handleToggle = (e: MouseEvent) => {
        e.stopPropagation();
        const statusCode = this.getStatusCode();
        this.onToggle(this.robot.id, statusCode);
    }

    render(): void {
        const isActive = this.robot.status === 1;
        const nextStatusName = this.getNextStatusName();
        const lastStarted = this.formatDate(this.robot.last_started);
        const showError = this.shouldShowError();

        this.container.innerHTML = `
            <div class="robot-card ${this.isRefreshing ? 'loading' : ''}" data-status="${isActive ? 'active' : 'stopped'}">
                <div class="robot-card-row">
                    <div class="robot-name-wrapper">
                        <span class="robot-name">${this.robot.name}</span>
                        <span class="robot-type-badge">${this.robot.typeName}</span>
                    </div>
                    <button class="robot-toggle ${isActive ? 'active' : ''}" 
                            id="toggle-${this.robot.id}">
                        <span class="toggle-dot"></span>
                        <span class="toggle-text">${nextStatusName}</span>
                    </button>
                </div>
                
                <div class="robot-subrow">
                    <span class="robot-subrow-icon">🔑</span>
                    ${this.robot.token.typeName}
                </div>
                
                <div class="robot-card-row secondary">
                    <div class="robot-info-group">
                        <div class="robot-info">
                            <span class="info-icon">⏱️</span>
                            <span class="info-label">Запуск</span>
                            <span class="info-value ${!this.robot.last_started ? 'muted' : ''}">
                                ${lastStarted}
                            </span>
                        </div>
                        
                        ${showError ? `
                        <div class="robot-info error" title="${this.robot.last_error}">
                            <span class="info-icon">⚠️</span>
                            <span class="info-label">Ошибка</span>
                            <span class="info-value">${this.formatDate(this.robot.last_error_at)}</span>
                        </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;

        this.attachEvents();
    }

    private attachEvents(): void {
        const toggleBtn = document.getElementById(`toggle-${this.robot.id}`);
        if (toggleBtn) {
            toggleBtn.addEventListener('click', this.handleToggle);
        }
    }

    destroy(): void {
        this.container.innerHTML = '';
    }
}