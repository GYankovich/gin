"""OsEngine market-data boundary: facade, leases, history ingest."""

from app.modules.osengine.coverage import expand_lookback, merge_ranges, missing_ranges
from app.modules.osengine.facade import (
    DefaultOsEngineFacade,
    OsEngineFacade,
    build_candle_ensure_request,
    get_osengine_facade,
    reset_osengine_facade_for_tests,
)
from app.modules.osengine.history_files import FileHistoryProvider
from app.modules.osengine.history_mcp import McpHistoryProvider
from app.modules.osengine.lifecycle import release_osengine_leases_for_run
from app.modules.osengine.mcp_client import OsEngineMcpClient, OsEngineMcpError
from app.modules.osengine.process import start_osengine_process, stop_osengine_process
from app.modules.osengine.snapshots import ensure_daily_snapshot_from_osengine
from app.modules.osengine.stats import (
    CacheGcStats,
    EnsureCandlesStats,
    LeaseReleaseStats,
    LiveIngestStatus,
)
from app.modules.osengine.types import (
    CacheLease,
    CandleEnsureRequest,
    InstrumentKey,
    TimeRange,
)

__all__ = [
    "CacheGcStats",
    "CacheLease",
    "CandleEnsureRequest",
    "DefaultOsEngineFacade",
    "EnsureCandlesStats",
    "FileHistoryProvider",
    "InstrumentKey",
    "LeaseReleaseStats",
    "LiveIngestStatus",
    "McpHistoryProvider",
    "OsEngineFacade",
    "OsEngineMcpClient",
    "OsEngineMcpError",
    "TimeRange",
    "build_candle_ensure_request",
    "ensure_daily_snapshot_from_osengine",
    "expand_lookback",
    "get_osengine_facade",
    "merge_ranges",
    "missing_ranges",
    "release_osengine_leases_for_run",
    "reset_osengine_facade_for_tests",
    "start_osengine_process",
    "stop_osengine_process",
]
