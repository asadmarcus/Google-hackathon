# CIRO — Product Brief

> Context document for Antigravity. Explains *what* is being built and *why*, and maps every
> Challenge-3 requirement to a concrete feature so Antigravity (and the judges) can see coverage.

---

## 1. One-paragraph pitch

**CIRO (Crisis Intelligence & Response Orchestrator)** is a multi-agent AI system that fuses
real-time signals to predict and respond to urban crises — **floods and heatwaves** — across
**8 cities in Pakistan**. Six cooperating agents collect data, run a dual-ML 30-day forecast,
interpret satellite imagery, stage a 3-expert LLM debate, and generate a simulated coordinated
emergency response with before/after impact. It ships as a **FastAPI backend** + **Flutter mobile
app** + two web dashboards.

---

## 2. The problem (Challenge 3)

Cities face localized crises — urban flooding, heatwaves, road blockages, infrastructure failure.
Signals exist (social media, weather, traffic, sensors, field reports) but response systems are
**fragmented, reactive, slow**. Critical signals are never converted into **coordinated, actionable
decisions in real time**.

**Challenge 3 asks for an Agentic AI System that:**
1. Ingests & fuses ≥3 signal sources.
2. Detects & classifies crises (type, location, severity, confidence, affected population, evolution).
3. Prioritises & allocates constrained response resources across simultaneous crises.
4. Simulates coordinated actions (rerouting, dispatch, hospital prep, alerts).
5. Predicts outcomes/side-effects; handles false positives/negatives & conflicting signals.

---

## 3. The solution — a 6-agent system

CIRO is built as a pipeline of six cooperating agents. (Full technical detail: `02_ARCHITECTURE.md`.)

| # | Agent | Role | One-line behaviour |
|---|-------|------|--------------------|
| 1 | **Imagery & Geospatial** | Satellite ground-truth | Sentinel-2 NDWI change detection + GeoGemma (Gemini Vision) flood interpretation |
| 2 | **Data & API Collector** | Multi-signal fusion | Polls 6 sources every 15 min, normalises to one Signal schema, stores in SQLite, pushes via WebSocket |
| 3 | **ML Predictor** | Crisis detection & severity | Dual-model 30-day forecast: XGBoost flood classifier + Prophet weather + UNICEF heat engine |
| — | **Debater** | Reasoning | 3 Gemini personas (Hydrologist, Meteorologist, Urban Planner) + a consensus synthesiser |
| — | **Orchestrator** | Coordination | Every 2 h: predict all zones → threshold-gate → debate high-risk → hand to Agent 4 → log full trace |
| 4 | **Response Commander** | Action & simulation | Gemini plans 4–8 response actions, simulates before/after state, estimates lives saved |

The data flow: **Agent 1 + Agent 2 (signals) → Agent 3 (predict) → Debater (reason) → Agent 4
(act + simulate)**, all coordinated by the **Orchestrator** and surfaced through the **Flutter app**.

---

## 4. Challenge-3 requirements → CIRO features (coverage map)

Give this table to Antigravity and reuse it in the README. Every mandatory requirement is covered.

| Challenge-3 requirement | Where CIRO delivers it |
|--------------------------|------------------------|
| Ingest & fuse ≥3 signal sources | Agent 2 fuses **6**: Open-Meteo weather, GloFAS flood discharge, OpenWeatherMap, Google Maps traffic, NDMA alerts, social keywords (Urdu+English). Agent 1 adds a 7th: satellite NDWI. |
| Source credibility / misinformation | Every signal carries a `confidence` field; simulated sources are honestly tagged `0.50`; real APIs `0.85–0.95`. Debater is told which numbers are ML-derived vs LLM opinion. |
| Crisis classification (type, severity, confidence) | Agent 3 outputs `flood_risk` + `heatstroke_risk` per day, `alert_level` (NONE→CRITICAL), confidence tier (high/moderate/low) per day. Debater classifies `trigger_type` = FLOOD / HEAT / BOTH. |
| Severity & evolution prediction | Agent 3 produces a **30-day** day-by-day forecast with peak day, peak risk, high-risk-day counts; temporal EWMA models how risk *builds* over time. |
| Resource allocation optimisation | Agent 4 plans constrained actions (evacuation buses, shelters, medical units, rescue boats) sized to zone population/shelters/hospitals. |
| Multi-crisis coordination | Orchestrator evaluates all **8 zones** each cycle, threshold-gates, and routes multiple high-risk zones through Debater + Agent 4 with an explicit action queue. |
| Impact simulation (before/after) | Agent 4 `ResponseSimulation`: `before` vs `after` state — population evacuated, shelters activated, lives saved, response-coverage %. |
| Stakeholder notification | Agent 4 actions name real agencies (NDMA, PDMA, Rescue 1122, Pakistan Army, Pakistan Navy) and channels (SMS, mosque loudspeakers, TV). |
| False positive / conflicting signals | Debater `trigger_type` logic prevents a heat-only event reporting a flood probability; Agent 1 vs weather conflict is surfaced; every external call has retry + circuit breaker + graceful fallback. |
| Robustness / degraded mode | `retry_client.py` (exponential backoff + circuit breaker), `gemini_retry.py` (429 handling), simulation fallbacks on every data source, lazy model training. |
| Agentic workflow / traceable decisions | Orchestrator writes a full `OrchestrationLog` per cycle: timestamped steps, debate transcripts, Agent-4 reasoning traces — exposed at `/api/v1/orchestrator/logs` and shown in the app. |
| Working mobile app (**mandatory**) | Flutter app `ciro_app/` — Home, AI Agents (pipeline), Live Map, Prediction screens. |
| Web app (optional) | Two dashboards: control panel (`/`) and interactive crisis map (`/map`). |

