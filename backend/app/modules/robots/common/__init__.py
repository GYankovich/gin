# app/modules/robots/common/__init__.py
from .logger import get_logger, close_logger, RobotLogger
from .utils import (
    safe_int, safe_str, safe_float, safe_bool,
    safe_datetime_now, safe_json_dumps, safe_json_loads,
    mask_token, format_duration,
    parse_account_type, parse_account_status,
    parse_money_value, parse_quotation,
    Singleton
)

__all__ = [
    'get_logger',
    'close_logger',
    'RobotLogger',
    'safe_int',
    'safe_str',
    'safe_float',
    'safe_bool',
    'safe_datetime_now',
    'safe_json_dumps',
    'safe_json_loads',
    'mask_token',
    'format_duration',
    'parse_account_type',
    'parse_account_status',
    'parse_money_value',
    'parse_quotation',
    'Singleton'
]