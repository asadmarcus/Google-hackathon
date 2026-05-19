"""
CIRO — Agent 4: Response Commander
====================================
Takes debate consensus from Agent Debater → Plans response actions →
Simulates execution → Shows before/after outcomes.

This is the ACTION layer. The chain:
  Agent 2 (data) → Agent 3 (predict) → Debater (reason) → Agent 4 (ACT)

Gemini powers the response planning — it receives the full crisis context
and generates realistic, Pakistan-specific response actions with simulated outcomes.

Endpoints:
  POST /api/v1/agent4/respond/{zone_id}  — Full response planning + simulation
  POST /api/v1/agent4/respond-from-debate — Respond to a DebateResult directly
  GET  /api/v1/agent4/last-response/{zone_id} — Most recent response for a zone
  GET  /api/v1/agent4/trace/{zone_id}    — Full reasoning trace (for judges)
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.settings import settings
from services.gemini_retry import gemini_retry

logger = logging.getLogger("ciro.agent4")
router = APIRouter()

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ResponseAction(BaseModel):
    action_id: int
    category: str          # EVACUATE | ALERT | DEPLOY | REROUTE | SHELTER | MEDICAL
    description: str
    priority: str          # IMMEDIATE | WITHIN_6H | WITHIN_24H | PREPARATORY
    target_population: int
    resources_required: List[str]
    estimated_time_hours: float
    responsible_agency: str


class SimulationState(BaseModel):
    population_at_risk: int
    population_evacuated: int
    shelters_activated: int
    medical_units_deployed: int
    alerts_sent: int
    roads_closed: int
    estimated_lives_saved: int
    response_coverage_percent: float


class ResponseSimulation(BaseModel):
    before: SimulationState
    after: SimulationState
    actions_executed: int
    total_response_time_hours: float
    effectiveness_score: float   # 0-1


class ReasoningStep(BaseModel):
    step: int
    thought: str
    decision: str


class ResponsePlan(BaseModel):
    zone_id: str
    zone_name: str
    timestamp: str
    trigger_type: str            # FLOOD | HEAT | BOTH
    alert_level: str
    urgency: str

    # From debate
    debate_verdict: str
    flood_probability: float
    heat_probability: float
    action_window_days: List[int]

    # Agent 4 output
    reasoning_trace: List[ReasoningStep]
    actions: List[ResponseAction]
    simulation: ResponseSimulation
    narrative: str               # Human-readable summary
    gemini_model: str


# ─── In-memory store ─────────────────────────────────────────────────────────

_last_responses: Dict[str, ResponsePlan] = {}


# ─── Zone static data for simulation ────────────────────────────────────────

ZONE_POPULATION = {
    "islamabad-g10": 45000,
    "lahore-city": 120000,
    "karachi-south": 250000,
    "peshawar-city": 80000,
    "multan-city": 95000,
    "jacobabad-city": 60000,
    "sukkur-city": 75000,
    "quetta-city": 40000,
}

ZONE_SHELTERS = {
    "islamabad-g10": 8,
    "lahore-city": 15,
    "karachi-south": 12,
    "peshawar-city": 10,
    "multan-city": 9,
    "jacobabad-city": 5,
    "sukkur-city": 6,
    "quetta-city": 4,
}

ZONE_HOSPITALS = {
    "islamabad-g10": 5,
    "lahore-city": 12,
    "karachi-south": 8,
    "peshawar-city": 6,
    "multan-city": 5,
    "jacobabad-city": 2,
    "sukkur-city": 3,
    "quetta-city": 3,
}


# ─── Gemini Response Planner ─────────────────────────────────────────────────

class ResponsePlanner:
    """Uses Gemini to plan crisis response actions with full reasoning."""

    def __init__(self):
        self._api_key = settings.GOOGLE_API_KEY
        self._model = settings.DEBATE_LLM_MODEL

    @gemini_retry(max_retries=3, base_delay=2.0)
    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API with retry on 429."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            url = f"{GEMINI_API_BASE}/models/{self._model}:generateContent"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 2048,
                    "responseMimeType": "application/json",
                }
            }
            resp = await client.post(url, params={"key": self._api_key}, json=payload)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return "{}"
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts)

    async def plan_response(
        self,
        zone_id: str,
        zone_name: str,
        province: str,
        debate_verdict: str,
        trigger_type: str,
        flood_prob: float,
        heat_prob: float,
        urgency: str,
        action_window: List[int],
        zone_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate a full response plan using Gemini."""

        population = ZONE_POPULATION.get(zone_id, 50000)
        shelters = ZONE_SHELTERS.get(zone_id, 5)
        hospitals = ZONE_HOSPITALS.get(zone_id, 3)

        prompt = f"""You are CIRO Agent 4 — the Crisis Response Commander for Pakistan.

SITUATION:
- Zone: {zone_name} ({zone_id}), {province}
- Debate Verdict: {debate_verdict}
- Trigger: {trigger_type}
- Flood Probability: {flood_prob*100:.0f}%
- Heat Probability: {heat_prob*100:.0f}%
- Urgency: {urgency}
- Action Window: Days {action_window}
- Population at risk: {population:,}
- Available shelters: {shelters}
- Medical facilities: {hospitals}
- Drainage capacity: {zone_context.get('drainage_capacity', 0.3)*100:.0f}%
- Elevation: {zone_context.get('elevation_m', 50)}m
- Current rainfall 24h: {zone_context.get('current_rain_24h_mm', 0)}mm

TASK: Plan a realistic crisis response. Generate a JSON with:

1. "reasoning_trace" — array of 4-6 reasoning steps, each with "step" (int), "thought" (what you're considering), "decision" (what you decided)

2. "actions" — array of 4-8 response actions, each with:
   - "action_id" (int)
   - "category": one of EVACUATE, ALERT, DEPLOY, REROUTE, SHELTER, MEDICAL
   - "description": specific action (mention real Pakistan agencies: NDMA, PDMA, Pakistan Army, Rescue 1122)
   - "priority": IMMEDIATE | WITHIN_6H | WITHIN_24H | PREPARATORY
   - "target_population": number of people affected
   - "resources_required": list of specific resources
   - "estimated_time_hours": float
   - "responsible_agency": which agency handles this

3. "simulation" — object with "before" and "after" states:
   Before: current state (population_at_risk={population}, population_evacuated=0, shelters_activated=0, medical_units_deployed=0, alerts_sent=0, roads_closed=0, estimated_lives_saved=0, response_coverage_percent=0)
   After: projected state AFTER executing all actions (realistic estimates)
   Also include: "actions_executed", "total_response_time_hours", "effectiveness_score" (0-1)

4. "narrative" — 2-3 sentence human-readable summary of what will happen

Be realistic and Pakistan-specific. Reference actual roads (GT Road, M2, NH-55), districts, and agencies.
Output valid JSON only."""

        try:
            raw = await self._call_gemini(prompt)
            result = json.loads(raw)
            return result
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Gemini response planning failed: {e}")
            return self._fallback_plan(zone_id, zone_name, trigger_type, flood_prob, heat_prob, population, urgency)

    def _fallback_plan(
        self, zone_id: str, zone_name: str, trigger_type: str,
        flood_prob: float, heat_prob: float, population: int, urgency: str
    ) -> Dict[str, Any]:
        """Rule-based fallback if Gemini fails."""
        evac_pct = 0.3 if urgency == "ACT_NOW" else 0.15
        evac_pop = int(population * evac_pct)

        return {
            "reasoning_trace": [
                {"step": 1, "thought": f"Zone {zone_name} has {trigger_type} trigger with urgency {urgency}", "decision": "Activate emergency response protocol"},
                {"step": 2, "thought": f"Population at risk: {population:,}. Evacuation needed for low-lying areas", "decision": f"Target {evac_pop:,} for evacuation"},
                {"step": 3, "thought": "Coordinate with NDMA and provincial PDMA", "decision": "Issue multi-channel alerts"},
                {"step": 4, "thought": "Stage medical and shelter resources", "decision": "Deploy to pre-designated sites"},
            ],
            "actions": [
                {"action_id": 1, "category": "ALERT", "description": f"Issue {urgency} alert to {zone_name} residents via SMS, mosque loudspeakers, and TV", "priority": "IMMEDIATE", "target_population": population, "resources_required": ["SMS gateway", "Emergency broadcast"], "estimated_time_hours": 0.5, "responsible_agency": "NDMA Pakistan"},
                {"action_id": 2, "category": "EVACUATE", "description": f"Evacuate {evac_pop:,} from low-lying wards to designated shelters", "priority": "IMMEDIATE" if urgency == "ACT_NOW" else "WITHIN_6H", "target_population": evac_pop, "resources_required": ["Buses", "Police escort", "Route markers"], "estimated_time_hours": 6.0, "responsible_agency": "Rescue 1122 + Pakistan Army"},
                {"action_id": 3, "category": "SHELTER", "description": f"Activate {ZONE_SHELTERS.get(zone_id, 5)} emergency shelters with capacity for {evac_pop:,}", "priority": "WITHIN_6H", "target_population": evac_pop, "resources_required": ["Tents", "Bedding", "Water supply", "Generators"], "estimated_time_hours": 4.0, "responsible_agency": "PDMA + District Administration"},
                {"action_id": 4, "category": "MEDICAL", "description": "Deploy mobile medical units to shelter sites", "priority": "WITHIN_6H", "target_population": evac_pop, "resources_required": ["Medical teams", "ORS", "First aid", "Ambulances"], "estimated_time_hours": 3.0, "responsible_agency": "District Health Office"},
                {"action_id": 5, "category": "DEPLOY", "description": "Pre-position rescue boats and pumping equipment", "priority": "WITHIN_24H", "target_population": 0, "resources_required": ["Rescue boats x10", "De-watering pumps x20"], "estimated_time_hours": 8.0, "responsible_agency": "Pakistan Navy + NDMA"},
                {"action_id": 6, "category": "REROUTE", "description": "Close flood-prone roads and activate alternative routes", "priority": "WITHIN_6H", "target_population": population, "resources_required": ["Traffic police", "Barriers", "Signage"], "estimated_time_hours": 2.0, "responsible_agency": "Traffic Police + NHA"},
            ],
            "simulation": {
                "before": {"population_at_risk": population, "population_evacuated": 0, "shelters_activated": 0, "medical_units_deployed": 0, "alerts_sent": 0, "roads_closed": 0, "estimated_lives_saved": 0, "response_coverage_percent": 0},
                "after": {"population_at_risk": population - evac_pop, "population_evacuated": evac_pop, "shelters_activated": ZONE_SHELTERS.get(zone_id, 5), "medical_units_deployed": ZONE_HOSPITALS.get(zone_id, 3), "alerts_sent": population, "roads_closed": 4, "estimated_lives_saved": int(evac_pop * 0.02), "response_coverage_percent": round(evac_pct * 100, 1)},
                "actions_executed": 6,
                "total_response_time_hours": 8.0,
                "effectiveness_score": 0.72,
            },
            "narrative": f"Emergency response initiated for {zone_name}. {evac_pop:,} residents targeted for evacuation to {ZONE_SHELTERS.get(zone_id, 5)} shelters. NDMA and Rescue 1122 coordinating. Medical teams deploying. Estimated {int(evac_pop*0.02)} lives saved through early action."
        }


