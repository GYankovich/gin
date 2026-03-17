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
    }

    async loadData(): Promise<void> {
        console.log('📊 ===== LOAD CREATE PAGE DATA =====');
        console.log('📊 Loading strategies and tokens...');

        this.loading = true;

        if (this.container) {
            this.render(this.container);
        }

        try {
            const token = localStorage.getItem('auth_token');
            if (!token) {
                console.error('❌ No auth token found!');
                router.navigate('/login');
                return;
            }

            console.log('📡 Fetching strategies and tokens...');
            const [strategies, tokens] = await Promise.all([
                robotService.getStrategies(),
                robotService.getAvailableTokens()
            ]);

            console.log('✅ Strategies loaded:', strategies);
            console.log('✅ Tokens loaded:', tokens);

            this.strategies = strategies || [];
            this.availableTokens = tokens || [];

        } catch (error) {
            console.error('❌ Failed to load data:', error);
            this.strategies = [];
            this.availableTokens = [];

            if (this.container) {
                this.showError(error);
            }
        } finally {
            this.loading = false;
            console.log('📊 Loading finished');

            if (this.container) {
                this.render(this.container);
            }
        }
    }

    private showError(error: unknown): void {
        if (!this.container) return;

        this.container.innerHTML = `
            <div style="text-align: center; padding: 2rem;">
                <h3 style="color: #f44336;">Ошибка загрузки</h3>
                <p>${error instanceof Error ? error.message : 'Неизвестная ошибка'}</p>
                <button id="retry-load" style="
                    margin-top: 1rem;
                    padding: 0.5rem 2rem;
                    background: #3498db;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                ">
                    Повторить
                </button>
                <button id="go-back" style="
                    margin-top: 1rem;
                    margin-left: 1rem;
                    padding: 0.5rem 2rem;
                    background: #666;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                ">
                    Назад
                </button>
            </div>
        `;

        setTimeout(() => {
            document.getElementById('retry-load')?.addEventListener('click', () => {
                this.loadData();
            });
            document.getElementById('go-back')?.addEventListener('click', () => {
                router.navigate('/robots');
            });
        }, 0);
    }

    private handleSubmit = async (data: RobotCreate): Promise<void> => {
        console.log('📤 Submitting robot creation:', data);
        try {
            await robotService.createRobot(data);
            console.log('✅ Robot created successfully');
            router.navigate('/robots');
        } catch (error) {
            console.error('❌ Failed to create robot:', error);
            alert(`Не удалось создать робота: ${error instanceof Error ? error.message : 'Неизвестная ошибка'}`);
        }
    }

    private handleCancel = (): void => {
        console.log('👈 Cancelling, going back to robots list');
        router.navigate('/robots');
    }

    render(container: HTMLElement): void {
        console.log('🎨 ===== RENDER CREATE PAGE =====');
        console.log('🎨 Rendering CreateRobotPage', {
            loading: this.loading,
            strategiesCount: this.strategies.length,
            tokensCount: this.availableTokens.length
        });

        this.container = container;

        if (this.loading) {
            container.innerHTML = `
                <div style="text-align: center; padding: 4rem;">
                    <div style="
                        display: inline-block;
                        width: 50px;
                        height: 50px;
                        border: 4px solid #f3f3f3;
                        border-top: 4px solid #3498db;
                        border-radius: 50%;
                        animation: spin 1s linear infinite;
                        margin-bottom: 1rem;
                    "></div>
                    <div style="color: #666;">Загрузка...</div>
                </div>
                <style>
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            `;

            if (!this.initialized) {
                this.initialized = true;
                setTimeout(() => {
                    console.log('⏰ Timeout triggered, loading data');
                    this.loadData();
                }, 100);
            }
            return;
        }

        if (this.strategies.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 2rem;">
                    <h3>Нет доступных стратегий</h3>
                    <button id="go-back" style="
                        margin-top: 1rem;
                        padding: 0.5rem 2rem;
                        background: #666;
                        color: white;
                        border: none;
                        border-radius: 6px;
                        cursor: pointer;
                    ">
                        Назад
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

        // Создаем форму
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

        // Рендерим форму
        container.innerHTML = ''; // Очищаем контейнер
        console.log('🎯 Rendering RobotForm');
        this.form.render(container);
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