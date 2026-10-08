# Backend service

Run locally after installing dependencies:

```powershell
uvicorn backend.api.main:app --reload --port 8000
```

The Streamlit UI consumes `GET /v1/market/overview` and `GET /v1/stocks/{symbol}/bars`. NSE MCP access is confined to `backend/data/nse_provider.py`.

Additional persisted-data endpoints:

- `GET /v1/sectors` - latest Nifty 200 sector breadth and turnover.
- `GET /v1/screener?industry=Healthcare&min_rsi=55&above_sma50=true` - safe, indexed technical filters.

For production, set `DATABASE_URL` to PostgreSQL/TimescaleDB and `REDIS_URL` to a managed Redis instance. Use a scheduler to invoke `backend.worker.tasks.ingest_nifty_200_market_close` after each market close.

## First data load

Run `ingest_nifty_200_market_close` first to persist the official membership and latest EOD bars. Then invoke `enqueue_initial_backfill.delay(36)` once; it creates one 36-month history task per active constituent. Technical snapshots are calculated after each backfill and refreshed after every subsequent EOD ingestion.

When Redis/Celery is not available locally, use the resumable development runner instead:

```powershell
python -m backend.worker.local_backfill --months 36 --pause-seconds 2
```
