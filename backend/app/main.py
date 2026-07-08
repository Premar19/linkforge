from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, dashboard, links, redirect


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

# The React dashboard runs on a different origin (Vite's dev server, or a
# separately-hosted build later) — without this, the browser blocks both
# the REST calls AND the EventSource stream. allow_credentials is False
# since auth travels via Bearer token / query param, never cookies, so we
# don't need the browser to send/receive cookies cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(links.router)
app.include_router(redirect.router)
app.include_router(dashboard.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
