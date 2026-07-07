import redis.asyncio as redis

from app.config import settings

# One shared connection pool for both the redirect cache and rate limiting.
# decode_responses=True means we get back plain Python strings, not bytes.
redis_client = redis.from_url(settings.redis_url, decode_responses=True)
