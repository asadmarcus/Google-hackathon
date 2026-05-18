"""
Retry HTTP Client — Resilient API Communication
=================================================
Production-grade HTTP client with:
  - Exponential backoff retry logic
  - Configurable max retries and timeouts
  - Circuit breaker pattern (stop calling failing APIs)
  - Request/response logging
  - Per-source success rate tracking

Architecture:
  ┌──────────────────────────────────┐
  │        RetryClient               │
  │                                  │
  │  request() ──┐                   │
  │              ▼                   │
  │  ┌─── Attempt 1 ───┐            │
  │  │   Success? ──── Return       │
  │  │   Fail? ─── Wait 1s          │
  │  ├─── Attempt 2 ───┐            │
  │  │   Success? ──── Return       │
  │  │   Fail? ─── Wait 2s          │
  │  ├─── Attempt 3 ───┐            │
  │  │   Success? ──── Return       │
  │  │   Fail? ─── Raise            │
  │  └──────────────────┘            │
  │                                  │
  │  Circuit Breaker:                │
  │  5 failures → OPEN (skip 60s)   │
  └──────────────────────────────────┘

Author: CIRO Team
"""
import httpx
import asyncio
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger("ciro.http")


@dataclass
class CircuitState:
    """Tracks circuit breaker state for a single API source."""
    failures: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False
    
    # Configuration
    failure_threshold: int = 5
    recovery_timeout: float = 60.0  # seconds before retry after circuit opens


@dataclass
class RequestMetrics:
    """Tracks request metrics per source."""
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    retries: int = 0
    avg_response_time_ms: float = 0.0
    last_request_time: Optional[str] = None
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.successful / self.total_requests * 100, 1)


class RetryClient:
    """
    HTTP client with exponential backoff, circuit breaker, and metrics.
    
    Usage:
        client = RetryClient(source_name="openweathermap")
        response = await client.get("https://api.openweathermap.org/...", params={...})
    
    Configuration:
        max_retries: Maximum retry attempts (default 3)
        base_delay: Initial delay in seconds (default 1.0)
        max_delay: Maximum delay cap in seconds (default 10.0)
        timeout: Request timeout in seconds (default 10.0)
    """

    # Class-level metrics shared across all instances
    _metrics: Dict[str, RequestMetrics] = defaultdict(RequestMetrics)
    _circuits: Dict[str, CircuitState] = defaultdict(CircuitState)

    def __init__(
        self,
        source_name: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 10.0,
        timeout: float = 10.0,
    ):
        self.source_name = source_name
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Execute a GET request with retry logic."""
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Execute a POST request with retry logic."""
        return await self._request("POST", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs) -> Optional[httpx.Response]:
        """
        Internal request handler with retries and circuit breaker.
        
        Returns:
            httpx.Response on success, None if all retries exhausted.
            
        Raises:
            Nothing — failures return None (graceful degradation).
        """
        metrics = self._metrics[self.source_name]
        circuit = self._circuits[self.source_name]
        
        # Circuit breaker check
        if circuit.is_open:
            elapsed = time.time() - circuit.last_failure_time
            if elapsed < circuit.recovery_timeout:
                logger.warning(
                    f"⚡ Circuit OPEN for {self.source_name} — skipping request "
                    f"(retry in {int(circuit.recovery_timeout - elapsed)}s)"
                )
                return None
            else:
                # Half-open: allow one request through
                logger.info(f"⚡ Circuit half-open for {self.source_name} — attempting recovery")
                circuit.is_open = False
                circuit.failures = 0
        
        # Attempt request with retries
        last_error = None
        for attempt in range(self.max_retries + 1):
            start_time = time.time()
            metrics.total_requests += 1
            
            try:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                
                # Success
                elapsed_ms = (time.time() - start_time) * 1000
                metrics.successful += 1
                metrics.avg_response_time_ms = (
                    (metrics.avg_response_time_ms * (metrics.successful - 1) + elapsed_ms)
                    / metrics.successful
                )
                metrics.last_request_time = datetime.now().isoformat()
                
                # Reset circuit on success
                circuit.failures = 0
                circuit.is_open = False
                
                return response
                
            except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as e:
                last_error = e
                metrics.failed += 1
                
                if attempt < self.max_retries:
                    # Exponential backoff: 1s, 2s, 4s (capped at max_delay)
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    metrics.retries += 1
                    
                    logger.warning(
                        f"⚠️ {self.source_name} attempt {attempt + 1}/{self.max_retries + 1} failed: "
                        f"{type(e).__name__}. Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    # All retries exhausted
                    circuit.failures += 1
                    circuit.last_failure_time = time.time()
                    
                    if circuit.failures >= circuit.failure_threshold:
                        circuit.is_open = True
                        logger.error(
                            f"🔴 Circuit OPENED for {self.source_name} after "
                            f"{circuit.failures} consecutive failures. "
                            f"Will retry in {circuit.recovery_timeout}s."
                        )
                    else:
                        logger.error(
                            f"✗ {self.source_name} failed after {self.max_retries + 1} attempts: "
                            f"{type(last_error).__name__}: {last_error}"
                        )
        
        return None

    @classmethod
    def get_all_metrics(cls) -> Dict[str, Dict]:
        """Get metrics for all tracked sources."""
        return {
            source: {
                "total_requests": m.total_requests,
                "successful": m.successful,
                "failed": m.failed,
                "retries": m.retries,
                "success_rate_pct": m.success_rate,
                "avg_response_time_ms": round(m.avg_response_time_ms, 1),
                "last_request": m.last_request_time,
                "circuit_open": cls._circuits[source].is_open,
            }
            for source, m in cls._metrics.items()
        }

    async def close(self):
        """Close the underlying HTTP client."""
        await self._client.aclose()


# Import datetime here to avoid circular imports
from datetime import datetime
