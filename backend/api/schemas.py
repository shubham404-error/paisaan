from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class MarketOverviewResponse(BaseModel):
    index: str
    as_of: str | None
    ingested_at: str
    source: str
    is_stale: bool
    universe_count: int
    breadth: dict[str, int]
    average_change_pct: float
    constituents: list[dict]
