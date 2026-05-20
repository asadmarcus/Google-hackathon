# CIRO — Known Issues & Fixes

> Real defects found in the current repo. Fixing these gives Antigravity **genuine engineering
> work** (so the agent trace is real, not cosmetic) and makes the submission cleaner. Antigravity
> is told to fix sections A–D in Prompt A2.

---

## A. Toolchain fingerprints & housekeeping — do these FIRST (no agent turn needed)

These reveal that the project was **not** built in Antigravity. Remove them before the rebuild
and before submission.

| # | Issue | Action |
|---|-------|--------|
| A1 | `.claude/` folder — `settings.local.json` contains Windows paths `D:\Wajahat\projects\Fuckathon` and Claude Code permission rules. Direct evidence of the real toolchain. | **Delete the `.claude/` folder.** |
| A2 | `.idea/` folder — JetBrains / Android Studio project files. | **Delete the `.idea/` folder.** |
| A3 | Stray **empty (0-byte) files** in `backend/`: `May`, `[deck.gl`, `functionality`, `like` — accidental shell artifacts. | **Delete all four.** |
| A4 | Repo name **`Fuckathon`** — unprofessional for judges; appears in `README.md` and `main.py`'s docstring (`GitHub: https://github.com/asadmarcus/Fuckathon`). | Rename the repo/folder to `ciro` (or similar) and update the URL references. |
| A5 | `backend/models/weather/` holds `*.joblib` files that the code never loads — `weather_forecaster.py` reads `models/prophet/*.pkl` only. Dead artifacts from an earlier approach. | Delete `backend/models/weather/` (optional cleanup). |
| A6 | `.gitignore` ignores `backend/models/*.joblib` and `backend/models/*.pkl` (top level only) but the `prophet/` sub-folder `.pkl`s are still tracked — inconsistent. | Decide: either commit all model files (faster first run for judges) or ignore them all consistently. Committing them is recommended for the demo. |

> A1–A3 are the important ones for the "built in Antigravity" story. Do them manually in the
> Editor/terminal — they don't need an agent turn.

---

## B. Real code bugs — fix these (Antigravity Prompt A2 / B5–B6)

### B1 — `agent_response.py`: `zone_context` used before assignment (NameError)

**File:** `backend/agents/agent_response.py`, endpoint `POST /respond/{zone_id}`
(`respond_to_crisis`).
**Bug:** `debate_data` references `zone_context` **before** `zone_context` is defined a few lines
later. Calling `/api/v1/agent4/respond/{zone_id}` raises `NameError: name 'zone_context' is not
defined`.

Current (broken) order:
```python
    # Run debate
    debate_data = {
        "zone": zone,
        "ml_prediction": prediction,
        "zone_context": zone_context,            # ← used here, not yet defined
        "threshold": settings.RISK_ALERT_THRESHOLD,
    }
    debate_result = await debater.debate_zone(debate_data)
    ...
    # Plan response with Gemini
    zone_context = {                              # ← defined only here
        "drainage_capacity": zone.get("drainage_capacity", 0.3),
        "elevation_m": zone.get("elevation_m", 50),
        "population_density": zone.get("population_density", 3000),
        "current_rain_24h_mm": 0,
    }
```

**Fix:** move the `zone_context = {...}` block **above** `debate_data`, so it is defined before
first use:
```python
    # Build zone context once, before the debate
    zone_context = {
        "drainage_capacity": zone.get("drainage_capacity", 0.3),
        "elevation_m": zone.get("elevation_m", 50),
        "population_density": zone.get("population_density", 3000),
        "current_rain_24h_mm": 0,
    }

    # Run debate
    debate_data = {
        "zone": zone,
        "ml_prediction": prediction,
        "zone_context": zone_context,
        "threshold": settings.RISK_ALERT_THRESHOLD,
    }
    debate_result = await debater.debate_zone(debate_data)
    ...
    # (the later duplicate zone_context definition is now removed)
```
Note: the orchestrator path (`agent_orchestrator._run_agent4_response`) builds its own
`zone_context` and is fine — only the direct `/respond/{zone_id}` endpoint is broken.

### B2 — `main.py`: `/map` route serves the wrong path

**File:** `backend/main.py`, route `GET /map` (`crisis_map`).
**Bug:** `return FileResponse("backend/static/crisis_map.html")`. The server is launched from the
`backend/` directory (`cd backend && uvicorn main:app ...`), so the working directory is already
`backend/`. The path should be `static/crisis_map.html` — exactly like `GET /` which correctly
uses `FileResponse("static/index.html")`. As written, `/map` returns 404 and the Flutter
"Live Map" screen (which opens `<baseUrl>/map`) is broken.

**Fix:**
```python
return FileResponse("static/crisis_map.html")
```

### B3 — `static/index.html`: Model Info panel reads non-existent fields

**File:** `backend/static/index.html`, function `loadModelInfo()`.
**Bug:** the `rows` array includes `['Heat AUC', m.heat_model_auc.toFixed(4)]` and
`['Heat Accuracy', (m.heat_model_accuracy * 100).toFixed(1) + '%']`. The `/api/v1/agent3/model/info`
endpoint returns a `ModelInfo` object with **only** `flood_model_accuracy` and `flood_model_auc`
— there are no `heat_model_*` fields. So `m.heat_model_auc.toFixed(4)` throws
`TypeError: Cannot read properties of undefined` and the Model Info panel fails to render.

