import time

from fastapi import Depends, HTTPException, status

from app.deps import get_current_token
from app.redis_client import redis_client
from app.security import TokenPayload


def rate_limiter(*, times: int, seconds: int, key_prefix: str):
    """
    Fixed-window per-tenant rate limiter. Factory function — call it with
    limits, get back a FastAPI dependency:

        Depends(rate_limiter(times=5, seconds=60, key_prefix="create_link"))

    Keyed by tenant_id (from the verified JWT) + the current time window,
    so it's Tenant A vs Tenant B, not user vs user — a heavy individual
    user still counts against their whole team's shared quota, which is
    the usual real-world intent ("this workspace is rate-limited", not
    "this one person is").

    Fixed-window (not sliding/token-bucket) is the simplest correct
    version: cheap, one INCR + one EXPIRE per request, no background
    cleanup needed since Redis expires the key itself. Trade-off worth
    knowing: a burst right at a window boundary can momentarily allow up
    to ~2x the limit (e.g. a burst at 0:59 and another at 1:00) — a
    sliding-window log would avoid that at the cost of more Redis calls
    per request. Fine for this use case, worth saying out loud in an
    interview if asked "what would you improve."
    """

    async def dependency(token: TokenPayload = Depends(get_current_token)):
        window = int(time.time() // seconds)
        key = f"ratelimit:{key_prefix}:{token.tenant_id}:{window}"

        count = await redis_client.incr(key)
        if count == 1:
            # Only set on the first request in this window — subsequent
            # INCRs on the same key must NOT reset the TTL, or a steady
            # trickle of requests could keep the key alive forever.
            await redis_client.expire(key, seconds)

        if count > times:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Rate limit exceeded: max {times} requests per {seconds}s for this tenant",
            )

    return dependency
