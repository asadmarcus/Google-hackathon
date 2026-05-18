"""
Signal Store — SQLite Persistent Storage
==========================================
Production-grade signal storage with:
  - SQLite persistence (survives restarts)
  - Signal deduplication (prevents duplicates on repeated fetches)
  - Indexed queries by zone, type, and timestamp
  - Automatic pruning of signals older than buffer window
  - Async-compatible via aiosqlite

Architecture:
  ┌────────────────────────────────────┐
  │         SignalStore (SQLite)        │
  │                                    │
  │  signals table                     │
  │  ├─ signal_id (PK, unique)         │
  │  ├─ signal_type                    │
  │  ├─ zone_id (indexed)             │
  │  ├─ value, severity, confidence    │
  │  ├─ source                         │
  │  ├─ timestamp (indexed)            │
  │  └─ metadata (JSON)                │
  │                                    │
  │  Indexes: zone+timestamp, type     │
  │  Auto-prune: > 30 days removed     │
  └────────────────────────────────────┘

Author: CIRO Team
"""
import aiosqlite
import json
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from config.settings import settings

logger = logging.getLogger("ciro.store")

# Database path — stored in project data/ directory
DB_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "data"
DB_PATH = DB_DIR / "signals.db"


class SignalStore:
    """
    Persistent signal storage using SQLite.
    
    Features:
      - Deduplication via UNIQUE constraint on signal_id
      - Time-based queries with indexed columns
      - Automatic pruning of expired signals
      - Metrics tracking (inserts, duplicates skipped, queries)
    
    Usage:
        store = SignalStore()
        await store.initialize()  # Call once at startup
        await store.store_signals([...])
        signals = await store.get_signals("islamabad-g10", hours=24)
    """

    def __init__(self):
        self._db_path = str(DB_PATH)
        self._max_age_hours = settings.SIGNAL_BUFFER_DAYS * 24
        self._initialized = False
        
        # Metrics
        self.metrics = {
            "total_stored": 0,
            "duplicates_skipped": 0,
            "total_queries": 0,
            "last_store_time": None,
            "last_prune_time": None,
        }

    async def initialize(self) -> None:
        """
        Create database and tables if they don't exist.
        Must be called once during application startup.
        """
        # Ensure data directory exists
        DB_DIR.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    signal_type TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    zone_name TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    value REAL NOT NULL,
                    severity INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indexes for fast queries
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_zone_time 
                ON signals(zone_id, timestamp DESC)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_type 
                ON signals(signal_type)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_source 
                ON signals(source)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_severity 
                ON signals(severity DESC)
            """)
            
            await db.commit()
        
        self._initialized = True
        logger.info(f"✓ SignalStore initialized at {self._db_path}")

    async def store_signals(self, signals: List[Dict]) -> int:
        """
        Store a batch of signals with deduplication.
        
        Args:
            signals: List of signal dictionaries matching the Signal schema.
            
        Returns:
            Number of NEW signals stored (excludes duplicates).
        """
        if not self._initialized:
            await self.initialize()
        
        stored = 0
        duplicates = 0
        
        async with aiosqlite.connect(self._db_path) as db:
            for signal in signals:
                try:
                    await db.execute("""
                        INSERT OR IGNORE INTO signals 
                        (signal_id, signal_type, zone_id, zone_name, lat, lng, 
                         value, severity, confidence, source, timestamp, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        signal["signal_id"],
                        signal["signal_type"],
                        signal["zone_id"],
                        signal["zone_name"],
                        signal["lat"],
                        signal["lng"],
                        signal["value"],
                        signal["severity"],
                        signal["confidence"],
                        signal["source"],
                        signal["timestamp"],
                        json.dumps(signal.get("metadata", {})),
                    ))
                    
                    if db.total_changes > 0:
                        stored += 1
                    else:
                        duplicates += 1
                        
                except aiosqlite.IntegrityError:
                    duplicates += 1
                except Exception as e:
                    logger.warning(f"Failed to store signal {signal.get('signal_id', '?')}: {e}")
            
            await db.commit()
        
        # Update metrics
        self.metrics["total_stored"] += stored
        self.metrics["duplicates_skipped"] += duplicates
        self.metrics["last_store_time"] = datetime.utcnow().isoformat()
        
        if duplicates > 0:
            logger.debug(f"Store: {stored} new, {duplicates} duplicates skipped")
        
        return stored

    async def get_signals(self, zone_id: str, hours: int = 24) -> List[Dict]:
        """
        Retrieve signals for a zone within a time window.
        
        Args:
            zone_id: The zone identifier (e.g., "islamabad-g10")
            hours: How many hours back to look (default 24)
            
        Returns:
            List of signal dictionaries, newest first.
        """
        if not self._initialized:
            await self.initialize()
        
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat() + "Z"
        self.metrics["total_queries"] += 1
        
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM signals 
                WHERE zone_id = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            """, (zone_id, cutoff))
            
            rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def get_signals_by_type(
        self, zone_id: str, signal_type: str, hours: int = 24
    ) -> List[Dict]:
        """Get signals filtered by both zone and type."""
        if not self._initialized:
            await self.initialize()
        
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat() + "Z"
        
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM signals 
                WHERE zone_id = ? AND signal_type = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            """, (zone_id, signal_type, cutoff))
            
            rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def get_zone_summary(self, zone_id: str) -> Dict:
        """Get summary statistics for a zone."""
        if not self._initialized:
            await self.initialize()
        
        async with aiosqlite.connect(self._db_path) as db:
            # Total signals
            cursor = await db.execute(
                "SELECT COUNT(*) FROM signals WHERE zone_id = ?", (zone_id,)
            )
            total = (await cursor.fetchone())[0]
            
            # Latest signal
            cursor = await db.execute(
                "SELECT timestamp FROM signals WHERE zone_id = ? ORDER BY timestamp DESC LIMIT 1",
                (zone_id,)
            )
            row = await cursor.fetchone()
            latest = row[0] if row else None
            
            # Signals by source
            cursor = await db.execute("""
                SELECT source, COUNT(*) as cnt 
                FROM signals WHERE zone_id = ? 
                GROUP BY source
            """, (zone_id,))
            by_source = {row[0]: row[1] for row in await cursor.fetchall()}
        
        return {
            "zone_id": zone_id,
            "total_signals": total,
            "latest_signal": latest,
            "signals_by_source": by_source,
        }

    async def get_all_metrics(self) -> Dict:
        """Get comprehensive store metrics for the /metrics endpoint."""
        if not self._initialized:
            await self.initialize()
        
        async with aiosqlite.connect(self._db_path) as db:
            # Total signals in DB
            cursor = await db.execute("SELECT COUNT(*) FROM signals")
            total = (await cursor.fetchone())[0]
            
            # Signals by source
            cursor = await db.execute("""
                SELECT source, COUNT(*) as cnt FROM signals GROUP BY source
            """)
            by_source = {row[0]: row[1] for row in await cursor.fetchall()}
            
            # Signals by zone
            cursor = await db.execute("""
                SELECT zone_id, COUNT(*) as cnt FROM signals GROUP BY zone_id
            """)
            by_zone = {row[0]: row[1] for row in await cursor.fetchall()}
            
            # Last signal per zone
            cursor = await db.execute("""
                SELECT zone_id, MAX(timestamp) as last_ts 
                FROM signals GROUP BY zone_id
            """)
            last_by_zone = {row[0]: row[1] for row in await cursor.fetchall()}
            
            # DB file size
            db_size_mb = os.path.getsize(self._db_path) / (1024 * 1024) if os.path.exists(self._db_path) else 0
        
        return {
            "database": {
                "path": self._db_path,
                "size_mb": round(db_size_mb, 2),
                "total_signals": total,
            },
            "signals_by_source": by_source,
            "signals_by_zone": by_zone,
            "last_signal_per_zone": last_by_zone,
            "runtime_metrics": self.metrics,
        }

    async def prune_expired(self) -> int:
        """
        Remove signals older than the buffer window.
        Called automatically by the scheduler.
        
        Returns:
            Number of signals deleted.
        """
        if not self._initialized:
            await self.initialize()
        
        cutoff = (datetime.utcnow() - timedelta(hours=self._max_age_hours)).isoformat() + "Z"
        
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM signals WHERE timestamp < ?", (cutoff,)
            )
            deleted = cursor.rowcount
            await db.commit()
        
        if deleted > 0:
            logger.info(f"🗑️ Pruned {deleted} expired signals (older than {settings.SIGNAL_BUFFER_DAYS} days)")
        
        self.metrics["last_prune_time"] = datetime.utcnow().isoformat()
        return deleted

    @staticmethod
    def _row_to_dict(row) -> Dict:
        """Convert a sqlite Row to a signal dictionary."""
        return {
            "signal_id": row["signal_id"],
            "signal_type": row["signal_type"],
            "zone_id": row["zone_id"],
            "zone_name": row["zone_name"],
            "lat": row["lat"],
            "lng": row["lng"],
            "value": row["value"],
            "severity": row["severity"],
            "confidence": row["confidence"],
            "source": row["source"],
            "timestamp": row["timestamp"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
        }
