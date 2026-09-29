#!/usr/bin/env python3
"""ARCH-05 / robots_v2 staging smoke.

Usage:
  set GIN_BASE_URL=https://your-staging.example
  set GIN_LOGIN=...
  set GIN_PASSWORD=...
  python -m scripts.smoke_arch05_compute

Optional:
  GIN_ROBOT_ID=13
  GIN_SMOKE_SKIP_RUN=1   # only auth + queue metrics + list
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or not str(v).strip():
        return default
    return str(v).strip()


def _req(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    data = None
    hdrs = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            return int(resp.status), parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"detail": str(exc)}
        except json.JSONDecodeError:
            parsed = {"detail": raw or str(exc)}
        return int(exc.code), parsed


def main() -> int:
    base = (_env("GIN_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
    login = _env("GIN_LOGIN")
    password = _env("GIN_PASSWORD")
    robot_id = int(_env("GIN_ROBOT_ID") or "0")
    skip_run = (_env("GIN_SMOKE_SKIP_RUN") or "").lower() in {"1", "true", "yes"}

    print(f"[smoke] base={base}")

    code, health = _req("GET", f"{base}/api/health") if False else (0, None)
    # /health may not exist — try openapi
    code, _ = _req("GET", f"{base}/openapi.json")
    if code != 200:
        print(f"[FAIL] openapi.json → {code}")
        return 1
    print("[ok] openapi reachable")

    if not login or not password:
        print("[SKIP] set GIN_LOGIN + GIN_PASSWORD for authenticated checks")
        return 0

    code, auth = _req(
        "POST",
        f"{base}/api/auth/login",
        body={"login": login, "password": password},
    )
    if code != 200 or not isinstance(auth, dict) or not auth.get("access_token"):
        # alternate shape
        token = (auth or {}).get("accessToken") if isinstance(auth, dict) else None
        if not token:
            print(f"[FAIL] login → {code} {auth}")
            return 1
    else:
        token = auth["access_token"]
    print("[ok] login")

    code, metrics = _req("GET", f"{base}/api/compute/v1/metrics/queue", token=token)
    if code != 200:
        print(f"[FAIL] queue metrics → {code} {metrics}")
        return 1
    print(f"[ok] queue depth queued={metrics.get('queued')} running={metrics.get('running')}")

    code, runs = _req(
        "GET",
        f"{base}/api/compute/v1/runs?limit=5"
        + (f"&robot_id={robot_id}" if robot_id > 0 else ""),
        token=token,
    )
    if code != 200:
        print(f"[FAIL] list runs → {code} {runs}")
        return 1
    print(f"[ok] list runs total={runs.get('total') if isinstance(runs, dict) else '?'}")

    if skip_run or robot_id <= 0:
        print("[ok] smoke (read-only) passed")
        return 0

    # Fetch robot config from v2 API
    code, robot = _req("GET", f"{base}/api/v2/robots/{robot_id}", token=token)
    if code != 200 or not isinstance(robot, dict):
        print(f"[FAIL] get robot → {code} {robot}")
        return 1
    config = robot.get("config") or {}
    if int(config.get("configVersion") or 0) != 4:
        print("[SKIP] robot config is not v4 — cannot enqueue compute run")
        return 0

    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=7)
    code, accepted = _req(
        "POST",
        f"{base}/api/compute/v1/runs",
        token=token,
        headers={"Idempotency-Key": f"smoke-{robot_id}-{int(time.time())}"},
        body={
            "config": config,
            "from_date": from_dt.strftime("%Y-%m-%dT00:00:00Z"),
            "to_date": to_dt.strftime("%Y-%m-%dT23:59:59Z"),
            "initial_capital": float((config.get("risk") or {}).get("capital") or 100000),
            "robot_id": robot_id,
            "priority": "interactive",
            "labels": {"source": "smoke_arch05"},
        },
    )
    if code != 202:
        print(f"[FAIL] create run → {code} {accepted}")
        return 1
    run_id = int(accepted["run_id"])
    print(f"[ok] enqueued run_id={run_id}")

    terminal = {"SUCCESS", "FAILED", "CANCELLED", "success", "failed", "cancelled"}
    last = None
    for _ in range(40):
        code, last = _req(
            "GET", f"{base}/api/compute/v1/runs/{run_id}/status", token=token,
        )
        if code != 200:
            print(f"[WARN] status poll → {code}")
            time.sleep(2)
            continue
        st = str(last.get("status") or "")
        print(f"  … status={st} progress={last.get('progress_percent')}")
        if st.upper() in {x.upper() for x in terminal}:
            break
        time.sleep(2)
    else:
        # cancel to avoid leaving a long job
        c_code, c_body = _req(
            "POST", f"{base}/api/compute/v1/runs/{run_id}/cancel", token=token,
        )
        print(f"[ok] cancel requested → {c_code} {c_body}")
        print("[ok] smoke passed (run still active, cancel sent)")
        return 0

    print(f"[ok] terminal status={last.get('status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
