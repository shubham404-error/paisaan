# paisaan · CapitalSense Advisors

A standalone CapitalSense Advisors market desk, built around the **paisaan** meme. It includes a calm dark dashboard, full-universe EOD screener, historical charts, watchlist and news screens. The deployed application is self-contained: Streamlit reads the official Nifty 200 constituent file and NSE Bhavcopy MCP directly, then caches results in the running app.

## Run it

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

This is the deployment command for Streamlit Community Cloud as well. Add any required configuration through Streamlit secrets; the default official NSE endpoints are already configured in code.

For local Postgres/Redis containers:

```powershell
docker compose up --build
```

## NSE MCP data layer

The Streamlit data adapter uses the official NSE public Streamable HTTP endpoints:

```text
https://mcp.nseindia.in/cmmkt/mcp
https://mcp.nseindia.in/bhavcopy/cm/mcp
```

The app first loads the official Nifty 200 constituent list from NSE Indices, then quotes every constituent through the Bhavcopy MCP `get_bulk_quote` tool in batches. The Charts screen fetches historical Bhavcopy data only for the selected symbol and caches it, avoiding an expensive full-history reload on each visit.

The Screener is intentionally based on the complete cached EOD quote snapshot (industry, daily move, volume, price range). A Streamlit-only deployment cannot reliably run a persistent 200-stock, three-year backfill or scheduled technical pipeline; advanced historical metrics remain available in the repository's optional backend path for a future infrastructure upgrade.

The Dashboard preview and Charts view use Yahoo Finance daily data for the selected Nifty 200 stock only. They retain raw Close, build adjusted OHLC consistently from Adjusted Close, then render Terminal-compatible EMA/SMA, volume, RSI, and bullish-crossover signals. Provider failures are controlled and retain the last valid chart for the active session.

The app has no user accounts or persistent storage in this release, so Watchlists are intentionally not shown. It also protects the NSE upstream with a shared 60-second manual-refresh cooldown.

See [the deployment checklist](DEPLOYMENT.md) before publishing to Streamlit Community Cloud.

Exchange data is informational; this project does not provide trading recommendations or order execution.
