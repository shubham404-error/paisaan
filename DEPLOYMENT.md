# Streamlit Cloud deployment checklist

## Before publishing

- [ ] Run `python -m unittest discover -s tests -v` locally.
- [ ] Run `python -m streamlit run app.py` and confirm Dashboard, Screener, and Charts load.
- [ ] Confirm the dashboard reports **200** verified Nifty 200 constituents and a current `as of` date.
- [ ] Open a chart for a few different symbols and ranges; confirm Yahoo daily candlesticks, overlays, volume, RSI, and crossover markers render.
- [ ] Use **Refresh NSE data** once and confirm the app recovers cleanly.
- [ ] Confirm no placeholder news or investment recommendations are visible.

## Streamlit Community Cloud

1. Push the `main` branch to GitHub.
2. Create a new app from the repository, with `app.py` as the entrypoint.
3. Use Python 3.11 or later and let Community Cloud install `requirements.txt`.
4. Do not configure `STREAMLIT_API_BASE_URL`; the production app does not use a separate API.
5. Open the deployed URL and repeat the pre-publish checks.

## Operating limits

- NSE MCP is an upstream public service. The app retries a failed constituent, quote, or dashboard-chart request three times with backoff, then presents a retry button.
- Yahoo Finance supplies selected-symbol daily charts. A Yahoo rate limit or provider error leaves the last valid session chart available.
- Market data is cached in the Streamlit runtime: quotes for 10 minutes, NSE dashboard history for one hour, and Yahoo charts for four hours.
- Session-only watchlists are deliberately hidden until a persistent, authenticated implementation is available.
- The full-universe screener uses cached EOD fields. A durable 200-stock historical technical screen needs external persistence and scheduled workers, which are deliberately outside this Streamlit-only deployment.
