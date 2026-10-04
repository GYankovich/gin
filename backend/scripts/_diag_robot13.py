"""Diagnose robots_v2 #13 start hang."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def req(method: str, path: str, token: str | None = None, data=None, timeout: int = 30):
    body = None if data is None else json.dumps(data).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
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
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}


def main() -> int:
    st, auth = req("POST", "/api/auth/login", data={"login": "gy", "password": "4272"})
    token = (auth or {}).get("access_token")
    print("login", st, bool(token))
    if not token:
        return 1

    st, robot = req("GET", "/api/v2/robots/13", token=token)
    print("get_robot", st)
    print(json.dumps(robot, ensure_ascii=False, indent=2, default=str)[:4000])

    # common status / session probes
    for path in (
        "/api/v2/robots/13/status",
        "/api/v2/robots/13/session",
        "/api/v2/robots/13/runtime",
        "/api/v2/robots/13/logs?limit=20",
        "/api/v2/robots/data",
    ):
        if path.endswith("/data"):
            st, body = req("POST", path, token=token, data={})
        else:
            st, body = req("GET", path, token=token)
        print("---", path, st)
        if isinstance(body, dict):
            print(json.dumps(body, ensure_ascii=False, default=str)[:1500])
        else:
            print(str(body)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