---

## 5. Evaluation rubric → where CIRO scores (Challenge 3)

| Criterion | Weight | CIRO's evidence |
|-----------|-------:|-----------------|
| Antigravity integration | 20% | This rebuild kit — Antigravity plans, verifies, hardens, runs and documents the system; artifacts exported. |
| Crisis detection & severity analysis | 25% | Dual-ML 30-day forecast; XGBoost trained on 1,572 real Pakistan samples (60 flood events); 6 temporal-intelligence enhancements; UNICEF heatwave methodology. |
| Resource optimisation & multi-crisis coordination | 20% | Orchestrator multi-zone cycle + Agent 4 constrained action planning + action queue. |
| Impact simulation & stakeholder coordination | 15% | Agent 4 before/after simulation, effectiveness score, agency-specific actions. |
| Robustness, scalability, cost & latency | 10% | Retry/circuit-breaker, fallbacks, SQLite buffer + auto-prune, caching; cost/latency notes in README. |
| Innovation & UX | 10% | Multi-persona LLM debate, satellite+ML fusion, polished dark-mode Flutter app + live map. |

> **Note:** the FAQ rubric for Challenge 3 reads *Antigravity 20% / detection 25% / resources 20% /
> simulation 15% / robustness 10% / innovation 10%*. The Challenges PDF lists slightly different
> weights. Use the FAQ version — it is the more recent document.

---

## 6. Scope — what is real vs mocked

Per the hackathon rule "use mock data if real APIs are unavailable", CIRO is honest about this:

**Real, live data (no key needed):**
- Open-Meteo weather + 16-day ECMWF/GFS forecast.
- Open-Meteo GloFAS 30-day river-discharge flood forecast.
- ML models trained on **real** Pakistan data — Google Earth Engine (MODIS LST + CHIRPS), 2000–2021.

**Real with an optional key:** OpenWeatherMap, Google Maps traffic, Gemini (Debater/Agent 4/GeoGemma),
Google Earth Engine satellite imagery, Google Flood Hub.

**Honestly simulated (tagged `confidence = 0.50`):** NDMA official alerts (no public API),
social-media crisis keywords. Both use realistic Urdu+English templates and seasonal probabilities.

**Graceful degradation:** every component falls back to simulation if its API/key is missing, so
the system always runs for a demo.

---

## 7. The 8 monitored zones

| Zone ID | City | Province | Why it matters |
|---------|------|----------|----------------|
| `islamabad-g10` | G-10, Islamabad | Federal | Capital; moderate flood risk |
| `lahore-city` | Lahore City | Punjab | Dense urban; active heatwave zone |
| `karachi-south` | Karachi South | Sindh | Coastal megacity; flash-flood risk |
| `peshawar-city` | Peshawar City | KPK | Mountain-runoff floods |
| `multan-city` | Multan City | Punjab | Extreme heat (47 °C+) |
| `jacobabad-city` | Jacobabad City | Sindh | Hottest city in Pakistan (52 °C recorded) |
| `sukkur-city` | Sukkur City | Sindh | 2022 Indus flood epicentre |
| `quetta-city` | Quetta City | Balochistan | Flash floods from surrounding hills |

---

## 8. The demo-video narrative (3–5 min)

Challenge 3 wants: *multi-source input → crisis detection → severity prediction → resource
allocation → simulated response → impact visualisation → recovery*. Film this flow:

1. **Open the Flutter app** — Home screen, 8 zones sorted by risk, live WebSocket dot = LIVE.
2. **Tap a high-risk zone** → Prediction screen: 30-day flood/heat chart, AI risk summary,
   current conditions, Agent-1 satellite status, confidence tiers.
3. **Backend dashboard** (`/`) — trigger **Fetch All Signals**: 6 sources × 8 zones ingest live.
4. **AI Agents screen** → **Run Full Pipeline**: Orchestrator predicts all 8 zones, threshold-gates,
   runs the 3-persona debate on high-risk zones, Agent 4 plans response + simulation.
5. Show the **debate transcripts**, the **action queue**, the **before/after simulation** (lives
   saved, evacuated, shelters), and the **run log trace**.
6. **Live crisis map** (`/map`) — heatmap of all 8 zones with the 30-day timeline slider.
7. **Recovery** — narrate the false-alarm path: Debater `trigger_type` keeps a heat event from
   reporting flood probability; a failed API falls back to simulation.

Separately record the **2–3 min Antigravity screen-capture** (see `05_ANTIGRAVITY_PLAYBOOK.md` §5).
