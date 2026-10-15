import math
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Competitor, Item
from app.schemas import ErrorResponse, FeedItemRead, FeedResponse

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get(
    "",
    response_model=FeedResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Get recent competitive moves across competitors with filtering and pagination",
)
def get_feed(
    tag: Optional[str] = Query(None, description="Filter by tag: M&A, Leadership, Product, Pricing"),
    competitor: Optional[str] = Query(None, description="Filter by competitor ID/slug"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=50, description="Items per page"),
    db: Session = Depends(get_db),
):
    """
    Returns verified intelligence feed items across all competitors,
    supporting filtering by tag and competitor with pagination.
    """
    query = (
        db.query(Item, Competitor.name, Competitor.ticker)
        .join(Competitor, Item.competitor_id == Competitor.id)
    )

    if tag:
        query = query.filter(Item.tag == tag)
    if competitor:
        query = query.filter(Item.competitor_id == competitor)

    total = query.count()
    offset = (page - 1) * limit

    results = (
        query.order_by(Item.date.desc(), Item.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        FeedItemRead(
            id=item.id,
            competitor_id=item.competitor_id,
            competitor_name=comp_name,
            competitor_ticker=comp_ticker,
            title=item.title,
            tag=item.tag,
            date=item.date,
            summary=item.summary,
            source_url=item.source_url,
            impact_score=item.impact_score,
            is_sample=item.is_sample,
            created_at=item.created_at,
        )
        for item, comp_name, comp_ticker in results
    ]

    total_pages = max(1, math.ceil(total / limit))

    return FeedResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )
