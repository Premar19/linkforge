"""clicks table for async click tracking + linkforge_worker role

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-08
"""
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

WORKER_DB_PASSWORD = os.environ.get("WORKER_DB_PASSWORD", "changeme_worker")


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'linkforge_worker') THEN
                CREATE ROLE linkforge_worker LOGIN PASSWORD '{WORKER_DB_PASSWORD}' NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "clicks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("links.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_clicks_tenant_id", "clicks", ["tenant_id"])
    op.create_index("ix_clicks_link_id", "clicks", ["link_id"])

    # linkforge_app can READ clicks (Week 3 dashboard will query aggregates)
    # but never writes them — only the worker does that.
    op.execute("GRANT SELECT ON clicks TO linkforge_app")
    # linkforge_worker can ONLY insert — no SELECT, no access to any other
    # table. It doesn't need to read anything; the redirect handler already
    # looked up link_id/tenant_id and just hands them to the queued job.
    op.execute("GRANT INSERT ON clicks TO linkforge_worker")

    op.execute("ALTER TABLE clicks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE clicks FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY dashboard_read ON clicks
        FOR SELECT
        TO linkforge_app
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    # The worker processes jobs for ALL tenants (it's a trusted internal
    # service, not a per-tenant-scoped user session) — so its insert policy
    # is intentionally unrestricted by tenant, same reasoning as
    # linkforge_authn's login lookup in migration 0001.
    op.execute(
        """
        CREATE POLICY worker_insert ON clicks
        FOR INSERT
        TO linkforge_worker
        WITH CHECK (true)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS worker_insert ON clicks")
    op.execute("DROP POLICY IF EXISTS dashboard_read ON clicks")
    op.drop_table("clicks")
    op.execute("DROP ROLE IF EXISTS linkforge_worker")
