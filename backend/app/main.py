from fastapi import FastAPI

app = FastAPI(title="Youtube Clone API", version="1.0.0", docs_url="/docs")


@app.get("api/health", tags=["system"])
async def health():
    return {"status": "ok"}
