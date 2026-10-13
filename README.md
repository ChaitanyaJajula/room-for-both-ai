# room-for-both-ai
A capacity-aware personal planning agent powered by NVIDIA Nemotron on Nebius Token Factory.

## Backend setup (Windows PowerShell)

Requires Python 3.12 or newer; tested with Python 3.14.

```powershell
cd services\api
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set NEBIUS_API_KEY (never commit .env)
```

If activation is blocked: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

### Run the API

```powershell
uvicorn app.main:app --reload
# http://127.0.0.1:8000/health
```

### Run tests

```powershell
pytest
```

### Test the Nemotron connection

```powershell
python -m app.services.nebius_client
```
