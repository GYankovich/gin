import { store } from '../../core/store';
import { router } from '../../core/router';
import { themeManager, Theme } from '../../core/theme';

export class Navbar {
    private container: HTMLElement;
    private dropdownOpen: boolean = false;
    private mobileMenuOpen: boolean = false;
    private currentTheme: Theme;
    private isMobile: boolean = window.innerWidth <= 768;
    private boundHandleDocumentClick: (e: MouseEvent) => void;

    constructor(container: HTMLElement) {
        this.container = container;
        this.currentTheme = themeManager.getTheme();

        // Привязываем обработчик к экземпляру класса
        this.boundHandleDocumentClick = this.handleDocumentClick.bind(this);

        window.addEventListener('resize', () => {
            this.isMobile = window.innerWidth <= 768;
            if (!this.isMobile) {
                this.mobileMenuOpen = false;
            }
            this.render();
        });

        themeManager.subscribe((theme) => {
            this.currentTheme = theme;
            this.render();
        });
    }

    private getInitials(): string {
        const user = store.getState().user;
        if (!user) return 'U';
        return user.login.slice(0, 2).toUpperCase() || 'U';
    }

    private getActiveClass(path: string): string {
        return window.location.pathname === path ? 'nav-link-active' : '';
    }

    private renderTemplate(): string {
        const initials = this.getInitials();
        const isDark = this.currentTheme === 'dark';

        return `
      <div class="navbar">
        <div class="navbar-left">
          ${this.isMobile ? `
            <button class="mobile-menu-button" id="mobile-menu-toggle">
              <span class="menu-icon">${this.mobileMenuOpen ? '✕' : '☰'}</span>
            </button>
          ` : ''}
          
          <div class="nav-items">
            <div class="logo-minimal" id="logo-home">
              <span class="logo-g">G</span>
              <span class="logo-in">IN</span>
            </div>
            
            ${!this.isMobile ? `
              <button class="nav-link ${this.getActiveClass('/analytics')}" id="nav-analytics">
                Аналитика
              </button>
              <button class="nav-link ${this.getActiveClass('/robots')}" id="nav-robots">
                Роботы
              </button>
            ` : ''}
          </div>
        </div>

        <div class="navbar-right">
          <div class="avatar-wrapper" id="avatar-wrapper">
            <div class="avatar" id="avatar">${initials}</div>
          </div>
          
          ${this.dropdownOpen ? `
            <div class="dropdown" id="dropdown-menu">
              <div class="dropdown-item" id="dropdown-settings">
                <span class="dropdown-icon">⚙️</span>
                Настройки
              </div>
              <div class="dropdown-item" id="dropdown-robots">
                <span class="dropdown-icon">🤖</span>
                Роботы
              </div>
              <div class="dropdown-item" id="dropdown-theme">
                <span class="dropdown-icon">${isDark ? '☀️' : '🌙'}</span>
                ${isDark ? 'Светлая тема' : 'Темная тема'}
              </div>
              <div class="dropdown-divider"></div>
              <div class="dropdown-item" id="dropdown-logout">
                <span class="dropdown-icon">🚪</span>
                Выход
              </div>
            </div>
          ` : ''}
        </div>
      </div>

      ${this.isMobile && this.mobileMenuOpen ? `
        <div class="mobile-menu" id="mobile-menu">
          <div class="mobile-menu-header">
            <div class="logo-minimal">
              <span class="logo-g">G</span>
              <span class="logo-in">IN</span>
            </div>
            <button class="mobile-menu-close" id="mobile-menu-close">✕</button>
          </div>
          <div class="mobile-menu-items">
            <button class="mobile-menu-item ${this.getActiveClass('/analytics')}" id="mobile-analytics">
              <span class="menu-item-icon">📊</span>
              Аналитика
            </button>
            <button class="mobile-menu-item ${this.getActiveClass('/robots')}" id="mobile-robots">
              <span class="menu-item-icon">🤖</span>
              Роботы
            </button>
          </div>
        </div>
      ` : ''}
    `;
    }

    private handleAvatarClick = (e: MouseEvent): void => {
        e.stopPropagation();
        e.preventDefault();
        console.log('👤 Avatar clicked, current state:', this.dropdownOpen);
        this.dropdownOpen = !this.dropdownOpen;
        this.render();
    }

    private handleDocumentClick = (e: MouseEvent): void => {
        const dropdown = document.getElementById('dropdown-menu');
        const avatarWrapper = document.getElementById('avatar-wrapper');

        if (this.dropdownOpen) {
            // Если клик был по дропдауну или аватару - ничего не делаем
            if (dropdown?.contains(e.target as Node) || avatarWrapper?.contains(e.target as Node)) {
                return;
            }

            // Иначе закрываем дропдаун
            console.log('📝 Click outside, closing dropdown');
            this.dropdownOpen = false;
            this.render();
        }
    }

    private toggleMobileMenu(): void {
        this.mobileMenuOpen = !this.mobileMenuOpen;
        this.render();
    }

    private closeMobileMenu(): void {
        this.mobileMenuOpen = false;
        this.render();
    }

    private toggleTheme(): void {
        themeManager.toggleTheme();
        this.dropdownOpen = false;
        this.closeMobileMenu();
    }

    private async handleLogout(): Promise<void> {
        try {
            const { authService } = await import('../../modules/auth/services/authService');
            await authService.logout();
            store.setUser(null);
            store.setToken(null);
            router.navigate('/login');
        } catch (error) {
            console.error('Logout error:', error);
        }
    }

