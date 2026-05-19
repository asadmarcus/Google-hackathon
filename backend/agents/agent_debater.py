"""
CIRO — Debater Agent: Multi-Persona LLM Crisis Debate
======================================================
Three expert personas (Hydrologist, Meteorologist, Urban Planner) each
analyse a high-risk zone independently via Gemini, then a 4th consensus
call synthesises their verdicts into a structured DebateResult JSON.

Trigger type (FLOOD | HEAT | BOTH) is determined before debate starts.
Persona focuses and consensus schema adapt accordingly so a pure heat
event never produces a misleading flood probability.

Input:  Zone metadata + Agent 2 features + Agent 3 ML prediction
Output: DebateResult JSON (Agent 4 input contract)
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

logger = logging.getLogger("ciro.debater")
router = APIRouter()

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# ─── Schemas ───────────────────────────────────────────────────────────────────

class PersonaVerdict(BaseModel):
    persona: str
    assessment: str
    risk_vote: float
    key_factor: str
    urgency: str  # MONITOR | PREPARE | ACT_NOW


class DebateConsensus(BaseModel):
    trigger_type: str            # FLOOD | HEAT | BOTH
    flood_probability: float     # from ML peak_flood_risk (not invented by LLM)
    heat_probability: float      # from ML peak_heat_risk  (not invented by LLM)
    primary_risk_probability: float  # whichever triggered the alert
    verdict: str
    urgency: str
    recommended_action_window_days: List[int]
    unanimous: bool
    rationale: str


class DebateResult(BaseModel):
    zone_id: str
    zone_name: str
    debate_timestamp: str
    trigger: str
    trigger_type: str            # FLOOD | HEAT | BOTH — top-level for quick filtering
    ml_risk_input: Dict[str, Any]
    zone_context: Dict[str, Any]
    personas: List[PersonaVerdict]
    consensus: DebateConsensus
    agent4_ready: bool


# ─── Trigger classification ────────────────────────────────────────────────────

def _classify_trigger(peak_flood: float, peak_heat: float, threshold: float) -> str:
    """Determine what kind of risk triggered this debate."""
    flood_triggered = peak_flood >= threshold
    heat_triggered = peak_heat >= threshold
    if flood_triggered and heat_triggered:
        return "BOTH"
    if flood_triggered:
        return "FLOOD"
    return "HEAT"


# ─── Persona focus library ─────────────────────────────────────────────────────

_PERSONA_FOCUSES: Dict[str, Dict[str, str]] = {
    "FLOOD": {
        "Hydrologist": (
            "River discharge dynamics, antecedent soil moisture (AMI), GloFAS discharge signals, "
            "historical flood pattern matching — especially the catastrophic 2022 Pakistan floods"
        ),
        "Meteorologist": (
            "ECMWF/GFS rainfall forecasts, monsoon progression, 48-hour extreme precipitation risk, "
            "cumulative rainfall trajectory over the forecast window"
        ),
        "Urban_Planner": (
            "Urban drainage capacity vs forecast rainfall, population exposure in low-lying areas, "
            "infrastructure flood failure risk, evacuation route feasibility"
        ),
    },
    "HEAT": {
        "Hydrologist": (
            "Heat stress on soil stability and infrastructure (pipe expansion, road buckling), "
            "evaporation-driven water scarcity, how extreme heat degrades drainage system integrity"
        ),
        "Meteorologist": (
            "Temperature trajectory and heatwave persistence (3+ consecutive days above local 90th percentile), "
            "humidity levels, nocturnal cooling deficit, likelihood of the heat peak sustaining beyond Day 19"
        ),
        "Urban_Planner": (
            "Public health vulnerability under extreme heat — at-risk populations (elderly, outdoor workers), "
            "cooling infrastructure availability, shelter-in-place vs evacuation planning, "
            "urban heat island effect in dense wards"
        ),
    },
    "BOTH": {
        "Hydrologist": (
            "Combined threat: river discharge + heat-induced soil hardening reducing infiltration. "
            "GloFAS signals, AMI, and how heatwave conditions amplify flood runoff risk"
        ),
        "Meteorologist": (
            "Compound hazard: rainfall accumulation trajectory AND heatwave persistence. "
            "ECMWF forecasts for both temperature and precipitation over the 30-day window"
        ),
        "Urban_Planner": (
            "Compound disaster planning: simultaneous flood and heat exposure. "
            "Drainage capacity, cooling centre availability, evacuation vs shelter trade-offs"
        ),
    },
}


# ─── Debater Core ──────────────────────────────────────────────────────────────

class ZoneDebater:
    """
    Runs the 4-call Gemini debate for a single high-risk zone.
    Trigger type is determined before the debate and drives persona focuses
    and consensus schema — a heat-only event never reports a flood probability.
    """

    def _api_key(self) -> str:
        return settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY

    def _endpoint(self) -> str:
        return (
            f"{GEMINI_API_BASE}/models/{settings.DEBATE_LLM_MODEL}"
            f":generateContent?key={self._api_key()}"
        )

    @gemini_retry(max_retries=5, base_delay=2.0)
    async def _call_gemini(self, prompt: str) -> str:
        """Single Gemini REST call. Returns raw text response."""
        api_key = self._api_key()
        if not api_key:
            raise RuntimeError("No Gemini API key configured (GEMINI_API_KEY or GOOGLE_API_KEY)")

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": settings.DEBATE_TEMPERATURE,
                "responseMimeType": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self._endpoint(), json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates")
        return candidates[0]["content"]["parts"][0]["text"]

    def _build_context_block(self, zone_data: Dict[str, Any], trigger_type: str) -> str:
        """
        Shared context block injected into every persona prompt.
        Explicitly states the trigger type so personas focus on the right risk.
        """
        ml = zone_data.get("ml_prediction", {})
        summary = ml.get("summary", {})
        ctx = zone_data.get("zone_context", {})
        zone = zone_data.get("zone", {})
        peak_flood = summary.get("peak_flood_risk", 0)
        peak_heat = summary.get("peak_heat_risk", 0)

        # Human-readable trigger explanation
        if trigger_type == "HEAT":
            trigger_note = (
                f"⚠️  ALERT TRIGGER: HEAT RISK (peak_heat_risk={peak_heat:.2f}). "
                f"Flood risk is LOW ({peak_flood:.2f}). Do NOT speculate about flood probability. "
                f"Focus your analysis entirely on heat-related threats."
            )
        elif trigger_type == "FLOOD":
            trigger_note = (
                f"⚠️  ALERT TRIGGER: FLOOD RISK (peak_flood_risk={peak_flood:.2f}). "
                f"Heat risk is LOW ({peak_heat:.2f}). Focus your analysis on flood-related threats."
            )
        else:
            trigger_note = (
                f"⚠️  ALERT TRIGGER: COMPOUND RISK — both FLOOD ({peak_flood:.2f}) "
                f"and HEAT ({peak_heat:.2f}) are elevated. Analyse both dimensions."
            )

        return f"""
{trigger_note}

