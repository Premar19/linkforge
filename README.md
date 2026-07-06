# LinkForge — Multi-Tenant Link Shortening & Analytics Platform

Status: **Week 1 in progress** (data model, auth, RLS, basic create+redirect)

## Why this project exists
Companion portfolio piece to a solo-built AI/RAG project (KidneyWise), specifically
scoped to demonstrate backend/infra depth that a pure AI project doesn't cover:
multi-tenancy, database-enforced isolation, caching, async processing, and
measured performance under load.

## Architecture (target, end of Week 3)

```
                     ┌─────────────┐
   Browser  ───────► │   FastAPI   │──────► Postgres (RLS, tenant_id)
  (dashboard)         │   API       │           ▲
                     └──────┬──────┘           │ SET LOCAL app.tenant_id
                            │                    │
                     ┌──────▼──────┐      ┌──────┴──────┐
                     │   Redis     │◄─────│  arq worker │
                     │ (cache +    │      │ (async click│
                     │  queue)     │      │  writes)    │
                     └─────────────┘      └─────────────┘
```

## Tech stack
- **Backend**: FastAPI (async), SQLAlchemy 2.0 (asyncpg), Pydantic v2
- **DB**: PostgreSQL with Row-Level Security (shared schema, `tenant_id` column)
- **Cache/Queue**: Redis + `arq`
- **Frontend**: React + TypeScript + Vite (Week 3)
- **Load testing**: k6 (Week 3)
- **Infra**: Docker Compose (local), Fly.io (deployed demo)

## Key design decisions (worth reading before you touch the code)

1. **RLS, not app-level `WHERE tenant_id = ...` filtering.** Every tenant-scoped
   query is enforced at the database layer. Even if a route handler forgets a
   filter, Postgres refuses to return or mutate another tenant's rows.
2. **Tenant context travels via `SET LOCAL app.tenant_id`, scoped to a single
   transaction.** Set once per request from the JWT's `tenant_id` claim, then
   every query in that request is automatically scoped — no per-query
   boilerplate, no way to forget it.
3. **Two permissive policies on `links`, not two DB roles.** Postgres OR's
   permissive policies together for the same command type. So `links` has:
   - `tenant_isolation`: tenant members can CRUD only their own rows
   - `public_redirect_read`: anyone can `SELECT` an *active* link by code,
     with no tenant context required — because resolving a short link is
     supposed to be public. This is intentional, not a leak: the isolation
     boundary that matters is "Tenant A cannot list/edit Tenant B's links,"
     not "nobody but the owner can ever resolve the redirect."
4. **App DB role has `NOSUPERUSER` / is not the table owner, and RLS is
   `FORCE`d.** Table owners bypass RLS by default in Postgres — a mistake
   that silently defeats the whole scheme. See migration `0001`.

## Local setup
```bash
cp .env.example .env
docker compose up -d db redis
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

## Progress log (fill in as you go — this becomes your CV bullets later)
- [ ] Week 1: data model, JWT auth w/ tenant claims, RLS policies, create+redirect
- [ ] Week 2: Redis cache, arq worker for async click tracking, per-tenant rate limiting
- [ ] Week 3: React dashboard (SSE), k6 load test + published numbers, Docker Compose, Fly.io deploy