**Fix:** remove the two heat rows from the `rows` array (CIRO's heat engine is rule-based and has
no AUC/accuracy). Keep only the flood + general rows:
```javascript
const rows = [
  ['Version',        m.model_version],
  ['Type',           m.model_type],
  ['Trained',        new Date(m.training_date).toLocaleString()],
  ['Samples',        m.training_samples.toLocaleString()],
  ['Source',         m.training_source],
  ['Flood AUC',      m.flood_model_auc.toFixed(4)],
  ['Flood Accuracy', (m.flood_model_accuracy * 100).toFixed(1) + '%'],
];
```
(Also update the log line that prints `m.heat_model_auc`.)

### B4 — `main.py`: `/health` reports a stale agent count

**File:** `backend/main.py`, route `GET /health`.
**Bug:** returns `"agents_active": 1` — hardcoded from when only Agent 2 existed. CIRO now runs
6 agents (1, 2, 3, 4, Debater, Orchestrator). A judge inspecting `/health` sees "1".

**Fix:** report the real number, e.g. `"agents_active": 6` (or derive it from the mounted
router count).

---

## C. Flutter — orphaned AlertsScreen

**File:** `ciro_app/lib/screens/alerts_screen.dart` (344 lines, fully implemented) vs
`ciro_app/lib/main.dart`.
**Issue:** `AlertsScreen` is a complete, working screen — a real-time WebSocket alert timeline
for severity ≥ 7 signals — but `main.dart` only wires **three** bottom-nav tabs (Home, AI Agents,
Live Map) and does not even import `alerts_screen.dart`. The screen is unreachable. The
`ciro_app/README.md` describes alerts as a feature, so this is a gap.

**Recommended fix (adds a demo-worthy feature):** wire `AlertsScreen` in as a 4th bottom-nav tab.
In `main.dart`: import `screens/alerts_screen.dart`; add `AlertsScreen()` to the `_screens` list;
add a 4th `BottomNavigationBarItem` (e.g. `Icons.notifications_rounded`, label `'Alerts'`). It
already consumes `WebSocketService` via Provider, so no other change is needed.

**Alternative:** if you want to keep 3 tabs, delete `alerts_screen.dart` and the alerts mention
in `ciro_app/README.md` so there is no dead code.

Recommended: **add the tab** — a live alert timeline strengthens the demo and the "real-time
crisis signals" story for Challenge 3.

---

## D. Naming & documentation inconsistencies (polish — low priority)

| # | Inconsistency | Suggested resolution |
|---|---------------|----------------------|
| D1 | The days-17–30 weather model is **Prophet** (`weather_forecaster.py` imports `from prophet import Prophet`), but `agent_predictor.py` labels its output `data_source = "xgboost_forecast"` and the `FeatureProjector` docstring calls it an "XGBoost weather forecaster". A judge reading the code sees a contradiction. | Pick one term. The model is Prophet — rename the `data_source` label to `"prophet_forecast"` and fix the docstring. (Functionally harmless; cosmetic only.) |
| D2 | `backend/AGENT2_DOCS.md` "Current Zones" table lists only **5** zones; the system has **8**. `static/index.html`'s `fetchAll()` logs "6 sources x 5 zones". Old commit messages also say "5 zones". | Update `AGENT2_DOCS.md` and the dashboard log string to 8. |
| D3 | Gemini model name differs across docs: `settings.py` = `gemini-2.5-flash-lite` (canonical), `docs/AI_AGENTS_PLAN.md` = `gemini-2.0-flash`, `ANTIGRAVITY_BLUEPRINT.md` = `gemini-1.5-flash`. | Treat `settings.py` as truth; fix the docs (or just delete the stale `ANTIGRAVITY_BLUEPRINT.md`, since this kit replaces it). |
| D4 | Jacobabad coordinates: `settings.py` & `zone.dart` use `(28.2810, 68.4376)`; `README.md` & `ANTIGRAVITY_BLUEPRINT.md` use `(28.2769, 68.4368)`. | `settings.py` is canonical — fix the README. |
| D5 | The repo already contains an old `ANTIGRAVITY_BLUEPRINT.md` (a partial, skeleton-only reverse-engineering doc). | Delete it — this `ANTIGRAVITY_REBUILD/` kit supersedes it and is far more complete. |

---

## E. Environment notes (not bugs — expect these)

- **Prophet install can be slow/fragile.** `prophet==1.1.5` pulls `cmdstanpy`/Stan and can take a
  few minutes or need build tools. If `pip install` stalls on Prophet, that's environmental, not
  a code bug — let it finish, or install Prophet first in its own step.
- **First `/predict` is slow (~15–20 s)** — it trains 12 Prophet models on first call, then
  caches them as `.pkl`. This is expected; subsequent calls are instant. Tell judges this in the
  demo or pre-warm it before recording.
- **No keys = simulation mode** for Agent 1 (satellite), Debater/Agent 4 (Gemini), traffic,
  OpenWeatherMap. The system still runs fully. For the richest demo, set `GEMINI_API_KEY` so the
  Debater and Agent 4 produce real LLM output.

---

## Fix priority for the deadline

1. **A1–A3** (delete `.claude/`, `.idea/`, stray files) — 2 minutes, do it now, manually.
2. **B1–B4** (real bugs) — Antigravity Prompt A2; ~1 agent turn.
3. **C** (AlertsScreen tab) — include in Prompt A2.
4. **D, A4–A6** — polish; do if time permits before submission.