ZONE: {zone.get('name', zone.get('id', 'Unknown'))} ({ctx.get('province', 'Unknown Province')})
Population Density: {ctx.get('population_density', 0):,} people/km²
Drainage Capacity: {ctx.get('drainage_capacity', 0) * 100:.0f}% of design capacity
Elevation: {ctx.get('elevation_m', 0)}m ASL

CURRENT CONDITIONS:
  Rain last 24h: {ctx.get('current_rain_24h_mm', 0):.1f}mm
  Temperature: {ctx.get('current_temp_c', 0):.1f}°C
  Humidity: {ctx.get('current_humidity_pct', 0):.0f}%
  GloFAS River Discharge: {ctx.get('glofas_discharge_ratio', 1.0):.2f}x normal
  Satellite NDWI Delta: {ctx.get('ndwi_delta', 0):.3f} (>0 = water expanding)

ML PREDICTION (XGBoost + Temporal Intelligence):
  Peak Flood Risk: {peak_flood:.3f} on Day {summary.get('peak_flood_day', 0)}
  Peak Heat Risk:  {peak_heat:.3f} on Day {summary.get('peak_heat_day', 0)}
  Overall Alert Level: {summary.get('overall_alert_level', 'UNKNOWN')}
  Dominant Factor: {summary.get('dominant_factor', 'unknown')}
  High Flood Risk Days: {summary.get('high_flood_days', 0)}/30
""".strip()

    async def _run_persona(
        self, persona_name: str, focus: str, context: str, trigger_type: str
    ) -> PersonaVerdict:
        """Run a single expert persona call."""
        risk_label = "heat risk" if trigger_type == "HEAT" else "flood risk" if trigger_type == "FLOOD" else "compound risk"

        prompt = f"""You are a senior {persona_name} in Pakistan's National Disaster Management Authority crisis team.

Your focus: {focus}

ZONE DATA:
{context}

