from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.api.schemas import HealthResponse, MarketOverviewResponse
from backend.core.config import get_settings
from backend.db.schema import ensure_local_schema
from backend import db as _db  # ensures database package is registered
import backend.db.models  # registers model metadata before local initialization
from backend.services.market import bars, overview, screen, sectors

settings = get_settings()
app = FastAPI(title="paisaan API", version="0.1.0", docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])


@app.on_event("startup")
def create_local_schema() -> None:
    """Convenience only for local SQLite; production uses versioned migrations."""
    ensure_local_schema()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="paisaan-api")


@app.get("/v1/market/overview", response_model=MarketOverviewResponse)
def market_overview(index: str = Query("NIFTY200")) -> dict:
    if index.upper() != "NIFTY200":
        raise HTTPException(status_code=400, detail="Only NIFTY200 is available in this release.")
    return overview()


@app.get("/v1/stocks/{symbol}/bars")
def stock_bars(symbol: str, range: str = Query("3M", pattern="^(1D|1W|1M|3M|6M|1Y|3Y)$")) -> dict:
    try:
        return bars(symbol, range)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/v1/sectors")
def market_sectors() -> dict:
    return sectors()


@app.get("/v1/screener")
def market_screener(
    industry: str | None = None,
    min_rsi: float | None = Query(None, ge=0, le=100),
    min_volume_ratio: float | None = Query(None, ge=0),
    above_sma50: bool | None = None,
    min_return_1m: float | None = None,
    above_sma200: bool | None = None,
    min_return_3m: float | None = None,
    min_rel_strength_6m: float | None = Query(None, ge=0, le=100),
    near_52w_high_pct: float | None = Query(None, ge=0, le=100),
    new_52w_high: bool | None = None,
    volume_spike: bool | None = None,
    golden_cross: bool | None = None,
    limit: int = Query(100, ge=1, le=200),
) -> dict:
    return screen(industry, min_rsi, min_volume_ratio, above_sma50, min_return_1m, above_sma200, min_return_3m, min_rel_strength_6m, near_52w_high_pct, new_52w_high, volume_spike, golden_cross, limit)
