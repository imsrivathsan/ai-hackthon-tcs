from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Battlecard, Competitor
from app.schemas import BattlecardResponse

router = APIRouter(prefix="/battlecards", tags=["battlecards"])


@router.get("", response_model=List[BattlecardResponse], summary="List all competitor battlecards")
def list_battlecards(db: Session = Depends(get_db)):
    """Retrieve all current battlecards served from the DB."""
    results = (
        db.query(Battlecard, Competitor.name)
        .join(Competitor, Battlecard.competitor_id == Competitor.id)
        .all()
    )
    return [
        BattlecardResponse(
            competitor=name,
            severity=card.severity,
            threat_score=card.threat_score,
            headline=card.headline,
            subtext=card.subtext,
            wins=card.wins,
            moves=card.moves,
            metrics=card.metrics,
            updated_at=card.updated_at.isoformat(),
        )
        for card, name in results
    ]
