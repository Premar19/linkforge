import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.database import tenant_scoped_session
from app.models import Click, Link
from app.security import decode_access_token

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

POLL_INTERVAL_SECONDS = 2


@router.get("/stream")
async def stream_click_counts(token: str = Query(...)):
    """
    Server-Sent Events stream of live per-link click counts, scoped to the
    caller's tenant via the exact same tenant_scoped_session/RLS mechanism
    as every other authenticated route.

    One deliberate exception to "auth always via header": browsers'
    EventSource API cannot send custom headers, so the JWT travels as a
    query parameter here instead. It's validated identically
    (decode_access_token) to the header-based flow everywhere else.

    Implementation is poll-based (re-query Postgres every few seconds),
    not push-based — simpler and correct for this scale. A stricter-latency
    production version could use Postgres LISTEN/NOTIFY or have the worker
    publish to a Redis pub/sub channel directly after each insert instead.
    """
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    async def event_generator():
        while True:
            async with tenant_scoped_session(payload.tenant_id) as session:
                result = await session.execute(
                    select(
                        Link.code,
                        Link.target_url,
                        Link.is_active,
                        func.count(Click.id).label("clicks"),
                    )
                    .outerjoin(Click, Click.link_id == Link.id)
                    .group_by(Link.id)
                    .order_by(Link.created_at.desc())
                )
                rows = [
                    {
                        "code": code,
                        "target_url": target_url,
                        "is_active": is_active,
                        "clicks": clicks,
                    }
                    for code, target_url, is_active, clicks in result.all()
                ]
            yield f"data: {json.dumps(rows)}\n\n"
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
