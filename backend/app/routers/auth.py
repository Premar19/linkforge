from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_authn_db
from app.models import Role, Tenant, User
from app.schemas import LoginRequest, SignupRequest, TokenResponse
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_authn_db)):
    """
    Creates a brand-new tenant plus its first user (OWNER). Runs as the
    `linkforge_authn` role rather than `linkforge_app` — there's no tenant to
    scope to yet, since we're creating it, and normal tenant-isolation
    policies would block the insert.
    """
    existing = await db.execute(select(Tenant).where(Tenant.slug == body.tenant_slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tenant slug already taken")

    tenant = Tenant(name=body.tenant_name, slug=body.tenant_slug)
    db.add(tenant)
    await db.flush()  # populate tenant.id without committing yet

    user = User(
        tenant_id=tenant.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=Role.OWNER,
    )
    db.add(user)
    await db.commit()

    token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=user.role)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_authn_db)):
    result = await db.execute(
        select(User, Tenant)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(Tenant.slug == body.tenant_slug, User.email == body.email)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    user, tenant = row
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=user.role)
    return TokenResponse(access_token=token)
