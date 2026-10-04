"""Enqueue a short V2 backtest and assert glass-box P0–P2 fields on SUCCESS."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "http://127.0.0.1:8000"
LOGIN = "gy"
PASSWORD = "4272"
ROBOT_ID = 13
MAX_POLL = 90
POLL_SLEEP = 3


def req(method: str, path: str, token: str | None = None, data=None, headers=None, timeout: int = 120):
    url = BASE + path
    body = None if data is None else json.dumps(data).encode()
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if headers:
        hdrs.update(headers)
    request = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"raw": raw[:800]}
        return exc.code, payload


def main() -> int:
    st, auth = req("POST", "/api/auth/login", data={"login": LOGIN, "password": PASSWORD})
    token = (auth or {}).get("access_token")
    if st != 200 or not token:
        print("FAIL login", st, auth)
        return 1
    print("OK login")

    st, robot = req("GET", f"/api/v2/robots/{ROBOT_ID}", token=token)
    if st != 200 or not isinstance(robot, dict):
        print("FAIL get_robot", st, robot)
        return 1
    config = robot.get("config") or {}
    print(f"OK robot id={ROBOT_ID} configVersion={config.get('configVersion')}")

    token_id = robot.get("tokenId") or robot.get("token_id")
    try:
        token_id = int(token_id) if token_id is not None else None
    except (TypeError, ValueError):
        token_id = None

    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=5)
    body = {
        "config": config,
        "from_date": from_dt.strftime("%Y-%m-%dT00:00:00Z"),
        "to_date": to_dt.strftime("%Y-%m-%dT23:59:59Z"),
        "initial_capital": float((config.get("risk") or {}).get("capital") or 100000),
        "robot_id": ROBOT_ID,
        "priority": "interactive",
        "labels": {"source": "smoke_glass_box"},
    }
    if token_id:
        body["token_id"] = token_id

    # Prefer v2 backtest enqueue; fall back to compute
    st, accepted = req(
        "POST",
        "/api/v2/robots/backtest",
        token=token,
        data=body,
        headers={"Idempotency-Key": f"smoke-gb-{ROBOT_ID}-{int(time.time())}"},
    )
    if st not in (200, 202):
        print(f"WARN v2 backtest enqueue → {st}, trying compute…")
        st, accepted = req(
            "POST",
            "/api/compute/v1/runs",
            token=token,
            data=body,
            headers={"Idempotency-Key": f"smoke-gb-c-{ROBOT_ID}-{int(time.time())}"},
        )
    if st not in (200, 202) or not isinstance(accepted, dict):
        print("FAIL enqueue", st, accepted)
        return 1
    run_id = accepted.get("run_id") or accepted.get("id") or (accepted.get("run") or {}).get("id")
    print(f"OK enqueued run_id={run_id} via status={st}")
    if not run_id:
        return 1

    last = None
    for i in range(MAX_POLL):
        st, last = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/status", token=token)
        if st != 200:
            st, last = req("GET", f"/api/compute/v1/runs/{run_id}/status", token=token)
        status = str((last or {}).get("status") or "")
        print(f"  [{i}] status={status} progress={(last or {}).get('progress_percent')}")
        if status.upper() in {"SUCCESS", "FAILED", "CANCELLED"}:
            break
        time.sleep(POLL_SLEEP)
    else:
        req("POST", f"/api/v2/robots/backtest/runs/{run_id}/cancel", token=token)
        print("FAIL timeout — cancel sent")
        return 2

    if str((last or {}).get("status") or "").upper() != "SUCCESS":
        print("FAIL terminal", last)
        return 2
    print("OK SUCCESS")

    checks = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, cond, detail))
        print(("OK" if cond else "FAIL"), name, detail)

    st, details = req("GET", f"/api/v2/robots/backtest/runs/{run_id}", token=token)
    check("details", st == 200, f"status={st}")
    obs = (details or {}).get("observability") or {}
    check("observability", bool(obs), f"keys={list(obs.keys())}")
    em = obs.get("execution_model") or {}
    check("NEXT_BAR_OPEN", em.get("code") == "NEXT_BAR_OPEN", str(em))
    check("reject_counts", isinstance(obs.get("reject_reason_counts"), list), str(len(obs.get("reject_reason_counts") or [])))
    check("status_counts", isinstance(obs.get("status_counts"), dict), str(obs.get("status_counts")))

    fee = (details or {}).get("fee_summary") or ((details or {}).get("result_payload") or {}).get("fee_summary")
    check("fee_summary", isinstance(fee, dict), f"fee={fee}")

    narr = (details or {}).get("narrative") or []
    check("narrative_nonempty", isinstance(narr, list) and len(narr) > 0, f"n={len(narr) if isinstance(narr, list) else 0}")

    snaps = (details or {}).get("portfolio_snapshots") or []
    rich = any(isinstance(s.get("positions"), list) for s in snaps[:5])
    check("holdings_rich", rich or not snaps, f"snaps={len(snaps)} rich={rich}")

    st, uni = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/universe", token=token)
    items = (uni or {}).get("items") or []
    check("universe", st == 200, f"status={st} items={len(items)} days={(uni or {}).get('days')}")

    st, ev = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/execution-events?limit=50", token=token)
    events = (ev or {}).get("items") or (ev or {}).get("events") or []
    check("execution_events", st == 200, f"status={st} n={len(events)}")

    st, narr_ep = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/narrative", token=token)
    narr_items = (narr_ep or {}).get("items") or []
    check("narrative_endpoint", st == 200 and len(narr_items) > 0, f"status={st} n={len(narr_items)}")

    # Find cycle_id + ticker for price window / cycle bundle
    signals = (details or {}).get("signals") or []
    if not signals:
        st, sig_page = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/signals?limit=50", token=token)
        signals = (sig_page or {}).get("items") or []
    trades = ((details or {}).get("result_payload") or {}).get("trades") or (details or {}).get("trades") or []

    cycle_id = None
    for row in signals:
        cycle_id = row.get("cycle_id") or ((row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {}).get("cycle_id")
        if cycle_id:
            break
    check("cycle_id_stamped", bool(cycle_id) or not signals, f"cycle_id={cycle_id} signals={len(signals)}")
    if cycle_id:
        st, bundle = req(
            "GET",
            f"/api/v2/robots/backtest/runs/{run_id}/cycles/{urllib.parse.quote(str(cycle_id))}",
            token=token,
        )
        check("cycle_bundle", st == 200, f"status={st} keys={list((bundle or {}).keys())[:8]}")

    ticker = None
    around = None
    src = trades[0] if trades else (signals[0] if signals else None)
    if src:
        ticker = src.get("ticker") or src.get("figi")
        around = src.get("bar_time") or src.get("signal_time") or src.get("time")
    if ticker and around:
        qs = urllib.parse.urlencode({"ticker": str(ticker), "around": str(around), "bars": 30})
        st, pw = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/price-window?{qs}", token=token)
        candles = (pw or {}).get("candles") or (pw or {}).get("items") or []
        check("price_window", st == 200, f"status={st} gap={(pw or {}).get('gap')} candles={len(candles) if isinstance(candles, list) else 0}")
    else:
        check("price_window", True, "skipped — no trades/signals")

    failed = [n for n, c, _ in checks if not c]
    print("---")
    print(f"run_id={run_id} passed={sum(1 for _, c, _ in checks if c)} failed={len(failed)}")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 3
    print("ALL NEW-RUN GLASS-BOX CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
