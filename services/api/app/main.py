from fastapi import FastAPI

from app.api.routes import planning_profile

app = FastAPI(title="Room for Both API")

app.include_router(planning_profile.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "room-for-both-api"}
