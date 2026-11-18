from fastapi import FastAPI

from app.routers import (
    admin,
    auth,
    channels,
    comments,
    feed,
    media,
    moderation,
    playlists,
    videos,
)

app = FastAPI(title="TubeClone API", version="1.0.0", docs_url="/docs")
for r in (
    auth.router,
    admin.router,
    channels.router,
    feed.router,
    videos.router,
    comments.router,
    playlists.router,
    moderation.router,
    media.router,
):
    app.include_router(r)


@app.get("/api/health", tags=["system"])
async def health():
    return {"status": "ok"}
