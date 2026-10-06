# InvestorPaisa-style Streamlit desk

A hands-on Streamlit recreation of the visual patterns in InvestorPaisa: a calm dark market dashboard, screener, chart, watchlist and news screens. Live market data is loaded directly through NSE's official CM-market MCP, and historical charts are loaded through NSE's official Bhavcopy MCP.

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

The dashboard and screener load 200 live NSE equity records using `cm_get_equity_stocks`. The Charts screen calls `get_stock_history` in three-month Bhavcopy chunks and offers 1D, 1W, 1M, 3M, 6M, 1Y, and 3Y views. The adapter lives in `nse_mcp.py`; `NSE_MCP_URL` can override the CM-market endpoint.

Exchange data is informational; this project does not provide trading recommendations or order execution.