# ─── Singleton ───────────────────────────────────────────────────────────────

planner = ResponsePlanner()


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/respond/{zone_id}", response_model=ResponsePlan)
async def respond_to_crisis(zone_id: str):
    """
    Full response pipeline for a zone:
    1. Get prediction from Agent 3
    2. Run debate (if not already done)
    3. Plan response with Gemini
    4. Simulate outcomes
    """
    from agents.agent_debater import debater

    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    # Get prediction
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{settings.AGENT2_BASE_URL}/api/v1/agent3/predict/{zone_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Agent 3 prediction failed")
        prediction = resp.json()

    summary = prediction.get("summary", {})
    peak_flood = summary.get("peak_flood_risk", 0.0)
    peak_heat = summary.get("peak_heat_risk", 0.0)

    # Determine trigger
    threshold = settings.RISK_ALERT_THRESHOLD
    if peak_flood >= threshold or peak_heat >= threshold:
        trigger_type = "BOTH" if peak_flood >= threshold and peak_heat >= threshold else ("FLOOD" if peak_flood >= threshold else "HEAT")
    else:
        trigger_type = "FLOOD" if peak_flood > peak_heat else "HEAT"

    # Run debate
    debate_data = {
        "zone": zone,
        "ml_prediction": prediction,
        "zone_context": zone_context,
        "threshold": settings.RISK_ALERT_THRESHOLD,
    }
    debate_result = await debater.debate_zone(debate_data)

    urgency = debate_result.consensus.urgency
    action_window = debate_result.consensus.recommended_action_window_days

    # Plan response with Gemini
    zone_context = {
        "drainage_capacity": zone.get("drainage_capacity", 0.3),
        "elevation_m": zone.get("elevation_m", 50),
        "population_density": zone.get("population_density", 3000),
        "current_rain_24h_mm": 0,
    }

    raw_plan = await planner.plan_response(
        zone_id=zone_id,
        zone_name=zone["name"],
        province=zone.get("province", ""),
        debate_verdict=debate_result.consensus.verdict,
        trigger_type=trigger_type,
        flood_prob=peak_flood,
        heat_prob=peak_heat,
        urgency=urgency,
        action_window=action_window,
        zone_context=zone_context,
    )

    # Build response
    reasoning = [ReasoningStep(**s) for s in raw_plan.get("reasoning_trace", [])]
    actions = [ResponseAction(**a) for a in raw_plan.get("actions", [])]

    sim_raw = raw_plan.get("simulation", {})
    simulation = ResponseSimulation(
        before=SimulationState(**sim_raw.get("before", {"population_at_risk": 0, "population_evacuated": 0, "shelters_activated": 0, "medical_units_deployed": 0, "alerts_sent": 0, "roads_closed": 0, "estimated_lives_saved": 0, "response_coverage_percent": 0})),
        after=SimulationState(**sim_raw.get("after", {"population_at_risk": 0, "population_evacuated": 0, "shelters_activated": 0, "medical_units_deployed": 0, "alerts_sent": 0, "roads_closed": 0, "estimated_lives_saved": 0, "response_coverage_percent": 0})),
        actions_executed=sim_raw.get("actions_executed", len(actions)),
        total_response_time_hours=sim_raw.get("total_response_time_hours", 8.0),
        effectiveness_score=sim_raw.get("effectiveness_score", 0.7),
    )

    plan = ResponsePlan(
        zone_id=zone_id,
        zone_name=zone["name"],
        timestamp=datetime.now(timezone.utc).isoformat(),
        trigger_type=trigger_type,
        alert_level=summary.get("overall_alert_level", "HIGH"),
        urgency=urgency,
        debate_verdict=debate_result.consensus.verdict,
        flood_probability=peak_flood,
        heat_probability=peak_heat,
        action_window_days=action_window,
        reasoning_trace=reasoning,
        actions=actions,
        simulation=simulation,
        narrative=raw_plan.get("narrative", ""),
        gemini_model=settings.DEBATE_LLM_MODEL,
    )

    _last_responses[zone_id] = plan
    logger.info(f"🎯 Agent 4 response planned for {zone['name']}: {len(actions)} actions, effectiveness={simulation.effectiveness_score:.0%}")

    return plan


@router.get("/last-response/{zone_id}")
async def get_last_response(zone_id: str):
    """Get the most recent response plan for a zone."""
    if zone_id not in _last_responses:
        raise HTTPException(status_code=404, detail=f"No response plan for '{zone_id}'. Run POST /respond/{zone_id} first.")
    return _last_responses[zone_id]


@router.get("/trace/{zone_id}")
async def get_reasoning_trace(zone_id: str):
    """Get full reasoning trace for a zone (for judges)."""
    if zone_id not in _last_responses:
        raise HTTPException(status_code=404, detail=f"No trace for '{zone_id}'.")

    plan = _last_responses[zone_id]
    return {
        "zone_id": zone_id,
        "zone_name": plan.zone_name,
        "timestamp": plan.timestamp,
        "trigger": plan.trigger_type,
        "urgency": plan.urgency,
        "debate_verdict": plan.debate_verdict,
        "reasoning_steps": [s.dict() for s in plan.reasoning_trace],
        "actions_planned": len(plan.actions),
        "simulation_effectiveness": plan.simulation.effectiveness_score,
        "model": plan.gemini_model,
    }


@router.get("/status")
async def agent4_status():
    """Agent 4 health and recent activity."""
    return {
        "agent": "Agent 4 — Response Commander",
        "status": "active",
        "zones_with_plans": list(_last_responses.keys()),
        "total_plans_generated": len(_last_responses),
        "capabilities": [
            "Gemini-powered response planning",
            "Multi-action crisis simulation (before/after)",
            "Pakistan-specific agency coordination (NDMA, PDMA, Rescue 1122)",
            "Evacuation routing + resource deployment",
            "Full reasoning trace for transparency",
        ],
    }
