from collections import defaultdict
import time
from typing import List, Union
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Competitor
from app.schemas import AdminRefreshResponse, ErrorResponse
from app.services.pipeline import run_pipeline_for_competitor

router = APIRouter(prefix="/admin", tags=["admin"])

# In-memory sliding window rate limiter: 10 refreshes per 60 seconds
_RATE_LIMITS = defaultdict(list)
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60.0


def enforce_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    history = [t for t in _RATE_LIMITS[client_ip] if now - t < RATE_LIMIT_WINDOW]
    if len(history) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded (10 requests per minute). Please wait before refreshing again.",
        )
    history.append(now)
    _RATE_LIMITS[client_ip] = history


@router.post(
    "/refresh/{id}",
    response_model=Union[AdminRefreshResponse, List[AdminRefreshResponse]],
    responses={
        404: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Trigger ingestion pipeline and battlecard regeneration for a competitor (or 'all')",
)
def refresh_competitor(id: str, request: Request, db: Session = Depends(get_db)):
    """
    Executes the ingestion pipeline for competitor {id}:
    - Fetches configured URLs from sources.yaml
    - Cleans HTML to text
    - Extracts items via model router (gemini-2.5-flash-lite)
    - Validates with Pydantic and upserts into database
    - Regenerates the battlecard with pure metrics formulas
    - Falls back gracefully to seed data if network fetch fails.
    """
    enforce_rate_limit(request)

    if id == "all":
        competitors = db.query(Competitor).all()
        results = []
        for comp in competitors:
            try:
                res = run_pipeline_for_competitor(db, comp.id)
                results.append(
                    AdminRefreshResponse(
                        status="ok",
                        competitor_id=res["competitor_id"],
                        competitor_name=res["competitor_name"],
                        items_upserted=res["items_upserted"],
                        threat_score=res["threat_score"],
                        severity=res["severity"],
                        updated_at=res["updated_at"],
                    )
                )
            except Exception as e:
                results.append(
                    AdminRefreshResponse(
                        status="error",
                        competitor_id=comp.id,
                        competitor_name=comp.name,
                        items_upserted=0,
                        threat_score=0,
                        severity="Low",
                        updated_at="",
                    )
                )
        return results

    try:
        res = run_pipeline_for_competitor(db, id)
        return AdminRefreshResponse(
            status="ok",
            competitor_id=res["competitor_id"],
            competitor_name=res["competitor_name"],
            items_upserted=res["items_upserted"],
            threat_score=res["threat_score"],
            severity=res["severity"],
            updated_at=res["updated_at"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error during refresh of {id}: {e}",
        )


@router.post(
    "/scrape",
    summary="Scrape any live URL on-demand and extract insurance competitive intelligence",
)
def scrape_url_endpoint(payload: dict, db: Session = Depends(get_db)):
    """
    On-demand live web scraping endpoint:
    - Fetches the webpage live via BeautifulSoup
    - Extracts title, paragraphs, and intelligence signals
    - Returns structured extraction without hallucination
    """
    url = payload.get("url")
    if not url or not url.startswith("http"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid 'url' starting with http/https is required.",
        )

    from app.services.scraper import scrape_live_page, extract_intelligence_from_scraped_page

    competitor_id = payload.get("competitor_id", "marsh-mclennan")
    competitor = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    comp_name = competitor.name if competitor else "Competitor Brokerage"

    page_data = scrape_live_page(url, timeout=8.0)
    if not page_data.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to scrape live webpage at {url}: {page_data.get('error')}",
        )

    extracted_items = extract_intelligence_from_scraped_page(competitor_id, comp_name, page_data)

    return {
        "status": "ok",
        "url": url,
        "title": page_data.get("title"),
        "description": page_data.get("description"),
        "text_length": page_data.get("text_length"),
        "paragraphs_scraped": len(page_data.get("paragraphs", [])),
        "text_sample": page_data.get("text", "")[:350],
        "extracted_items": extracted_items,
    }

