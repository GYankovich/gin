#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsCommonLoggingFileLogger [1]
#/// Исходный модуль `backend/app/modules/robots/common/logging/file_logger.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/robots/common/logging/file_logger.py

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler


class RobotFileLogger:
    """Единый файловый логгер для всех роботов"""

    _instance = None
    _loggers: Dict[str, logging.Logger] = {}
    _system_logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._log_dir = Path("logs/robots")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._setup_root_logger()
        self._setup_system_logger()

    def _setup_root_logger(self):
        """Настраивает корневой логгер для всех роботов"""
        self._root_logger = logging.getLogger("robots")
        self._root_logger.setLevel(logging.DEBUG)
        self._root_logger.propagate = False

        if self._root_logger.handlers:
            for handler in self._root_logger.handlers:
                handler.close()
                self._root_logger.removeHandler(handler)

        common_handler = RotatingFileHandler(
            self._log_dir / "robots_common.log",
            maxBytes=10_485_760,
            backupCount=10,
            encoding='utf-8'
        )
        common_handler.setLevel(logging.DEBUG)
        common_handler.setFormatter(self._get_formatter())
        self._root_logger.addHandler(common_handler)

    def _setup_system_logger(self):
        """Настраивает системный логгер (без exec_id)"""
        self._system_logger = logging.getLogger("robots.system")
        self._system_logger.setLevel(logging.INFO)
        self._system_logger.propagate = False

        # Очищаем существующие хендлеры
        if self._system_logger.handlers:
            for handler in self._system_logger.handlers:
                handler.close()
                self._system_logger.removeHandler(handler)

        # Системный логгер пишет в отдельный файл
        system_handler = RotatingFileHandler(
            self._log_dir / "system.log",
            maxBytes=10_485_760,
            backupCount=10,
            encoding='utf-8'
        )
        system_handler.setLevel(logging.INFO)
        system_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        )
        self._system_logger.addHandler(system_handler)

        # Добавляем также вывод в консоль для отладки
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s')
        )
        self._system_logger.addHandler(console_handler)

    def _get_formatter(self) -> logging.Formatter:
        """Возвращает форматтер для логов роботов"""
        return logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(levelname)-8s | [%(robot_type)s:%(robot_name)s] | [%(exec_id)s] | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    def get_logger(self, robot_type: str, robot_name: str, execution_id: Optional[int] = None) -> logging.LoggerAdapter:
        """Получает логгер для конкретного робота"""
        logger_key = f"{robot_type}_{robot_name}"

        if logger_key not in self._loggers:
            logger = logging.getLogger(f"robots.{logger_key}")
            logger.setLevel(logging.DEBUG)
            logger.propagate = False

            robot_log_file = self._log_dir / f"{robot_type}_{robot_name}.log"
            file_handler = RotatingFileHandler(
                robot_log_file,
                maxBytes=10_485_760,
                backupCount=20,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(self._get_formatter())
            logger.addHandler(file_handler)

            logger.propagate = True
            self._loggers[logger_key] = logger

        base_logger = self._loggers[logger_key]

        class RobotLoggerAdapter(logging.LoggerAdapter):
            def process(self, msg, kwargs):
                kwargs.setdefault('extra', {})
                kwargs['extra']['robot_type'] = self.extra['robot_type']
                kwargs['extra']['robot_name'] = self.extra['robot_name']
                kwargs['extra']['exec_id'] = self.extra.get('exec_id', '')
                return msg, kwargs

        return RobotLoggerAdapter(
            base_logger,
            {
                'robot_type': robot_type,
                'robot_name': robot_name,
                'exec_id': str(execution_id) if execution_id else ''
            }
        )

    def get_system_logger(self) -> logging.Logger:
        """Возвращает системный логгер (без привязки к роботу)"""
        return self._system_logger

    def set_execution_id(self, adapter: logging.LoggerAdapter, execution_id: int):
        """Обновляет execution_id в адаптере"""
        if hasattr(adapter, 'extra'):
            adapter.extra['exec_id'] = str(execution_id)

    def close(self):
        """Закрывает все логгеры"""
        for logger in self._loggers.values():
            for handler in logger.handlers:
                handler.close()
        self._loggers.clear()

        if self._system_logger:
            for handler in self._system_logger.handlers:
                handler.close()

        for handler in self._root_logger.handlers:
            handler.close()
        self._root_logger.handlers.clear()


# Глобальный экземпляр
_robot_file_logger = RobotFileLogger()


def get_file_logger(
        robot_type: str,
        robot_name: str,
        execution_id: Optional[int] = None
) -> logging.LoggerAdapter:
    """Получает файловый логгер для робота"""
    return _robot_file_logger.get_logger(robot_type, robot_name, execution_id)


def get_system_logger() -> logging.Logger:
    """Получает системный логгер (без exec_id)"""
    return _robot_file_logger.get_system_logger()


def set_execution_id(adapter: logging.LoggerAdapter, execution_id: int):
    """Обновляет execution_id в логгере"""
    _robot_file_logger.set_execution_id(adapter, execution_id)


def close_file_loggers():
    """Закрывает все файловые логгеры"""
    _robot_file_logger.close()