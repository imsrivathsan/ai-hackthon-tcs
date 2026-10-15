import json
import logging
from pathlib import Path
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import Battlecard, Competitor, Item, utcnow
from app.services.metrics import calculate_metrics_summary

logger = logging.getLogger("meridian.seed")


def get_seed_dir() -> Path:
    """Find the seed directory whether running from root, backend, or app."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "data" / "seed",
        Path.cwd() / "data" / "seed",
        Path.cwd() / "backend" / "data" / "seed",
    ]
    for p in candidates:
        if p.exists() and p.is_dir():
            return p
    raise FileNotFoundError("Could not locate backend/data/seed directory")


def load_seed_data(db: Session, force: bool = False) -> Dict[str, Any]:
    """
    Reads backend/data/seed/*.json for 6 competitors, loads realistic sample items,
    computes pure metrics via metrics.py, and stores Battlecards in the DB.
    """
    seed_dir = get_seed_dir()
    json_files = list(seed_dir.glob("*.json"))
    if not json_files:
        logger.warning("No seed JSON files found in %s", seed_dir)
        return {"loaded_competitors": 0, "loaded_items": 0, "loaded_battlecards": 0}

    loaded_competitors = 0
    loaded_items = 0
    loaded_battlecards = 0

    for json_path in json_files:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        comp_data = data["competitor"]
        comp_id = comp_data["id"]

        competitor = db.query(Competitor).filter(Competitor.id == comp_id).first()
        if competitor and not force:
            logger.info("Competitor '%s' already exists in DB. Skipping.", comp_id)
            continue

        if not competitor:
            competitor = Competitor(
                id=comp_id,
                name=comp_data["name"],
                ticker=comp_data.get("ticker"),
                description=comp_data.get("description"),
                website=comp_data.get("website"),
                headquarters=comp_data.get("headquarters"),
                market_cap_tier=comp_data.get("market_cap_tier"),
            )
            db.add(competitor)
            db.flush()
            loaded_competitors += 1
        else:
            competitor.name = comp_data["name"]
            competitor.ticker = comp_data.get("ticker")
            competitor.description = comp_data.get("description")
            competitor.website = comp_data.get("website")
            competitor.headquarters = comp_data.get("headquarters")
            competitor.market_cap_tier = comp_data.get("market_cap_tier")
            competitor.updated_at = utcnow()

        # Remove existing items if reloading
        db.query(Item).filter(Item.competitor_id == comp_id).delete()

        created_items = []
        for raw_item in data.get("items", []):
            item = Item(
                competitor_id=comp_id,
                title=raw_item["title"],
                tag=raw_item["tag"],
                date=raw_item["date"],
                summary=raw_item["summary"],
                source_url=raw_item["source_url"],
                impact_score=raw_item["impact_score"],
                is_sample=raw_item.get("is_sample", True),
            )
            db.add(item)
            created_items.append(item)
            loaded_items += 1

        db.flush()

        # Compute metrics using pure functions from metrics.py
        summary = calculate_metrics_summary(created_items)
        template = data.get("battlecard_template", {})

        wins = template.get("wins", [])
        moves = template.get("moves", [])

        # Ensure exactly 3 wins and 3 moves as per battlecard specification
        if len(wins) != 3:
            raise ValueError(f"Battlecard for {comp_id} must have exactly 3 wins, found {len(wins)}")
        if len(moves) != 3:
            raise ValueError(f"Battlecard for {comp_id} must have exactly 3 moves, found {len(moves)}")

        battlecard = db.query(Battlecard).filter(Battlecard.competitor_id == comp_id).first()
        if not battlecard:
            battlecard = Battlecard(
                competitor_id=comp_id,
                severity=summary["severity"],
                threat_score=summary["threat_score"],
                headline=template.get("headline", f"Competitive Analysis: {comp_data['name']}"),
                subtext=template.get("subtext", "Automated competitive intelligence profile."),
                wins=wins,
                moves=moves,
                metrics=summary["metrics"],
                updated_at=utcnow(),
            )
            db.add(battlecard)
            loaded_battlecards += 1
        else:
            battlecard.severity = summary["severity"]
            battlecard.threat_score = summary["threat_score"]
            battlecard.headline = template.get("headline", battlecard.headline)
            battlecard.subtext = template.get("subtext", battlecard.subtext)
            battlecard.wins = wins
            battlecard.moves = moves
            battlecard.metrics = summary["metrics"]
            battlecard.updated_at = utcnow()

    db.commit()
    logger.info(
        "Seed loading complete: %d competitors, %d items, %d battlecards",
        loaded_competitors,
        loaded_items,
        loaded_battlecards,
    )
    return {
        "loaded_competitors": loaded_competitors,
        "loaded_items": loaded_items,
        "loaded_battlecards": loaded_battlecards,
    }


if __name__ == "__main__":
    init_db()
    with SessionLocal() as session:
        result = load_seed_data(session, force=True)
        print("Seed result:", result)
