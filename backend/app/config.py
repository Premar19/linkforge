from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central app config, loaded from environment / .env.
    Two DB URLs on purpose:
      - database_url: the low-privilege runtime role (RLS enforced against it)
      - database_url_migrations: the owning role, used only by Alembic to
        create tables / roles / policies. The app never connects with this one.
    """
    database_url_redirect: str
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    database_url_migrations: str
    # Separate low-privilege role used ONLY by signup/login, where no tenant
    # is known yet so the normal tenant-scoped RLS policy can't apply. See
    # migration 0001 for the narrowly-scoped policy this role gets.
    database_url_authn: str
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


settings = Settings()
