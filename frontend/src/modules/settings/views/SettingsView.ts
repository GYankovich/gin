// frontend/src/modules/settings/views/SettingsView.ts

import { apiKeyService } from '../services/apiKeyService';
import { router } from '../../../core/router';
import { store } from '../../../core/store';
import { themeManager, Theme } from '../../../core/theme';
import { CreateTokenModal } from '../components/CreateTokenModal';
import type { ApiKey } from '../types';
// Импортируем общие стили модальных окон
import '../../../shared/styles/modal.css';

export class SettingsView {
    private container: HTMLElement;
    private keys: ApiKey[] = [];
    private message: { text: string; type: 'success' | 'error' | 'info' } | null = null;
    private isLoading: boolean = true;
    private currentTheme: Theme;
    private isMobile: boolean = window.innerWidth <= 768;

    constructor(container: HTMLElement) {
        this.container = container;
        this.currentTheme = themeManager.getTheme();

        window.addEventListener('resize', () => {
            this.isMobile = window.innerWidth <= 768;
            this.render();
        });

        themeManager.subscribe((theme) => {
            this.currentTheme = theme;
            document.documentElement.setAttribute('data-theme', theme);
        });
    }

    async loadData(): Promise<void> {
        console.log('📊 SettingsView.loadData() called');
        this.isLoading = true;
        this.render();

        try {
            const token = store.getState().token;

            if (!token) {
                console.error('❌ No token, redirecting to login');
                router.navigate('/login');
                return;
            }

            const response = await apiKeyService.getKeys({
                limit: 100
            });

            this.keys = response.keys.sort((a, b) =>
                new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
            );

            console.log('✅ Loaded keys:', this.keys);

        } catch (error: any) {
            console.error('❌ Failed to load settings:', error);
            this.showMessage('error', error.message || 'Не удалось загрузить настройки');
        } finally {
            this.isLoading = false;
            this.render();
        }
    }

    private showMessage(type: 'success' | 'error' | 'info', text: string, timeout: number = 3000): void {
        this.message = { type, text };
        this.render();

        if (timeout > 0) {
            setTimeout(() => {
                this.message = null;
                this.render();
            }, timeout);
        }
    }

    private async handleAddToken(data: { name: string; token: string; tokenType: number }): Promise<void> {
        await apiKeyService.createKey({
            token: data.token,
            key_type: data.tokenType.toString(),
            name: data.name
        });

        this.showMessage('success', 'Токен успешно добавлен');
        await this.loadData();
    }

    private async handleDeleteKey(keyId: number): Promise<void> {
        if (!confirm('Вы уверены, что хотите удалить этот токен?')) {
            return;
        }

        try {
            await apiKeyService.deleteKey(keyId);
            this.showMessage('success', 'Токен успешно удален');
            await this.loadData();
        } catch (error: any) {
            this.showMessage('error', error.message || 'Ошибка при удалении токена');
        }
    }

    private openAddTokenModal(): void {
        const modalContainer = document.createElement('div');
        document.body.appendChild(modalContainer);

        const modal = new CreateTokenModal(
            modalContainer,
            () => {
                // onClose
                modalContainer.remove();
            },
            async (data) => {
                // onSuccess
                await this.handleAddToken(data);
                modalContainer.remove();
            }
        );

        modal.loadData();
    }

