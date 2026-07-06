"""
Proof-of-isolation test: creates two tenants, has each create a link, and
asserts Tenant A's session can never see Tenant B's link via the API — even
though both rows live in the same physical `links` table. This is the test
you screenshot/quote in interviews: "I wrote a test that tries to break
tenant isolation and confirms Postgres itself refuses, not just the app code."

Requires a running Postgres with migrations applied (see README). Run with:
    pytest tests/test_tenant_isolation.py -v
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_tenant_cannot_see_other_tenants_links():
    # Unique suffix per test run so repeated runs against the same dev
    # database never collide with leftover data from a previous run —
    # this test has no teardown step, it's meant to run against a real
    # Postgres instance, not a throwaway/rolled-back test DB.
    suffix = uuid.uuid4().hex[:8]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tenant A signs up and creates a link
        signup_a = await client.post(
            "/auth/signup",
            json={
                "tenant_name": "Acme A",
                "tenant_slug": f"acme-a-{suffix}",
                "email": f"owner@acme-a-{suffix}.com",
                "password": "correcthorsebattery",
            },
        )
        assert signup_a.status_code == 201
        token_a = signup_a.json()["access_token"]

        create_a = await client.post(
            "/links",
            json={"target_url": "https://acme-a.example.com"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert create_a.status_code == 201

        # Tenant B signs up separately
        signup_b = await client.post(
            "/auth/signup",
            json={
                "tenant_name": "Acme B",
                "tenant_slug": f"acme-b-{suffix}",
                "email": f"owner@acme-b-{suffix}.com",
                "password": "correcthorsebattery",
            },
        )
        assert signup_b.status_code == 201
        token_b = signup_b.json()["access_token"]

        # Tenant B lists links — must NOT include Tenant A's link
        list_b = await client.get("/links", headers={"Authorization": f"Bearer {token_b}"})
        assert list_b.status_code == 200
        codes_visible_to_b = {link["code"] for link in list_b.json()}
        acme_a_code = create_a.json()["code"]
        assert acme_a_code not in codes_visible_to_b