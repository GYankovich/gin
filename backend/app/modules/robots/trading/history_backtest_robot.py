"""

History backtest robot — делегат в TradingOrchestrator (mode=BACKTEST).



REST `run_robot_history_backtest`: scoring/candles/persist в service.py;

фаза simulating — только `get_trading_orchestrator().run_backtest_replay`.

"""



from __future__ import annotations



from typing import Any, Awaitable, Callable, Dict, List, Optional



from sqlalchemy.orm import Session



from app.modules.robots.base.base_robot import BaseRobot

from app.modules.robots.trading.backtest.types import BacktestResult

from app.modules.robots.trading.runtime import get_trading_orchestrator





class HistoryBacktestRobot(BaseRobot):

    """Робот history-backtest: thin wrapper над TradingOrchestrator."""



    def __init__(self) -> None:

        super().__init__(

            robot_type="history_backtest",

            robot_name="history_simulation",

            version="1.0.0",

        )



    async def execute(self, **kwargs) -> Dict[str, Any]:

        raise NotImplementedError(

            "HistoryBacktestRobot.execute не используется; вызовите run_simulation()"

        )



    @classmethod

    async def run_simulation(

        cls,

        *,

        db: Session,

        schema: str,

        robot_id: int,

        user_id: int,

        token_id: int,

        token: str,

        config: Dict[str, Any],

        candles_by_figi: Dict[str, List[Dict[str, Any]]],

        allowed_figis_by_date: Dict[str, List[str]],

        initial_capital: float,

        log_func=None,

        cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,

        cancel_check_sync: Optional[Callable[[], bool]] = None,

        progress_callback_sync: Optional[Callable[[int, int], None]] = None,

    ) -> BacktestResult:

        return await get_trading_orchestrator().run_backtest_replay(

            db=db,

            schema=schema,

            robot_id=robot_id,

            user_id=user_id,

            token_id=token_id,

            token=token,

            config=config,

            candles_by_figi=candles_by_figi,

            allowed_figis_by_date=allowed_figis_by_date,

            initial_capital=initial_capital,

            log_func=log_func,

            cancel_check=cancel_check,

            cancel_check_sync=cancel_check_sync,

            progress_callback_sync=progress_callback_sync,

        )





__all__ = ["HistoryBacktestRobot"]


