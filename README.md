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
- [x] Week 1: data model, JWT auth w/ tenant claims, RLS policies, create+redirect
- [x] Week 2: Redis cache, arq worker for async click tracking, per-tenant rate limiting
- [ ] Week 3: React dashboard (SSE), k6 load test + published numbers, Docker Compose, Fly.io deploy

### Week 1 retrospective
- Automated tenant-isolation test caught a real bug: initial RLS design put
  both the tenant-scoped policy and the public-redirect policy on the same
  DB role. Postgres OR's permissive policies per role+command, so the
  dashboard's list-links query was unintentionally exposed to every
  tenant's active links via the redirect policy.
- Fixed by splitting into a dedicated `linkforge_redirect` role with no
  other table access — migration 0002.

### Week 2 retrospective
- Redis-cached the redirect lookup (`link:{code}` → JSON of id/tenant_id/
  target_url, 5 min TTL) so repeated hits skip Postgres entirely — this is
  the baseline the Week 3 load test will measure against.
- Click tracking is fully decoupled from the redirect path: the handler
  enqueues a job onto Redis (via `arq`) and returns immediately; a separate
  worker process does the actual Postgres write on its own schedule.
- Caught a second real bug via the worker's own error logs (not a
  pre-written test this time, just watching it run): `linkforge_worker` was
  granted **INSERT only** on `clicks` (least-privilege, by design), but
  SQLAlchemy's ORM auto-appends a `RETURNING` clause to fetch
  server-generated columns (`created_at`) back into Python — and Postgres
  requires **SELECT** privilege for anything named in `RETURNING`, not just
  INSERT. Fixed by switching the worker to a raw SQL `INSERT` with no
  `RETURNING`, so the true minimum privilege (INSERT-only) actually holds.
  Worth knowing cold for an interview: "least privilege" has to account for
  what your ORM does under the hood, not just what your code appears to ask
  for.
- Also relied on `arq`'s built-in retry to prove the pipeline is resilient:
  jobs that failed against the old worker code were still sitting in the
  queue and succeeded automatically once the bug was fixed and the worker
  restarted — nothing was silently dropped.
- Rate limiting: fixed-window per-tenant counter in Redis (`INCR` +
  `EXPIRE`), scoped to tenant_id from the JWT, not per-user — a heavy
  individual still counts against their whole team's shared quota.
