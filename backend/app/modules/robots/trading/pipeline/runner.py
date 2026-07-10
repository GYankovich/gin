"""
PipelineRunner — единая утренняя фильтрация тикеров.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §5.

Использует существующий `DmsService._evaluate_pipeline_row` (все 17 фильтров),
добавляет шаг дивидендного календаря (общий с history-backtest, закрывает зазор
§3.0.1 BRD-ARCH-02 для live).

Принимает на вход либо list[dict] (DMS-формат строк снапшота), либо
`MarketSnapshot` из contracts.py — последний автоматически конвертируется в
ожидаемый DMS-формат.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingPipelineRunner [1]
#/// Исходный модуль `backend/app/modules/robots/trading/pipeline/runner.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from sqlalchemy.orm import Session

from app.modules.dms.service import dms_service
from app.modules.robots.trading.contracts import MarketSnapshot, SnapshotRow


@dataclass
class PipelineDecision:
    secid: str
    accepted: bool
    reason: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    accepted: List[str]
    rejected: List[Tuple[str, str]]
    decisions: List[PipelineDecision]

    def reasons_by_ticker(self) -> Dict[str, str]:
        return {d.secid: d.reason for d in self.decisions}


# ---------------------------------------------------------------------------
# Конвертация SnapshotRow в DMS-формат строки
# ---------------------------------------------------------------------------

def _snapshot_row_to_dms_dict(row: SnapshotRow) -> Dict[str, Any]:
    """Маппит поля `SnapshotRow` в имена, которые ожидает `_evaluate_pipeline_row`.

    Соответствие следует тому, что отдаёт `DmsService._fetch_moex_board_snapshot`.
    """
    return {
        "ticker": row.secid,
        "open_price": row.open,
        "prev_price": row.prev_close,
        "last_price": row.last_price,
        "high_price": row.high,
        "low_price": row.low,
        "value_today": row.volume_rub,
        "volume_lots": row.volume_lots,
        "num_trades": row.num_trades,
        "issue_size": row.issue_size,
        "spread": None,
        "bid": row.bid,
        "ask": row.ask,
        "security_status": row.security_status,
        "trading_status": row.trading_status,
        "atr_percent": row.atr_pct,
        "min_step": (row.meta.get("min_step") if row.meta else None),
        "securities_payload": (row.meta.get("securities_payload") if row.meta else None),
    }


# ---------------------------------------------------------------------------
# PipelineRunner
# ---------------------------------------------------------------------------

class PipelineRunner:
    """Применяет declarative-список фильтров к набору строк снапшота.

    Композиция AND/OR — режимом `mode` ("ALL"/"ANY") внутри `_evaluate_pipeline_row`.

    Дивидендный календарь — отдельный шаг **после** прохождения фильтров, чтобы
    отказы по дивидендам логировались с понятной причиной.
    """

    def __init__(
        self,
        filters: List[Dict[str, Any]],
        *,
        mode: str = "ALL",
        optimize_order: bool = True,
        allowed_tickers: Optional[Iterable[str]] = None,
        allow_missing_spread: bool = False,
    ):
        self.filters = [dict(f) for f in (filters or []) if isinstance(f, dict)]
        self.mode = (mode or "ALL").upper()
        self.optimize_order = bool(optimize_order)
        self.allowed_tickers = (
            {str(x).upper() for x in allowed_tickers if x} if allowed_tickers else None
        )
        self.allow_missing_spread = bool(allow_missing_spread)

    # --- основной API ---

    def run(
        self,
        rows: Union[MarketSnapshot, List[Dict[str, Any]]],
        *,
        trade_date: Optional[date] = None,
        db: Optional[Session] = None,
        dividend_policy: Any = None,
    ) -> PipelineResult:
        """Возвращает `PipelineResult` со списком принятых/отказанных тикеров."""
        dms_rows = self._to_dms_rows(rows)
        decisions: List[PipelineDecision] = []
        accepted: List[str] = []
        rejected: List[Tuple[str, str]] = []

        for row in dms_rows:
            ticker = str(row.get("ticker") or "").upper()
            if not ticker:
                continue
            eval_res = dms_service._evaluate_pipeline_row(
                row,
                self.filters,
                self.mode,
                optimize_order=self.optimize_order,
                allowed_figis=self.allowed_tickers,
                allow_missing_spread=self.allow_missing_spread,
            )
            if not eval_res.get("accepted"):
                reason = str(eval_res.get("reason") or "rejected")
                decisions.append(PipelineDecision(secid=ticker, accepted=False, reason=reason,
                                                  payload={"stage": "filters"}))
                rejected.append((ticker, reason))
                continue

            # --- дивидендный календарь ---
            if dividend_policy is not None and trade_date is not None and db is not None:
                try:
                    from app.modules.corporate_actions.dividend_calendar_service import (
                        DividendCalendarService,
                    )
                    svc = DividendCalendarService(db)
                    div_reason = svc.exclusion_reason_for_day(
                        ticker=ticker, trade_date=trade_date, policy=dividend_policy
                    )
                except Exception:
                    div_reason = None
                if div_reason:
                    decisions.append(PipelineDecision(
                        secid=ticker, accepted=False, reason=div_reason,
                        payload={"stage": "dividend_calendar"},
                    ))
                    rejected.append((ticker, div_reason))
                    continue

            decisions.append(PipelineDecision(
                secid=ticker, accepted=True, reason="ok",
                payload={"stage": "filters",
                         "gap_percent": eval_res.get("gap_percent"),
                         "atr_percent": eval_res.get("atr_percent"),
                         "spread_percent": eval_res.get("spread_percent")},
            ))
            accepted.append(ticker)

        return PipelineResult(accepted=accepted, rejected=rejected, decisions=decisions)

    async def run_async(self, *args, **kwargs) -> PipelineResult:
        """Async-обёртка (DMS-метод сам по себе синхронный)."""
        return self.run(*args, **kwargs)

    # --- helpers ---

    def _to_dms_rows(self, rows: Union[MarketSnapshot, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        if isinstance(rows, MarketSnapshot):
            return [_snapshot_row_to_dms_dict(r) for r in rows.rows.values()]
        if isinstance(rows, list):
            return list(rows)
        raise TypeError(f"Unsupported rows type for PipelineRunner: {type(rows)!r}")


__all__ = ["PipelineRunner", "PipelineResult", "PipelineDecision"]
