import html
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import urllib.request

from sqlalchemy.orm import Session
import yaml

from app.models import Battlecard, Competitor, Item, utcnow
from app.schemas import ItemBase
from app.services.llm_router import extract_items, write_card
from app.services.metrics import calculate_metrics_summary

logger = logging.getLogger("meridian.pipeline")


def get_sources_path() -> Path:
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "data" / "sources.yaml",
        Path.cwd() / "data" / "sources.yaml",
        Path.cwd() / "backend" / "data" / "sources.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("Could not locate backend/data/sources.yaml")


def load_sources_config() -> Dict[str, Any]:
    path = get_sources_path()
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


from app.services.scraper import scrape_live_page, extract_intelligence_from_scraped_page


def clean_html_to_text(raw_html: str) -> str:
    """Strips HTML tags, scripts, and entities to return clean prose."""
    text = re.sub(r"<(script|style).*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_url_text(url: str, fallback_text: Optional[str] = None) -> tuple[str, bool]:
    """
    Fetches and cleans text from a live URL using BeautifulSoup scraper.
    Returns tuple: (cleaned_text, is_live_scraped).
    Gracefully falls back to configured fallback text when network fetch fails.
    """
    scraped = scrape_live_page(url, timeout=7.0)
    if scraped.get("success") and len(scraped.get("text", "")) > 100:
        logger.info("Successfully scraped live web content from %s (%d chars)", url, len(scraped["text"]))
        return scraped["text"], True

    logger.warning("Scraping failed for %s. Using configured fallback.", url)
    if fallback_text and len(fallback_text.strip()) > 0:
        return fallback_text.strip(), False

    return "Brokerage continues commercial middle-market expansion and regional client placement advisory.", False


def run_pipeline_for_competitor(db: Session, competitor_id: str) -> Dict[str, Any]:
    """
    Runs full ingestion pipeline for a competitor:
    1. Read live sources from sources.yaml (or seed data fallback).
    2. Scrape live web page via BeautifulSoup.
    3. Run extract via model router (gemini-2.5-flash-lite) or scraper extractor.
    4. Validate with Pydantic.
    5. Upsert items with live URL and is_sample=False.
    6. Regenerate battlecard with pure metrics formulas.
    """
    competitor = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not competitor:
        raise ValueError(f"Competitor '{competitor_id}' not found in database.")

    sources_data = load_sources_config().get("sources", {})
    comp_config = sources_data.get(competitor_id, {})
    targets = comp_config.get("targets", [])

    upserted_count = 0

    if targets:
        for target in targets:
            url = target.get("url", f"https://www.google.com/search?q={competitor_id}")
            fallback = target.get("fallback_text")
            category = target.get("category", "M&A")

            # Scrape live text from URL
            cleaned_text, is_live = fetch_url_text(url, fallback)

            # Run extract via model router
            raw_extracted_items = extract_items(cleaned_text, source_url=url, default_tag=category)

            for raw in raw_extracted_items:
                try:
                    # Validate with Pydantic
                    validated = ItemBase(
                        title=raw.get("title", f"Strategic Intelligence: {competitor.name}"),
                        tag=raw.get("tag", category),
                        date=raw.get("date", "2026-10-15"),
                        summary=raw.get("summary", cleaned_text[:200]),
                        source_url=raw.get("source_url", url),
                        impact_score=int(raw.get("impact_score", 4)),
                        is_sample=not is_live,
                    )

                    # Upsert item by source_url and competitor_id
                    existing_item = (
                        db.query(Item)
                        .filter(Item.competitor_id == competitor_id, Item.source_url == validated.source_url)
                        .first()
                    )

                    if existing_item:
                        existing_item.title = validated.title
                        existing_item.tag = validated.tag
                        existing_item.date = validated.date
                        existing_item.summary = validated.summary
                        existing_item.impact_score = validated.impact_score
                        existing_item.is_sample = validated.is_sample
                    else:
                        new_item = Item(
                            competitor_id=competitor_id,
                            title=validated.title,
                            tag=validated.tag,
                            date=validated.date,
                            summary=validated.summary,
                            source_url=validated.source_url,
                            impact_score=validated.impact_score,
                            is_sample=validated.is_sample,
                        )
                        db.add(new_item)

                    upserted_count += 1
                except Exception as val_err:
                    logger.warning("Item validation error for %s: %s", competitor_id, val_err)
    else:
        logger.info("No targets configured for %s in sources.yaml", competitor_id)

    db.flush()

    # Regenerate Battlecard
    all_items = db.query(Item).filter(Item.competitor_id == competitor_id).order_by(Item.date.desc()).all()
    metrics_summary = calculate_metrics_summary(all_items)

    existing_card = db.query(Battlecard).filter(Battlecard.competitor_id == competitor_id).first()
    template_data = None
    if existing_card:
        template_data = {
            "headline": existing_card.headline,
            "subtext": existing_card.subtext,
            "wins": existing_card.wins,
            "moves": existing_card.moves,
        }

    # Generate card components via model router (write_card)
    card_components = write_card(competitor.name, all_items, current_template=template_data)

    if not existing_card:
        existing_card = Battlecard(
            competitor_id=competitor_id,
            severity=metrics_summary["severity"],
            threat_score=metrics_summary["threat_score"],
            headline=card_components.get("headline", f"Competitive Coverage: {competitor.name}"),
            subtext=card_components.get("subtext", "Automated competitive intelligence profile."),
            wins=card_components.get("wins", []),
            moves=card_components.get("moves", []),
            metrics=metrics_summary["metrics"],
            updated_at=utcnow(),
        )
        db.add(existing_card)
    else:
        existing_card.severity = metrics_summary["severity"]
        existing_card.threat_score = metrics_summary["threat_score"]
        existing_card.headline = card_components.get("headline", existing_card.headline)
        existing_card.subtext = card_components.get("subtext", existing_card.subtext)
        existing_card.wins = card_components.get("wins", existing_card.wins)
        existing_card.moves = card_components.get("moves", existing_card.moves)
        existing_card.metrics = metrics_summary["metrics"]
        existing_card.updated_at = utcnow()

    db.commit()
    logger.info("Pipeline complete for %s. Upserted %d items.", competitor_id, upserted_count)

    return {
        "competitor_id": competitor_id,
        "competitor_name": competitor.name,
        "items_upserted": upserted_count,
        "threat_score": metrics_summary["threat_score"],
        "severity": metrics_summary["severity"],
        "updated_at": existing_card.updated_at.isoformat(),
    }
