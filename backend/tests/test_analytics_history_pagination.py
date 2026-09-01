"""SPEC-02: paginated analytics snapshots & operations."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.analytics import queries, schemas
from app.modules.analytics.service import AnalyticsService
from app.modules.auth.models import User

AUTH_HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture
def mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = 7
    user.login = "tester"
    return user


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@contextmanager
def _analytics_client(mock_user: User, mock_db: MagicMock) -> Iterator[TestClient]:
    from app.main import app

    async def override_user() -> User:
        return mock_user

    def override_db() -> Iterator[MagicMock]:
        yield mock_db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --- schema ---


def test_history_page_defaults() -> None:
    body = schemas.AnalyticsSnapshotsRequest(account_id=1)
    assert body.limit == 50
    assert body.offset == 0
    assert body.from_date is None
    assert body.to_date is None


def test_history_page_rejects_half_date_range() -> None:
    with pytest.raises(ValidationError) as exc:
        schemas.AnalyticsOperationsRequest(
            account_id=1,
            from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    assert "both be set or both omitted" in str(exc.value)


def test_history_page_rejects_inverted_dates() -> None:
    with pytest.raises(ValidationError) as exc:
        schemas.AnalyticsSnapshotsRequest(
            account_id=1,
            from_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
            to_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    assert "from_date must be <=" in str(exc.value)


def test_history_page_rejects_limit_over_max() -> None:
    with pytest.raises(ValidationError):
        schemas.AnalyticsSnapshotsRequest(account_id=1, limit=201)


def test_history_page_rejects_negative_offset() -> None:
    with pytest.raises(ValidationError):
        schemas.AnalyticsOperationsRequest(account_id=1, offset=-1)


def test_operations_response_uses_count_not_total() -> None:
    fields = schemas.AnalyticsOperationsResponse.model_fields
    assert "count" in fields
    assert "total" not in fields


# --- queries ---


def test_snapshots_count_all_time_omits_dates() -> None:
    sql, params = queries.build_account_snapshots_count_query(42)
    assert "COUNT(*)" in sql
    assert "from_date" not in params
    assert "to_date" not in params
    assert params["account_id"] == 42


def test_snapshots_page_order_limit_offset() -> None:
    sql, params = queries.build_account_snapshots_page_query(
        42,
        from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        to_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        limit=50,
        offset=100,
    )
    assert "ORDER BY snapshot_date DESC" in sql
    assert "LIMIT :limit OFFSET :offset" in sql
    assert params["limit"] == 50
    assert params["offset"] == 100
    assert "snapshot_date >= :from_date" in sql
    assert "snapshot_date <= :to_date" in sql


def test_operations_page_all_time_and_type_filter() -> None:
    sql, params = queries.build_account_operations_query(
        7, operation_type="OPERATION_TYPE_BUY", limit=50, offset=0
    )
    assert "from_date" not in params
    assert params["operation_type"] == "OPERATION_TYPE_BUY"
    assert "ORDER BY po.operation_date DESC" in sql
    assert "LIMIT :limit OFFSET :offset" in sql

    count_sql, count_params = queries.build_account_operations_count_query(
        7, operation_type="OPERATION_TYPE_BUY"
    )
    assert "COUNT(*)" in count_sql
    assert count_params["operation_type"] == "OPERATION_TYPE_BUY"
    assert "from_date" not in count_params


# --- service ---


def test_service_snapshots_page_count_and_newest_first() -> None:
    svc = AnalyticsService()
    db = MagicMock()
    newer = datetime(2026, 8, 20, tzinfo=timezone.utc)
    older = datetime(2026, 8, 10, tzinfo=timezone.utc)

    with patch.object(svc, "check_account_ownership", return_value={"id": 1}):
        with patch.object(
            svc,
            "_execute",
            side_effect=[
                (120,),  # count
                [
                    (2, newer, 200.0, 1.0, 2.0),
                    (1, older, 100.0, 0.5, 1.0),
                ],
            ],
        ):
            result = svc.get_account_snapshots_page(
                db, account_id=1, user_id=7, limit=50, offset=0
            )

    assert result is not None
    assert result["count"] == 120
    assert result["limit"] == 50
    assert result["offset"] == 0
    assert result["from_date"] is None
    assert len(result["history"]) == 2
    assert result["history"][0]["date"] == newer
    assert result["history"][1]["date"] == older


def test_service_operations_offset_page_empty_when_past_end() -> None:
    svc = AnalyticsService()
    db = MagicMock()

    with patch.object(svc, "check_account_ownership", return_value={"id": 1}):
        with patch.object(
            svc,
            "_execute",
            side_effect=[
                (3,),  # count
                [],  # empty page
            ],
        ):
            result = svc.get_account_operations(
                db, account_id=1, user_id=7, limit=50, offset=50
            )

    assert result is not None
    assert result["count"] == 3
    assert result["items"] == []
    assert result["offset"] == 50


def test_service_ownership_returns_none() -> None:
    svc = AnalyticsService()
    db = MagicMock()
    with patch.object(svc, "check_account_ownership", return_value=None):
        assert svc.get_account_snapshots_page(db, 99, 7) is None
        assert svc.get_account_operations(db, 99, 7) is None


# --- HTTP ---


def test_snapshots_http_defaults_and_shape(mock_user: User, mock_db: MagicMock) -> None:
    page = {
        "account_id": 123,
        "from_date": None,
        "to_date": None,
        "count": 842,
        "limit": 50,
        "offset": 0,
        "history": [
            {
                "snapshot_id": 1,
                "date": datetime(2026, 8, 27, tzinfo=timezone.utc),
                "total_value": 10.0,
                "daily_yield": 0.1,
                "expected_yield": 0.2,
            }
        ],
    }
    with _analytics_client(mock_user, mock_db) as client:
        with patch(
            "app.modules.analytics.router.analytics_service.get_account_snapshots_page",
            return_value=page,
        ) as mocked:
            response = client.post(
                "/api/analytics/snapshots",
                json={"account_id": 123},
                headers=AUTH_HEADERS,
            )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 842
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert body["from_date"] is None
    assert body["to_date"] is None
    assert len(body["history"]) == 1
    assert "total" not in body
    mocked.assert_called_once()
    kwargs = mocked.call_args.kwargs
    assert kwargs["limit"] == 50
    assert kwargs["offset"] == 0
    assert kwargs["from_date"] is None
    assert kwargs["to_date"] is None


def test_operations_http_pagination_and_count(mock_user: User, mock_db: MagicMock) -> None:
    page = {
        "account_id": 123,
        "from_date": None,
        "to_date": None,
        "count": 1204,
        "limit": 50,
        "offset": 50,
        "items": [],
    }
    with _analytics_client(mock_user, mock_db) as client:
        with patch(
            "app.modules.analytics.router.analytics_service.get_account_operations",
            return_value=page,
        ) as mocked:
            response = client.post(
                "/api/analytics/operations",
                json={"account_id": 123, "limit": 50, "offset": 50},
                headers=AUTH_HEADERS,
            )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1204
    assert body["offset"] == 50
    assert body["items"] == []
    assert "total" not in body
    assert mocked.call_args.kwargs["offset"] == 50


def test_snapshots_http_ownership_404(mock_user: User, mock_db: MagicMock) -> None:
    with _analytics_client(mock_user, mock_db) as client:
        with patch(
            "app.modules.analytics.router.analytics_service.get_account_snapshots_page",
            return_value=None,
        ):
            response = client.post(
                "/api/analytics/snapshots",
                json={"account_id": 999},
                headers=AUTH_HEADERS,
            )
    assert response.status_code == 404


def test_operations_http_ownership_404(mock_user: User, mock_db: MagicMock) -> None:
    with _analytics_client(mock_user, mock_db) as client:
        with patch(
            "app.modules.analytics.router.analytics_service.get_account_operations",
            return_value=None,
        ):
            response = client.post(
                "/api/analytics/operations",
                json={"account_id": 999},
                headers=AUTH_HEADERS,
            )
    assert response.status_code == 404


def test_snapshots_http_half_date_validation(mock_user: User, mock_db: MagicMock) -> None:
    with _analytics_client(mock_user, mock_db) as client:
        response = client.post(
            "/api/analytics/snapshots",
            json={"account_id": 1, "from_date": "2026-01-01T00:00:00Z"},
            headers=AUTH_HEADERS,
        )
    assert response.status_code == 422
