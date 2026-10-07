# Backend service

Run locally after installing dependencies:

```powershell
uvicorn backend.api.main:app --reload --port 8000
```

The Streamlit UI consumes `GET /v1/market/overview` and `GET /v1/stocks/{symbol}/bars`. NSE MCP access is confined to `backend/data/nse_provider.py`.

For production, set `DATABASE_URL` to PostgreSQL/TimescaleDB and `REDIS_URL` to a managed Redis instance. Use a scheduler to invoke `backend.worker.tasks.refresh_nifty_200_overview` after each market close.
