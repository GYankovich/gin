///@EPIC Frontend.ITEM Core.TOPIC FrontendSrcCoreRouter [1]
///@ Исходный модуль `frontend/src/core/router.ts` — автоматическая разметка для Obsidian Source Scanner.

type RouteHandler = () => void;

class Router {
    private routes: Map<string, RouteHandler> = new Map();
    private currentPath: string = window.location.pathname;
    private wildcardHandler: RouteHandler | null = null;

    constructor() {
        window.addEventListener('popstate', () => {
            this.handleRoute(window.location.pathname);
        });
    }

    register(path: string, handler: RouteHandler): void {
        if (path === '*') {
            this.wildcardHandler = handler;
        } else {
            this.routes.set(path, handler);
        }
    }

    navigate(path: string): void {
        window.history.pushState({}, '', path);
        this.handleRoute(path);
    }

    private handleRoute(path: string): void {
        const handler = this.routes.get(path);

        if (handler) {
            this.currentPath = path;
            handler();
        } else if (this.wildcardHandler) {
            this.currentPath = path;
            this.wildcardHandler();
        } else {
            console.warn(`No handler for path: ${path}`);
        }
    }

    start(): void {
        this.handleRoute(this.currentPath);
    }
}

export const router = new Router();