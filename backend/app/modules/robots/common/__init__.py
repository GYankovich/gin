#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsCommonInit [1]
#/// Исходный модуль `backend/app/modules/robots/common/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/robots/common/__init__.py
# from .logger import get_logger, close_logger, RobotLogger  # ← ЗАКОММЕНТИРОВАТЬ ИЛИ УДАЛИТЬ
from .utils import (
    safe_int, safe_str, safe_float, safe_bool,
    safe_datetime_now, safe_json_dumps, safe_json_loads,
    mask_token, format_duration,
    Singleton
)
from .mixins import TradePersistenceMixin, PriceParsingMixin

__all__ = [
    # Logger - временно убрали, используем app.core.logging_config
    # 'get_logger',
    # 'close_logger',
    # 'RobotLogger',
    # Utils
    'safe_int',
    'safe_str',
    'safe_float',
    'safe_bool',
    'safe_datetime_now',
    'safe_json_dumps',
    'safe_json_loads',
    'mask_token',
    'format_duration',
    'Singleton',
    # Mixins
    'TradePersistenceMixin',
    'PriceParsingMixin'
]