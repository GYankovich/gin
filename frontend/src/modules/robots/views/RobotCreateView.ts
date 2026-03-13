import { router } from '../../../core/router';
import { robotService } from '../services/robotService';
import type { RobotCreate, AvailableToken } from '../types';

export class RobotCreateView {
    private container: HTMLElement;
    private tokens: AvailableToken[] = [];
    private isLoading = true;
    private error: string | null = null;

    constructor() {
        this.container = document.getElementById('app')!;
    }

    private async loadTokens() {
        try {
            this.isLoading = true;
            this.tokens = await robotService.getAvailableTokens();
        } catch (error) {
            console.error('Failed to load tokens:', error);
            this.error = 'Не удалось загрузить список токенов';
        } finally {
            this.isLoading = false;
            this.render();
        }
    }

    private async handleSubmit(e: Event) {
        e.preventDefault();

        const form = e.target as HTMLFormElement;
        const formData = new FormData(form);

        try {
            const robotData: RobotCreate = {
                name: formData.get('name') as string,
                description: formData.get('description') as string || undefined,
                robot_type: formData.get('robot_type') as string,
                token_id: formData.get('token_id') ? Number(formData.get('token_id')) : undefined,
                strategy_params: {
                    grid_step: Number(formData.get('grid_step')) || 0.5,
                    grid_levels: Number(formData.get('grid_levels')) || 10,
                    initial_investment: Number(formData.get('initial_investment')) || 100000
                },
                max_daily_loss: formData.get('max_daily_loss') ? Number(formData.get('max_daily_loss')) : undefined,
                max_position_size: formData.get('max_position_size') ? Number(formData.get('max_position_size')) : undefined
            };

            await robotService.createRobot(robotData);
            router.navigate('/robots');
        } catch (error) {
            console.error('Failed to create robot:', error);
            alert('Ошибка при создании робота');
        }
    }

    render() {
        if (this.isLoading) {
            this.container.innerHTML = '<div class="loading">Загрузка...</div>';
            return;
        }

        this.container.innerHTML = `
            <div class="robot-form-view">
                <div class="view-header">
                    <h1>Создание торгового робота</h1>
                    <button class="btn-secondary" id="cancel">Отмена</button>
                </div>

                ${this.error ? `<div class="error-message">${this.error}</div>` : ''}

                <form id="create-robot-form" class="robot-form">
                    <div class="form-section">
                        <h3>Основная информация</h3>
                        
                        <div class="form-group">
                            <label for="name">Название робота *</label>
                            <input type="text" id="name" name="name" required 
                                   minlength="3" maxlength="255">
                        </div>

                        <div class="form-group">
                            <label for="description">Описание</label>
                            <textarea id="description" name="description" rows="3"></textarea>
                        </div>

                        <div class="form-group">
                            <label for="robot_type">Тип стратегии *</label>
                            <select id="robot_type" name="robot_type" required>
                                <option value="grid">Сеточный робот</option>
                                <option value="trend">Трендовый робот</option>
                                <option value="arbitrage">Арбитраж</option>
                            </select>
                        </div>
                    </div>

                    <div class="form-section">
                        <h3>Подключение к счету</h3>
                        
                        <div class="form-group">
                            <label for="token_id">Токен доступа</label>
                            <select id="token_id" name="token_id">
                                <option value="">-- Без токена (робот неактивен) --</option>
                                ${this.tokens.map(token => `
                                    <option value="${token.id}">
                                        ${token.token_name || 'Без названия'} (${token.token_preview})
                                        ${token.last_used_at ? '• последнее использование: ' + new Date(token.last_used_at).toLocaleDateString() : ''}
                                    </option>
                                `).join('')}
                            </select>
                            <small>Токен можно добавить в разделе "Настройки"</small>
                        </div>
                    </div>

                    <div class="form-section">
                        <h3>Параметры стратегии (для сеточного робота)</h3>
                        
                        <div class="form-group">
                            <label for="grid_step">Шаг сетки (%)</label>
                            <input type="number" id="grid_step" name="grid_step" 
                                   step="0.1" min="0.1" max="10" value="0.5">
                        </div>

                        <div class="form-group">
                            <label for="grid_levels">Количество уровней</label>
                            <input type="number" id="grid_levels" name="grid_levels" 
                                   min="1" max="50" value="10">
                        </div>

                        <div class="form-group">
                            <label for="initial_investment">Начальный капитал (₽)</label>
                            <input type="number" id="initial_investment" name="initial_investment" 
                                   min="1000" step="1000" value="100000">
                        </div>
                    </div>

                    <div class="form-section">
                        <h3>Риск-менеджмент</h3>
                        
                        <div class="form-group">
                            <label for="max_daily_loss">Максимальный дневной убыток (%)</label>
                            <input type="number" id="max_daily_loss" name="max_daily_loss" 
                                   step="0.1" min="0" max="100" placeholder="Например: 5">
                        </div>

                        <div class="form-group">
                            <label for="max_position_size">Максимальный размер позиции (₽)</label>
                            <input type="number" id="max_position_size" name="max_position_size" 
                                   step="1000" min="0" placeholder="Например: 50000">
                        </div>
                    </div>

                    <div class="form-actions">
                        <button type="submit" class="btn-primary">Создать робота</button>
                        <button type="button" class="btn-secondary" id="cancel-form">Отмена</button>
                    </div>
                </form>
            </div>
        `;

        document.getElementById('cancel')?.addEventListener('click', () => {
            router.navigate('/robots');
        });

        document.getElementById('cancel-form')?.addEventListener('click', () => {
            router.navigate('/robots');
        });

        document.getElementById('create-robot-form')?.addEventListener('submit', this.handleSubmit.bind(this));
    }
}