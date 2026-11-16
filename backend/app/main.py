from fastapi import FastAPI

from app.routers import auth

app = FastAPI(title="Youtube Clone API", version="1.0.0", docs_url="/docs")

app.include_router(auth.router)


@app.get("api/health", tags=["system"])
async def health():
    return {"status": "ok"}
