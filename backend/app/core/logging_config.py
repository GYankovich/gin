"""
Единая настройка логирования приложения и роботов.

Ротация — каждые 4 часа (0-4, 4-8, 8-12, 12-16, 16-20, 20-24).

Layout:
  logs/app/{YYYY-MM-DD}/app/{HH}-{HH}.log
  logs/app/{YYYY-MM-DD}/rest/{HH}-{HH}.log
  logs/app/{YYYY-MM-DD}/errors/{HH}-{HH}.log
  logs/app/{YYYY-MM-DD}/robots/portfolio_updater_robot/id_{id}_{HH}-{HH}.log
  logs/app/{YYYY-MM-DD}/robots/trading_robot/id_{id}_{HH}-{HH}.log
"""
#///EPIC Platform.ITEM Core.TOPIC BackendAppCoreLoggingConfig [1]
#/// Исходный модуль `backend/app/core/logging_config.py` — автоматическая разметка для Obsidian Source Scanner.

import logging
import sys
import io
from datetime import datetime
from pathlib import Path
from logging.handlers import BaseRotatingHandler
from typing import Optional

ROTATION_HOURS = 4

# Корень репозитория (директория `gin`).
# backend/app/core/logging_config.py -> parents[0]=core, [1]=app, [2]=backend, [3]=gin
_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOG_ROOT = _REPO_ROOT / "logs" / "app"
# Совместимость: каталог текущего дня.
_LOG_DIR = _LOG_ROOT / datetime.now().strftime("%Y-%m-%d")

_ROBOT_LOG_FOLDERS = {
    "portfolio_updater": "portfolio_updater_robot",
    "trading": "trading_robot",
}


def _slot_now() -> tuple:
    """(date_str, hour_start, hour_end) текущего 4-часового слота."""
    now = datetime.now()
    slot_start = (now.hour // ROTATION_HOURS) * ROTATION_HOURS
    slot_end = slot_start + ROTATION_HOURS
    return now.strftime("%Y-%m-%d"), slot_start, slot_end


class _ChannelSlotFileHandler(BaseRotatingHandler):
    """
    Канал приложения:
      logs/app/{YYYY-MM-DD}/{channel}/{HH}-{HH}.log
    """

    def __init__(
        self,
        log_root: Path,
        channel: str,
        level: int,
        formatter: logging.Formatter,
        backup_count: int = 60,
    ):
        self._log_root = log_root
        self._channel = str(channel or "app").replace("/", "_")
        self._backup_count = backup_count
        self._current_slot = _slot_now()
        file_path = self._make_path(self._current_slot)
        super().__init__(str(file_path), mode="a", encoding="utf-8")
        self.setLevel(level)
        self.setFormatter(formatter)

    def _make_path(self, slot: tuple) -> Path:
        date_str, h_start, h_end = slot
        day_dir = self._log_root / date_str / self._channel
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"{h_start:02d}-{h_end:02d}.log"

    def shouldRollover(self, record: logging.LogRecord) -> int:
        return 1 if _slot_now() != self._current_slot else 0

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]
        self._current_slot = _slot_now()
        self.baseFilename = str(self._make_path(self._current_slot))
        self.stream = self._open()
        self._cleanup_old()

    def _cleanup_old(self) -> None:
        files: list[Path] = []
        try:
            if not self._log_root.is_dir():
                return
            for day_dir in self._log_root.iterdir():
                channel_dir = day_dir / self._channel
                if not channel_dir.is_dir():
                    continue
                files.extend(f for f in channel_dir.iterdir() if f.suffix == ".log")
        except OSError:
            return
        files = sorted(files, key=lambda p: p.stat().st_mtime)
        while len(files) > self._backup_count:
            oldest = files.pop(0)
            try:
                oldest.unlink()
            except OSError:
                pass


# Backward-compatible alias (tests / old imports).
_Timed4hHandler = _ChannelSlotFileHandler


class RobotLogFormatter(logging.Formatter):
    """Форматтер логов роботов: [ts] [ROBOT_id] [LEVEL] message"""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "robot_id"):
            record.robot_id = "-"
        return super().format(record)


class _RobotSlotFileHandler(BaseRotatingHandler):
    """
    logs/app/{YYYY-MM-DD}/robots/{portfolio_updater_robot}/id_{id}_{HH}-{HH}.log
    """

    def __init__(
        self,
        log_root: Path,
        robot_folder: str,
        robot_id: str,
        level: int,
        formatter: logging.Formatter,
        backup_count: int = 90,
    ):
        self._log_root = log_root
        self._robot_folder = str(robot_folder or "robot").replace("/", "_")
        self._robot_id = str(robot_id or "-").replace("/", "_")
        self._backup_count = backup_count
        self._current_slot = _slot_now()
        file_path = self._make_path(self._current_slot)
        super().__init__(str(file_path), mode="a", encoding="utf-8")
        self.setLevel(level)
        self.setFormatter(formatter)

    def _make_path(self, slot: tuple) -> Path:
        date_str, h_start, h_end = slot
        day_dir = self._log_root / date_str / "robots" / self._robot_folder
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"id_{self._robot_id}_{h_start:02d}-{h_end:02d}.log"

    def shouldRollover(self, record: logging.LogRecord) -> int:
        return 1 if _slot_now() != self._current_slot else 0

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]
        self._current_slot = _slot_now()
        self.baseFilename = str(self._make_path(self._current_slot))
        self.stream = self._open()
        self._cleanup_old()

    def _cleanup_old(self) -> None:
        prefix = f"id_{self._robot_id}_"
        files: list[Path] = []
        try:
            if not self._log_root.is_dir():
                return
            for day_dir in self._log_root.iterdir():
                robot_dir = day_dir / "robots" / self._robot_folder
                if not robot_dir.is_dir():
                    continue
                files.extend(
                    f for f in robot_dir.iterdir() if f.name.startswith(prefix) and f.suffix == ".log"
                )
        except OSError:
            return
        files = sorted(files, key=lambda p: p.stat().st_mtime)
        while len(files) > self._backup_count:
            oldest = files.pop(0)
            try:
                oldest.unlink()
            except OSError:
                pass


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


