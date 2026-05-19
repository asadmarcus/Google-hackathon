"""
Scheduler Service — Automatic Periodic Data Fetching
=====================================================
Uses APScheduler to automatically trigger signal collection every N minutes.
No manual /fetch calls needed — the system self-populates.

Architecture:
  ┌──────────────────────────────────────────┐
  │           APScheduler                    │
  │                                          │
  │  Every 15 min:                           │
  │    → fetch_all_zones()                   │
  │    → store in SQLite                     │
  │    → broadcast via WebSocket             │
  │    → prune expired signals               │
  │                                          │
  │  Every 24 hours:                         │
  │    → prune_expired_signals()             │
  │                                          │
  │  On startup:                             │
  │    → initial backfill (if DB empty)      │
  └──────────────────────────────────────────┘

Author: CIRO Team
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings

logger = logging.getLogger("ciro.scheduler")


class CIROScheduler:
    """
    Manages periodic background tasks for Agent 2.
    
    Jobs:
      1. fetch_cycle: Collect signals from all APIs every FETCH_INTERVAL_MINUTES
      2. prune_job: Remove expired signals daily
      3. backfill_job: One-time initial backfill on first startup
    
    Usage:
        scheduler = CIROScheduler()
        await scheduler.start(fetch_callback, prune_callback)
        # ... app runs ...
        await scheduler.shutdown()
    """

    def __init__(self):
        self._scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,       # If a job is missed, run it once (not multiple times)
                "max_instances": 1,      # Don't stack up if previous run is still going
                "misfire_grace_time": 60,  # Allow 60s late execution
            }
        )
        self._is_running = False
        self._fetch_count = 0
        self._last_fetch_time: Optional[str] = None
        self._last_fetch_duration_ms: float = 0

    async def start(
        self,
        fetch_callback,
        prune_callback,
        backfill_callback=None,
    ) -> None:
        """
        Start the scheduler with configured jobs.
        
        Args:
            fetch_callback: Async function that fetches signals from all sources.
            prune_callback: Async function that prunes expired signals.
            backfill_callback: Optional async function for initial backfill.
        """
        interval_minutes = settings.FETCH_INTERVAL_MINUTES

        # Job 1: Periodic signal fetch
        self._scheduler.add_job(
            self._wrapped_fetch,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="signal_fetch",
            name=f"Fetch signals every {interval_minutes} min",
            kwargs={"callback": fetch_callback},
        )

        # Job 2: Daily pruning at 3 AM UTC
        self._scheduler.add_job(
            self._wrapped_prune,
            trigger=CronTrigger(hour=3, minute=0),
            id="signal_prune",
            name="Prune expired signals (daily 3AM UTC)",
            kwargs={"callback": prune_callback},
        )

        # Job 3: Initial backfill (runs once, 10 seconds after startup)
        if backfill_callback:
            self._scheduler.add_job(
                backfill_callback,
                trigger="date",
                run_date=datetime.utcnow(),
                id="initial_backfill",
                name="Initial 30-day backfill",
            )

        self._scheduler.start()
        self._is_running = True
        
        logger.info(
            f"⏰ Scheduler started — fetching every {interval_minutes} min, "
            f"pruning daily at 03:00 UTC"
        )

    def add_orchestrator_job(self, callback) -> None:
        """Register the AI orchestrator job (called after scheduler.start)."""
        hours = settings.ORCHESTRATOR_INTERVAL_HOURS
        self._scheduler.add_job(
            self._wrapped_orchestrator,
            trigger=IntervalTrigger(hours=hours),
            id="ai_orchestrator_cycle",
            name=f"AI Orchestrator every {hours}h",
            kwargs={"callback": callback},
        )
        logger.info(f"⏰ Orchestrator job registered — runs every {hours}h")

    async def _wrapped_orchestrator(self, callback) -> None:
        """Wrapper for orchestrator job."""
        logger.info("🤖 AI Orchestrator cycle starting...")
        try:
            results = await callback()
            logger.info(f"🤖 AI Orchestrator cycle complete — {len(results) if results else 0} zones debated")
        except Exception as e:
            logger.error(f"🤖 AI Orchestrator cycle failed: {e}")

    async def shutdown(self) -> None:
        """Gracefully shutdown the scheduler."""
        if self._is_running:
            self._scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("⏰ Scheduler shut down")

    async def trigger_fetch_now(self, fetch_callback) -> None:
        """Manually trigger a fetch cycle (used by POST /fetch endpoint)."""
        await self._wrapped_fetch(callback=fetch_callback)

    async def _wrapped_fetch(self, callback) -> None:
        """Wrapper that tracks fetch timing and count."""
        start = datetime.utcnow()
        self._fetch_count += 1
        
        logger.info(f"⏰ Scheduled fetch #{self._fetch_count} starting...")
        
        try:
            await callback()
        except Exception as e:
            logger.error(f"⏰ Scheduled fetch failed: {e}")
        
        duration = (datetime.utcnow() - start).total_seconds() * 1000
        self._last_fetch_time = start.isoformat()
        self._last_fetch_duration_ms = duration
        
        logger.info(f"⏰ Scheduled fetch #{self._fetch_count} completed in {duration:.0f}ms")

    async def _wrapped_prune(self, callback) -> None:
        """Wrapper for prune job."""
        try:
            deleted = await callback()
            logger.info(f"⏰ Scheduled prune completed: {deleted} signals removed")
        except Exception as e:
            logger.error(f"⏰ Scheduled prune failed: {e}")

    def get_status(self) -> dict:
        """Get scheduler status and job information."""
        jobs = []
        if self._is_running:
            for job in self._scheduler.get_jobs():
                jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run": str(job.next_run_time) if job.next_run_time else None,
                })
        
        return {
            "is_running": self._is_running,
            "fetch_count": self._fetch_count,
            "last_fetch_time": self._last_fetch_time,
            "last_fetch_duration_ms": round(self._last_fetch_duration_ms, 1),
            "jobs": jobs,
            "interval_minutes": settings.FETCH_INTERVAL_MINUTES,
        }
