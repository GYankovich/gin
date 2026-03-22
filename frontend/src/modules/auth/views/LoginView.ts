import { authService } from '../services/authService';
import { router } from '../../../core/router';
import { store } from '../../../core/store';
import { themeManager, Theme } from '../../../core/theme';

export class LoginView {
    private container: HTMLElement;
    private error: string | null = null;
    private isLoading: boolean = false;
    private formData: { login: string; password: string } = { login: '', password: '' };
    private showError: boolean = false;
    private currentTheme: Theme;

    constructor(container: HTMLElement) {
        this.container = container;
        this.currentTheme = themeManager.getTheme();
        console.log('🆕 LoginView created');
    }

    private renderTemplate(): string {
        const isDark = this.currentTheme === 'dark';

        return `
      <div class="login-container">
        <div class="login-card">
          <div class="login-header">
            <h1 class="login-title">Вход</h1>
            <button class="theme-toggle-login" id="theme-toggle" title="Сменить тему">
              <span class="theme-icon">${isDark ? '☀️' : '🌙'}</span>
            </button>
          </div>

          ${this.error && this.showError ? `
            <div class="error-toast">
              <span class="error-icon">⚠️</span>
              <span class="error-text">${this.error}</span>
              <button class="error-close" id="close-error">×</button>
            </div>
          ` : ''}

          <div class="login-form" id="login-form">
            <div class="form-group">
              <label class="form-label" for="login">Логин</label>
              <input 
                type="text" 
                id="login" 
                class="form-input" 
                placeholder="gy"
                autocomplete="username"
                value="${this.formData.login}"
              />
            </div>

            <div class="form-group">
              <label class="form-label" for="password">Пароль</label>
              <input 
                type="password" 
                id="password" 
                class="form-input" 
                placeholder="••••••••"
                autocomplete="current-password"
                value="${this.formData.password}"
              />
            </div>

            ${this.error && !this.showError ? `
              <div class="error-message">
                <span class="error-icon-small">⚠️</span>
                ${this.error}
              </div>
            ` : ''}

            <button 
              class="login-button" 
              id="login-button"
              ${this.isLoading ? 'disabled' : ''}
            >
              ${this.isLoading ? 'Вход...' : 'Войти'}
            </button>
          </div>
        </div>
      </div>
    `;
    }

    private toggleTheme(): void {
        themeManager.toggleTheme();
        this.currentTheme = themeManager.getTheme();
        this.render();
    }

    private showErrorToast(message: string): void {
        this.error = message;
        this.showError = true;
        this.render();

        setTimeout(() => {
            if (this.showError) {
                this.showError = false;
                this.error = null;
                this.render();
            }
        }, 5000);
    }

    private async handleLogin(e?: Event): Promise<void> {
        if (e) {
            e.preventDefault();
        }

        if (this.isLoading) return;

        const loginInput = document.getElementById('login') as HTMLInputElement;
        const passwordInput = document.getElementById('password') as HTMLInputElement;
        const button = document.getElementById('login-button') as HTMLButtonElement;

        if (!loginInput || !passwordInput) {
            console.error('❌ Form inputs not found');
            return;
        }

        this.formData.login = loginInput.value.trim();
        this.formData.password = passwordInput.value;

        if (!this.formData.login || !this.formData.password) {
            this.showErrorToast('Заполните все поля');
            return;
        }

        this.isLoading = true;
        this.error = null;
        this.showError = false;

        if (button) {
            button.disabled = true;
            button.textContent = 'Вход...';
        }

        try {
            store.setLoading(true);

            const response = await authService.login({
                login: this.formData.login,
                password: this.formData.password
            });

            const user = await authService.getCurrentUser();

            store.setUser(user);
            store.setToken(response.access_token);

            router.navigate('/analytics');

        } catch (error: any) {
            console.error('❌ Login error:', error);
            this.showErrorToast(error.message || 'Неверный логин или пароль');

            this.isLoading = false;
            if (button) {
                button.disabled = false;
                button.textContent = 'Войти';
            }

        } finally {
            this.isLoading = false;
            store.setLoading(false);
        }
    }

    private attachEvents(): void {
        setTimeout(() => {
            const button = document.getElementById('login-button');
            const closeError = document.getElementById('close-error');
            const themeToggle = document.getElementById('theme-toggle');

            if (button) {
                button.addEventListener('click', (e) => this.handleLogin(e));
            }

            if (closeError) {
                closeError.addEventListener('click', () => {
                    this.showError = false;
                    this.error = null;
                    this.render();
                });
            }

            if (themeToggle) {
                themeToggle.addEventListener('click', () => this.toggleTheme());
            }

            const handleKeyPress = (e: KeyboardEvent) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.handleLogin();
                }
            };

            const loginInput = document.getElementById('login');
            const passwordInput = document.getElementById('password');

            loginInput?.addEventListener('keypress', handleKeyPress);
            passwordInput?.addEventListener('keypress', handleKeyPress);
        }, 0);
    }

    render(): void {
        if (!this.container) {
            return;
        }
      document.body.classList.add('no-navbar');

        this.container.innerHTML = this.renderTemplate();
        this.attachEvents();
    }

    destroy(): void {
        console.log('🧹 Destroying LoginView');
        document.body.classList.remove('no-navbar');
    }
}