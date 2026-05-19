"""
Gemini Rate-Limit Retry Decorator
===================================
Wraps any async function that calls the Gemini REST API with exponential
backoff on HTTP 429 (Too Many Requests) responses.

Usage:
    from services.gemini_retry import gemini_retry

    @gemini_retry(max_retries=5, base_delay=2.0)
    async def _call_gemini(self, prompt: str) -> str:
        ...
"""
import asyncio
import functools
import logging
import random
from typing import Callable, TypeVar

import httpx

logger = logging.getLogger("ciro.gemini_retry")

F = TypeVar("F", bound=Callable)


def gemini_retry(max_retries: int = 5, base_delay: float = 2.0) -> Callable[[F], F]:
    """
    Decorator factory — retries the wrapped async function on Gemini 429s.

    Backoff formula: base_delay * 2^attempt + uniform(0, 1) seconds
    Example delays:  2.Xs, 4.Xs, 8.Xs, 16.Xs, 32.Xs

    Raises the original exception if all retries are exhausted or if the
    error is anything other than a 429.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPStatusError as exc:
                    is_rate_limit = exc.response.status_code == 429
                    last_attempt = attempt == max_retries - 1

                    if not is_rate_limit or last_attempt:
                        raise

                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Gemini 429 — attempt {attempt + 1}/{max_retries}, "
                        f"retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)

        return wrapper  # type: ignore[return-value]
    return decorator
