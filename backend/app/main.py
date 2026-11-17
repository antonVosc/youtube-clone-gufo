from fastapi import FastAPI

from app.routers import auth, media, videos

app = FastAPI(title="TubeClone API", version="1.0.0", docs_url="/docs")

for r in (auth.router, videos.router, media.router):
    app.include_router(r)


@app.get("api/health", tags=["system"])
async def health():
    return {"status": "ok"}
