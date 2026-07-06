from fastapi import FastAPI

from app.routers import auth, links, redirect

app = FastAPI(title="LinkForge API")

app.include_router(auth.router)
app.include_router(links.router)
app.include_router(redirect.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
