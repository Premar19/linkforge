import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_redirect_db
from app.models import Link
from app.redis_client import redis_client

router = APIRouter(tags=["redirect"])

CACHE_TTL_SECONDS = 300  # how long a resolved link stays cached before we
# re-check Postgres. Trade-off: if a link is deactivated, it can still
# resolve from cache for up to this long. Fine for a link shortener; would
# need active cache invalidation on deactivate for something stricter.


@router.get("/r/{code}")
async def redirect_to_target(
    code: str,
    request: Request,
    session: AsyncSession = Depends(get_redirect_db),
):
    """
    Week 2: Redis-cached redirect, decoupled async click tracking.

    1. Check Redis first (`link:{code}`). On a hit, skip Postgres entirely
       — this is the "after" side of the Week 3 load-test comparison.
    2. On a miss, fall back to the Week 1 query (still via the narrow
       `linkforge_redirect` role + RLS), then populate the cache so the
       next request for this code is a hit.
    3. Either way, do NOT write the click to Postgres here. Enqueue a job
       onto the arq/Redis queue and return the redirect immediately — the
       separate worker process (app/worker.py) does the actual INSERT on
       its own schedule. This is what keeps a write-heavy analytics path
       from ever slowing down the latency-sensitive redirect path.
    """
    cache_key = f"link:{code}"
    cached = await redis_client.get(cache_key)

    if cached is not None:
        link_data = json.loads(cached)
        # Purpose-built counter, isolated from arq's own Redis traffic on
        # this same instance (job enqueue/dequeue also generates GETs/SETs,
        # which would otherwise contaminate Redis's own global
        # keyspace_hits/misses counters if we tried to read those instead).
        await redis_client.incr("metrics:cache_hit")
    else:
        result = await session.execute(select(Link).where(Link.code == code))
        link = result.scalar_one_or_none()
        if link is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")

        link_data = {
            "id": str(link.id),
            "tenant_id": str(link.tenant_id),
            "target_url": link.target_url,
        }
        await redis_client.set(cache_key, json.dumps(link_data), ex=CACHE_TTL_SECONDS)
        await redis_client.incr("metrics:cache_miss")

    # Fire-and-forget: enqueue click tracking, don't block the redirect on it.
    await request.app.state.arq_pool.enqueue_job("track_click", link_data["id"], link_data["tenant_id"])

    return RedirectResponse(url=link_data["target_url"], status_code=status.HTTP_307_TEMPORARY_REDIRECT)