import re
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models import Competitor, Item

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "should", "shouldn't", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "wasn't", "we", "were", "weren't", "what", "when", "where", "which", "while",
    "who", "whom", "why", "with", "won't", "would", "wouldn't", "you", "your",
    "yours", "yourself", "yourselves", "recently", "recent", "tell", "show", "find"
}


def tokenize(text: str) -> List[str]:
    """Tokenize query into lowercase alphanumeric words, filtering out common stopwords."""
    words = re.findall(r"\b[a-zA-Z0-9_\-&']+\b", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]


def retrieve_items(
    db: Session,
    query: str,
    competitor_id: Optional[str] = None,
    tag: Optional[str] = None,
    top_k: int = 12,
) -> List[Item]:
    """
    Retrieves up to top_k items from SQLite using keyword matching plus tag and competitor filtering.
    Strictly uses SQLite without external vector DB.
    """
    base_query = db.query(Item).join(Competitor, Item.competitor_id == Competitor.id)

    # Apply strict competitor filter if provided
    if competitor_id:
        base_query = base_query.filter(Item.competitor_id == competitor_id)

    # Apply tag filter if provided
    if tag:
        base_query = base_query.filter(Item.tag == tag)

    candidates = base_query.all()
    if not candidates:
        return []

    tokens = tokenize(query)
    if not tokens:
        # If no specific keywords found, return recent items up to top_k
        return sorted(candidates, key=lambda x: x.date, reverse=True)[:top_k]

    # Keyword scoring across title, summary, tag, competitor using word boundaries
    scored_items = []
    for item in candidates:
        score = 0.0
        title_lower = item.title.lower()
        summary_lower = item.summary.lower()
        tag_lower = item.tag.lower()
        comp_id_lower = item.competitor_id.lower()

        for token in tokens:
            pattern = r"\b" + re.escape(token) + r"\b"
            # Title match carries highest relevance
            if re.search(pattern, title_lower):
                score += 5.0
            # Summary match
            if re.search(pattern, summary_lower):
                score += 2.0
            # Tag match (e.g. "m&a", "pricing", "leadership", "product")
            if re.search(pattern, tag_lower):
                score += 3.0
            # Competitor slug match (e.g. "marsh", "gallagher", "aon", "wtw")
            if re.search(pattern, comp_id_lower):
                score += 4.0

        if score > 0:
            scored_items.append((score, item))

    if not scored_items:
        # No relevant keyword matches found in candidates
        return []

    # Sort descending by score, then by date descending
    scored_items.sort(key=lambda x: (x[0], x[1].date), reverse=True)
    return [item for _, item in scored_items[:top_k]]

