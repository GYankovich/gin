"""
Единая настройка логирования приложения и роботов.

Ротация всех файлов — каждые 4 часа (0-4, 4-8, 8-12, 12-16, 16-20, 20-24).
Имена файлов: rest_2026-04-01_08-12.log, app_2026-04-01_08-12.log, и т.д.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import BaseRotatingHandler
from typing import Optional

ROTATION_HOURS = 4


class _Timed4hHandler(BaseRotatingHandler):
    """
    Файловый хендлер с ротацией каждые 4 часа.

    Имя файла: <base>_YYYY-MM-DD_HH1-HH2.log
    Пример:    logs/rest_2026-04-01_08-12.log
    """

    def __init__(self, log_dir: Path, base_name: str, level: int,
                 formatter: logging.Formatter, backup_count: int = 30):
        self._log_dir = log_dir
        self._base_name = base_name
        self._backup_count = backup_count
        self._current_slot = self._slot_now()
        file_path = self._make_path(self._current_slot)
        super().__init__(str(file_path), mode="a", encoding="utf-8")
        self.setLevel(level)
        self.setFormatter(formatter)

    # --- rotation logic ---

    @staticmethod
    def _slot_now() -> tuple:
        """Возвращает (date_str, hour_start, hour_end) текущего 4-часового слота."""
        now = datetime.now()
        slot_start = (now.hour // ROTATION_HOURS) * ROTATION_HOURS
        slot_end = slot_start + ROTATION_HOURS
        return now.strftime("%Y-%m-%d"), slot_start, slot_end

    def _make_path(self, slot: tuple) -> Path:
        date_str, h_start, h_end = slot
        return self._log_dir / f"{self._base_name}_{date_str}_{h_start:02d}-{h_end:02d}.log"

    def shouldRollover(self, record: logging.LogRecord) -> int:
        return 1 if self._slot_now() != self._current_slot else 0

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]
        self._current_slot = self._slot_now()
        self.baseFilename = str(self._make_path(self._current_slot))
        self.stream = self._open()
        self._cleanup_old()

    def _cleanup_old(self) -> None:
        prefix = f"{self._base_name}_"
        files = sorted(
            [f for f in self._log_dir.iterdir() if f.name.startswith(prefix) and f.suffix == ".log"],
            key=lambda p: p.stat().st_mtime,
        )
        while len(files) > self._backup_count:
            oldest = files.pop(0)
            try:
                oldest.unlink()
            except OSError:
                pass


class RobotLogFormatter(logging.Formatter):
    """Форматтер логов роботов: [ts] [ROBOT_id] [LEVEL] message"""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "robot_id"):
            record.robot_id = "-"
        return super().format(record)


def _clear_existing_handlers() -> None:
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)
    for name in list(logging.root.manager.loggerDict):
        logger = logging.getLogger(name)
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)


def _h(log_dir: Path, base_name: str, level: int, formatter: logging.Formatter) -> _Timed4hHandler:
    """Shortcut: создаёт 4-часовой ротирующий хендлер."""
    return _Timed4hHandler(log_dir, base_name, level, formatter)


def setup_logging() -> None:
    """Настраивает единое логирование для приложения и роботов."""

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    app_fmt = logging.Formatter(
        "[%(asctime)s.%(msecs)03d] [APP] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    robot_fmt = RobotLogFormatter(
        "[%(asctime)s.%(msecs)03d] [ROBOT_%(robot_id)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    rest_fmt = logging.Formatter(
        "[%(asctime)s.%(msecs)03d] [REST] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _clear_existing_handlers()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(app_fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console_handler)
    root.addHandler(_h(log_dir, "app", logging.DEBUG, app_fmt))
    root.addHandler(_h(log_dir, "errors", logging.ERROR, app_fmt))

    # REST API logger
    rest_logger = logging.getLogger("rest")
    rest_logger.setLevel(logging.DEBUG)
    rest_logger.propagate = False
    rest_logger.addHandler(_h(log_dir, "rest", logging.DEBUG, rest_fmt))

    # Portfolio updater
    portfolio_logger = logging.getLogger("robots.portfolio_updater")
    portfolio_logger.setLevel(logging.DEBUG)
    portfolio_logger.propagate = False
    portfolio_logger.addHandler(_h(log_dir, "portfolio_updater", logging.DEBUG, robot_fmt))

    # Trading robots
    trading_logger = logging.getLogger("robots.trading")
    trading_logger.setLevel(logging.DEBUG)
    trading_logger.propagate = False
    trading_logger.addHandler(_h(log_dir, "trading_robot", logging.DEBUG, robot_fmt))

    logging.getLogger("sqlalchemy.engine").setLevel(logging.DEBUG)
    logging.info("Logging configured (4h rotation)")


def get_logger(name: str) -> logging.Logger:
    """Возвращает общий логгер по имени."""
    logger = logging.getLogger(name)
    if name.startswith("robots.portfolio_updater") or name.startswith("robots.trading"):
        logger.propagate = False
    else:
        logger.propagate = True
    return logger


def get_rest_logger() -> logging.Logger:
    """Возвращает логгер для REST-эндпоинтов."""
    return logging.getLogger("rest")


def get_robot_logger(base_name: str, robot_id: Optional[int] = None) -> logging.LoggerAdapter:
    """Возвращает логгер-адаптер робота с robot_id."""
    return logging.LoggerAdapter(get_logger(base_name), {"robot_id": robot_id if robot_id is not None else "-"})


def register_trading_session_logger(robot_id: int) -> logging.LoggerAdapter:
    """
    Возвращает логгер trading-сессии с отдельным файловым хендлером.
    """
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = RobotLogFormatter(
        "[%(asctime)s.%(msecs)03d] [ROBOT_%(robot_id)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger_name = f"robots.trading.session.{robot_id}"
    session_logger = logging.getLogger(logger_name)
    session_logger.setLevel(logging.DEBUG)
    session_logger.propagate = False
    log_file_base = f"trading_session_{robot_id}"
    if not any(isinstance(h, _Timed4hHandler) and h._base_name == log_file_base for h in session_logger.handlers):
        session_logger.addHandler(_Timed4hHandler(log_dir, log_file_base, logging.DEBUG, formatter))
    return logging.LoggerAdapter(session_logger, {"robot_id": robot_id})