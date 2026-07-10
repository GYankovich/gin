from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from app.core.db_retry import run_db_read_with_retry


class _FakeSession:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1

    def pop(self):
        if not self._outcomes:
            raise RuntimeError("no more outcomes")
        item = self._outcomes.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def test_run_db_read_with_retry_succeeds_first_try():
    db = _FakeSession([42])
    assert run_db_read_with_retry(db, db.pop) == 42
    assert db.rollbacks == 0


def test_run_db_read_with_retry_recovers_after_operational_error():
    err = OperationalError("stmt", {}, Exception("server closed the connection unexpectedly"))
    db = _FakeSession([err, "ok"])
    assert run_db_read_with_retry(db, db.pop) == "ok"
    assert db.rollbacks == 1


def test_run_db_read_with_retry_reraises_second_failure():
    err = OperationalError("stmt", {}, Exception("server closed the connection unexpectedly"))
    db = _FakeSession([err, err])
    with pytest.raises(OperationalError):
        run_db_read_with_retry(db, db.pop)
    assert db.rollbacks == 1
