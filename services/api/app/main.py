from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, calendar, capacity, planning_profile
from app.core.config import get_settings

app = FastAPI(title="Room for Both API")

# Explicit origins only; no credentials, so a wildcard is never combined with them.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in get_settings().cors_origins if o != "*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(planning_profile.router)
app.include_router(calendar.router)
app.include_router(capacity.router)
app.include_router(analysis.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "room-for-both-api"}
