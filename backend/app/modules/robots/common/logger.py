# app/modules/robots/common/logger.py
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# Настройка директории для логов
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


class RobotLogger:
    """
    Единый логгер для всех роботов с ротацией каждые 4 часа
    """

    _instance = None
    _current_period = None
    _file_handler = None
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._setup_logger()

    def _get_period(self, dt: datetime = None) -> str:
        """Определяет 4-часовой период"""
        if dt is None:
            dt = datetime.now()

        hour = dt.hour
        period_start = (hour // 4) * 4
        period_end = period_start + 4
        date_str = dt.strftime("%Y-%m-%d")
        return f"{date_str}_{period_start:02d}-{period_end:02d}"

    def _get_log_filename(self) -> Path:
        """Генерирует имя файла лога"""
        period = self._get_period()
        return LOG_DIR / f"robots_{period}.log"

    def _setup_logger(self):
        """Настраивает корневой логгер"""
        self._logger = logging.getLogger("robots")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        if self._logger.handlers:
            for handler in self._logger.handlers:
                self._logger.removeHandler(handler)
                handler.close()

        self._rotate_if_needed()

    def _rotate_if_needed(self):
        """Проверяет, нужно ли переключиться на новый файл"""
        now = datetime.now()
        current_period = self._get_period(now)

        if current_period != self._current_period:
            self._current_period = current_period
            log_file = self._get_log_filename()

            if self._file_handler:
                self._logger.removeHandler(self._file_handler)
                self._file_handler.close()

            self._file_handler = logging.FileHandler(
                log_file,
                encoding='utf-8',
                mode='a'
            )

            formatter = logging.Formatter(
                '%(asctime)s.%(msecs)03d | %(levelname)-8s | [%(robot_type)s:%(robot_name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            self._file_handler.setFormatter(formatter)
            self._file_handler.setLevel(logging.DEBUG)

            self._logger.addHandler(self._file_handler)

            # Заголовок нового файла
            self._logger.info("=" * 100, extra={'robot_type': 'SYSTEM', 'robot_name': 'BOOT'})
            self._logger.info(f"НОВЫЙ ПЕРИОД ЛОГИРОВАНИЯ: {now.strftime('%Y-%m-%d %H:%M:%S')}",
                              extra={'robot_type': 'SYSTEM', 'robot_name': 'BOOT'})
            self._logger.info("=" * 100, extra={'robot_type': 'SYSTEM', 'robot_name': 'BOOT'})

    def get_logger(self, robot_type: str, robot_name: str) -> logging.LoggerAdapter:
        """
        Возвращает логгер для конкретного робота
        robot_type: 'portfolio_updater' или 'trading'
        robot_name: уникальное имя (например 'main', 'backup' или ID)
        """
        self._rotate_if_needed()

        class RobotAdapter(logging.LoggerAdapter):
            def process(self, msg, kwargs):
                kwargs['extra'] = {
                    'robot_type': self.extra['robot_type'],
                    'robot_name': self.extra['robot_name']
                }
                return msg, kwargs

        return RobotAdapter(self._logger, {'robot_type': robot_type, 'robot_name': robot_name})

    def close(self):
        """Закрывает логгер"""
        if self._file_handler:
            self._logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None


# Глобальный экземпляр
_robot_logger = RobotLogger()


def get_logger(robot_type: str, robot_name: str) -> logging.LoggerAdapter:
    """Получает логгер для робота"""
    return _robot_logger.get_logger(robot_type, robot_name)


def close_logger():
    """Закрывает логгер"""
    _robot_logger.close()