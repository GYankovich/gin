import { apiKeyService } from '../services/apiKeyService';
import { router } from '../../../core/router';
import { store } from '../../../core/store';
import { themeManager, Theme } from '../../../core/theme';
import type { ApiKey } from '../types';

export class SettingsView {
    private container: HTMLElement;
    private keys: ApiKey[] = [];
    private message: { text: string; type: 'success' | 'error' | 'info' } | null = null;
    private modalError: string | null = null;
    private isLoading: boolean = true;
    private isSaving: boolean = false;
    private showAddModal: boolean = false;
    private currentTheme: Theme;
    private isMobile: boolean = window.innerWidth <= 768;
    private showTokenInModal: boolean = false;

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
                include_inactive: true,
                limit: 100
            });

            this.keys = response.keys.sort((a, b) =>
                new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
            );

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

    private async handleAddKey(token: string, name: string): Promise<void> {
        this.modalError = null;

        if (!token.trim()) {
            this.modalError = 'Введите токен';
            this.render();
            return;
        }

        if (!token.startsWith('t.')) {
            this.modalError = 'Токен должен начинаться с t.';
            this.render();
            return;
        }

        this.isSaving = true;
        this.render();

        try {
            await apiKeyService.createKey({
                token,
                key_type: 'tinvest',
                name: name.trim() || null,
            });

            this.showMessage('success', 'Токен успешно добавлен');
            this.showAddModal = false;
            this.modalError = null;
            await this.loadData();

        } catch (error: any) {
            this.modalError = error.message || 'Ошибка при добавлении токена';
            this.render();
        } finally {
            this.isSaving = false;
            this.render();
        }
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

    private renderAddModal(): string {
        if (!this.showAddModal) return '';

        return `
      <div class="modal-overlay" id="modal-overlay">
        <div class="modal-container">
          <div class="modal-header">
            <h3>Добавить новый токен</h3>
            <button class="modal-close" id="modal-close">✕</button>
          </div>
          
          <div class="modal-content">
            <div class="form-group">
              <label class="form-label">Название токена (опционально)</label>
              <input 
                type="text" 
                id="new-token-name" 
                class="form-input" 
                placeholder="Например: Основной токен"
                autocomplete="off"
              />
            </div>

            <div class="form-group">
              <label class="form-label">Токен доступа</label>
              <div class="token-input-wrapper">
                <input 
                  type="${this.showTokenInModal ? 'text' : 'password'}" 
                  id="new-token-value" 
                  class="form-input" 
                  placeholder="t.xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                  autocomplete="off"
                />
                <button class="token-visibility-toggle" id="toggle-new-token" type="button">
                  <span class="eye-icon">${this.showTokenInModal ? '👁️‍🗨️' : '👁️'}</span>
                </button>
              </div>
            </div>

            ${this.modalError ? `
              <div class="modal-error">
                <span class="error-icon">⚠️</span>
                <span>${this.modalError}</span>
              </div>
            ` : ''}

            <div class="modal-actions">
              <button class="modal-button cancel" id="modal-cancel">Отмена</button>
              <button class="modal-button save" id="modal-save" ${this.isSaving ? 'disabled' : ''}>
                ${this.isSaving ? 'Добавление...' : 'Добавить'}
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
    }

    private renderMobileKeyCard(key: ApiKey): string {
        return `
            <div class="mobile-key-card" data-key-id="${key.id}">
                <div class="mobile-key-header">
                    <div class="key-title">
                        <span class="key-name">${key.name || 'Без названия'}</span>
                        <span class="key-type-badge">${key.key_type}</span>
                    </div>
                    <button class="mobile-delete-btn" data-key-id="${key.id}" title="Удалить токен">
                        🗑️
                    </button>
                </div>
                <div class="mobile-key-content">
                    <div class="mobile-key-row">
                        <span class="detail-label">Токен:</span>
                        <span class="token-masked">${key.masked_token}</span>
                    </div>
                    <div class="mobile-key-row">
                        <span class="detail-label">Последнее использование:</span>
                        <span class="detail-value">${this.formatDate(key.last_used_at)}</span>
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

        const tinvestKeys = this.keys.filter(k => k.key_type === 'tinvest');

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
                  <div class="col-last-used">Последнее использование</div>
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
                        <span class="key-name">${key.name || '—'}</span>
                      </div>
                      <div class="col-token">
                        <span class="token-masked">${key.masked_token}</span>
                      </div>
                      <div class="col-last-used">
                        <span class="last-used">${this.formatDate(key.last_used_at)}</span>
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
            <span>${this.message.text}</span>
          </div>
        ` : ''}
      </div>

      ${this.renderAddModal()}
    `;

        this.attachEvents();
    }

    private attachEvents(): void {
        const addButton = document.getElementById('add-key-btn');
        addButton?.addEventListener('click', () => {
            this.showAddModal = true;
            this.modalError = null;
            this.showTokenInModal = false;
            this.render();

            setTimeout(() => {
                const newNameInput = document.getElementById('new-token-name') as HTMLInputElement;
                const newTokenInput = document.getElementById('new-token-value') as HTMLInputElement;
                if (newNameInput) newNameInput.value = '';
                if (newTokenInput) newTokenInput.value = '';
            }, 0);
        });

        const modalOverlay = document.getElementById('modal-overlay');
        const modalClose = document.getElementById('modal-close');
        const modalCancel = document.getElementById('modal-cancel');
        const modalSave = document.getElementById('modal-save');
        const toggleVisibility = document.getElementById('toggle-new-token');

        const closeModal = () => {
            this.showAddModal = false;
            this.modalError = null;
            this.showTokenInModal = false;
            this.render();
        };

        modalOverlay?.addEventListener('click', (e) => {
            if (e.target === modalOverlay) closeModal();
        });

        modalClose?.addEventListener('click', closeModal);
        modalCancel?.addEventListener('click', closeModal);

        if (toggleVisibility) {
            toggleVisibility.addEventListener('click', () => {
                this.showTokenInModal = !this.showTokenInModal;
                this.render();
            });
        }

        modalSave?.addEventListener('click', async () => {
            const nameInput = document.getElementById('new-token-name') as HTMLInputElement;
            const tokenInput = document.getElementById('new-token-value') as HTMLInputElement;
            await this.handleAddKey(tokenInput.value, nameInput.value);
        });

        document.querySelectorAll('.delete-btn, .mobile-delete-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const keyId = (e.currentTarget as HTMLElement).dataset.keyId;
                if (keyId) this.handleDeleteKey(parseInt(keyId));
            });
        });
    }
}