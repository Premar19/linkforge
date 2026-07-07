"""
arq worker: consumes click-tracking jobs off the Redis queue and writes them
to Postgres, one row per click, as its own long-running process, separate
from the FastAPI app. Run it with:

    arq app.worker.WorkerSettings

This is what actually decouples the redirect path from the analytics
write path: GET /r/{code} never waits on a Postgres INSERT — it enqueues a
job and returns immediately. This process picks that job up and does the
(comparatively slow) database write whenever it gets to it, on its own
schedule, under its own narrowly-scoped DB role (linkforge_worker —
INSERT-only on `clicks`, nothing else, see migration 0003).
"""
import uuid

from arq.connections import RedisSettings
from sqlalchemy import text

from app.config import settings
from app.database import WorkerSessionLocal


async def track_click(ctx, link_id: str, tenant_id: str) -> None:
    """
    Deliberately a raw SQL INSERT, not the ORM's `session.add(Click(...))`.
    SQLAlchemy's ORM automatically appends `RETURNING clicks.created_at` to
    fetch that server-generated default back into the Python object — but
    Postgres requires SELECT privilege on any column named in a RETURNING
    clause, on top of INSERT. That would silently defeat the point of
    linkforge_worker being INSERT-only (see migration 0003). A plain INSERT
    with no RETURNING needs nothing beyond the INSERT grant it already has.
    """
    async with WorkerSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("INSERT INTO clicks (id, tenant_id, link_id) VALUES (:id, :tenant_id, :link_id)"),
                {"id": str(uuid.uuid4()), "tenant_id": tenant_id, "link_id": link_id},
            )


class WorkerSettings:
    functions = [track_click]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)