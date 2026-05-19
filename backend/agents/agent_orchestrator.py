"""
CIRO — Orchestrator Agent
==========================
Runs every ORCHESTRATOR_INTERVAL_HOURS (default: 2h).

Cycle:
  1. Fetch 30-day ML predictions for all 8 zones (Agent 3 ML)
  2. Filter zones where peak_flood_risk OR peak_heat_risk >= RISK_ALERT_THRESHOLD
  3. Pass each high-risk zone to the Debater for LLM analysis
  4. Send agent4_ready zones to Agent 4 for response planning + action simulation
  5. Save full orchestration log (accessible via /logs endpoint for app display)

Exposes:
  GET  /api/v1/orchestrator/status  — last run info, next run time
  POST /api/v1/orchestrator/run     — manually trigger a full cycle
  GET  /api/v1/orchestrator/logs    — full run logs (for app display)
  GET  /api/v1/orchestrator/logs/{run_id} — specific run log
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException

from agents.agent_debater import DebateResult, debater
from config.settings import settings

logger = logging.getLogger("ciro.orchestrator")
router = APIRouter()


# ─── Orchestration Log Schema ─────────────────────────────────────────────────

class OrchestrationLog:
    """Full log of a single orchestration run — stored in memory for app display."""

    def __init__(self):
        self.run_id: str = ""
        self.started_at: str = ""
        self.completed_at: str = ""
        self.duration_seconds: float = 0
        self.cycle_number: int = 0
        self.zones_evaluated: int = 0
        self.zones_above_threshold: int = 0
        self.zones_debated: int = 0
        self.zones_responded: int = 0
        self.threshold: float = 0.0
        self.steps: List[Dict[str, Any]] = []  # Trace of every step
        self.debate_results: List[Dict[str, Any]] = []
        self.agent4_responses: List[Dict[str, Any]] = []
        self.summary: Dict[str, Any] = {}

    def add_step(self, action: str, detail: str, zone_id: str = "", status: str = "ok"):
        self.steps.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "detail": detail,
            "zone_id": zone_id,
            "status": status,
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "cycle_number": self.cycle_number,
            "zones_evaluated": self.zones_evaluated,
            "zones_above_threshold": self.zones_above_threshold,
            "zones_debated": self.zones_debated,
            "zones_responded": self.zones_responded,
            "threshold": self.threshold,
            "steps": self.steps,
            "debate_results": self.debate_results,
            "agent4_responses": self.agent4_responses,
            "summary": self.summary,
        }


# ─── Orchestrator Core ─────────────────────────────────────────────────────────

class CIROOrchestrator:
    """
    Coordinates the full AI pipeline:
      Agent 3 (predict) → Debater (reason) → Agent 4 (respond + simulate)
    Saves full logs for each run.
    """

    def __init__(self):
        self._last_run: Optional[str] = None
        self._last_zones_evaluated: int = 0
        self._last_high_risk_count: int = 0
        self._last_results: List[DebateResult] = []
        self._cycle_count: int = 0
        self._run_logs: List[OrchestrationLog] = []  # All run logs (most recent first)
        self._max_logs: int = 20  # Keep last 20 runs

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

    async def _run_agent4_response(
        self, zone_id: str, zone_cfg: Dict, debate_result: DebateResult, zone_context: Dict
    ) -> Optional[Dict[str, Any]]:
        """Call Agent 4 to plan response actions for a zone."""
        from agents.agent_response import planner

        try:
            summary_data = debate_result.consensus
            raw_plan = await planner.plan_response(
                zone_id=zone_id,
                zone_name=zone_cfg["name"],
                province=zone_cfg.get("province", ""),
                debate_verdict=summary_data.verdict,
                trigger_type=debate_result.trigger_type,
                flood_prob=summary_data.flood_probability,
                heat_prob=summary_data.heat_probability,
                urgency=summary_data.urgency,
                action_window=summary_data.recommended_action_window_days,
                zone_context=zone_context,
            )
            return {
                "zone_id": zone_id,
                "zone_name": zone_cfg["name"],
                "urgency": summary_data.urgency,
                "trigger_type": debate_result.trigger_type,
                "reasoning_trace": raw_plan.get("reasoning_trace", []),
                "actions": raw_plan.get("actions", []),
                "simulation": raw_plan.get("simulation", {}),
                "narrative": raw_plan.get("narrative", ""),
            }
        except Exception as e:
            logger.error(f"Agent 4 response failed for {zone_id}: {e}")
            return None

    async def run_cycle(self) -> Dict[str, Any]:
        """
        Full orchestration cycle:
          1. Predict all zones
          2. Filter by threshold
          3. Debate high-risk zones
          4. Send agent4_ready zones to Agent 4 for response
          5. Log everything
        Returns full orchestration result dict.
        """
        self._cycle_count += 1
        cycle_start = datetime.now(timezone.utc)

        # Create log for this run
        run_log = OrchestrationLog()
        run_log.run_id = f"run_{cycle_start.strftime('%Y%m%d_%H%M%S')}_{self._cycle_count}"
        run_log.started_at = cycle_start.isoformat()
        run_log.cycle_number = self._cycle_count
        run_log.threshold = settings.RISK_ALERT_THRESHOLD

        logger.info(f"🤖 Orchestrator cycle #{self._cycle_count} starting — evaluating {len(settings.ZONES)} zones")
        run_log.add_step("CYCLE_START", f"Evaluating {len(settings.ZONES)} zones with threshold={settings.RISK_ALERT_THRESHOLD}")

        results: List[DebateResult] = []

        # Step 1: Fetch predictions + features for all zones
        run_log.add_step("FETCH_PREDICTIONS", "Fetching 30-day ML predictions from Agent 3 for all zones")

        async with httpx.AsyncClient() as client:
            prediction_tasks = [self._get_zone_prediction(client, zone["id"]) for zone in settings.ZONES]
            feature_tasks = [self._get_zone_features(client, zone["id"]) for zone in settings.ZONES]

            all_predictions, all_features = await asyncio.gather(
                asyncio.gather(*prediction_tasks),
                asyncio.gather(*feature_tasks),
            )

        run_log.add_step("PREDICTIONS_RECEIVED", f"Got {sum(1 for p in all_predictions if p)} predictions successfully")

        # Step 2: Filter zones above threshold
        high_risk_zones = []
        for zone_cfg, prediction, features in zip(settings.ZONES, all_predictions, all_features):
            if prediction is None:
                run_log.add_step("ZONE_SKIP", f"No prediction available", zone_id=zone_cfg["id"], status="skip")
                continue

            summary = prediction.get("summary", {})
            peak_flood = summary.get("peak_flood_risk", 0.0)
            peak_heat = summary.get("peak_heat_risk", 0.0)

            if self._exceeds_threshold(prediction):
                run_log.add_step("THRESHOLD_EXCEEDED", f"{zone_cfg['name']} — flood={peak_flood:.2f} heat={peak_heat:.2f} → ABOVE {settings.RISK_ALERT_THRESHOLD}", zone_id=zone_cfg["id"])

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
                run_log.add_step("ZONE_SAFE", f"{zone_cfg['name']} — flood={peak_flood:.2f} heat={peak_heat:.2f} → below threshold", zone_id=zone_cfg["id"], status="ok")

        run_log.zones_evaluated = sum(1 for p in all_predictions if p is not None)
        run_log.zones_above_threshold = len(high_risk_zones)
        run_log.add_step("THRESHOLD_FILTER", f"{len(high_risk_zones)}/{run_log.zones_evaluated} zones above threshold")

        # Step 3: Debate each high-risk zone
        run_log.add_step("DEBATE_START", f"Running multi-agent debate for {len(high_risk_zones)} zones")

        for zone_data in high_risk_zones:
            zone_id = zone_data["zone"]["id"]
            zone_name = zone_data["zone"]["name"]
            try:
                run_log.add_step("DEBATE_ZONE", f"3 Gemini personas analyzing {zone_name}", zone_id=zone_id)
                debate_result = await debater.debate_zone(zone_data)
                results.append(debate_result)
                run_log.debate_results.append(debate_result.model_dump())
                run_log.add_step("DEBATE_COMPLETE", f"Consensus: {debate_result.consensus.urgency} — {debate_result.consensus.verdict[:80]}", zone_id=zone_id)
            except Exception as e:
                logger.error(f"Debate failed for {zone_id}: {e}")
                run_log.add_step("DEBATE_FAILED", str(e), zone_id=zone_id, status="error")

        run_log.zones_debated = len(results)

        # Step 4: Send agent4_ready zones to Agent 4 for response planning
        zones_for_agent4 = [r for r in results if r.agent4_ready]
        zones_dropped = [r for r in results if not r.agent4_ready]

        if zones_for_agent4:
            run_log.add_step("AGENT4_START", f"Sending {len(zones_for_agent4)} zones to Agent 4 for response planning")

        agent4_responses: List[Dict[str, Any]] = []
        for debate_result in zones_for_agent4:
            zone_id = debate_result.zone_id
            zone_cfg = next((z for z in settings.ZONES if z["id"] == zone_id), None)
            if not zone_cfg:
                continue

            # Get zone context from high_risk_zones
            zone_data = next((z for z in high_risk_zones if z["zone"]["id"] == zone_id), None)
            zone_context = zone_data["zone_context"] if zone_data else {}

            run_log.add_step("AGENT4_PLAN", f"Planning response for {debate_result.zone_name} (urgency: {debate_result.consensus.urgency})", zone_id=zone_id)

            response = await self._run_agent4_response(zone_id, zone_cfg, debate_result, zone_context)
            if response:
                agent4_responses.append(response)
                actions_count = len(response.get("actions", []))
                effectiveness = response.get("simulation", {}).get("effectiveness_score", 0)
                run_log.add_step("AGENT4_COMPLETE", f"{actions_count} actions planned, effectiveness={effectiveness:.0%}", zone_id=zone_id)
                run_log.agent4_responses.append(response)
            else:
                run_log.add_step("AGENT4_FAILED", "Response planning failed — using fallback", zone_id=zone_id, status="error")

        run_log.zones_responded = len(agent4_responses)

        # Step 5: Finalize log
        cycle_end = datetime.now(timezone.utc)
        duration_s = (cycle_end - cycle_start).total_seconds()
        run_log.completed_at = cycle_end.isoformat()
        run_log.duration_seconds = round(duration_s, 1)
        run_log.add_step("CYCLE_COMPLETE", f"Done in {duration_s:.1f}s — {len(results)} debated, {len(agent4_responses)} responses planned")

        run_log.summary = {
            "total_zones_evaluated": run_log.zones_evaluated,
            "zones_above_threshold": run_log.zones_above_threshold,
            "zones_debated": run_log.zones_debated,
            "zones_responded": run_log.zones_responded,
            "zones_dropped": len(zones_dropped),
            "threshold_used": settings.RISK_ALERT_THRESHOLD,
            "duration_seconds": run_log.duration_seconds,
        }

        # Save log
        self._run_logs.insert(0, run_log)
        if len(self._run_logs) > self._max_logs:
            self._run_logs = self._run_logs[:self._max_logs]

        # Cache state
        self._last_run = cycle_start.isoformat()
        self._last_zones_evaluated = run_log.zones_evaluated
        self._last_high_risk_count = len(high_risk_zones)
        self._last_results = results

        logger.info(
            f"🤖 Cycle #{self._cycle_count} done in {duration_s:.1f}s — "
            f"debated={len(results)}, agent4={len(agent4_responses)}, dropped={len(zones_dropped)}"
        )

        # Return full response
        return {
            "run_id": run_log.run_id,
            "summary": run_log.summary,
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
            "agent4_responses": agent4_responses,
            "dropped": [
                {
                    "zone_id": r.zone_id,
                    "zone_name": r.zone_name,
                    "trigger_type": r.trigger_type,
                    "urgency": r.consensus.urgency,
                    "verdict": r.consensus.verdict,
                }
                for r in zones_dropped
            ],
            "full_results": [r.model_dump() for r in results],
            "trace": run_log.steps,
        }

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
            "total_runs_logged": len(self._run_logs),
        }

    def get_logs(self) -> List[Dict[str, Any]]:
        """Get all run logs (most recent first)."""
        return [log.to_dict() for log in self._run_logs]

    def get_log_by_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific run log by ID."""
        for log in self._run_logs:
            if log.run_id == run_id:
                return log.to_dict()
        return None


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
    Runs: predict all → filter threshold → debate high-risk → Agent 4 response → log everything.
    """
    logger.info("🤖 Manual orchestrator cycle triggered via API")
    result = await orchestrator.run_cycle()
    return result


@router.get("/logs")
async def get_orchestration_logs():
    """
    Get all orchestration run logs (most recent first).
    Each log contains: steps trace, debate results, Agent 4 responses, timing.
    Used by the Flutter app to display full pipeline history.
    """
    logs = orchestrator.get_logs()
    return {
        "total_runs": len(logs),
        "logs": logs,
    }


@router.get("/logs/{run_id}")
async def get_orchestration_log(run_id: str):
    """
    Get a specific orchestration run log by ID.
    Returns full trace, debate results, Agent 4 responses.
    """
    log = orchestrator.get_log_by_id(run_id)
    if not log:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return log
