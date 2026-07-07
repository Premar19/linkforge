from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central app config, loaded from environment / .env.
    Two DB URLs on purpose:
      - database_url: the low-privilege runtime role (RLS enforced against it)
      - database_url_migrations: the owning role, used only by Alembic to
        create tables / roles / policies. The app never connects with this one.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    database_url_migrations: str
    # Separate low-privilege role used ONLY by signup/login, where no tenant
    # is known yet so the normal tenant-scoped RLS policy can't apply. See
    # migration 0001 for the narrowly-scoped policy this role gets.
    database_url_authn: str
    # Separate low-privilege role for the public /r/{code} redirect lookup
    # only — deliberately its own role (not linkforge_app) so its public-read
    # policy can never be OR'd into authenticated dashboard queries. See
    # migration 0002 for why this had to be split out.
    database_url_redirect: str
    # Separate low-privilege role for the arq worker that writes click
    # events. INSERT-only on `clicks`, nothing else — the worker never
    # needs to read anything, just record what the redirect handler
    # already looked up.
    database_url_worker: str
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


settings = Settings()
