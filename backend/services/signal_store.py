"""
Signal Store — In-Memory + Firebase Buffer
===========================================
Stores signals in a rolling 30-day buffer.
Uses in-memory storage for hackathon (swap to Firestore for production).
Provides query methods for Agent 3 feature computation.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict

logger = logging.getLogger("ciro.services.store")


class SignalStore:
    """
    Rolling 30-day signal buffer.
    In-memory for hackathon speed. Production would use Firestore.
    """

    def __init__(self):
        # In-memory store: zone_id -> list of signals
        self._store: Dict[str, List] = defaultdict(list)
        self._max_age_hours = 30 * 24  # 30 days

    async def store_signals(self, signals: List[Dict]) -> int:
        """Store a batch of signals. Returns count stored."""
        stored = 0
        for signal in signals:
            zone_id = signal.get("zone_id", "unknown")
            self._store[zone_id].append(signal)
            stored += 1
        
        # Prune old signals
        self._prune_old()
        
        return stored

    async def get_signals(self, zone_id: str, hours: int = 24) -> List:
        """Get signals for a zone within the time window."""
        from agents.agent_data_collector import Signal
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        results = []
        
        for signal_dict in self._store.get(zone_id, []):
            try:
                ts = signal_dict.get("timestamp", "")
                signal_time = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                if signal_time > cutoff:
                    results.append(Signal(**signal_dict))
            except (ValueError, TypeError):
                # If timestamp parsing fails, include anyway (recent)
                results.append(Signal(**signal_dict))
        
        return results

    async def get_all_zones_summary(self) -> Dict:
        """Get summary stats for all zones."""
        summary = {}
        for zone_id, signals in self._store.items():
            summary[zone_id] = {
                "total_signals": len(signals),
                "last_signal": signals[-1]["timestamp"] if signals else None,
            }
        return summary

    def _prune_old(self):
        """Remove signals older than max_age_hours."""
        cutoff = datetime.utcnow() - timedelta(hours=self._max_age_hours)
        
        for zone_id in list(self._store.keys()):
            self._store[zone_id] = [
                s for s in self._store[zone_id]
                if self._is_recent(s.get("timestamp", ""), cutoff)
            ]

    @staticmethod
    def _is_recent(timestamp_str: str, cutoff: datetime) -> bool:
        """Check if a timestamp is more recent than cutoff."""
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).replace(tzinfo=None)
            return ts > cutoff
        except:
            return True  # Keep if we can't parse


# ─── Firebase Integration (Production) ────────────────────────────────────────
# Uncomment below when you have Firebase credentials set up.
# For hackathon, the in-memory store above is sufficient.

"""
import firebase_admin
from firebase_admin import credentials, firestore

class FirestoreSignalStore(SignalStore):
    def __init__(self):
        super().__init__()
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        self.db = firestore.client()
    
    async def store_signals(self, signals: List[Dict]) -> int:
        batch = self.db.batch()
        for signal in signals:
            doc_ref = self.db.collection("signals").document(signal["signal_id"])
            batch.set(doc_ref, signal)
        batch.commit()
        return len(signals)
    
    async def get_signals(self, zone_id: str, hours: int = 24):
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        query = (self.db.collection("signals")
                 .where("zone_id", "==", zone_id)
                 .where("timestamp", ">=", cutoff.isoformat())
                 .order_by("timestamp", direction=firestore.Query.DESCENDING))
        docs = query.stream()
        return [Signal(**doc.to_dict()) for doc in docs]
"""
