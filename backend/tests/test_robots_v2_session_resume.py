"""Auto-resume robots v2 after API restart."""

from __future__ import annotations

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.engine.session_resume import SESSION_DESIRED_KEY, robots_to_resume


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows
        self.last_sql = ""

    def execute(self, stmt, params=None):
        self.last_sql = str(stmt)
        return _FakeResult(self._rows)


def test_robots_to_resume_prefers_session_desired_running():
    db = _FakeDb([
        type("R", (), {
            "id": 1,
            "user_id": 10,
            "token_id": 23,
            "config": {"core": {"mode": "live"}},
            "metadata": {SESSION_DESIRED_KEY: "running"},
        })(),
    ])
    out = robots_to_resume(db, schema="public")
    assert len(out) == 1
    assert out[0]["robot_id"] == 1


def test_robots_to_resume_sql_includes_legacy_open_audit():
    db = _FakeDb([])
    robots_to_resume(db, schema="public")
    assert "robots_v2_sessions" in db.last_sql
    assert SESSION_DESIRED_KEY in db.last_sql
    assert "'stopped'" in db.last_sql or "stopped" in db.last_sql
