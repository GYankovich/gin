"""PgLiveEventSubscriber reconnects after LISTEN connection drops."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from app.modules.robots.live_events import PgLiveEventSubscriber


def test_listen_loop_reconnects_after_ssl_drop():
    sub = PgLiveEventSubscriber()
    stop = threading.Event()
    connect_calls = {"n": 0}

    class _FakeConn:
        def __init__(self, fail_after_polls: int):
            self.fail_after_polls = fail_after_polls
            self.polls = 0
            self.notifies: list = []
            self.closed = False

        def set_isolation_level(self, *_a, **_k):
            return None

        def cursor(self):
            cur = MagicMock()
            cur.execute = MagicMock()
            return cur

        def poll(self):
            self.polls += 1
            if self.polls >= self.fail_after_polls:
                raise OSError("SSL connection has been closed unexpectedly")

        def close(self):
            self.closed = True

    def _connect():
        connect_calls["n"] += 1
        # First connection drops after one select/poll cycle; second stays until stop.
        if connect_calls["n"] == 1:
            return _FakeConn(fail_after_polls=1)
        return _FakeConn(fail_after_polls=10_000)

    def _select(readers, _w, _x, _timeout):
        # Always report readable so poll() is invoked.
        return (readers, [], [])

    with (
        patch("app.modules.robots.live_events._pg_connect", side_effect=_connect),
        patch("app.modules.robots.live_events.select.select", side_effect=_select),
    ):
        t = threading.Thread(
            target=sub._listen_loop,
            args=(24, stop),
            daemon=True,
        )
        t.start()
        deadline = time.monotonic() + 5.0
        while connect_calls["n"] < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        stop.set()
        t.join(timeout=3.0)

    assert connect_calls["n"] >= 2, "expected reconnect after SSL drop"
    assert not t.is_alive()
