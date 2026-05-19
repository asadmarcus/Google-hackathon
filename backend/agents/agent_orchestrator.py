"""
CIRO — Orchestrator Agent
==========================
Runs every ORCHESTRATOR_INTERVAL_HOURS (default: 2h).

Cycle:
  1. Fetch 30-day ML predictions for all 8 zones (Agent 3 ML)
  2. Filter zones where peak_flood_risk OR peak_heat_risk >= RISK_ALERT_THRESHOLD
  3. Pass each high-risk zone to the Debater for LLM analysis
  4. Log the full DebateResult JSON → Agent 4 input contract

Exposes:
  GET  /api/v1/orchestrator/status  — last run info, next run time
  POST /api/v1/orchestrator/run     — manually trigger a full cycle
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter

from agents.agent_debater import DebateResult, debater
from config.settings import settings

logger = logging.getLogger("ciro.orchestrator")
router = APIRouter()


# ─── Orchestrator Core ─────────────────────────────────────────────────────────

class CIROOrchestrator:
    """
    Coordinates data collection → threshold filtering → LLM debate.
    Owns the in-memory state about the last cycle.
    """

    def __init__(self):
        self._last_run: Optional[str] = None
        self._last_zones_evaluated: int = 0
        self._last_high_risk_count: int = 0
        self._last_results: List[DebateResult] = []
        self._cycle_count: int = 0

    async def _get_zone_prediction(
        self, client: httpx.AsyncClient, zone_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch 30-day ML prediction for a zone from Agent 3."""
        try:
            resp = await client.post(
                f"{settings.AGENT2_BASE_URL}/api/v1/agent3/predict/{zone_id}",
                timeout=60.0,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Prediction fetch failed for {zone_id}: {e}")
        return None

    async def _get_zone_features(
        self, client: httpx.AsyncClient, zone_id: str
    ) -> Dict[str, Any]:
        """Fetch current ML features from Agent 2."""
        try:
            resp = await client.get(
                f"{settings.AGENT2_BASE_URL}/api/v1/agent2/features/{zone_id}",
                timeout=30.0,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Features fetch failed for {zone_id}: {e}")
        return {}

    def _exceeds_threshold(self, prediction: Dict[str, Any]) -> bool:
        """Check if a zone's ML prediction exceeds the risk threshold."""
        summary = prediction.get("summary", {})
        peak_flood = summary.get("peak_flood_risk", 0.0)
        peak_heat = summary.get("peak_heat_risk", 0.0)
        threshold = settings.RISK_ALERT_THRESHOLD
        return peak_flood >= threshold or peak_heat >= threshold

    async def run_cycle(self) -> List[DebateResult]:
        """
        Full orchestration cycle. Called by APScheduler every N hours.
        Returns list of DebateResult for high-risk zones (may be empty).
        """
        self._cycle_count += 1
        cycle_start = datetime.now(timezone.utc)
        logger.info(f"🤖 Orchestrator cycle #{self._cycle_count} starting — evaluating {len(settings.ZONES)} zones")

        results: List[DebateResult] = []

        async with httpx.AsyncClient() as client:
            # Step 1: Fetch predictions for all zones in parallel
            prediction_tasks = [
                self._get_zone_prediction(client, zone["id"])
                for zone in settings.ZONES
            ]
            feature_tasks = [
                self._get_zone_features(client, zone["id"])
                for zone in settings.ZONES
            ]

            all_predictions, all_features = await asyncio.gather(
                asyncio.gather(*prediction_tasks),
                asyncio.gather(*feature_tasks),
            )

        # Step 2: Filter zones above threshold
        high_risk_zones = []
        for zone_cfg, prediction, features in zip(settings.ZONES, all_predictions, all_features):
            if prediction is None:
                logger.warning(f"No prediction for {zone_cfg['id']} — skipping")
                continue

            if self._exceeds_threshold(prediction):
                summary = prediction.get("summary", {})
                logger.info(
                    f"⚠️  {zone_cfg['name']} — flood={summary.get('peak_flood_risk', 0):.2f} "
                    f"heat={summary.get('peak_heat_risk', 0):.2f} → ABOVE threshold={settings.RISK_ALERT_THRESHOLD}"
                )

                zone_context = {
                    "province": zone_cfg.get("province", "Unknown"),
                    "population_density": zone_cfg.get("population_density", 0),
                    "drainage_capacity": zone_cfg.get("drainage_capacity", 0.5),
                    "elevation_m": zone_cfg.get("elevation_m", 0),
                    "current_rain_24h_mm": features.get("cumulative_rain_24h", features.get("rain_intensity_24h", 0.0)),
                    "current_temp_c": features.get("max_temp_24h", 0.0),
                    "current_humidity_pct": features.get("avg_humidity_24h", 0.0),
                    "glofas_discharge_ratio": features.get("glofas_discharge_ratio", 1.0),
                    "ndwi_delta": features.get("ndwi_delta", 0.0),
                }

                high_risk_zones.append({
                    "zone": zone_cfg,
                    "zone_context": zone_context,
                    "ml_prediction": prediction,
                    "threshold": settings.RISK_ALERT_THRESHOLD,
                })
            else:
                summary = prediction.get("summary", {})
                logger.debug(
                    f"✅ {zone_cfg['name']} — flood={summary.get('peak_flood_risk', 0):.2f} "
                    f"heat={summary.get('peak_heat_risk', 0):.2f} → below threshold"
                )

        logger.info(
            f"🤖 {len(high_risk_zones)}/{len(settings.ZONES)} zones above threshold={settings.RISK_ALERT_THRESHOLD}"
        )

        # Step 3: Debate each high-risk zone (sequential — each debate is already 4 LLM calls)
        for zone_data in high_risk_zones:
            try:
                debate_result = await debater.debate_zone(zone_data)
                results.append(debate_result)
            except Exception as e:
                logger.error(f"Debate failed for {zone_data['zone']['id']}: {e}")

        # Step 4: Print JSON output (Agent 4 input contract)
        if results:
            output = [r.model_dump() for r in results]
            logger.info("=" * 60)
            logger.info("🤖 DEBATE RESULTS — Agent 4 Input:")
            logger.info(json.dumps(output, indent=2, default=str))
            logger.info("=" * 60)
        else:
            logger.info("🤖 No zones above threshold — no debates triggered this cycle")

        # Cache state for status endpoint
        self._last_run = cycle_start.isoformat()
        self._last_zones_evaluated = len([p for p in all_predictions if p is not None])
        self._last_high_risk_count = len(high_risk_zones)
        self._last_results = results

        duration_s = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        for_agent4 = [r for r in results if r.agent4_ready]
        dropped = [r for r in results if not r.agent4_ready]
        logger.info(
            f"🤖 Cycle #{self._cycle_count} done in {duration_s:.1f}s — "
            f"debated={len(results)}, agent4={len(for_agent4)}, dropped={len(dropped)}"
        )
        return results

    def get_status(self) -> Dict[str, Any]:
        return {
            "cycle_count": self._cycle_count,
            "last_run": self._last_run,
            "last_zones_evaluated": self._last_zones_evaluated,
            "last_high_risk_count": self._last_high_risk_count,
            "last_results_count": len(self._last_results),
            "risk_threshold": settings.RISK_ALERT_THRESHOLD,
            "interval_hours": settings.ORCHESTRATOR_INTERVAL_HOURS,
            "total_zones": len(settings.ZONES),
        }


# Module-level singleton
orchestrator = CIROOrchestrator()


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def orchestrator_status():
    """Get orchestrator state — last run info, threshold, next interval."""
    return orchestrator.get_status()


@router.post("/run")
async def trigger_orchestrator_cycle():
    """
    Manually trigger a full orchestration cycle.
    Blocks until complete and returns all debate results.
    """
    logger.info("🤖 Manual orchestrator cycle triggered via API")
    results = await orchestrator.run_cycle()

    zones_for_agent4 = [r for r in results if r.agent4_ready]
    zones_dropped = [r for r in results if not r.agent4_ready]

    return {
        "summary": {
            "total_zones_evaluated": orchestrator._last_zones_evaluated,
            "zones_above_threshold": orchestrator._last_high_risk_count,
            "zones_debated": len(results),
            "zones_for_agent4": len(zones_for_agent4),
            "zones_dropped": len(zones_dropped),
            "threshold_used": settings.RISK_ALERT_THRESHOLD,
        },
        "agent4_queue": [
            {
                "zone_id": r.zone_id,
                "zone_name": r.zone_name,
                "trigger_type": r.trigger_type,
                "urgency": r.consensus.urgency,
                "flood_probability": r.consensus.flood_probability,
                "heat_probability": r.consensus.heat_probability,
                "primary_risk_probability": r.consensus.primary_risk_probability,
                "verdict": r.consensus.verdict,
                "action_window_days": r.consensus.recommended_action_window_days,
            }
            for r in zones_for_agent4
        ],
        "dropped": [
            {
                "zone_id": r.zone_id,
                "zone_name": r.zone_name,
                "trigger_type": r.trigger_type,
                "urgency": r.consensus.urgency,
                "flood_probability": r.consensus.flood_probability,
                "heat_probability": r.consensus.heat_probability,
                "primary_risk_probability": r.consensus.primary_risk_probability,
                "verdict": r.consensus.verdict,
            }
            for r in zones_dropped
        ],
        "full_results": [r.model_dump() for r in results],
    }
