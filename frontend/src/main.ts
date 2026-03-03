import { LoginView } from './modules/auth/views/LoginView';
import { AnalyticsView } from './modules/analytics/views/AnalyticsView';
import { SettingsView } from './modules/settings/views/SettingsView';
import { Navbar } from './shared/components/Navbar';
import { router } from './core/router';
import { store } from './core/store';
import { themeManager } from './core/theme';

console.log('🚀 GAnal Frontend starting...');

// Глобальный экземпляр навбара
let navbar: Navbar | null = null;
let navbarContainer: HTMLElement;
let contentContainer: HTMLElement;

// Создаем базовую структуру один раз
function initAppLayout(): void {
    const app = document.getElementById('app');
    if (!app) return;

    // Создаем структуру только если её ещё нет
    if (!document.getElementById('navbar-container')) {
        app.innerHTML = `
      <div class="app-layout">
        <div id="navbar-container" class="navbar-container"></div>
        <div id="content-container" class="content-container"></div>
      </div>
    `;
    }

    navbarContainer = document.getElementById('navbar-container')!;
    contentContainer = document.getElementById('content-container')!;

    // Создаем навбар один раз
    if (!navbar) {
        navbar = new Navbar(navbarContainer);
    }
}

// Функция для рендеринга контента
function renderContent(view: any): void {
    if (!contentContainer) {
        initAppLayout();
    }

    // Очищаем контейнер контента
    contentContainer.innerHTML = '';

    // Рендерим новое представление
    if (view && typeof view.render === 'function') {
        view.render(contentContainer);
    }
}

// Регистрируем маршруты
router.register('/login', () => {
    // Для логина не показываем навбар
    const app = document.getElementById('app');
    if (app) {
        app.innerHTML = ''; // Очищаем полностью
        const loginView = new LoginView(app);
        loginView.render();

        // Сбрасываем навбар при выходе на логин
        navbar = null;
    }
});

router.register('/analytics', () => {
    initAppLayout();
    if (navbar) {
        navbar.render(); // Перерендериваем навбар (обновляем активную ссылку)
    }
    const analyticsView = new AnalyticsView();
    renderContent(analyticsView);
});

router.register('/settings', async () => {
    initAppLayout();
    if (navbar) {
        navbar.render(); // Перерендериваем навбар (обновляем активную ссылку)
    }
    const settingsView = new SettingsView(contentContainer);
    await settingsView.loadData();
    // Не вызываем renderContent, так как SettingsView сам рендерит себя в переданный контейнер
});

router.register('/', () => {
    if (store.getState().token) {
        router.navigate('/analytics');
    } else {
        router.navigate('/login');
    }
});

// Запускаем роутер
router.start();

// Применяем сохраненную тему при загрузке
document.documentElement.setAttribute('data-theme', themeManager.getTheme());

// Первоначальная навигация
setTimeout(() => {
    const token = store.getState().token;
    const currentPath = window.location.pathname;

    console.log('📍 Current path:', currentPath);
    console.log('🔑 Token:', token ? 'present' : 'absent');

    if (currentPath === '/' || currentPath === '/login') {
        if (token) {
            router.navigate('/analytics');
        } else {
            router.navigate('/login');
        }
    }
}, 100);