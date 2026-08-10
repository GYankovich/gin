"""Deprecated: use nginx TLS + plain HTTP uvicorn (see docs/DEPLOY-NEFOR.md)."""
raise SystemExit(
 "run_https.py is deprecated. "
 "Production: nginx SSL → HTTP :8000 (scripts/start-public.ps1 + backend/run.py). "
 "See docs/DEPLOY-NEFOR.md"
)
