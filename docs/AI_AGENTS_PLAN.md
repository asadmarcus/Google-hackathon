# CIRO AI Agents Layer — Orchestrator + Debater

## Overview

Adds an AI reasoning layer on top of existing data collection and ML prediction.  
Every 2 hours (configurable), the system:
1. Fetches fresh predictions for all 8 zones
2. Filters zones above `RISK_ALERT_THRESHOLD`
3. Runs a 3-persona LLM debate on each high-risk zone
4. Outputs structured JSON (future Agent 4 input)

---

## Agent Roles (Updated Architecture)

| Agent | File | Role | Status |
|-------|------|------|--------|
| Agent 1 | `agent_imagery.py` | Satellite NDWI / GeoGemma | Active |
| Agent 2 | `agent_data_collector.py` | 15-min real-time signal collection | Active |
| Agent 3 (ML) | `agent_predictor.py` | XGBoost 30-day flood/heat forecast | Active |
| **Debater** | `agent_debater.py` (NEW) | 3-persona Gemini LLM debate | **New** |
| **Orchestrator** | `agent_orchestrator.py` (NEW) | 2-hour cycle, threshold gate, coordination | **New** |
| Agent 4 | TBD | Response dispatch (planned) | Planned |

---

## Data Flow

```
Every 2 hours — Orchestrator cycle:
  ┌─ For each of 8 zones (parallel):
  │   ├── GET /api/v1/agent2/features/{zone_id}   → ML feature vector
  │   └── POST /api/v1/agent3/predict/{zone_id}   → 30-day risk prediction
  │
  ├─ Filter: peak_flood_risk OR peak_heat_risk >= RISK_ALERT_THRESHOLD (0.30)
  │
  ├─ High-risk zones → Debater:
  │   ├── Gemini call 1: Hydrologist persona
  │   ├── Gemini call 2: Meteorologist persona
  │   ├── Gemini call 3: Urban Planner persona
  │   └── Gemini call 4: Consensus synthesis
  │
  └─ logger.info(JSON)  ←── Agent 4 will consume this later

15-min signal_fetch job is unchanged.
```

---

## Debater Agent Design (`agent_debater.py`)

### Three Personas

Each persona gets: zone metadata, current weather signals, 30-day ML prediction, GloFAS discharge ratio, NDWI delta, drainage capacity, population density.

| Persona | Focus |
|---------|-------|
| **Hydrologist** | River discharge, antecedent moisture, soil saturation, 2022 flood comparison |
| **Meteorologist** | ECMWF/GFS forecast, monsoon progression, 48h rainfall accumulation |
| **Urban Planner** | Drainage capacity vs forecast rain, population density, infrastructure vulnerability |

### Per-Persona Output
```json
{
  "persona": "Hydrologist",
  "assessment": "Discharge pattern matches 2022 flood. HIGH risk Day 9.",
  "risk_vote": 0.82,
  "key_factor": "GloFAS discharge 2.1x normal with rising momentum",
  "urgency": "ACT_NOW"
}
```
`urgency` values: `MONITOR | PREPARE | ACT_NOW`

### Consensus Output (4th Gemini call)
```json
{
  "flood_probability": 0.78,
  "verdict": "CRITICAL — 78% flood probability, Days 9-12",
  "urgency": "ACT_NOW",
  "recommended_action_window_days": [9, 12],
  "unanimous": false,
  "rationale": "Two of three experts rate ACT_NOW. Hydrologist discharge match to 2022 is decisive."
}
```

### Full DebateResult JSON Schema
```json
{
  "zone_id": "sukkur-city",
  "zone_name": "Sukkur City",
  "debate_timestamp": "2026-05-19T14:00:00Z",
  "trigger": "peak_flood_risk=0.78 exceeded threshold=0.30",
  "ml_risk_input": {
    "peak_flood_risk": 0.78,
    "peak_flood_day": 9,
    "peak_heat_risk": 0.20,
    "overall_alert_level": "CRITICAL",
    "dominant_factor": "monsoon_onset",
    "avg_flood_risk": 0.45,
    "high_flood_days": 7
  },
  "zone_context": {
    "province": "Sindh",
    "population_density": 3800,
    "drainage_capacity": 0.30,
    "elevation_m": 66,
    "current_rain_24h_mm": 42.0,
    "glofas_discharge_ratio": 2.1,
    "ndwi_delta": 0.18
  },
  "personas": [
    { "persona": "Hydrologist", "assessment": "...", "risk_vote": 0.82, "key_factor": "...", "urgency": "ACT_NOW" },
    { "persona": "Meteorologist", "assessment": "...", "risk_vote": 0.75, "key_factor": "...", "urgency": "ACT_NOW" },
    { "persona": "Urban_Planner", "assessment": "...", "risk_vote": 0.71, "key_factor": "...", "urgency": "PREPARE" }
  ],
  "consensus": {
    "flood_probability": 0.78,
    "verdict": "CRITICAL — 78% flood probability, Days 9-12",
    "urgency": "ACT_NOW",
    "recommended_action_window_days": [9, 12],
    "unanimous": false,
    "rationale": "..."
  },
  "agent4_ready": true
}
```

---

## Orchestrator Agent Design (`agent_orchestrator.py`)

```python
class CIROOrchestrator:
    async def run_cycle(self) -> List[DebateResult]:
        # 1. Parallel: predict all 8 zones via existing ML endpoints
        # 2. Filter by RISK_ALERT_THRESHOLD
        # 3. Debate each high-risk zone
        # 4. Log JSON → Agent 4 input contract
```

Uses `httpx.AsyncClient` to call own FastAPI endpoints (loose coupling pattern already used in codebase).

### Router Endpoints
- `GET /api/v1/orchestrator/status` — last run time, zones evaluated, high-risk count, next run
- `POST /api/v1/orchestrator/run` — manually trigger full cycle

### Debater Router Endpoints
- `POST /api/v1/debater/debate/{zone_id}` — manually debate a single zone
- `GET /api/v1/debater/last-results` — most recent debate results

---

## New Settings (`config/settings.py` + `.env`)

```python
ORCHESTRATOR_INTERVAL_HOURS: int = 2
DEBATE_LLM_MODEL: str = "gemini-2.0-flash"
DEBATE_TEMPERATURE: float = 0.3
```

---

## Scheduler Change (`services/scheduler.py`)

New method on `CIROScheduler`:
```python
def add_orchestrator_job(self, callback) -> None:
    # IntervalTrigger(hours=ORCHESTRATOR_INTERVAL_HOURS)
    # id="ai_orchestrator_cycle"
```

---

## Files Changed

| File | Change |
|------|--------|
| `agents/agent_debater.py` | **New** — 3-persona Gemini debate + consensus |
| `agents/agent_orchestrator.py` | **New** — 2h scheduler cycle, threshold gate |
| `config/settings.py` | Add 3 new settings fields |
| `services/scheduler.py` | Add `add_orchestrator_job()` method |
| `main.py` | Mount 2 new routers, wire orchestrator job at startup |
| `.env` | Add 3 new env vars |

---

## Agent 4 (Future)

Agent 4 will consume the `DebateResult` JSON array from the orchestrator.  
The `agent4_ready: true` field marks zones where consensus urgency is `ACT_NOW` or `PREPARE`.  
Implementation deferred — orchestrator will call Agent 4 once it exists.
