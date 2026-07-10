from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class RecommendationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RecommendationCategory(str, Enum):
    STRATEGY = "strategy"
    PARAMS = "params"
    RISK = "risk"
    BACKTEST = "backtest"
    LIVE = "live"
    OPERATIONAL = "operational"


class SuggestedChange(BaseModel):
    path: str = Field(..., description="Путь в config, напр. strategy_params.interval")
    current_value: Optional[Any] = None
    suggested_value: Optional[Any] = None
    reason: Optional[str] = None


class RecommendationItem(BaseModel):
    id: str
    category: RecommendationCategory
    severity: RecommendationSeverity
    title: str
    message: str
    suggested_changes: List[SuggestedChange] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)


class BacktestRunInsight(BaseModel):
    run_id: int
    status: Optional[str] = None
    total_return_percent: Optional[float] = None
    max_drawdown_percent: Optional[float] = None
    win_rate_percent: Optional[float] = None
    trades_total: Optional[int] = None
    sharpe_ratio: Optional[float] = None
    requested_from: Optional[datetime] = None
    requested_to: Optional[datetime] = None
    created_at: Optional[datetime] = None
    score: Optional[float] = Field(
        None, description="Эвристика для ранжирования: return - 0.5*drawdown"
    )


class LiveSituationSummary(BaseModel):
    robot_status: Optional[int] = None
    stream_connected_hint: Optional[bool] = None
    last_event_at: Optional[datetime] = None
    open_positions: int = 0
    signal_execution_rate_pct: Optional[float] = None
    risk_events_7d: int = 0
    metrics: Optional[Dict[str, Any]] = None


class RobotRecommendationsResponse(BaseModel):
    robot_id: int
    strategy: str
    strategy_title: Optional[str] = None
    generated_at: datetime
    backtest_runs_analyzed: int
    best_backtest_run_id: Optional[int] = None
    best_backtest: Optional[BacktestRunInsight] = None
    latest_backtest: Optional[BacktestRunInsight] = None
    live: LiveSituationSummary
    recommendations: List[RecommendationItem]
    config_snapshot_summary: Dict[str, Any] = Field(default_factory=dict)


class StrategyTipsResponse(BaseModel):
    strategy: str
    strategy_title: Optional[str] = None
    tips: List[RecommendationItem]


class OptimizationGoal(str, Enum):
    BALANCED = "balanced"
    MAX_RETURN = "max_return"
    MIN_DRAWDOWN = "min_drawdown"
    MAX_SHARPE = "max_sharpe"


class OptimizationMode(str, Enum):
    SPEED = "speed"
    FULL = "full"


class OptimizationRankItem(BaseModel):
    rank: int
    run_id: int
    score: float
    total_return_percent: Optional[float] = None
    max_drawdown_percent: Optional[float] = None
    win_rate_percent: Optional[float] = None
    trades_total: Optional[int] = None
    sharpe_ratio: Optional[float] = None
    requested_from: Optional[datetime] = None
    requested_to: Optional[datetime] = None
    started_at: Optional[datetime] = None
    param_summary: Dict[str, Any] = Field(default_factory=dict)


class OptimizationParamSuggestion(BaseModel):
    path: str
    current_value: Optional[Any] = None
    suggested_value: Optional[Any] = None
    reason: Optional[str] = None


class OptimizationFailedRunItem(BaseModel):
    run_id: int
    error_message: Optional[str] = None
    failure_category: str = "unknown"
    failure_summary: Optional[str] = None
    top_rejects: Dict[str, int] = Field(default_factory=dict)
    suggested_changes: List[OptimizationParamSuggestion] = Field(default_factory=list)
    param_summary: Dict[str, Any] = Field(default_factory=dict)
    requested_from: Optional[datetime] = None
    requested_to: Optional[datetime] = None
    started_at: Optional[datetime] = None


class OptimizationRankResponse(BaseModel):
    robot_id: int
    strategy: str
    goal: OptimizationGoal
    runs_analyzed: int
    ranked: List[OptimizationRankItem]
    failed_runs: List[OptimizationFailedRunItem] = Field(default_factory=list)
    overfitting_warnings: List[str] = Field(default_factory=list)


class OptimizationPlanCandidate(BaseModel):
    index: int
    param_summary: Dict[str, Any] = Field(default_factory=dict)
    config_snapshot: Dict[str, Any] = Field(default_factory=dict)


class OptimizationPlanRequest(BaseModel):
    goal: OptimizationGoal = OptimizationGoal.BALANCED
    mode: OptimizationMode = OptimizationMode.SPEED


class OptimizationPlanResponse(BaseModel):
    robot_id: int
    strategy: str
    goal: OptimizationGoal
    mode: OptimizationMode
    total_candidates: int
    candidates: List[OptimizationPlanCandidate]
    note: str = Field(
        default="Кандидаты сетки; запустите массовый прогон кнопкой «Запустить сетку».",
    )


class OptimizationRunRequest(BaseModel):
    goal: OptimizationGoal = OptimizationGoal.BALANCED
    mode: OptimizationMode = OptimizationMode.SPEED
    from_date: datetime = Field(..., description="Начало периода бэктеста (UTC)")
    to_date: datetime = Field(..., description="Конец периода бэктеста (UTC)")
    initial_capital: float = Field(default=1_000_000.0, ge=1000)

    @model_validator(mode="after")
    def check_range(self):
        if self.to_date <= self.from_date:
            raise ValueError("to_date must be after from_date")
        return self


class OptimizationBatchStartedResponse(BaseModel):
    batch_id: int
    robot_id: int
    goal: OptimizationGoal
    mode: OptimizationMode
    total_candidates: int
    enqueued: int
    run_ids: List[int] = Field(default_factory=list)
    status: str = "running"


class OptimizationBatchProgress(BaseModel):
    queued: int = 0
    running: int = 0
    success: int = 0
    failed: int = 0
    cancelled: int = 0
    done: int = 0
    percent: float = 0.0


class OptimizationBatchItem(BaseModel):
    candidate_index: int
    run_id: Optional[int] = None
    status: str
    score: Optional[float] = None
    param_summary: Dict[str, Any] = Field(default_factory=dict)
    total_return_percent: Optional[float] = None
    max_drawdown_percent: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    trades_total: Optional[int] = None
    error_message: Optional[str] = None
    failure_category: Optional[str] = None
    failure_summary: Optional[str] = None
    top_rejects: Dict[str, int] = Field(default_factory=dict)
    suggested_changes: List[OptimizationParamSuggestion] = Field(default_factory=list)


class OptimizationBatchStatusResponse(BaseModel):
    batch_id: int
    robot_id: int
    goal: OptimizationGoal
    mode: OptimizationMode
    status: str
    total_candidates: int
    progress: OptimizationBatchProgress
    requested_from: Optional[datetime] = None
    requested_to: Optional[datetime] = None
    initial_capital: Optional[float] = None
    overfitting_warnings: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    items: List[OptimizationBatchItem] = Field(default_factory=list)
    ranked: List[OptimizationRankItem] = Field(default_factory=list)


class OptimizationBatchCancelResponse(BaseModel):
    batch_id: int
    cancelled_runs: int
    status: str = "cancelled"


class OptimizationSessionFailuresResponse(BaseModel):
    """Неуспешные прогоны без привязки к роботу (страница тестирования)."""
    failed_runs: List[OptimizationFailedRunItem] = Field(default_factory=list)
