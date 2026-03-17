import { LoginView } from './modules/auth/views/LoginView';
import { AnalyticsView } from './modules/analytics/views/AnalyticsView';
import { SettingsView } from './modules/settings/views/SettingsView';
import { TradingView } from './modules/trading/views/TradingView';
import { TradingCreateView } from './modules/trading/views/TradingCreateView';
import { Navbar } from './shared/components/Navbar';
import { router } from './core/router';
import { store } from './core/store';
import { themeManager } from './core/theme';
import { initAuthModule } from './modules/auth';
import { initRobotsModule } from './modules/robots';

// Импортируем представления для роботов
import { RobotsPage } from './modules/robots/pages/RobotsPage';
import { RobotDetailPage } from './modules/robots/pages/RobotDetailPage';
import { CreateRobotPage } from './modules/robots/pages/CreateRobotPage';


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
    const app = document.getElementById('app');
    if (app) {
        app.innerHTML = ''; // Очищаем полностью
        const loginView = new LoginView(app);
        loginView.render();
        navbar = null;
    }
});

router.register('/analytics', () => {
    initAppLayout();
    if (navbar) navbar.render();
    const analyticsView = new AnalyticsView();
    renderContent(analyticsView);
});

router.register('/settings', async () => {
    initAppLayout();
    if (navbar) navbar.render();
    const settingsView = new SettingsView(contentContainer);
    await settingsView.loadData();
});

// Маршруты для роботов
router.register('/robots', () => {
    initAppLayout();
    if (navbar) navbar.render();
    const robotsPage = new RobotsPage();
    renderContent(robotsPage);
});

router.register('/robots/create', () => {
    initAppLayout();
    if (navbar) navbar.render();
    const createPage = new CreateRobotPage();
    renderContent(createPage);
});

router.register('/robots/:id', (params?: { id?: string }) => {
    const robotId = params?.id ? parseInt(params.id) : 0;
    if (!robotId) {
        router.navigate('/robots');
        return;
    }

    initAppLayout();
    if (navbar) navbar.render();
    const detailPage = new RobotDetailPage(robotId);
    renderContent(detailPage);
});

router.register('/robots/:id/edit', (params?: { id?: string }) => {
    const robotId = params?.id ? parseInt(params.id) : 0;
    if (!robotId) {
        router.navigate('/robots');
        return;
    }

    initAppLayout();
    if (navbar) navbar.render();
    // TODO: Создать страницу редактирования
    router.navigate(`/robots/${robotId}`);
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