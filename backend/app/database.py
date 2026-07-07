from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Separate engine/pool for the narrow authn role — never used for ordinary
# request handling, only signup/login (see app/routers/auth.py).
authn_engine = create_async_engine(settings.database_url_authn, pool_pre_ping=True)
AuthnSessionLocal = async_sessionmaker(authn_engine, expire_on_commit=False)


async def get_authn_db() -> AsyncIterator[AsyncSession]:
    """
    Used only by /auth/signup and /auth/login. Connects as `linkforge_authn`,
    a role with its own narrow policy (see migration 0001) permitting reads
    across all tenants on `users`/`tenants` — necessary because at login time
    we don't yet know which tenant to scope to; that's what we're looking up.
    Password verification is still the real security gate, this role just
    solves the bootstrap problem of finding the row to check the password
    against in the first place.
    """
    async with AuthnSessionLocal() as session:
        yield session


# Separate engine/pool for the public redirect-only role. Never used for
# authenticated dashboard queries — see migration 0002 for why mixing this
# into linkforge_app caused a real cross-tenant leak.
redirect_engine = create_async_engine(settings.database_url_redirect, pool_pre_ping=True)
RedirectSessionLocal = async_sessionmaker(redirect_engine, expire_on_commit=False)


async def get_redirect_db() -> AsyncIterator[AsyncSession]:
    async with RedirectSessionLocal() as session:
        yield session


# Used by the arq worker (app/worker.py), NOT by FastAPI request handling —
# the worker is a separate process with no HTTP requests to depend-inject
# into, so this is used directly as `async with WorkerSessionLocal() as s`.
worker_engine = create_async_engine(settings.database_url_worker, pool_pre_ping=True)
WorkerSessionLocal = async_sessionmaker(worker_engine, expire_on_commit=False)


@asynccontextmanager
async def tenant_scoped_session(tenant_id: UUID) -> AsyncIterator[AsyncSession]:
    """
    DB session with RLS tenant context set for the lifetime of one transaction.

    `SET LOCAL` only survives until the end of the current transaction, so we
    open one explicitly, set the GUC, yield the session for the request to
    use, then commit/rollback on exit. This means every query issued through
    this session is automatically filtered to the caller's tenant by Postgres
    itself — there is no `WHERE tenant_id = ...` for a route handler to forget.
    """
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                # set_config's third arg (is_local=true) scopes this to the
                # current transaction only, so connections can't leak tenant
                # context across requests when pooled/reused.
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            yield session
