"""fix cross-tenant leak: split public redirect role from app role

The 0001 migration put both `tenant_isolation` and `public_redirect_read` on
the SAME role (linkforge_app). Postgres OR's permissive policies together
per (table, command, role) — not per query/endpoint — so `list_links()`
(a SELECT via linkforge_app) was unintentionally covered by
`public_redirect_read` too, letting any tenant see any OTHER tenant's active
links through the dashboard. Caught by tests/test_tenant_isolation.py.

Fix: give the public redirect lookup its own role (`linkforge_redirect`)
that has ONLY the public-read policy and ONLY SELECT on `links` — nothing
else, no other tables. `linkforge_app` goes back to tenant_isolation only.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-07
"""
import os

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

REDIRECT_DB_PASSWORD = os.environ.get("REDIRECT_DB_PASSWORD", "changeme_redirect")


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'linkforge_redirect') THEN
                CREATE ROLE linkforge_redirect LOGIN PASSWORD '{REDIRECT_DB_PASSWORD}' NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )

    # Remove the leaky policy from linkforge_app entirely.
    op.execute("DROP POLICY IF EXISTS public_redirect_read ON links")

    # Re-create it scoped ONLY to the new, narrow role.
    op.execute(
        """
        CREATE POLICY public_redirect_read ON links
        FOR SELECT
        TO linkforge_redirect
        USING (is_active = true)
        """
    )

    # linkforge_redirect can ONLY read links — no users/tenants access at all,
    # and no INSERT/UPDATE/DELETE even on links.
    op.execute("GRANT SELECT ON links TO linkforge_redirect")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS public_redirect_read ON links")
    op.execute(
        """
        CREATE POLICY public_redirect_read ON links
        FOR SELECT
        TO linkforge_app
        USING (is_active = true)
        """
    )
    op.execute("REVOKE SELECT ON links FROM linkforge_redirect")
    op.execute("DROP ROLE IF EXISTS linkforge_redirect")
