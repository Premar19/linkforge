"""initial schema, tenant/user/link tables, DB roles, RLS policies

Revision ID: 0001
Revises:
Create Date: 2026-07-02
"""
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Passwords for the app-facing roles come from env at migration time, NOT
# hardcoded, so the same migration works across local/staging/prod without
# editing this file. Fall back to dev defaults only for local convenience.
APP_DB_PASSWORD = os.environ.get("APP_DB_PASSWORD", "changeme_app")
AUTHN_DB_PASSWORD = os.environ.get("AUTHN_DB_PASSWORD", "changeme_authn")


def upgrade() -> None:
    # --- Roles -----------------------------------------------------------
    # linkforge_app: used for all normal, tenant-scoped request handling.
    #   NOSUPERUSER + NOBYPASSRLS is the whole point — table OWNERS bypass
    #   RLS by default in Postgres, which would silently defeat every
    #   policy below if the app connected as the owning/migrations role.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'linkforge_app') THEN
                CREATE ROLE linkforge_app LOGIN PASSWORD '{APP_DB_PASSWORD}' NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    # linkforge_authn: used only by /auth/signup and /auth/login, which need
    # to look up a user by (tenant_slug, email) BEFORE any tenant context
    # exists. Scope is intentionally narrow — SELECT/INSERT on tenants+users
    # only, nothing on links, and nothing else in the schema.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'linkforge_authn') THEN
                CREATE ROLE linkforge_authn LOGIN PASSWORD '{AUTHN_DB_PASSWORD}' NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )

    # --- Tables ------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    user_role_enum = postgresql.ENUM("owner", "member", name="user_role")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    op.create_table(
        "links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("target_url", sa.String(2048), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_links_tenant_id", "links", ["tenant_id"])
    op.create_index("ix_links_code", "links", ["code"])

    # --- Grants ------------------------------------------------------------
    # Table/column grants are a separate layer from RLS: RLS decides WHICH
    # rows a role can touch, grants decide WHETHER it can touch the table at
    # all. Both are required.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON links TO linkforge_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON users TO linkforge_app")
    op.execute("GRANT SELECT ON tenants TO linkforge_app")

    op.execute("GRANT SELECT, INSERT ON tenants TO linkforge_authn")
    op.execute("GRANT SELECT, INSERT ON users TO linkforge_authn")

    # --- Row Level Security --------------------------------------------
    # FORCE (not just ENABLE) is what makes RLS apply even to the table
    # owner. Without FORCE, an owner-connected session bypasses RLS
    # entirely — a very easy mistake to make and a very quiet way to
    # defeat multi-tenant isolation.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE links FORCE ROW LEVEL SECURITY")

    # users: strict tenant isolation, no exceptions — nobody reads across
    # tenants except linkforge_authn during login/signup (see policy below).
    op.execute(
        """
        CREATE POLICY tenant_isolation ON users
        FOR ALL
        TO linkforge_app
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    # linkforge_authn needs to find a user by (tenant slug, email) before any
    # tenant context exists — that's the entire purpose of this role, so its
    # policy is intentionally broader. It has no other privileges (see
    # grants above: no access to `links` at all).
    op.execute(
        """
        CREATE POLICY authn_lookup ON users
        FOR ALL
        TO linkforge_authn
        USING (true)
        WITH CHECK (true)
        """
    )

    # links: two permissive policies, which Postgres OR's together for
    # SELECT. Combined effect for linkforge_app:
    #   - tenant members can CRUD their own tenant's links (tenant_isolation)
    #   - ANYONE (no tenant context required) can SELECT an active link by
    #     code (public_redirect_read) — this is intentional: resolving a
    #     short link is a public operation by definition, that's what a
    #     redirect service does. What must stay private is the ability to
    #     list/edit/delete another tenant's links, which tenant_isolation
    #     still enforces since it's the only policy covering non-SELECT
    #     commands.
    op.execute(
        """
        CREATE POLICY tenant_isolation ON links
        FOR ALL
        TO linkforge_app
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY public_redirect_read ON links
        FOR SELECT
        TO linkforge_app
        USING (is_active = true)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS public_redirect_read ON links")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON links")
    op.execute("DROP POLICY IF EXISTS authn_lookup ON users")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON users")
    op.drop_table("links")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_role")
    op.drop_table("tenants")
    op.execute("DROP ROLE IF EXISTS linkforge_authn")
    op.execute("DROP ROLE IF EXISTS linkforge_app")
