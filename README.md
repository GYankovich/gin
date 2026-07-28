# GIN Project

Backend + frontend project for trading robots and analytics.

## Quick start

### 1) Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- PostgreSQL

### 2) Clone and configure env
```powershell
cp .env.example .env
```
Edit `.env` with your PostgreSQL credentials.

### 3) Backend setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
python backend/run.py migrate
```

### 4) Frontend setup
```powershell
npm install
```

### 5) Run project
All backend processes (API + workers + WS):
```powershell
python backend/run.py all
```

Frontend dev server:
```powershell
npm run dev
```

## Useful endpoints
- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Frontend: `http://localhost:5173`