# Dev / Prod runbook for nefor.online
#
# Architecture
#   Dev:  browser → Vite :5173 → proxy /api,/ws → FastAPI :8000 / WS :8001 → DB (.env)
#   Prod: browser → nginx :443 (TLS) → dist/ + HTTP :8000 / :8001 → DB (.env.production)
#         fallback nginx :8443 if ISP blocks inbound 443
#
# SSL terminates only at nginx. Uvicorn stays plain HTTP on the LAN/loopback.

## Prerequisites

- Python (same env as usual for this repo), Node/npm
- PostgreSQL reachable (local or remote)
- Prod only: DNS `nefor.online` → WAN IP, router port-forward **80→80** and **443→443**
  to this PC (dest port must match), Windows Firewall allow those ports, certs
  `nefor.online-chain.pem` + `nefor.online-key.pem` in repo root
- Keep **8080→8080** / **8443→8443** as backup if provider blocks 80/443
- Do **not** expose `:8000`, `:8001`, or RDP `:3389` to the public Internet

---

## Development (local UI, remote or local DB)

1. Copy env template and fill DB / secrets:

   ```powershell
   copy .env.example .env
   # edit .env — DB_HOST may be a remote host; DB_SSL_MODE=require if needed
   ```

2. Start API + WS + workers:

   ```powershell
   # do NOT set GIN_ENV=production
   python backend/run.py all
   ```

3. Start Vite:

   ```powershell
   npm run dev
   ```

4. Open **http://localhost:5173**

Same-origin `/api` and `/ws` go through the Vite proxy to `127.0.0.1:8000` / `:8001`.

---

## Production (https://nefor.online)

1. Env:

   ```powershell
   copy .env.production.example .env.production
   # edit .env.production — DEBUG=false, CORS includes https://nefor.online, strong SECRET_KEY
   ```

2. Build frontend:

   ```powershell
   npm run build
   ```

3. Start backend with production env file:

   ```powershell
   $env:GIN_ENV = "production"
   python backend/run.py all
   ```

   After changing `CORS_ORIGINS`, restart the backend.

4. Start nginx:

   ```powershell
   npm run nginx:start
   ```

5. Keenetic port forward (critical: **dest port = open port**):

   | Open | Dest port | Purpose |
   |------|-----------|---------|
   | TCP 80 | 80 | HTTP → redirect to https://nefor.online |
   | TCP 443 | 443 | Canonical HTTPS (no port in URL) |
   | TCP 8080 | 8080 | Backup HTTP |
   | TCP 8443 | 8443 | Backup HTTPS if 443 blocked |

6. Open **https://nefor.online** (no port). Fallback: **https://nefor.online:8443**

   Cert warning on `https://IP:...` is expected — cert is for the domain only.

### If https://nefor.online times out but :8443 works

Provider often blocks inbound **80/443** on residential plans. Options:

1. Ask ISP for a “white IP” / business plan that allows 80/443  
2. Cloudflare orange-cloud proxy: public 443 at CF → origin `https://YOUR_IP:8443` (SSL mode Full)  
3. Cloudflare Tunnel (`cloudflared`) — no port forward for web

---

## Checklist (prod)

| Item | OK |
|------|----|
| `dist/index.html` exists after `npm run build` | |
| `GIN_ENV=production` and `.env.production` loaded | |
| `python backend/run.py all` — :8000 and :8001 listening | |
| nginx listening on :80, :443, :8080, :8443 | |
| Router 80→80, 443→443 (dest = open) | |
| Firewall allows 80/443/8080/8443 | |
| :8000/:8001/:3389 not forwarded publicly | |

---

## Database notes

- All application tables live in PostgreSQL **`public`** (no `ganaly` / custom schema).
- SQL and Alembic migrations use unqualified table names; `DB_SCHEMA=public` is legacy/compat only.
- After pull: `alembic upgrade head` (includes `0053` drop of leftover unused tables).
