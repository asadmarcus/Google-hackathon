"""
WebSocket Manager — Real-Time Signal Push to Flutter
=====================================================
Manages WebSocket connections for real-time signal broadcasting.
Flutter app connects once and receives live updates as signals arrive.

Architecture:
  ┌──────────────────────────────────────────┐
  │          WebSocket Manager               │
  │                                          │
  │  Flutter App ←──── ws://host/ws/signals  │
  │                                          │
  │  On new signal:                          │
  │    1. Store in SQLite                    │
  │    2. Broadcast to all connected clients │
  │    3. Filter by zone subscription        │
  │                                          │
  │  Subscriptions:                          │
  │    /ws/signals              → all zones  │
  │    /ws/signals?zone=g10    → one zone   │
  │    /ws/signals?min_sev=7   → high only  │
  └──────────────────────────────────────────┘

Usage in Flutter:
  final channel = WebSocketChannel.connect(
    Uri.parse('ws://localhost:8000/ws/signals?zone=islamabad-g10')
  );
  channel.stream.listen((message) {
    final signal = jsonDecode(message);
    // Update UI
  });

Author: CIRO Team
"""
import asyncio
import json
import logging
from typing import Set, Dict, Optional, List
from dataclasses import dataclass, field
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("ciro.websocket")


@dataclass
class ClientSubscription:
    """Represents a connected WebSocket client and their filter preferences."""
    websocket: WebSocket
    zone_filter: Optional[str] = None      # None = all zones
    min_severity: int = 0                   # 0 = all severities
    signal_types: Optional[List[str]] = None  # None = all types
    connected_at: str = ""


class WebSocketManager:
    """
    Manages WebSocket connections and broadcasts signals in real-time.
    
    Features:
      - Multiple simultaneous client connections
      - Per-client filtering (zone, severity, type)
      - Automatic cleanup on disconnect
      - Connection count metrics
      - Graceful error handling (one bad client doesn't crash others)
    
    Usage:
        manager = WebSocketManager()
        
        # In WebSocket endpoint:
        await manager.connect(websocket, zone_filter="islamabad-g10")
        
        # When new signals arrive:
        await manager.broadcast_signals(new_signals)
    """

    def __init__(self):
        self._clients: List[ClientSubscription] = []
        self._lock = asyncio.Lock()
        
        # Metrics
        self.total_connections = 0
        self.total_messages_sent = 0
        self.total_broadcasts = 0

    @property
    def active_connections(self) -> int:
        """Number of currently connected clients."""
        return len(self._clients)

    async def connect(
        self,
        websocket: WebSocket,
        zone_filter: Optional[str] = None,
        min_severity: int = 0,
        signal_types: Optional[List[str]] = None,
    ) -> ClientSubscription:
        """
        Accept a new WebSocket connection and register the client.
        
        Args:
            websocket: The FastAPI WebSocket instance
            zone_filter: Only send signals for this zone (None = all)
            min_severity: Only send signals with severity >= this value
            signal_types: Only send these signal types (None = all)
            
        Returns:
            The ClientSubscription object for this connection.
        """
        await websocket.accept()
        
        from datetime import datetime
        client = ClientSubscription(
            websocket=websocket,
            zone_filter=zone_filter,
            min_severity=min_severity,
            signal_types=signal_types,
            connected_at=datetime.utcnow().isoformat(),
        )
        
        async with self._lock:
            self._clients.append(client)
        
        self.total_connections += 1
        
        logger.info(
            f"🔌 WebSocket connected (total: {self.active_connections}) "
            f"[zone={zone_filter or 'all'}, min_sev={min_severity}]"
        )
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "CIRO real-time signal stream",
            "filters": {
                "zone": zone_filter or "all",
                "min_severity": min_severity,
                "signal_types": signal_types or "all",
            },
            "active_clients": self.active_connections,
        })
        
        return client

    async def disconnect(self, client: ClientSubscription) -> None:
        """Remove a client from the active connections."""
        async with self._lock:
            if client in self._clients:
                self._clients.remove(client)
        
        logger.info(f"🔌 WebSocket disconnected (remaining: {self.active_connections})")

    async def broadcast_signals(self, signals: List[Dict]) -> int:
        """
        Broadcast new signals to all connected clients.
        Applies per-client filters before sending.
        
        Args:
            signals: List of signal dicts to broadcast.
            
        Returns:
            Number of messages sent across all clients.
        """
        if not self._clients:
            return 0
        
        self.total_broadcasts += 1
        messages_sent = 0
        disconnected = set()
        
        async with self._lock:
            clients = list(self._clients)  # Copy to avoid modification during iteration
        
        for client in clients:
            # Filter signals for this client
            filtered = self._filter_for_client(signals, client)
            
            if not filtered:
                continue
            
            try:
                # Send each matching signal as a separate message
                for signal in filtered:
                    await client.websocket.send_json({
                        "type": "signal",
                        "data": signal,
                    })
                    messages_sent += 1
                    
            except (WebSocketDisconnect, RuntimeError, Exception) as e:
                logger.debug(f"Client disconnected during broadcast: {e}")
                disconnected.add(client)
        
        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for c in disconnected:
                    if c in self._clients:
                        self._clients.remove(c)
        
        self.total_messages_sent += messages_sent
        return messages_sent

    async def broadcast_alert(self, alert: Dict) -> None:
        """
        Broadcast a high-priority alert to ALL connected clients (ignores filters).
        Used by Agent 4 for critical notifications.
        """
        if not self._clients:
            return
        
        disconnected = set()
        
        async with self._lock:
            clients = list(self._clients)
        
        for client in clients:
            try:
                await client.websocket.send_json({
                    "type": "alert",
                    "priority": "critical",
                    "data": alert,
                })
            except Exception:
                disconnected.add(client)
        
        if disconnected:
            async with self._lock:
                for c in disconnected:
                    if c in self._clients:
                        self._clients.remove(c)

    def _filter_for_client(self, signals: List[Dict], client: ClientSubscription) -> List[Dict]:
        """Apply client's subscription filters to a signal batch."""
        filtered = []
        
        for signal in signals:
            # Zone filter
            if client.zone_filter and signal.get("zone_id") != client.zone_filter:
                continue
            
            # Severity filter
            if signal.get("severity", 0) < client.min_severity:
                continue
            
            # Type filter
            if client.signal_types and signal.get("signal_type") not in client.signal_types:
                continue
            
            filtered.append(signal)
        
        return filtered

    def get_metrics(self) -> Dict:
        """Get WebSocket manager metrics."""
        return {
            "active_connections": self.active_connections,
            "total_connections_ever": self.total_connections,
            "total_messages_sent": self.total_messages_sent,
            "total_broadcasts": self.total_broadcasts,
            "clients": [
                {
                    "zone_filter": c.zone_filter or "all",
                    "min_severity": c.min_severity,
                    "connected_at": c.connected_at,
                }
                for c in self._clients
            ],
        }


# Global instance
ws_manager = WebSocketManager()
