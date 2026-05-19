# Agent 1 — Imagery & Geospatial

> Satellite-based flood detection using Google Earth Engine + GeoGemma (Gemini Vision)

## Overview

Agent 1 provides **ground-truth visual flood evidence** by analyzing Sentinel-2 satellite imagery. It fills the `ndwi_delta` feature in Agent 3's prediction pipeline with actual water body expansion data from space.

## Pipeline

```
Sentinel-2 (10m) → Earth Engine (NDWI compute) → GeoGemma (AI interpret) → Signal Store → Agent 3
```

1. **Google Earth Engine** pulls the latest cloud-free Sentinel-2 L2A image for each zone
2. **NDWI** (Normalized Difference Water Index) is computed: `(B3-B8)/(B3+B8)`
3. **Change detection** compares current NDWI with 30-day baseline
4. **GeoGemma** (Gemini Vision) analyzes the imagery and provides structured flood assessment
5. **Signal** (`ndwi_delta`) is stored in Agent 2's buffer and broadcast via WebSocket

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/agent1/status` | Agent health + auth status |
| POST | `/api/v1/agent1/initialize` | Initialize GEE authentication |
| POST | `/api/v1/agent1/analyze/{zone_id}` | Analyze one zone |
| POST | `/api/v1/agent1/analyze-all` | Analyze all 8 zones |
| GET | `/api/v1/agent1/latest/{zone_id}` | Get cached analysis result |
| GET | `/api/v1/agent1/imagery/{zone_id}` | Get satellite image URLs |
| GET | `/api/v1/agent1/history/{zone_id}` | NDWI trend over time |
| GET | `/api/v1/agent1/flood-map/{zone_id}` | Classified flood extent map |

## Configuration

```env
# Required for AI analysis
GOOGLE_API_KEY=your_gemini_api_key

# Optional for live satellite data (falls back to simulation without these)
GEE_PROJECT_ID=your-gee-project
GEE_SERVICE_ACCOUNT=account@project.iam.gserviceaccount.com
GEE_CREDENTIALS_PATH=./gee-key.json
```

## Modes

### Full Mode (GEE + Gemini authenticated)
- Real Sentinel-2 imagery from Google Earth Engine
- 10m resolution NDWI/NDVI computation
- GeoGemma visual analysis of actual satellite images
- Thumbnail URLs served to Flutter app
- Confidence: 0.85+

### Simulation Mode (no GEE auth)
- Realistic simulated NDWI values based on zone characteristics + seasonality
- GeoGemma still analyzes numeric data (text-based, no images)
- Lower confidence: 0.50
- **Still functional for hackathon demo**

### Fallback Mode (no Gemini key either)
- Rule-based analysis using NDWI delta + zone vulnerability
- No AI interpretation
- Lowest confidence: 0.50
- Basic recommendations generated from severity rules

## Integration with Agent 2/3

Agent 1 stores signals with:
- `signal_type`: `"satellite_ndwi"`
- `source`: `"satellite_agent1"`
- `value`: the `ndwi_delta` (positive = more water)

Agent 2's `/features/{zone_id}` endpoint already has the `ndwi_delta` field.
Agent 3's XGBoost model uses it as a flood prediction feature.

## GeoGemma Output Format

```json
{
  "flood_detected": true,
  "water_expansion_percent": 35.2,
  "affected_area_description": "Significant water accumulation detected...",
  "estimated_flood_extent_km2": 12.5,
  "confidence": 0.82,
  "risk_factors": ["Monsoon rainfall", "Poor drainage", "Low elevation"],
  "severity": 7,
  "recommendations": ["Issue flood warning", "Activate evacuation routes"],
  "land_use_changes": "Agricultural land submerged near river bank",
  "vegetation_stress": "NDVI decrease indicates waterlogging"
}
```

## Scheduling

- **Default**: Daily analysis (Sentinel-2 revisit ~5 days)
- **Cache TTL**: 6 hours (avoids redundant GEE calls)
- **On-demand**: Available via POST endpoints
- **Background mode**: `POST /analyze-all?background=true` for non-blocking

## Files

```
backend/
├── agents/agent_imagery.py              # Router + endpoints + pipeline
├── services/earth_engine_service.py     # GEE auth + Sentinel-2 + NDWI
└── services/geogemma_service.py         # Gemini Vision API + analysis
```
