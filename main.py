"""
CIRO — Crisis Intelligence & Response Orchestrator
Main FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from agents.agent_data_collector import router as data_collector_router
from config.settings import settings

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ciro")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 CIRO Backend starting up...")
    logger.info(f"   Environment: {settings.ENVIRONMENT}")
    logger.info(f"   Monitored zones: {len(settings.ZONES)}")
    yield
    logger.info("🛑 CIRO Backend shutting down...")


app = FastAPI(
    title="CIRO — Crisis Intelligence & Response Orchestrator",
    description="Multi-Agent AI System for Urban Crisis Prediction & Response",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow Flutter app to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register agent routers
app.include_router(data_collector_router, prefix="/api/v1/agent2", tags=["Agent 2 — Data Collector"])


@app.get("/")
async def root():
    return {
        "service": "CIRO — Crisis Intelligence & Response Orchestrator",
        "version": "1.0.0",
        "status": "online",
        "agents": {
            "agent_1": "imagery (planned)",
            "agent_2": "data_collector (active)",
            "agent_3": "predictor (planned)",
            "agent_4": "orchestrator (planned)",
        }
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "agents_active": 1}
