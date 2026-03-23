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
    date_creation?: string;
}

export class RobotCard {
    private container: HTMLElement;
    private robot: RobotCardData;
    private onToggle: (id: number, statusCode: number) => Promise<boolean>;
    private isUpdating: boolean = false;
    private cardElement: HTMLElement | null = null;

    constructor(
        container: HTMLElement,
        robot: RobotCardData,
        onToggle: (id: number, statusCode: number) => Promise<boolean>
    ) {
        this.container = container;
        this.robot = robot;
        this.onToggle = onToggle;
    }

    private formatTimeAgo(dateString: string | null): string {
        if (!dateString) return '—';

        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'только что';
        if (diffMins < 60) return `${diffMins} мин`;
        if (diffHours < 24) return `${diffHours} ч`;
        if (diffDays < 7) return `${diffDays} дн`;

        return date.toLocaleDateString('ru-RU', {
            day: 'numeric',
            month: 'short'
        });
    }

    private formatDate(dateString: string | null): string {
        if (!dateString) return '—';
        const date = new Date(dateString);
        return date.toLocaleDateString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    }

    private shouldShowError(): boolean {
        if (!this.robot.last_error || !this.robot.last_error_at) return false;
        if (!this.robot.last_started) return true;

        const errorDate = new Date(this.robot.last_error_at).getTime();
        const startedDate = new Date(this.robot.last_started).getTime();
        return errorDate > startedDate;
    }

    private handleToggle = async (e: MouseEvent) => {
        e.stopPropagation();

        if (this.isUpdating) return;

        const newStatus = this.robot.status === 1 ? 2 : 1;
        const robotHead = this.cardElement?.querySelector('.robot-head-clickable');

        if (robotHead) {
            robotHead.classList.add('clicking');
        }

        this.isUpdating = true;

        try {
            const success = await this.onToggle(this.robot.id, newStatus);

            if (success) {
                this.robot.status = newStatus;
                this.robot.statusName = newStatus === 1 ? 'Включен' : 'Выключен';
                this.updateUI();
            }
        } finally {
            this.isUpdating = false;
            if (robotHead) {
                setTimeout(() => {
                    robotHead.classList.remove('clicking');
                }, 300);
            }
        }
    }

    private updateUI(): void {
        const isActive = this.robot.status === 1;
        const robotHead = this.cardElement?.querySelector('.robot-head-clickable');

        if (this.cardElement) {
            if (isActive) {
                this.cardElement.classList.add('active');
            } else {
                this.cardElement.classList.remove('active');
            }
        }

        if (robotHead) {
            if (isActive) {
                robotHead.classList.remove('inactive');
                robotHead.classList.add('active');
            } else {
                robotHead.classList.remove('active');
                robotHead.classList.add('inactive');
            }
        }
    }

    render(): void {
        const isActive = this.robot.status === 1;
        const lastStarted = this.formatTimeAgo(this.robot.last_started);
        const creationDate = this.formatDate(this.robot.date_creation || null);
        const showError = this.shouldShowError();

        this.container.innerHTML = `
            <div class="robots-page-card ${isActive ? 'active' : ''}">
                <div class="robots-page-card-content">
                    <!-- Верхняя строка: название робота + чипы -->
                    <div class="robots-page-card-header">
                        <div class="robots-page-card-title">
                            <h3 class="robots-page-card-name">${this.escapeHtml(this.robot.name)}</h3>
                            <div class="robots-page-card-chips">
                                <span class="robots-page-card-badge">${this.escapeHtml(this.robot.typeName)}</span>
                                <span class="robots-page-card-badge token-badge">
                                    ${this.escapeHtml(this.robot.token.typeName)}
                                </span>
                            </div>
                        </div>
                        <div class="robot-head-clickable ${isActive ? 'active' : 'inactive'}" title="${isActive ? 'Выключить робота' : 'Включить робота'}">
                            <div class="robot-head">
                                <div class="robot-eye left"></div>
                                <div class="robot-eye right"></div>
                                <div class="robot-antenna"></div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Даты -->
                    <div class="robots-page-card-dates">
                        <div class="date-item">
                            <span class="date-label">Последний запуск</span>
                            <span class="date-value">${lastStarted}</span>
                        </div>
                        <div class="date-item">
                            <span class="date-label">Создан</span>
                            <span class="date-value">${creationDate}</span>
                        </div>
                    </div>
                    
                    ${showError && this.robot.last_error ? `
                        <div class="robots-page-card-error">
                            <span class="error-icon">⚠️</span>
                            <span class="error-text">${this.escapeHtml(this.truncate(this.robot.last_error, 100))}</span>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;

        this.cardElement = this.container.querySelector('.robots-page-card');
        this.attachEvents();
    }

    private attachEvents(): void {
        const robotHead = this.cardElement?.querySelector('.robot-head-clickable');
        if (robotHead) {
            robotHead.addEventListener('click', this.handleToggle);
        }
    }

    private escapeHtml(str: string): string {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    private truncate(str: string, length: number): string {
        if (str.length <= length) return str;
        return str.substring(0, length) + '...';
    }

    destroy(): void {
        const robotHead = this.cardElement?.querySelector('.robot-head-clickable');
        if (robotHead) {
            robotHead.removeEventListener('click', this.handleToggle);
        }
        this.container.innerHTML = '';
    }
}