    private removeGlobalListeners(): void {
        document.removeEventListener('click', this.boundHandleDocumentClick);
    }

    private addGlobalListeners(): void {
        // Удаляем старый обработчик перед добавлением нового
        this.removeGlobalListeners();
        document.addEventListener('click', this.boundHandleDocumentClick);
    }

    private attachEvents(): void {
        setTimeout(() => {
            // Логотип - переход на главную
            const logo = document.getElementById('logo-home');
            if (logo) {
                const newLogo = logo.cloneNode(true) as HTMLElement;
                logo.parentNode?.replaceChild(newLogo, logo);
                newLogo.addEventListener('click', () => {
                    router.navigate('/analytics');
                });
                newLogo.style.cursor = 'pointer';
            }

            // Аватар
            const avatarWrapper = document.getElementById('avatar-wrapper');
            if (avatarWrapper) {
                const newWrapper = avatarWrapper.cloneNode(true) as HTMLElement;
                avatarWrapper.parentNode?.replaceChild(newWrapper, avatarWrapper);
                newWrapper.addEventListener('click', this.handleAvatarClick);
            }

            // Аналитика (десктоп)
            const analyticsBtn = document.getElementById('nav-analytics');
            if (analyticsBtn) {
                const newBtn = analyticsBtn.cloneNode(true) as HTMLElement;
                analyticsBtn.parentNode?.replaceChild(newBtn, analyticsBtn);
                newBtn.addEventListener('click', () => {
                    router.navigate('/analytics');
                });
            }

            // Роботы (десктоп)
            const robotsBtn = document.getElementById('nav-robots');
            if (robotsBtn) {
                const newBtn = robotsBtn.cloneNode(true) as HTMLElement;
                robotsBtn.parentNode?.replaceChild(newBtn, robotsBtn);
                newBtn.addEventListener('click', () => {
                    router.navigate('/robots');
                });
            }

            // Мобильное меню
            const mobileToggle = document.getElementById('mobile-menu-toggle');
            if (mobileToggle) {
                const newToggle = mobileToggle.cloneNode(true) as HTMLElement;
                mobileToggle.parentNode?.replaceChild(newToggle, mobileToggle);
                newToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.toggleMobileMenu();
                });
            }

            const mobileClose = document.getElementById('mobile-menu-close');
            if (mobileClose) {
                const newClose = mobileClose.cloneNode(true) as HTMLElement;
                mobileClose.parentNode?.replaceChild(newClose, mobileClose);
                newClose.addEventListener('click', () => {
                    this.closeMobileMenu();
                });
            }

            const mobileAnalytics = document.getElementById('mobile-analytics');
            if (mobileAnalytics) {
                const newMobileAnalytics = mobileAnalytics.cloneNode(true) as HTMLElement;
                mobileAnalytics.parentNode?.replaceChild(newMobileAnalytics, mobileAnalytics);
                newMobileAnalytics.addEventListener('click', () => {
                    router.navigate('/analytics');
                    this.closeMobileMenu();
                });
            }

            const mobileRobots = document.getElementById('mobile-robots');
            if (mobileRobots) {
                const newMobileRobots = mobileRobots.cloneNode(true) as HTMLElement;
                mobileRobots.parentNode?.replaceChild(newMobileRobots, mobileRobots);
                newMobileRobots.addEventListener('click', () => {
                    router.navigate('/robots');
                    this.closeMobileMenu();
                });
            }

            // Дропдаун элементы
            const settingsItem = document.getElementById('dropdown-settings');
            if (settingsItem) {
                const newSettings = settingsItem.cloneNode(true) as HTMLElement;
                settingsItem.parentNode?.replaceChild(newSettings, settingsItem);
                newSettings.addEventListener('click', () => {
                    this.dropdownOpen = false;
                    router.navigate('/settings');
                });
            }

            const robotsItem = document.getElementById('dropdown-robots');
            if (robotsItem) {
                const newRobots = robotsItem.cloneNode(true) as HTMLElement;
                robotsItem.parentNode?.replaceChild(newRobots, robotsItem);
                newRobots.addEventListener('click', () => {
                    this.dropdownOpen = false;
                    router.navigate('/robots');
                });
            }

            const themeItem = document.getElementById('dropdown-theme');
            if (themeItem) {
                const newTheme = themeItem.cloneNode(true) as HTMLElement;
                themeItem.parentNode?.replaceChild(newTheme, themeItem);
                newTheme.addEventListener('click', () => {
                    this.toggleTheme();
                });
            }

            const logoutItem = document.getElementById('dropdown-logout');
            if (logoutItem) {
                const newLogout = logoutItem.cloneNode(true) as HTMLElement;
                logoutItem.parentNode?.replaceChild(newLogout, logoutItem);
                newLogout.addEventListener('click', () => {
                    this.handleLogout();
                });
            }

            this.addGlobalListeners();

        }, 0);
    }

    private checkAuth(): void {
        const token = store.getState().token;
        const publicPaths = ['/login'];
        if (!token && !publicPaths.includes(window.location.pathname)) {
            router.navigate('/login');
        }
    }

    render(): void {
        this.checkAuth();

        if (!this.container) {
            console.error('❌ Navbar: container is undefined');
            return;
        }

        // Удаляем глобальные слушатели перед перерисовкой
        this.removeGlobalListeners();

        this.container.innerHTML = this.renderTemplate();
        this.attachEvents();
    }

    // Очищаем слушатели при уничтожении компонента
    destroy(): void {
        this.removeGlobalListeners();
    }
}