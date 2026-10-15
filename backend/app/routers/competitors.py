from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Battlecard, Competitor
from app.schemas import BattlecardResponse, CompetitorRead, ErrorResponse, MeetingBriefResponse
from app.services.llm_router import generate_meeting_brief

router = APIRouter(prefix="/competitors", tags=["competitors"])


@router.get(
    "",
    response_model=List[CompetitorRead],
    responses={500: {"model": ErrorResponse}},
    summary="List all tracked competitors",
)
def list_competitors(db: Session = Depends(get_db)):
    """Retrieve all tracked competitors sorted by name."""
    competitors = db.query(Competitor).order_by(Competitor.name.asc()).all()
    return competitors


@router.get(
    "/{id}",
    response_model=CompetitorRead,
    responses={404: {"model": ErrorResponse}},
    summary="Get competitor details",
)
def get_competitor(id: str, db: Session = Depends(get_db)):
    """Retrieve details for a specific competitor by ID/slug."""
    competitor = db.query(Competitor).filter(Competitor.id == id).first()
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor '{id}' not found",
        )
    return competitor


@router.get(
    "/{id}/battlecard",
    response_model=BattlecardResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get battlecard for a competitor",
)
def get_battlecard(id: str, db: Session = Depends(get_db)):
    """
    Retrieve the current battlecard for a competitor.
    Served directly from the database.
    """
    competitor = db.query(Competitor).filter(Competitor.id == id).first()
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor '{id}' not found",
        )

    battlecard = db.query(Battlecard).filter(Battlecard.competitor_id == id).first()
    if not battlecard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battlecard for competitor '{id}' not found",
        )

    return BattlecardResponse(
        competitor=competitor.name,
        severity=battlecard.severity,
        threat_score=battlecard.threat_score,
        headline=battlecard.headline,
        subtext=battlecard.subtext,
        wins=battlecard.wins,
        moves=battlecard.moves,
        metrics=battlecard.metrics,
        updated_at=battlecard.updated_at.isoformat(),
    )


@router.post(
    "/{id}/brief",
    response_model=MeetingBriefResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Generate 5-line meeting brief talk track via Gemini",
)
@router.get(
    "/{id}/brief",
    response_model=MeetingBriefResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Generate 5-line meeting brief talk track via Gemini",
)
def get_meeting_brief(id: str, db: Session = Depends(get_db)):
    """
    Generates a 5-line producer talk track tailored for commercial meetings
    against this competitor via gemini-2.5-flash with timeout and fallback.
    """
    competitor = db.query(Competitor).filter(Competitor.id == id).first()
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor '{id}' not found",
        )

    battlecard = db.query(Battlecard).filter(Battlecard.competitor_id == id).first()
    if not battlecard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battlecard for competitor '{id}' not found",
        )

    result = generate_meeting_brief(
        competitor_name=competitor.name,
        headline=battlecard.headline,
        subtext=battlecard.subtext,
        wins=battlecard.wins,
        moves=battlecard.moves,
    )

    return MeetingBriefResponse(
        competitor_id=competitor.id,
        competitor_name=competitor.name,
        talk_track=result["talk_track"],
        brief_text=result["brief_text"],
        model_used=result["model_used"],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

