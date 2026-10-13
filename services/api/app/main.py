from fastapi import FastAPI

app = FastAPI(title="Room for Both API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "room-for-both-api"}
