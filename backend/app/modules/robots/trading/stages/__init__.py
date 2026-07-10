#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStagesInit [1]
#/// Исходный модуль `backend/app/modules/robots/trading/stages/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

from .stage1_collect import Stage1Collect
from .stage2_websocket import Stage2WebSocket
from .stage3_portfolio import Stage3Portfolio
from .stage4_positions import Stage4Positions
from .stage5_signals import Stage5Signals
from .stage6_orders import Stage6Orders

__all__ = [
    'Stage1Collect',
    'Stage2WebSocket',
    'Stage3Portfolio',
    'Stage4Positions',
    'Stage5Signals',
    'Stage6Orders'
]