    private formatDate(dateStr?: string | null): string {
        if (!dateStr) return 'никогда';
        return new Date(dateStr).toLocaleString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    // Проверяем, является ли токен T-Invest
    private isTInvestKey(key: ApiKey): boolean {
        return key.token_type?.typeName === 'Т-Инвестиции' ||
            key.token_type?.typeDesc?.toLowerCase().includes('t-invest');
    }

    private renderMobileKeyCard(key: ApiKey): string {
        return `
            <div class="mobile-key-card" data-key-id="${key.id}">
                <div class="mobile-key-header">
                    <div class="key-title">
                        <span class="key-name">${this.escapeHtml(key.name || 'Без названия')}</span>
                        <span class="key-type-badge">${this.escapeHtml(key.token_type?.typeName || 'API Key')}</span>
                    </div>
                    <button class="mobile-delete-btn" data-key-id="${key.id}" title="Удалить токен">
                        🗑️
                    </button>
                </div>
                <div class="mobile-key-content">
                    <div class="mobile-key-row">
                        <span class="detail-label">Токен:</span>
                        <span class="token-masked">${this.escapeHtml(key.masked_token)}</span>
                    </div>
                    <div class="mobile-key-row">
                        <span class="detail-label">Создан:</span>
                        <span class="detail-value">${this.formatDate(key.created_at)}</span>
                    </div>
                </div>
            </div>
        `;
    }

    render(container?: HTMLElement): void {
        const target = container || this.container;
        if (!target) return;

        if (this.isLoading) {
            target.innerHTML = `
        <div class="settings-container">
          <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Загрузка...</p>
          </div>
        </div>
      `;
            return;
        }

        // Фильтруем только T-Invest токены
        const tinvestKeys = this.keys.filter(key => this.isTInvestKey(key));

        target.innerHTML = `
      <div class="settings-container">
        <div class="settings-header">
          <p class="settings-subtitle">Управление API ключами и подключениями</p>
        </div>

        <!-- T-Bank Section -->
        <div class="tbank-section">
          <div class="tbank-header">
            <div class="tbank-title">
              <img 
                src="https://cdn.tbank.ru/static/pages/files/d819b1e8-293e-43b9-b28e-1f38f5058372.png" 
                alt="T-Bank" 
                class="tbank-logo"
              />
              <h2>Т-Инвестиции</h2>
            </div>
            <button class="add-button" id="add-key-btn">
              ${this.isMobile ? '+' : 'Добавить токен'}
            </button>
          </div>

          <p class="tbank-description">
            Токен используется для получения данных о ваших инвестиционных счетах. 
            Получить токен можно в 
            <a href="https://www.tinkoff.ru/invest/settings/api/" target="_blank" rel="noopener noreferrer">
              личном кабинете Т-Банка
            </a>.
          </p>

          ${tinvestKeys.length > 0 ? `
            ${this.isMobile ? `
              <div class="mobile-keys-list">
                ${tinvestKeys.map(key => this.renderMobileKeyCard(key)).join('')}
              </div>
            ` : `
              <div class="keys-table">
                <div class="keys-table-header">
                  <div class="col-name">Название</div>
                  <div class="col-token">Токен</div>
                  <div class="col-last-used">Создан</div>
                  <div class="col-actions"></div>
                </div>
                
                <div class="keys-table-body">
                  ${tinvestKeys.map(key => `
                    <div 
                      class="key-row" 
                      data-key-id="${key.id}"
                      onmouseenter="this.classList.add('hover')" 
                      onmouseleave="this.classList.remove('hover')"
                    >
                      <div class="col-name">
                        <span class="key-name">${this.escapeHtml(key.name || '—')}</span>
                      </div>
                      <div class="col-token">
                        <span class="token-masked">${this.escapeHtml(key.masked_token)}</span>
                      </div>
                      <div class="col-last-used">
                        <span class="last-used">${this.formatDate(key.created_at)}</span>
                      </div>
                      <div class="col-actions">
                        <button class="delete-btn" data-key-id="${key.id}" title="Удалить токен">
                          🗑️
                        </button>
                      </div>
                    </div>
                  `).join('')}
                </div>
              </div>
            `}
          ` : `
            <div class="empty-state">
              <p>Нет добавленных токенов</p>
            </div>
          `}
        </div>

        ${this.message ? `
          <div class="message message-${this.message.type}">
            <span class="message-icon">
              ${this.message.type === 'success' ? '✓' : this.message.type === 'error' ? '⚠️' : 'ℹ️'}
            </span>
            <span>${this.escapeHtml(this.message.text)}</span>
          </div>
        ` : ''}
      </div>
    `;

        this.attachEvents();
    }

    private attachEvents(): void {
        const addButton = document.getElementById('add-key-btn');
        addButton?.addEventListener('click', () => {
            this.openAddTokenModal();
        });

        document.querySelectorAll('.delete-btn, .mobile-delete-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const keyId = (e.currentTarget as HTMLElement).dataset.keyId;
                if (keyId) this.handleDeleteKey(parseInt(keyId));
            });
        });
    }

    private escapeHtml(str: string): string {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}