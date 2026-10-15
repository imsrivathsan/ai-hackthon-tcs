from datetime import datetime
from typing import Annotated, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- Standard Error Model ---
class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


# --- Health Check Model ---
class HealthResponse(BaseModel):
    status: str
    app: str = "Meridian"
    version: str = "1.0.0"


# --- Item Models ---
ItemTag = Literal["M&A", "Leadership", "Product", "Pricing"]


class ItemBase(BaseModel):
    title: str
    tag: ItemTag
    date: str  # YYYY-MM-DD
    summary: str
    source_url: str
    impact_score: Annotated[int, Field(ge=1, le=5)]
    is_sample: bool = True


class ItemRead(ItemBase):
    id: str
    competitor_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Competitor Models ---
class CompetitorBase(BaseModel):
    id: str
    name: str
    ticker: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    headquarters: Optional[str] = None
    market_cap_tier: Optional[str] = None


class CompetitorRead(CompetitorBase):
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Battlecard Models ---
class BattlecardWin(BaseModel):
    title: str
    text: str
    source_url: str


class BattlecardMove(BaseModel):
    tag: ItemTag
    summary: str
    date: str  # YYYY-MM-DD
    source_url: str


class BattlecardMetrics(BaseModel):
    ma_deals_12m: int
    activity_trend: Annotated[List[int], Field(min_length=6, max_length=6)]
    evidence_confidence: int


class BattlecardResponse(BaseModel):
    competitor: str
    severity: Literal["High", "Medium", "Low"]
    threat_score: Annotated[int, Field(ge=0, le=100)]
    headline: str
    subtext: str
    wins: Annotated[List[BattlecardWin], Field(min_length=3, max_length=3)]
    moves: Annotated[List[BattlecardMove], Field(min_length=3, max_length=3)]
    metrics: BattlecardMetrics
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


# --- Overview Models ---
class RankedCompetitor(BaseModel):
    id: str
    name: str
    ticker: Optional[str] = None
    headquarters: Optional[str] = None
    market_cap_tier: Optional[str] = None
    threat_score: int
    severity: Literal["High", "Medium", "Low"]
    headline: str
    ma_deals_12m: int
    activity_trend: List[int]
    evidence_confidence: int
    updated_at: str


class QuarterlyMADeal(BaseModel):
    quarter: str
    deals: int
    competitor_breakdown: dict[str, int] = Field(default_factory=dict)


class MarketInsightResponse(BaseModel):
    insight: str
    model_used: str
    cached: bool = True


class OverviewResponse(BaseModel):
    competitors: List[RankedCompetitor]
    total_competitors: int
    quarterly_ma: List[QuarterlyMADeal]
    market_insight: Optional[MarketInsightResponse] = None
    generated_at: str


class AdminRefreshResponse(BaseModel):
    status: str = "ok"
    competitor_id: str
    competitor_name: str
    items_upserted: int
    threat_score: int
    severity: str
    updated_at: str



# --- Feed Models ---
class FeedItemRead(BaseModel):
    id: str
    competitor_id: str
    competitor_name: str
    competitor_ticker: Optional[str] = None
    title: str
    tag: ItemTag
    date: str
    summary: str
    source_url: str
    impact_score: int
    is_sample: bool = True
    created_at: datetime


class FeedResponse(BaseModel):
    items: List[FeedItemRead]
    total: int
    page: int
    limit: int
    total_pages: int


# --- Meeting Brief Model ---
class MeetingBriefResponse(BaseModel):
    competitor_id: str
    competitor_name: str
    talk_track: Annotated[List[str], Field(min_length=5, max_length=5)]
    brief_text: str
    model_used: str
    generated_at: str


# --- Ask / Analyst Models ---
class CitationItem(BaseModel):
    id: str
    competitor_id: str
    competitor_name: str
    title: str
    tag: ItemTag
    date: str
    summary: str
    source_url: str


class AskRequest(BaseModel):
    question: Annotated[str, Field(min_length=2, max_length=500)]
    competitor_id: Optional[str] = None
    tag: Optional[ItemTag] = None


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: List[CitationItem]
    model_used: str
    retrieved_count: int
    generated_at: str


