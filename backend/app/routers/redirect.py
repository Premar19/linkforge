from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_redirect_db
from app.models import Link

router = APIRouter(tags=["redirect"])


@router.get("/r/{code}")
async def redirect_to_target(code: str, session: AsyncSession = Depends(get_redirect_db)):
    """
    Deliberately public — no JWT, no tenant context set. Runs as the
    `linkforge_redirect` role, which has ONLY the `public_redirect_read`
    policy and ONLY SELECT on `links` (see migration 0002). This role is
    NEVER shared with authenticated dashboard queries — that separation is
    exactly what fixes the cross-tenant leak the isolation test caught
    (`linkforge_app` used to hold both policies, and Postgres ORs permissive
    policies together per role+command, so the dashboard's list query was
    unintentionally exposed to every tenant's active links).

    Week 1's naive version: hits Postgres on every request. Week 2 puts
    Redis in front of this exact lookup — keep this handler as the "before"
    baseline for the load test, don't optimise it yet.
    """
    result = await session.execute(select(Link).where(Link.code == code))
    link = result.scalar_one_or_none()

    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")

    return RedirectResponse(url=link.target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)