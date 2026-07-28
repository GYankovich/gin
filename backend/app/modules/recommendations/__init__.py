"""Рекомендации по стратегии и настройкам на основе бэктестов и лайва."""

__all__ = ["recommendations_service"]

# Не импортируем service здесь: robots.service тянет backtest_analytics из этого пакета,
# а service импортирует robot_service — получится circular import при старте приложения.
