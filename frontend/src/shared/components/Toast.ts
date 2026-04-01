type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastOptions {
    message: string;
    type?: ToastType;
    duration?: number;
}

const ICONS: Record<ToastType, string> = {
    success: '\u2713',
    error:   '\u2717',
    warning: '\u26A0',
    info:    '\u2139',
};

let container: HTMLElement | null = null;

function ensureContainer(): HTMLElement {
    if (!container || !document.body.contains(container)) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    return container;
}

export function showToast(opts: ToastOptions): void {
    const { message, type = 'info', duration = 3500 } = opts;
    const root = ensureContainer();

    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.innerHTML = `<span>${ICONS[type]}</span><span>${message}</span>`;
    root.appendChild(el);

    const timerId = setTimeout(() => dismiss(el), duration);
    el.addEventListener('click', () => {
        clearTimeout(timerId);
        dismiss(el);
    });
}

function dismiss(el: HTMLElement): void {
    el.classList.add('toast-out');
    el.addEventListener('animationend', () => el.remove(), { once: true });
}
