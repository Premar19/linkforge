from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI

from app.config import settings
from app.routers import auth, links, redirect


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One shared connection to the SAME Redis instance the arq worker
    # listens on — this is how redirect.py hands off click-tracking jobs
    # to the separate worker process (app/worker.py) without ever writing
    # to Postgres itself.
    app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.arq_pool.close()


app = FastAPI(title="LinkForge API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(links.router)
app.include_router(redirect.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
