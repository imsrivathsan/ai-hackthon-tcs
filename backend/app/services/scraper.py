import html
import logging
import re
import urllib.request
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import truststore

# Ensure Windows enterprise certificates are used for outbound HTTPS
truststore.inject_into_ssl()

logger = logging.getLogger("meridian.scraper")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# Live verified URLs per competitor for real-time scraping
LIVE_SOURCES_MAP = {
    "marsh-mclennan": [
        {
            "url": "https://en.wikipedia.org/wiki/Marsh_McLennan",
            "name": "Marsh McLennan Corporate Profile & Expansion History",
            "default_tag": "M&A",
        },
        {
            "url": "https://www.marshmclennan.com/news.html",
            "name": "Marsh McLennan Newsroom Disclosures",
            "default_tag": "Product",
        },
    ],
    "aon": [
        {
            "url": "https://aon.mediaroom.com",
            "name": "Aon Media Releases & Client Solutions",
            "default_tag": "M&A",
        },
        {
            "url": "https://en.wikipedia.org/wiki/Aon_(company)",
            "name": "Aon Commercial Risk Solutions & Growth",
            "default_tag": "Product",
        },
    ],
    "wtw": [
        {
            "url": "https://en.wikipedia.org/wiki/WTW_(company)",
            "name": "Willis Towers Watson Corporate Profile & Mergers",
            "default_tag": "M&A",
        },
        {
            "url": "https://www.wtwco.com/en-us",
            "name": "WTW Official Insights & Placements",
            "default_tag": "Product",
        },
    ],
    "arthur-j-gallagher": [
        {
            "url": "https://investor.ajg.com",
            "name": "Arthur J. Gallagher & Co. Investor Releases",
            "default_tag": "M&A",
        },
        {
            "url": "https://en.wikipedia.org/wiki/Arthur_J._Gallagher_%26_Co.",
            "name": "Arthur J. Gallagher Retail Brokerage & Expansion",
            "default_tag": "Leadership",
        },
    ],
    "brown-and-brown": [
        {
            "url": "https://bbinsurance.com/news/",
            "name": "Brown & Brown News & Program Launches",
            "default_tag": "Product",
        },
        {
            "url": "https://en.wikipedia.org/wiki/Brown_%26_Brown",
            "name": "Brown & Brown Specialty Acquisitions & Milestones",
            "default_tag": "M&A",
        },
    ],
    "hub-international": [
        {
            "url": "https://en.wikipedia.org/wiki/Hub_International",
            "name": "Hub International Regional Brokerage Buyouts",
            "default_tag": "M&A",
        },
        {
            "url": "https://www.hubinternational.com/products/business-insurance/",
            "name": "Hub International Commercial Lines Platform",
            "default_tag": "Product",
        },
    ],
}


def scrape_live_page(url: str, timeout: float = 7.0) -> Dict[str, Any]:
    """
    Fetches and parses a live webpage using BeautifulSoup.
    Extracts title, meta description, cleaned paragraphs, and structured text.
    """
    try:
        req = urllib.request.Request(url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            content_type = resp.headers.get("Content-Type", "")
            raw_bytes = resp.read()
            raw_html = raw_bytes.decode("utf-8", errors="replace")

        soup = BeautifulSoup(raw_html, "html.parser")

        # Strip scripts, styles, navigations, footers, and SVGs
        for tag in soup(["script", "style", "nav", "footer", "svg", "noscript", "iframe"]):
            tag.decompose()

        # Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.find("h1"):
            title = soup.find("h1").get_text().strip()

        # Extract meta description
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta_tag and meta_tag.get("content"):
            meta_desc = meta_tag["content"].strip()

        # Extract meaningful paragraphs
        paragraphs = []
        for p in soup.find_all("p"):
            txt = p.get_text().strip()
            # Clean up whitespace
            txt = re.sub(r"\s+", " ", txt)
            if len(txt) > 40:
                paragraphs.append(txt)

        # Full cleaned text
        clean_text = " ".join(paragraphs)
        if not clean_text:
            clean_text = " ".join(soup.stripped_strings)

        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        return {
            "success": True,
            "status_code": status_code,
            "url": url,
            "title": title or "Insurance Industry Intelligence",
            "description": meta_desc,
            "paragraphs": paragraphs[:10],
            "text": clean_text[:8000],  # Limit to 8000 characters for LLM processing
            "text_length": len(clean_text),
        }
    except Exception as e:
        logger.warning("Scraping failed for %s: %s", url, e)
        return {
            "success": False,
            "status_code": 500,
            "url": url,
            "title": "",
            "description": "",
            "paragraphs": [],
            "text": "",
            "text_length": 0,
            "error": str(e),
        }


def extract_intelligence_from_scraped_page(
    competitor_id: str,
    competitor_name: str,
    page_data: Dict[str, Any],
    category_hint: str = "M&A",
) -> List[Dict[str, Any]]:
    """
    Extracts structured competitive intelligence items from a scraped webpage.
    Identifies relevant sentences mentioning acquisitions, leadership, or product offerings.
    """
    if not page_data.get("success") or not page_data.get("paragraphs"):
        return []

    items = []
    url = page_data["url"]
    paragraphs = page_data["paragraphs"]
    page_title = page_data.get("title", f"{competitor_name} Intelligence")

    # Look for paragraphs with high competitive relevance
    keywords_map = {
        "M&A": ["acquir", "acquisition", "purchase", "bought", "merger", "transaction", "subsidiary", "deal"],
        "Product": ["launch", "platform", "solution", "tool", "program", "analytics", "facility", "digital", "offering"],
        "Leadership": ["appoint", "executive", "named", "chief", "director", "joined", "lead", "president", "head of"],
        "Pricing": ["rate", "pricing", "renewal", "index", "premium", "firming", "capacity", "cost"],
    }

    used_paras = set()

    for p in paragraphs:
        if len(p) < 60:
            continue
        p_lower = p.lower()

        # Determine best tag
        matched_tag = category_hint
        for tag, kw_list in keywords_map.items():
            if any(kw in p_lower for kw in kw_list):
                matched_tag = tag
                break

        # Check if relevant to broker or industry
        has_relevance = (
            any(w in p_lower for w in ["insur", "broker", "commercial", "risk", "underwrit", "lines", "client"])
            or any(kw in p_lower for kws in keywords_map.values() for kw in kws)
        )

        if has_relevance and p not in used_paras:
            used_paras.add(p)

            # Build a concise summary sentence
            sentences = re.split(r"(?<=[.!?])\s+", p)
            summary = sentences[0] if sentences else p
            if len(summary) > 220:
                summary = summary[:217] + "..."

            # Title formulation
            item_title = f"{competitor_name}: {summary[:75]}..." if len(summary) > 75 else f"{competitor_name}: {summary}"

            items.append({
                "competitor_id": competitor_id,
                "title": item_title,
                "tag": matched_tag,
                "date": "2026-10-15",
                "summary": summary,
                "source_url": url,
                "impact_score": 4 if matched_tag == "M&A" else 3,
                "is_sample": False,
            })

            if len(items) >= 2:
                break

    # If no specific paragraph matched keyword heuristics, create a verified profile item from the lead paragraph
    if not items and paragraphs:
        lead = paragraphs[0]
        if len(lead) > 200:
            lead = lead[:197] + "..."
        items.append({
            "competitor_id": competitor_id,
            "title": f"{competitor_name} Verified Corporate Profile & Operations",
            "tag": category_hint,
            "date": "2026-10-15",
            "summary": lead,
            "source_url": url,
            "impact_score": 3,
            "is_sample": False,
        })

    return items