Analyse this zone's {risk_label} from your expert perspective.
Your risk_vote must reflect the PRIMARY triggered risk ({risk_label}), not an unrelated hazard.
Return ONLY valid JSON in this exact schema:
{{
  "persona": "{persona_name}",
  "assessment": "<2-3 sentence expert assessment referencing specific numbers from the data above>",
  "risk_vote": <float 0.0-1.0, reflecting the {risk_label} severity>,
  "key_factor": "<single most important factor driving your verdict>",
  "urgency": "<one of: MONITOR, PREPARE, ACT_NOW>"
}}

Be specific. Reference actual values. Do not introduce risks not supported by the data."""

        try:
            raw = await self._call_gemini(prompt)
            data = json.loads(raw)
            return PersonaVerdict(
                persona=data.get("persona", persona_name),
                assessment=data.get("assessment", ""),
                risk_vote=float(data.get("risk_vote", 0.5)),
                key_factor=data.get("key_factor", ""),
                urgency=data.get("urgency", "MONITOR"),
            )
        except Exception as e:
            logger.warning(f"Persona {persona_name} call failed: {e} — using fallback")
            return PersonaVerdict(
                persona=persona_name,
                assessment=f"[Analysis unavailable: {str(e)[:80]}]",
                risk_vote=0.5,
                key_factor="data_unavailable",
                urgency="MONITOR",
            )

    async def _run_consensus(
        self,
        personas: List[PersonaVerdict],
        context: str,
        trigger_type: str,
        peak_flood: float,
        peak_heat: float,
    ) -> DebateConsensus:
        """
        Synthesise the 3 persona verdicts.
        flood_probability and heat_probability come directly from the ML model —
        Gemini only decides urgency, verdict text, rationale, and action window.
        """
        personas_json = json.dumps([p.model_dump() for p in personas], indent=2)
        primary_risk = peak_heat if trigger_type == "HEAT" else peak_flood if trigger_type == "FLOOD" else max(peak_flood, peak_heat)
        primary_label = "heat" if trigger_type == "HEAT" else "flood" if trigger_type == "FLOOD" else "compound"

        prompt = f"""You are the CIRO Consensus Engine. Three domain experts have independently assessed a {trigger_type} risk zone.

ZONE DATA:
{context}

EXPERT VERDICTS:
{personas_json}

The ML model has already computed:
  flood_probability = {peak_flood:.3f}  (do NOT change this)
  heat_probability  = {peak_heat:.3f}   (do NOT change this)
  primary_risk ({primary_label}) = {primary_risk:.3f}

