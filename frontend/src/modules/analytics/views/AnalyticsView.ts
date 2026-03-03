export class AnalyticsView {
    render(container: HTMLElement): void {
        if (!container) {
            console.error('❌ AnalyticsView: container is undefined');
            return;
        }

        container.innerHTML = `
      <div class="analytics-container">
        <div class="analytics-header">
          <h1 class="analytics-title">Аналитика доходности</h1>
          <p class="analytics-subtitle">Ваши инвестиционные метрики и графики</p>
        </div>

        <div class="metrics-grid">
          <div class="metric-card">
            <div class="metric-icon">💰</div>
            <div class="metric-content">
              <div class="metric-label">Общий доход</div>
              <div class="metric-value">0 ₽</div>
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">📈</div>
            <div class="metric-content">
              <div class="metric-label">Доходность</div>
              <div class="metric-value">0%</div>
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">💼</div>
            <div class="metric-content">
              <div class="metric-label">Портфель</div>
              <div class="metric-value">0 ₽</div>
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">📊</div>
            <div class="metric-content">
              <div class="metric-label">Сделок</div>
              <div class="metric-value">0</div>
            </div>
          </div>
        </div>

        <div class="charts-section">
          <div class="chart-placeholder">
            <div class="chart-icon">📉</div>
            <div class="chart-text">График доходности</div>
            <div class="chart-hint">Подключите T-Invest токен в настройках</div>
          </div>
          <div class="chart-placeholder">
            <div class="chart-icon">🥧</div>
            <div class="chart-text">Структура портфеля</div>
            <div class="chart-hint">Распределение по активам</div>
          </div>
        </div>
      </div>
    `;
    }
}