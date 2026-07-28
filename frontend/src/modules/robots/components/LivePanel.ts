///@EPIC Frontend.ITEM Modules.TOPIC FrontendSrcModulesRobotsComponentsLivepanel [1]
///@ Исходный модуль `frontend/src/modules/robots/components/LivePanel.ts` — автоматическая разметка для Obsidian Source Scanner.

import { showToast } from '../../../shared/components/Toast';

interface PriceUpdate {
    figi: string;
    price: number;
    time: string;
    direction?: 'up' | 'down';
}

interface SignalEvent {
    robot_id: number;
    figi: string;
    signal_type: string;
    price: number;
    time: string;
}

interface OrderEvent {
    robot_id: number;
    figi: string;
    side: string;
    quantity: number;
    price: number;
    status: string;
    time: string;
}

export class LivePanel {
    private container: HTMLElement;
    private ws: WebSocket | null = null;
    private prices: Map<string, PriceUpdate> = new Map();
    private signals: SignalEvent[] = [];
    private orders: OrderEvent[] = [];
    private connected = false;
    private reconnectTimer: number | null = null;
    private reconnectAttempt = 0;
    private maxSignals = 50;
    private maxOrders = 50;

    constructor(container: HTMLElement) {
        this.container = container;
    }

    connect(wsUrl?: string): void {
        const token = localStorage.getItem('auth_token');
        if (!token) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Prefer explicit URL; in DEV default to WS gateway :8001 (same as LivePage).
        const url = wsUrl || `${protocol}//${window.location.host}/ws/live?token=${encodeURIComponent(token)}`;

        try {
            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                this.connected = true;
                this.reconnectAttempt = 0;
                this.render();
            };

            this.ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    this.handleMessage(msg);
                } catch {}
            };

            this.ws.onclose = () => {
                this.connected = false;
                this.render();
                this.scheduleReconnect();
            };

            this.ws.onerror = () => {
                this.connected = false;
            };
        } catch {
            this.scheduleReconnect();
        }
    }

    disconnect(): void {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.connected = false;
    }

    private scheduleReconnect(): void {
        if (this.reconnectTimer) return;
        this.reconnectAttempt++;
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempt - 1), 30000);
        this.reconnectTimer = window.setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, delay);
    }

    private handleMessage(msg: any): void {
        switch (msg.type) {
            case 'price': {
                const prev = this.prices.get(msg.figi);
                const direction = prev ? (msg.price > prev.price ? 'up' : msg.price < prev.price ? 'down' : prev.direction) : undefined;
                this.prices.set(msg.figi, { figi: msg.figi, price: msg.price, time: msg.time, direction });
                this.updatePriceRow(msg.figi);
                break;
            }
            case 'signal': {
                this.signals.unshift(msg as SignalEvent);
                if (this.signals.length > this.maxSignals) this.signals.pop();
                this.renderSignalsFeed();
                break;
            }
            case 'order': {
                this.orders.unshift(msg as OrderEvent);
                if (this.orders.length > this.maxOrders) this.orders.pop();
                this.renderOrdersFeed();
                if (msg.status === 'filled') {
                    showToast({ message: `Заявка исполнена: ${msg.side} ${msg.figi}`, type: 'success' });
                }
                break;
            }
        }
    }

    /* ---- rendering ---- */

    render(): void {
        this.container.innerHTML = `
        <div class="live-panel">
            <div class="live-header">
                <h3 class="live-title">Live</h3>
                <span class="live-status ${this.connected ? 'live-connected' : 'live-disconnected'}">
                    ${this.connected ? 'Online' : 'Offline'}
                </span>
            </div>

            <div class="live-section">
                <h4 class="live-section-title">Цены</h4>
                <div class="live-prices" id="live-prices">
                    ${this.prices.size === 0
                        ? '<p class="live-empty">Ожидание данных...</p>'
                        : this.renderPricesTable()
                    }
                </div>
            </div>

            <div class="live-section">
                <h4 class="live-section-title">Сигналы</h4>
                <div class="live-feed" id="live-signals">
                    ${this.signals.length === 0
                        ? '<p class="live-empty">Нет сигналов</p>'
                        : this.renderSignals()
                    }
                </div>
            </div>

            <div class="live-section">
                <h4 class="live-section-title">Заявки</h4>
                <div class="live-feed" id="live-orders">
                    ${this.orders.length === 0
                        ? '<p class="live-empty">Нет заявок</p>'
                        : this.renderOrders()
                    }
                </div>
            </div>
        </div>`;
    }

    private renderPricesTable(): string {
        const rows = Array.from(this.prices.values()).map(p => `
            <tr class="live-price-row" id="price-${p.figi}">
                <td class="text-mono" style="font-size:0.8rem">${p.figi.slice(0, 12)}</td>
                <td class="text-mono ${p.direction === 'up' ? 'text-success' : p.direction === 'down' ? 'text-danger' : ''}" style="text-align:right">
                    ${p.price.toFixed(2)}
                </td>
                <td style="font-size:0.7rem;color:var(--text-muted);text-align:right">${this.fmtTime(p.time)}</td>
            </tr>
        `).join('');
        return `<table class="live-table"><tbody>${rows}</tbody></table>`;
    }

    private updatePriceRow(figi: string): void {
        const p = this.prices.get(figi);
        if (!p) return;
        const el = document.getElementById(`price-${figi}`);
        if (el) {
            const cells = el.querySelectorAll('td');
            if (cells[1]) {
                cells[1].className = `text-mono ${p.direction === 'up' ? 'text-success' : p.direction === 'down' ? 'text-danger' : ''}`;
                cells[1].textContent = p.price.toFixed(2);
                el.classList.add('live-flash');
                setTimeout(() => el.classList.remove('live-flash'), 400);
            }
            if (cells[2]) cells[2].textContent = this.fmtTime(p.time);
        } else {
            const pricesEl = document.getElementById('live-prices');
            if (pricesEl) pricesEl.innerHTML = this.renderPricesTable();
        }
    }

    private renderSignals(): string {
        return this.signals.slice(0, 10).map(s => `
            <div class="live-feed-item">
                <span class="badge ${s.signal_type === 'buy' ? 'badge-success' : 'badge-danger'}">${s.signal_type.toUpperCase()}</span>
                <span class="text-mono" style="font-size:0.8rem">${s.figi.slice(0, 12)}</span>
                <span class="text-mono" style="margin-left:auto">${s.price.toFixed(2)}</span>
                <span style="font-size:0.7rem;color:var(--text-muted)">${this.fmtTime(s.time)}</span>
            </div>
        `).join('');
    }

    private renderSignalsFeed(): void {
        const el = document.getElementById('live-signals');
        if (el) el.innerHTML = this.signals.length ? this.renderSignals() : '<p class="live-empty">Нет сигналов</p>';
    }

    private renderOrders(): string {
        return this.orders.slice(0, 10).map(o => `
            <div class="live-feed-item">
                <span class="badge ${o.side === 'buy' ? 'badge-success' : 'badge-danger'}">${o.side.toUpperCase()}</span>
                <span class="text-mono" style="font-size:0.8rem">${o.figi.slice(0, 12)}</span>
                <span style="font-size:0.75rem;color:var(--text-muted)">${o.quantity}x${o.price.toFixed(2)}</span>
                <span class="badge ${o.status === 'filled' ? 'badge-success' : o.status === 'rejected' ? 'badge-danger' : 'badge-warning'}" style="margin-left:auto">
                    ${o.status}
                </span>
                <span style="font-size:0.7rem;color:var(--text-muted)">${this.fmtTime(o.time)}</span>
            </div>
        `).join('');
    }

    private renderOrdersFeed(): void {
        const el = document.getElementById('live-orders');
        if (el) el.innerHTML = this.orders.length ? this.renderOrders() : '<p class="live-empty">Нет заявок</p>';
    }

    private fmtTime(iso: string): string {
        try {
            const d = new Date(iso);
            return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch {
            return iso;
        }
    }

    destroy(): void {
        this.disconnect();
    }
}
