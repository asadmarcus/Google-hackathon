# CIRO Backend — Crisis Intelligence & Response Orchestrator

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment
cp .env.example .env
# Edit .env with your API keys

# 4. Run the server
uvicorn main:app --reload --port 8000
```

## API Docs

Once running, visit: **http://localhost:8000/docs**

## Agent 2 Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/agent2/status` | GET | Agent health & config |
| `/api/v1/agent2/fetch` | POST | Trigger full signal fetch |
| `/api/v1/agent2/signals/{zone_id}` | GET | Latest signals for zone |
| `/api/v1/agent2/signals/{zone_id}/history` | GET | 30-day history |
| `/api/v1/agent2/features/{zone_id}` | GET | ML feature vector |
| `/api/v1/agent2/zones` | GET | All zones + risk summary |

## Architecture

```
ciro-backend/
├── main.py                  # FastAPI app entry point
├── config/
│   └── settings.py          # Zone definitions, API keys
├── agents/
│   └── agent_data_collector.py  # Agent 2 router + logic
├── services/
│   ├── weather_service.py   # OpenWeatherMap integration
│   ├── traffic_service.py   # Google Maps traffic
│   ├── social_service.py    # Simulated social signals
│   └── signal_store.py      # 30-day rolling buffer
├── models/                  # Agent 3 ML models (next)
├── requirements.txt
├── Dockerfile
└── .env.example
```

## Works Without API Keys!

All services have **simulation fallback** — if no API key is set, realistic Pakistan monsoon-aware data is generated. Perfect for demo/development.
