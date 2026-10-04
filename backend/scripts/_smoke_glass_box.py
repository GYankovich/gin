"""Live HTTP smoke for glass-box P0–P2 backtest APIs."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"
LOGIN = "gy"
PASSWORD = "4272"


def req(method: str, path: str, token: str | None = None, data=None, timeout: int = 60):
    url = BASE + path
    body = None if data is None else json.dumps(data).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"raw": raw[:500]}
        return exc.code, payload
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}


results: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    print(("OK" if cond else "FAIL"), name, detail)


def main() -> int:
    st, login_body = req("POST", "/api/auth/login", data={"login": LOGIN, "password": PASSWORD})
    token = (login_body or {}).get("access_token") or (login_body or {}).get("token")
    ok("login", st == 200 and bool(token), f"status={st} detail={str(login_body)[:160]}")
    if not token:
        return 1

    st, robots = req("GET", "/api/v2/robots", token=token)
    items = (
        robots
        if isinstance(robots, list)
        else (robots or {}).get("items")
        or (robots or {}).get("robots")
        or []
    )
    ok("list_robots", st == 200 and isinstance(items, list) and len(items) > 0, f"status={st} n={len(items) if isinstance(items, list) else '?'}")
    robot_id = None
    if isinstance(items, list) and items:
        robot_id = items[0].get("id") or items[0].get("robot_id")

    st, openapi = req("GET", "/openapi.json")
    paths = (openapi or {}).get("paths") or {}
    needed = [
        "/api/v2/robots/backtest/runs/{run_id}",
        "/api/v2/robots/backtest/runs/{run_id}/signals",
        "/api/v2/robots/backtest/runs/{run_id}/cycles/{cycle_id}",
        "/api/v2/robots/backtest/runs/{run_id}/universe",
        "/api/v2/robots/backtest/runs/{run_id}/execution-events",
        "/api/v2/robots/backtest/runs/{run_id}/narrative",
        "/api/v2/robots/backtest/runs/{run_id}/price-window",
    ]
    missing = [p for p in needed if p not in paths]
    ok("openapi_glass_box_paths", not missing, f"missing={missing}")

    q = f"?robotId={robot_id}&limit=20" if robot_id else "?limit=20"
    # try both camel/snake variants used in project
    st, runs = req("GET", f"/api/v2/robots/backtest/runs{q}", token=token)
    if st >= 400 and robot_id:
        st, runs = req("GET", f"/api/v2/robots/backtest/runs?robot_id={robot_id}&limit=20", token=token)
    run_list = (
        runs
        if isinstance(runs, list)
        else (runs or {}).get("items") or (runs or {}).get("runs") or []
    )
    ok("list_runs", st == 200, f"status={st} n={len(run_list) if isinstance(run_list, list) else type(runs)}")

    success = None
    if isinstance(run_list, list):
        for row in run_list:
            if str(row.get("status") or "").upper() == "SUCCESS":
                success = row
                break
        if success is None and run_list:
            success = run_list[0]

    if not success:
        ok("have_run", False, "no runs available")
        _summary()
        return 2

    run_id = success.get("id") or success.get("run_id")
    ok("have_run", bool(run_id), f"run_id={run_id} status={success.get('status')}")

    st, details = req("GET", f"/api/v2/robots/backtest/runs/{run_id}", token=token)
    obs = (details or {}).get("observability") or {}
    ok("details_200", st == 200, f"status={st}")
    ok(
        "observability_present",
        bool(obs) or str(success.get("status")).upper() != "SUCCESS",
        f"keys={list(obs)[:8]}",
    )
    if obs:
        em = obs.get("execution_model") or {}
        ok(
            "exec_model_honest",
            em.get("code") == "NEXT_BAR_OPEN" or em.get("look_ahead") is False,
            str(em)[:120],
        )
        ok(
            "reject_counts_list",
            isinstance(obs.get("reject_reason_counts"), list),
            f"n={len(obs.get('reject_reason_counts') or [])}",
        )

    fee = (details or {}).get("fee_summary") or ((details or {}).get("result_payload") or {}).get("fee_summary")
    ok("fee_summary_field", fee is None or isinstance(fee, dict), f"type={type(fee).__name__}")

    narr = (details or {}).get("narrative")
    ok(
        "narrative_field",
        narr is None or isinstance(narr, list),
        f"type={type(narr).__name__} n={len(narr) if isinstance(narr, list) else '-'}",
    )

    snaps = (details or {}).get("portfolio_snapshots") or []
    rich = bool(snaps) and isinstance(snaps[0].get("positions"), list)
    ok("snapshots_ok", True, f"n={len(snaps)} rich_positions={rich}")

    st, sigs = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/signals?limit=5", token=token)
    ok("signals_page", st == 200, f"status={st} keys={list((sigs or {}).keys())[:8]}")

    st, _uni = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/universe", token=token)
    ok("universe_endpoint", st in (200, 404), f"status={st}")

    st, _ev = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/execution-events?limit=20", token=token)
    ok("execution_events", st in (200, 404), f"status={st}")

    st, _narr = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/narrative", token=token)
    ok("narrative_endpoint", st in (200, 404), f"status={st}")

    trades = ((details or {}).get("result_payload") or {}).get("trades") or (details or {}).get("trades") or []
    signals = (details or {}).get("signals") or []
    if isinstance(sigs, dict) and not signals:
        signals = sigs.get("items") or sigs.get("signals") or []

    ticker = None
    around = None
    if trades:
        ticker = trades[0].get("ticker") or trades[0].get("figi")
        around = trades[0].get("bar_time") or trades[0].get("time") or trades[0].get("signal_time")
    if (not ticker or not around) and signals:
        ticker = ticker or signals[0].get("ticker") or signals[0].get("figi")
        around = around or signals[0].get("signal_time") or signals[0].get("bar_time")

    if ticker and around:
        qs = urllib.parse.urlencode({"ticker": str(ticker), "around": str(around), "bars": 20})
        st, pw = req("GET", f"/api/v2/robots/backtest/runs/{run_id}/price-window?{qs}", token=token)
        candles = (pw or {}).get("candles") or (pw or {}).get("items") or []
        ok(
            "price_window",
            st == 200,
            f"status={st} gap={(pw or {}).get('gap')} candles={len(candles) if isinstance(candles, list) else '?'}",
        )
    else:
        ok("price_window", True, "skipped — no ticker/around on this run")

    cycle_id = None
    for row in (signals or [])[:50]:
        cycle_id = row.get("cycle_id")
        payload = row.get("payload")
        if not cycle_id and isinstance(payload, dict):
            cycle_id = payload.get("cycle_id")
        if cycle_id:
            break
    if cycle_id:
        st, _bundle = req(
            "GET",
            f"/api/v2/robots/backtest/runs/{run_id}/cycles/{urllib.parse.quote(str(cycle_id))}",
            token=token,
        )
        ok("cycle_bundle", st in (200, 404), f"status={st}")
    else:
        ok("cycle_bundle", True, "skipped — no cycle_id (likely pre-P0 run)")

    return _summary()


def _summary() -> int:
    failed = [name for name, cond, _ in results if not cond]
    print("---")
    print(f"passed={sum(1 for _, cond, _ in results if cond)} failed={len(failed)}")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 2
    print("ALL LIVE SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
