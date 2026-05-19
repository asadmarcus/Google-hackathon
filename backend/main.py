"""
CIRO — Crisis Intelligence & Response Orchestrator
====================================================
Main FastAPI Application (Production-Grade)

Features:
  - Multi-agent architecture (Agent 2 active, 1/3/4 planned)
  - Automatic scheduled data collection (APScheduler)
  - SQLite persistent signal storage with deduplication
  - WebSocket real-time push to Flutter clients
  - Retry logic with circuit breaker on all API calls
  - Comprehensive metrics and monitoring endpoints
  - CORS configured for Flutter mobile app

Startup Flow:
  1. Initialize SQLite database
  2. Start APScheduler (auto-fetch every 15 min)
  3. Expose REST API + WebSocket endpoints
  4. Accept Flutter client connections

Author: CIRO Team
GitHub: https://github.com/asadmarcus/Fuckathon
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
import sys
from typing import Optional

from agents.agent_data_collector import router as data_collector_router
from agents.agent_predictor import router as predictor_router
from agents.agent_imagery import router as imagery_router
from agents.agent_response import router as response_router
from agents.agent_debater import router as debater_router
from agents.agent_orchestrator import router as orchestrator_router, orchestrator
from services.earth_engine_service import get_earth_engine_service
from services.signal_store import SignalStore
from services.scheduler import CIROScheduler
from services.websocket_manager import ws_manager
from services.retry_client import RetryClient
from config.settings import settings

# ─── Logging Configuration ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)-20s │ %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ciro")

# ─── Global Services ───────────────────────────────────────────────────────────
signal_store = SignalStore()
scheduler = CIROScheduler()


# ─── Application Lifespan ──────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown lifecycle.
    
    Startup:
      1. Initialize SQLite signal store
      2. Start APScheduler for periodic fetching
      
    Shutdown:
      1. Stop scheduler gracefully
      2. Close HTTP clients
    """
    logger.info("=" * 60)
    logger.info("   CIRO — Crisis Intelligence & Response Orchestrator")
    logger.info("=" * 60)
    logger.info(f"   Environment : {settings.ENVIRONMENT}")
    logger.info(f"   Zones       : {len(settings.ZONES)}")
    logger.info(f"   Fetch every : {settings.FETCH_INTERVAL_MINUTES} min")
    logger.info(f"   Buffer      : {settings.SIGNAL_BUFFER_DAYS} days")
    logger.info("=" * 60)

    # 1. Initialize database
    await signal_store.initialize()

    # 2. Initialize Earth Engine (Agent 1)
    ee_service = get_earth_engine_service()
    await ee_service.initialize()

    # 2. Start scheduler
    from agents.agent_data_collector import run_fetch_cycle
    await scheduler.start(
        fetch_callback=run_fetch_cycle,
        prune_callback=signal_store.prune_expired,
    )

    # 3. Register AI orchestrator job (runs every ORCHESTRATOR_INTERVAL_HOURS)
    scheduler.add_orchestrator_job(orchestrator.run_cycle)

    logger.info("🚀 CIRO Backend ready — accepting connections")
    logger.info("")

    yield  # App is running

    # Shutdown
    await scheduler.shutdown()
    logger.info("🛑 CIRO Backend shut down gracefully")


