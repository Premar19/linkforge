import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_token, get_tenant_db
from app.models import Link
from app.rate_limit import rate_limiter
from app.schemas import LinkCreate, LinkResponse
from app.security import TokenPayload

router = APIRouter(prefix="/links", tags=["links"])


def _generate_code() -> str:
    return secrets.token_urlsafe(6)  # ~8 url-safe chars


@router.post(
    "",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limiter(times=5, seconds=60, key_prefix="create_link"))],
)
async def create_link(
    body: LinkCreate,
    db: AsyncSession = Depends(get_tenant_db),
    token: TokenPayload = Depends(get_current_token),
):
    """
    `db` is a tenant-scoped session (see app/deps.py) — the INSERT is also
    covered by the `tenant_isolation` policy's WITH CHECK clause, so even if
    tenant_id below were ever wrong, Postgres would reject the row rather
    than silently accept it. tenant_id/created_by come from the verified
    JWT, never from client-supplied input.
    """
    code = body.code or _generate_code()
    link = Link(
        tenant_id=token.tenant_id,
        created_by=token.user_id,
        code=code,
        target_url=body.target_url,
    )
    db.add(link)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Code already in use")
    return link


@router.get("", response_model=list[LinkResponse])
async def list_links(db: AsyncSession = Depends(get_tenant_db)):
    """
    No WHERE clause needed (or possible to get wrong) — RLS on `links`
    means this query only ever sees rows for the tenant in the current
    session's `app.tenant_id` GUC, set by get_tenant_db from the JWT.
    """
    result = await db.execute(select(Link).order_by(Link.created_at.desc()))
    return result.scalars().all()