Your job is to synthesise the expert opinions into an action verdict.
Return ONLY valid JSON:
{{
  "verdict": "<one-line summary, e.g.: CRITICAL HEAT — 97% heat risk, peak Day 19, ACT before Day 17>",
  "urgency": "<ACT_NOW if 2+ experts say ACT_NOW, PREPARE if 2+ say PREPARE, else MONITOR>",
  "recommended_action_window_days": [<start_day>, <end_day>],
  "unanimous": <true if all 3 urgency values are identical, else false>,
  "rationale": "<3-4 sentences explaining consensus — which expert's factor is decisive and why>"
}}"""

        try:
            raw = await self._call_gemini(prompt)
            data = json.loads(raw)
            window = data.get("recommended_action_window_days", [1, 7])
            if not isinstance(window, list) or len(window) < 2:
                window = [1, 7]

            urgencies = [p.urgency for p in personas]
            return DebateConsensus(
                trigger_type=trigger_type,
                flood_probability=round(peak_flood, 4),
                heat_probability=round(peak_heat, 4),
                primary_risk_probability=round(primary_risk, 4),
                verdict=data.get("verdict", "UNKNOWN"),
                urgency=data.get("urgency", "MONITOR"),
                recommended_action_window_days=[int(window[0]), int(window[1])],
                unanimous=bool(data.get("unanimous", len(set(urgencies)) == 1)),
                rationale=data.get("rationale", ""),
            )
        except Exception as e:
            logger.warning(f"Consensus call failed: {e} — using fallback")
            urgencies = [p.urgency for p in personas]
            top_urgency = max(set(urgencies), key=urgencies.count)
            return DebateConsensus(
                trigger_type=trigger_type,
                flood_probability=round(peak_flood, 4),
                heat_probability=round(peak_heat, 4),
                primary_risk_probability=round(primary_risk, 4),
                verdict=f"{trigger_type} risk {primary_risk:.0%} — consensus unavailable",
                urgency=top_urgency,
                recommended_action_window_days=[1, 7],
                unanimous=len(set(urgencies)) == 1,
                rationale=f"[Consensus synthesis failed: {str(e)[:80]}]",
            )

    async def debate_zone(self, zone_data: Dict[str, Any]) -> DebateResult:
        """
        Run the full 4-call debate for one zone.
        Determines trigger type first, then adapts all prompts accordingly.
        """
        zone = zone_data.get("zone", {})
        ml = zone_data.get("ml_prediction", {})
        summary = ml.get("summary", {})
        ctx = zone_data.get("zone_context", {})
        threshold = zone_data.get("threshold", settings.RISK_ALERT_THRESHOLD)

        peak_flood = summary.get("peak_flood_risk", 0.0)
        peak_heat = summary.get("peak_heat_risk", 0.0)
        trigger_type = _classify_trigger(peak_flood, peak_heat, threshold)

        context = self._build_context_block(zone_data, trigger_type)
        focuses = _PERSONA_FOCUSES[trigger_type]

        logger.info(
            f"🗣  Debating {zone.get('name')} — trigger={trigger_type} "
            f"(flood={peak_flood:.2f}, heat={peak_heat:.2f})"
        )

        hydrologist = await self._run_persona("Hydrologist", focuses["Hydrologist"], context, trigger_type)
        meteorologist = await self._run_persona("Meteorologist", focuses["Meteorologist"], context, trigger_type)
        urban_planner = await self._run_persona("Urban_Planner", focuses["Urban_Planner"], context, trigger_type)

        personas = [hydrologist, meteorologist, urban_planner]
        consensus = await self._run_consensus(personas, context, trigger_type, peak_flood, peak_heat)

        primary_risk = max(peak_flood, peak_heat)
        result = DebateResult(
            zone_id=zone.get("id", "unknown"),
            zone_name=zone.get("name", "Unknown"),
            debate_timestamp=datetime.now(timezone.utc).isoformat(),
            trigger=f"{trigger_type} — peak_risk={primary_risk:.2f} exceeded threshold={threshold:.2f}",
            trigger_type=trigger_type,
            ml_risk_input={
                "peak_flood_risk": peak_flood,
                "peak_flood_day": summary.get("peak_flood_day", 0),
                "peak_heat_risk": peak_heat,
                "peak_heat_day": summary.get("peak_heat_day", 0),
                "overall_alert_level": summary.get("overall_alert_level", "UNKNOWN"),
                "dominant_factor": summary.get("dominant_factor", "unknown"),
                "avg_flood_risk": summary.get("avg_flood_risk", 0),
                "high_flood_days": summary.get("high_flood_days", 0),
            },
            zone_context=ctx,
            personas=personas,
            consensus=consensus,
            agent4_ready=consensus.urgency in ("ACT_NOW", "PREPARE"),
        )

        logger.info(
            f"🗣  Debate done: {zone.get('name')} → {trigger_type} {consensus.urgency} "
            f"(flood={peak_flood:.2f}, heat={peak_heat:.2f})"
        )
        return result


# Module-level singleton
debater = ZoneDebater()


# ─── Endpoints ─────────────────────────────────────────────────────────────────

_last_results: List[DebateResult] = []


@router.post("/debate/{zone_id}", response_model=DebateResult)
async def debate_zone(zone_id: str):
    """
    Manually trigger a debate for a single zone.
    Fetches current predictions from Agent 2 + Agent 3, then runs the LLM debate.
    """
    zone_cfg = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone_cfg:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    base_url = settings.AGENT2_BASE_URL
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            feat_resp = await client.get(f"{base_url}/api/v1/agent2/features/{zone_id}")
            features = feat_resp.json() if feat_resp.status_code == 200 else {}
        except Exception:
            features = {}

        try:
            pred_resp = await client.post(f"{base_url}/api/v1/agent3/predict/{zone_id}")
            ml_prediction = pred_resp.json() if pred_resp.status_code == 200 else {}
        except Exception:
            ml_prediction = {}

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

    zone_data = {
        "zone": zone_cfg,
        "zone_context": zone_context,
        "ml_prediction": ml_prediction,
        "threshold": settings.RISK_ALERT_THRESHOLD,
    }

    result = await debater.debate_zone(zone_data)
    _last_results.append(result)
    return result


@router.get("/last-results", response_model=List[DebateResult])
async def get_last_results():
    """Return the most recent batch of debate results from the orchestrator cycle."""
    return _last_results
