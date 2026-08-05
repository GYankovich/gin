"""Deprecated: use nginx TLS + plain HTTP WS gateway (see docs/DEPLOY-NEFOR.md)."""
raise SystemExit(
 "run_ws_https.py is deprecated. "
 "Production: nginx SSL → HTTP :8001 (python backend/run.py ws). "
 "See docs/DEPLOY-NEFOR.md"
)
