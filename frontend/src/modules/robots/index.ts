import { router } from '../../core/router';
import { RobotsView } from './views/RobotsView';
import { RobotCreateView } from './views/RobotCreateView';
import { RobotDetailView } from './views/RobotDetailView';
import { RobotEditView } from './views/RobotEditView';

export function initRobotsModule() {
    // Регистрируем маршруты
    router.register('/robots', () => {
        const view = new RobotsView();
        view.render();
    });

    router.register('/robots/create', () => {
        const view = new RobotCreateView();
        view.render();
    });

    router.register('/robots/:id', (params) => {
        const view = new RobotDetailView(parseInt(params.id));
        view.render();
    });

    router.register('/robots/:id/edit', (params) => {
        const view = new RobotEditView(parseInt(params.id));
        view.render();
    });
}

export * from './types';
export { robotService } from './services/robotService';