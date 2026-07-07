"""
One-off local script: bulk-creates a tenant, a user, and N links directly in
Postgres, bypassing the API entirely — including its 5-request/min rate
limit on POST /links, which would make seeding hundreds of links through
the real endpoint impractically slow (500 links / 5 per min = 100 minutes).

This is test-data setup, not production code — connecting straight to
Postgres as the owning role is fine here in a way it would NOT be for
actual application logic (see the whole point of Week 1's role separation).

Writes the resulting list of link codes to seeded_codes.json, which the k6
scripts read.

Usage (from this directory, with the backend venv active):
    python seed_links.py --count 500
"""
import argparse
import asyncio
import json
import secrets
import uuid

import asyncpg

DATABASE_DSN = "postgresql://linkforge_owner:changeme_owner@localhost:5432/linkforge"


async def main(count: int) -> None:
    conn = await asyncpg.connect(DATABASE_DSN)
    try:
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        suffix = uuid.uuid4().hex[:8]

        await conn.execute(
            "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
            tenant_id,
            "Load Test Tenant",
            f"loadtest-{suffix}",
        )
        await conn.execute(
            "INSERT INTO users (id, tenant_id, email, hashed_password, role) "
            "VALUES ($1, $2, $3, $4, 'owner')",
            user_id,
            tenant_id,
            f"loadtest-{suffix}@example.com",
            "not-a-real-hash-this-user-never-logs-in",
        )

        codes = [secrets.token_urlsafe(6) for _ in range(count)]
        rows = [
            (uuid.uuid4(), tenant_id, user_id, code, "https://example.com", True)
            for code in codes
        ]
        await conn.executemany(
            "INSERT INTO links (id, tenant_id, created_by, code, target_url, is_active) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            rows,
        )

        with open("seeded_codes.json", "w") as f:
            json.dump(codes, f)

        print(f"Seeded {count} links for tenant {tenant_id}.")
        print("Codes written to seeded_codes.json")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(main(args.count))
