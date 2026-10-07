# paisaan · CapitalSense Advisors

A standalone CapitalSense Advisors market desk, built around the **paisaan** meme. It includes a calm dark dashboard, screener, high-performance historical charts, watchlist and news screens. The Streamlit UI reads from the project API; only the backend talks to NSE MCP.

## Run it

```powershell
python -m pip install -r requirements.txt
python -m uvicorn backend.api.main:app --reload --port 8000
python -m streamlit run app.py
```

Run the API in one terminal before launching Streamlit in another. Streamlit reads from `http://localhost:8000` by default; set `STREAMLIT_API_BASE_URL` when deploying it elsewhere.

For local Postgres/Redis containers:

```powershell
docker compose up --build
```

## NSE MCP data layer

The backend uses the official NSE public Streamable HTTP endpoints:

```text
https://mcp.nseindia.in/cmmkt/mcp
https://mcp.nseindia.in/bhavcopy/cm/mcp
```

The backend first loads the official Nifty 200 constituent list from NSE Indices, then quotes every constituent through the Bhavcopy MCP `get_bulk_quote` tool in batches. The Charts screen requests cached history through the API; the backend performs source access and caching.

Exchange data is informational; this project does not provide trading recommendations or order execution.
