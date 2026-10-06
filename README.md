# InvestorPaisa-style Streamlit desk

A hands-on Streamlit recreation of the visual patterns in InvestorPaisa: a calm dark market dashboard, screener, chart, watchlist and news screens. It includes an NSE MCP lab so you can inspect and call the official NSE MCP server directly from the app.

## Run it

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## NSE MCP

The lab supports both official NSE public Streamable HTTP endpoints:

```text
https://mcp.nseindia.in/cmmkt/mcp
https://mcp.nseindia.in/bhavcopy/cm/mcp
```

Open **NSE MCP lab** in the sidebar, discover the server's current tools, then choose a tool and supply its JSON arguments. The adapter lives in `nse_mcp.py`; `NSE_MCP_URL` can override the endpoint (for example to use another NSE MCP server).

The dashboard launches on demo data so its screens remain predictable while you learn the live MCP tools. Exchange data is informational; this project does not provide trading recommendations or order execution.
