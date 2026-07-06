from typing import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import tenant_scoped_session
from app.security import TokenPayload, decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_token(token: str | None = Depends(oauth2_scheme)) -> TokenPayload:
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        return decode_access_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


async def get_tenant_db(
    token: TokenPayload = Depends(get_current_token),
) -> AsyncIterator[AsyncSession]:
    """
    The dependency every authenticated, tenant-scoped route should use.
    Pulls tenant_id off the verified JWT and opens a DB session with RLS
    context set for that tenant — route handlers never see tenant_id as a
    parameter and can't accidentally query across tenants even if they try.
    """
    async with tenant_scoped_session(token.tenant_id) as session:
        yield session
