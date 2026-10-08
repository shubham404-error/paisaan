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

The app first loads the official Nifty 200 constituent list from NSE Indices, then quotes every constituent through the Bhavcopy MCP `get_bulk_quote` tool in batches. Selected-symbol charts are served from Yahoo Finance daily data and cached in the Streamlit runtime.

The Screener begins with the complete cached EOD quote snapshot (industry, daily move, volume, price range). It can optionally enrich a user-requested shortlist with Yahoo Finance P/E, P/B, ROE, dividend yield, and market cap. If `GEMINI_API_KEY` is configured in Streamlit secrets, Gemini translates normal-language requests into that same small, validated filter set; it does not make market-data requests or recommendations.

The Dashboard preview and Charts view use Yahoo Finance daily data for the selected Nifty 200 stock only. They retain raw Close, build adjusted OHLC consistently from Adjusted Close, then render Terminal-compatible EMA/SMA, volume, RSI, and bullish-crossover signals. Provider failures are controlled and retain the last valid chart for the active session.

Watchlists are available without an account: users can create named session lists of up to 20 Nifty 200 stocks, download them as JSON, and restore them later by upload. Yahoo Finance supplies an on-demand performance and fundamentals overview. Hosted, Google-backed sync is deliberately deferred. The app also protects the NSE upstream with a shared 60-second manual-refresh cooldown.

See [the deployment checklist](DEPLOYMENT.md) before publishing to Streamlit Community Cloud.

Exchange data is informational; this project does not provide trading recommendations or order execution.
