from datetime import datetime, timezone
from typing import Dict, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Battlecard, Competitor, Item
from app.schemas import ErrorResponse, MarketInsightResponse, OverviewResponse, QuarterlyMADeal, RankedCompetitor
from app.services.llm_router import get_market_insight

router = APIRouter(prefix="/overview", tags=["overview"])


def get_quarter_str(date_str: str) -> str:
    """Converts YYYY-MM-DD into 'QX YYYY' format."""
    try:
        dt = datetime.fromisoformat(date_str[:10])
        quarter = (dt.month - 1) // 3 + 1
        return f"Q{quarter} {dt.year}"
    except Exception:
        return "Unknown"


@router.get(
    "",
    response_model=OverviewResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Get market overview with ranked competitors and quarterly M&A trends",
)
def get_overview(db: Session = Depends(get_db)):
    """
    Returns all tracked competitors ranked by threat_score descending,
    along with calculated quarterly M&A deals for the macro landscape.
    """
    # 1. Fetch competitors with battlecards
    competitor_rows = (
        db.query(Competitor, Battlecard)
        .outerjoin(Battlecard, Competitor.id == Battlecard.competitor_id)
        .all()
    )

    ranked: List[RankedCompetitor] = []
    for comp, card in competitor_rows:
        threat_score = card.threat_score if card else 0
        severity = card.severity if card else "Low"
        headline = card.headline if card else f"Coverage for {comp.name}"
        ma_deals = card.metrics.get("ma_deals_12m", 0) if card and card.metrics else 0
        trend = card.metrics.get("activity_trend", [0] * 6) if card and card.metrics else [0] * 6
        confidence = card.metrics.get("evidence_confidence", 0) if card and card.metrics else 0
        updated = card.updated_at.isoformat() if card else comp.updated_at.isoformat()

        ranked.append(
            RankedCompetitor(
                id=comp.id,
                name=comp.name,
                ticker=comp.ticker,
                headquarters=comp.headquarters,
                market_cap_tier=comp.market_cap_tier,
                threat_score=threat_score,
                severity=severity,
                headline=headline,
                ma_deals_12m=ma_deals,
                activity_trend=trend,
                evidence_confidence=confidence,
                updated_at=updated,
            )
        )

    # Sort competitors by threat_score descending
    ranked.sort(key=lambda x: x.threat_score, reverse=True)

    # 2. Compute quarterly M&A deal distribution
    ma_items = (
        db.query(Item, Competitor.name)
        .join(Competitor, Item.competitor_id == Competitor.id)
        .filter(Item.tag == "M&A")
        .order_by(Item.date.asc())
        .all()
    )

    # Chronological quarters order
    quarter_order = ["Q4 2025", "Q1 2026", "Q2 2026", "Q3 2026", "Q4 2026"]
    quarter_deals: Dict[str, int] = {q: 0 for q in quarter_order}
    quarter_breakdown: Dict[str, Dict[str, int]] = {q: {} for q in quarter_order}

    for item, comp_name in ma_items:
        q_str = get_quarter_str(item.date)
        if q_str not in quarter_deals:
            quarter_deals[q_str] = 0
            quarter_breakdown[q_str] = {}
            quarter_order.append(q_str)

        quarter_deals[q_str] += 1
        quarter_breakdown[q_str][comp_name] = quarter_breakdown[q_str].get(comp_name, 0) + 1

    quarterly_ma: List[QuarterlyMADeal] = [
        QuarterlyMADeal(
            quarter=q,
            deals=quarter_deals[q],
            competitor_breakdown=quarter_breakdown[q],
        )
        for q in quarter_order
        if q in quarter_deals
    ]

    # 3. Retrieve Pro Market Insight (cached)
    insight_data = get_market_insight(ranked, force_refresh=False)
    market_insight = MarketInsightResponse(
        insight=insight_data["insight"],
        model_used=insight_data["model_used"],
        cached=insight_data.get("cached", True),
    )

    return OverviewResponse(
        competitors=ranked,
        total_competitors=len(ranked),
        quarterly_ma=quarterly_ma,
        market_insight=market_insight,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