def _h(log_root: Path, channel: str, level: int, formatter: logging.Formatter) -> _ChannelSlotFileHandler:
    """Shortcut: канал под logs/app/{date}/{channel}/{HH}-{HH}.log."""
    return _ChannelSlotFileHandler(log_root, channel, level, formatter)


def setup_logging() -> None:
    """Настраивает единое логирование для приложения и роботов."""
    global _LOG_DIR
    _LOG_DIR = _LOG_ROOT / datetime.now().strftime("%Y-%m-%d")
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

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

    stream = sys.stdout
    if hasattr(sys.stdout, "buffer"):
        stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    console_handler = logging.StreamHandler(stream)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(app_fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console_handler)
    root.addHandler(_h(_LOG_ROOT, "app", logging.DEBUG, app_fmt))
    root.addHandler(_h(_LOG_ROOT, "errors", logging.ERROR, app_fmt))

    rest_logger = logging.getLogger("rest")
    rest_logger.setLevel(logging.DEBUG)
    rest_logger.propagate = False
    rest_logger.addHandler(_h(_LOG_ROOT, "rest", logging.DEBUG, rest_fmt))

    # Type-level aggregate (без конкретного robot_id) — id_all в той же папке.
    portfolio_logger = logging.getLogger("robots.portfolio_updater")
    portfolio_logger.setLevel(logging.DEBUG)
    portfolio_logger.propagate = False
    portfolio_logger.addHandler(
        _RobotSlotFileHandler(
            _LOG_ROOT,
            "portfolio_updater_robot",
            "all",
            logging.DEBUG,
            robot_fmt,
        )
    )

    trading_logger = logging.getLogger("robots.trading")
    trading_logger.setLevel(logging.DEBUG)
    trading_logger.propagate = False
    trading_logger.addHandler(
        _RobotSlotFileHandler(
            _LOG_ROOT,
            "trading_robot",
            "all",
            logging.DEBUG,
            robot_fmt,
        )
    )

    _sql_engine = logging.getLogger("sqlalchemy.engine")
    _sql_engine.setLevel(logging.WARNING)
    _sql_engine.propagate = False
    logging.info("Logging configured (date/channel folders, 4h slots)")


def get_logger(name: str) -> logging.Logger:
    """Возвращает общий логгер по имени.

    Type-roots ``robots.trading`` / ``robots.portfolio_updater`` имеют свои file handlers
    (id_all) и не должны дублироваться в APP.

    Дочерние логгеры (``robots.trading.scheduler``, ``robots.trading.session``, …)
    обязаны propagate=True, иначе сообщения исчезают: у них нет handlers, а
    propagate=False отрезает путь к type-root.
    """
    logger = logging.getLogger(name)
    if name in ("robots.portfolio_updater", "robots.trading"):
        logger.propagate = False
    else:
        logger.propagate = True
    return logger


def get_rest_logger() -> logging.Logger:
    """Возвращает логгер для REST-эндпоинтов."""
    return logging.getLogger("rest")


def _robot_folder_for(base_name: str) -> str:
    robot_type = str(base_name or "robot").rstrip(".").split(".")[-1] or "robot"
    robot_type = robot_type.replace("/", "_")
    return _ROBOT_LOG_FOLDERS.get(robot_type, f"{robot_type}_robot")


def get_robot_logger(base_name: str, robot_id: Optional[int] = None) -> logging.LoggerAdapter:
    """
    Логгер робота:
      logs/app/{YYYY-MM-DD}/robots/portfolio_updater_robot/id_{id}_{HH}-{HH}.log
    """
    robot_id_val = robot_id if robot_id is not None else "-"
    robot_folder = _robot_folder_for(base_name)
    slug_robot = str(robot_id_val).replace("/", "_")

    logger_name = f"{base_name.replace('.', '_')}.robot.{slug_robot}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = RobotLogFormatter(
        "[%(asctime)s.%(msecs)03d] [ROBOT_%(robot_id)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    has_slot = any(
        isinstance(h, _RobotSlotFileHandler)
        and h._robot_folder == robot_folder
        and h._robot_id == slug_robot
        for h in logger.handlers
    )
    if not has_slot:
        for h in list(logger.handlers):
            h.close()
            logger.removeHandler(h)
        logger.addHandler(
            _RobotSlotFileHandler(_LOG_ROOT, robot_folder, slug_robot, logging.DEBUG, formatter)
        )

    return logging.LoggerAdapter(logger, {"robot_id": robot_id_val})


def register_trading_session_logger(robot_id: int) -> logging.LoggerAdapter:
    """Логгер trading-сессии: тот же layout, что у get_robot_logger(trading)."""
    return get_robot_logger("robots.trading", robot_id)
