# paisaan · CapitalSense Advisors

A standalone CapitalSense Advisors market desk, built around the **paisaan** meme. It includes a calm dark dashboard, screener, high-performance historical charts, watchlist and news screens. Live market data is loaded directly through NSE's official CM-market MCP, and historical charts are loaded through NSE's official Bhavcopy MCP.

## Run it

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## NSE MCP data layer

The lab supports both official NSE public Streamable HTTP endpoints:

```text
https://mcp.nseindia.in/cmmkt/mcp
https://mcp.nseindia.in/bhavcopy/cm/mcp
```

The dashboard and screener first load the official Nifty 200 constituent list from NSE Indices, then quote every constituent through the Bhavcopy MCP `get_bulk_quote` tool in batches. The Charts screen calls `get_stock_history` in three-month Bhavcopy chunks and offers 1D, 1W, 1M, 3M, 6M, 1Y, and 3Y views.

Exchange data is informational; this project does not provide trading recommendations or order execution.
