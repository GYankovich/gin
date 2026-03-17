// frontend/src/modules/robots/index.ts

// Экспортируем сервис
export { robotService } from './services/robotService';

// Экспортируем типы
export * from './types';

// Экспортируем компоненты
export { RobotCard } from './components/RobotCard';
export { RobotForm } from './components/RobotForm';
export { RobotList } from './components/RobotList';
export { StrategyConfig } from './components/StrategyConfig';

// Экспортируем страницы
export { RobotsPage } from './pages/RobotsPage';
export { RobotDetailPage } from './pages/RobotDetailPage';
export { CreateRobotPage } from './pages/CreateRobotPage';