# ─── FastAPI Application ───────────────────────────────────────────────────────
app = FastAPI(
    title="CIRO — Crisis Intelligence & Response Orchestrator",
    description="""
## Multi-Agent AI System for Urban Crisis Prediction & Response

CIRO monitors Pakistani urban zones for flood and heatwave risks using:
- **Agent 1** (planned): Satellite imagery via GeoGemma + Earth Engine
- **Agent 2** (active): Real-time data collection from 6 API sources
- **Agent 3** (active): ML prediction (XGBoost, 30-day forecast)
- **Agent 4** (planned): Response orchestration & action simulation

### Data Sources (Agent 2):
| Source | Type | Key Required |
|--------|------|:---:|
| Open-Meteo Weather | Current + 7-day forecast + historical | ❌ FREE |
| Open-Meteo Flood (GloFAS) | 30-day river discharge forecast | ❌ FREE |
| OpenWeatherMap | Real-time weather | ✅ Free key |
| Google Maps Traffic | Congestion data | ✅ $200 credit |
| NDMA Pakistan | Official disaster alerts | ❌ Simulated |
| Social Media | Urdu+English crisis keywords | ❌ Simulated |

### Real-Time:
Connect via WebSocket at `ws://host/ws/signals` for live signal streaming.
    """,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow Flutter app from any origin (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Agent Routers ─────────────────────────────────────────────────────────────
app.include_router(
    data_collector_router,
    prefix="/api/v1/agent2",
    tags=["Agent 2 — Data & API Collector"],
)
app.include_router(
    predictor_router,
    prefix="/api/v1/agent3",
    tags=["Agent 3 — ML Predictor"],
)
app.include_router(
    imagery_router,
    prefix="/api/v1/agent1",
    tags=["Agent 1 — Imagery & Geospatial"],
)
app.include_router(
    debater_router,
    prefix="/api/v1/debater",
    tags=["Debater — LLM Multi-Persona Debate"],
)
app.include_router(
    orchestrator_router,
    prefix="/api/v1/orchestrator",
    tags=["Orchestrator — AI Pipeline Coordinator"],
)
app.include_router(
    response_router,
    prefix="/api/v1/agent4",
    tags=["Agent 4 — Response Commander"],
)


# ─── Root Endpoints ────────────────────────────────────────────────────────
@app.get("/api", tags=["System"])
async def api_root():
    """API status overview (JSON)."""
    return {
        "service": "CIRO — Crisis Intelligence & Response Orchestrator",
        "version": "2.0.0",
        "status": "online",
        "agents": {
            "agent_1": {"name": "Imagery & Geospatial", "status": "active"},
            "agent_2": {"name": "Data & API Collector", "status": "active"},
            "agent_3_ml": {"name": "ML Predictor (XGBoost)", "status": "active"},
            "debater": {"name": "LLM Multi-Persona Debate (Gemini)", "status": "active"},
            "orchestrator": {"name": "AI Pipeline Coordinator", "status": "active"},
            "agent_4": {"name": "Response Commander", "status": "active"},
        },
        "websocket": "ws://host/ws/signals",
        "docs": "/docs",
    }


@app.get("/", include_in_schema=False)
async def dashboard():
    """Serve the Agent 2 Control Panel dashboard."""
    return FileResponse("static/index.html")


@app.get("/map", include_in_schema=False)
async def crisis_map():
    """Serve the interactive crisis map visualization."""
    return FileResponse("backend/static/crisis_map.html")


@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint for monitoring/load balancers."""
    return {
        "status": "healthy",
        "agents_active": 1,
        "scheduler_running": scheduler._is_running,
        "websocket_clients": ws_manager.active_connections,
        "database": "sqlite (persistent)",
    }


@app.get("/metrics", tags=["System"])
async def metrics():
    """
    Comprehensive system metrics.
    Shows: signal counts, API success rates, scheduler status, WebSocket stats.
    """
    store_metrics = await signal_store.get_all_metrics()
    
    return {
        "signal_store": store_metrics,
        "api_clients": RetryClient.get_all_metrics(),
        "scheduler": scheduler.get_status(),
        "websocket": ws_manager.get_metrics(),
    }


# ─── WebSocket Endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws/signals")
async def websocket_signals(
    websocket: WebSocket,
    zone: Optional[str] = Query(None, description="Filter by zone_id"),
    min_severity: int = Query(0, description="Minimum severity to receive"),
):
    """
    Real-time signal stream via WebSocket.
    
    Connect from Flutter:
      ws://host/ws/signals                    → all signals
      ws://host/ws/signals?zone=islamabad-g10 → one zone only
      ws://host/ws/signals?min_severity=7     → high severity only
    
    Messages received:
      {"type": "connected", "filters": {...}}
      {"type": "signal", "data": {...}}
      {"type": "alert", "priority": "critical", "data": {...}}
    """
    client = await ws_manager.connect(
        websocket,
        zone_filter=zone,
        min_severity=min_severity,
    )
    
    try:
        # Keep connection alive — wait for client messages or disconnect
        while True:
            # Listen for any client messages (ping/pong, filter updates)
            data = await websocket.receive_text()
            
            # Client can update filters dynamically
            import json
            try:
                msg = json.loads(data)
                if msg.get("type") == "update_filters":
                    client.zone_filter = msg.get("zone")
                    client.min_severity = msg.get("min_severity", 0)
                    await websocket.send_json({
                        "type": "filters_updated",
                        "filters": {
                            "zone": client.zone_filter,
                            "min_severity": client.min_severity,
                        }
                    })
            except json.JSONDecodeError:
                pass  # Ignore invalid messages
                
    except WebSocketDisconnect:
        await ws_manager.disconnect(client)
    except Exception:
        await ws_manager.disconnect(client)
