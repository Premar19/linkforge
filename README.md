![LinkForge live dashboard demo](linkforge-recording.gif)
# LinkForge — Multi-Tenant Link Shortening & Analytics Platform

Status: **Week 3 in progress** (load testing done; dashboard, Docker Compose, deploy still to come)

## Why this project exists
Companion portfolio piece to a solo-built AI/RAG project (KidneyWise), specifically
scoped to demonstrate backend/infra depth that a pure AI project doesn't cover:
multi-tenancy, database-enforced isolation, caching, async processing, and
measured performance under load.

## Architecture (target, end of Week 3)
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
3. **Three DB roles, not two — this split exists because of a real bug an
   automated test caught.** The first version put the "public can read
   active links" policy on the same role used for authenticated dashboard
   queries. Postgres ORs permissive policies together per role+command, so
   the dashboard's list-links query got silently OR'd with the public-read
   policy too — meaning any tenant could see any other tenant's active
   links in their own dashboard. `linkforge_app` now holds ONLY
   `tenant_isolation`; a separate `linkforge_redirect` role (SELECT-only on
   `links`, nothing else) holds `public_redirect_read` and is used
   exclusively by `GET /r/{code}`. See migration `0002` and
   `tests/test_tenant_isolation.py`, which is the test that caught this.
4. **App DB role has `NOSUPERUSER` / is not the table owner, and RLS is
   `FORCE`d.** Table owners bypass RLS by default in Postgres — a mistake
   that silently defeats the whole scheme. See migration `0001`.

## Load test results (Week 3)

**Methodology:** rather than disabling the cache in code to get a synthetic
"before" number, both scenarios ran against the exact same deployed code,
using two different traffic patterns (see `load-test/redirect_test.js`):

- **cache-miss-dominated**: each request picks a random code from a
  pre-seeded pool of 500 links (`load-test/seed_links.py`, which bypasses
  the API's rate limiter — seeding 500 links through the real endpoint at
  5/min would take over an hour). With 500 codes and a short test window,
  repeats are rare, so requests overwhelmingly miss the cache and hit
  Postgres — this stands in for the pre-Redis (Week 1) behavior without
  needing to actually revert any code.
- **cache-hit-dominated**: every request hits the *same* single code, so
  after the first request populates the cache, every subsequent request is
  served from Redis.

Both runs: k6, 20 constant VUs, 30 seconds, against `GET /r/{code}`
(redirects not followed — measuring our response, not example.com's).

| Metric | Cache-miss (~Postgres) | Cache-hit (~Redis) | Change |
|---|---|---|---|
| avg | 37.65ms | 30.66ms | −18.6% |
| p90 | 53.03ms | 43.89ms | −17.2% |
| p95 | 60.42ms | 48.82ms | −19.2% |
| max | 910.62ms | 165.16ms | **−81.9%** |
| throughput | 524 req/s | 645 req/s | **+23.1%** |

**Honest interpretation:** the typical-case gain (avg/p95, ~18-19%) is real
but modest — Postgres and Redis both run on localhost here, and this is a
single indexed lookup by unique key, which Postgres is already fast at. The
more meaningful result is the **tail latency**: worst-case response time
drops 82% (911ms → 165ms), which is exactly what caching is for in a
redirect service — not shaving the average case, but eliminating the
occasional slow request caused by connection contention under load. The
+23% throughput gain follows directly: each request holds a Postgres
connection for less time when it's served from cache instead.

Caveat for anyone reading this later: this was run entirely on localhost,
with Postgres, Redis, and the API all on the same machine. Over a real
network (app and DB in different availability zones, say), the round-trip
saved by hitting Redis instead of Postgres would likely be larger, since
network latency — not query execution — tends to dominate in that setup.
Not measured here; worth caveating rather than assuming.

Raw output: `load-test/results/` (save your own run's full k6 summary
there as a `.txt` file for the portfolio writeup).

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
- [x] Week 3a: k6 load test + published before/after numbers
- [ ] Week 3b: React dashboard (SSE)
- [ ] Week 3c: Docker Compose (full stack, one-command spin-up)
- [ ] Week 3d: Deploy to Fly.io, final README polish

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
  the baseline the Week 3 load test measures against.
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

### Week 3 retrospective (load testing)
- See "Load test results" above. Key lesson: chose to vary *traffic
  pattern* against one real deployment rather than toggle the cache in
  code — more honest, and removes any risk of the "before" measurement
  testing code that isn't actually what's deployed.
- The seed script bypasses the API's own rate limiter on purpose, since
  that limiter exists to protect real traffic, not test tooling — worth
  being able to explain that distinction if asked.