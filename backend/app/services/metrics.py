from datetime import date, datetime, timezone
from typing import Any, Dict, List, Sequence, Tuple, Union


def _parse_date(val: Union[date, datetime, str]) -> date:
    """Helper to convert date, datetime, or ISO string to date object."""
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val[:10]).date()
    raise ValueError(f"Invalid date value: {val}")


def _get_val(item: Any, key: str, default: Any = None) -> Any:
    """Extract attribute whether item is a dict, Pydantic model, or ORM object."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def calculate_recency_weight(item_date: Union[date, datetime, str], reference_date: Union[date, datetime, None] = None) -> float:
    """
    Recency weight formula:
    - 1.0 within 30 days
    - 0.6 within 90 days
    - 0.3 within 365 days
    - else 0
    """
    dt = _parse_date(item_date)
    ref = _parse_date(reference_date) if reference_date else datetime.now(timezone.utc).date()
    days_diff = (ref - dt).days

    if days_diff < 0:
        return 0.0
    if days_diff <= 30:
        return 1.0
    if days_diff <= 90:
        return 0.6
    if days_diff <= 365:
        return 0.3
    return 0.0


def calculate_threat_score(items: Sequence[Any], reference_date: Union[date, datetime, None] = None) -> int:
    """
    threat_score = min(100, round(sum(impact_score * recency_weight) * 4))
    """
    total = 0.0
    for item in items:
        impact = _get_val(item, "impact_score", 0)
        item_date = _get_val(item, "date")
        if item_date is not None and impact:
            weight = calculate_recency_weight(item_date, reference_date)
            total += impact * weight

    return min(100, round(total * 4))


def calculate_severity(threat_score: int) -> str:
    """
    severity: High >= 70, Medium >= 40, else Low
    """
    if threat_score >= 70:
        return "High"
    if threat_score >= 40:
        return "Medium"
    return "Low"


def calculate_ma_deals_12m(items: Sequence[Any], reference_date: Union[date, datetime, None] = None) -> int:
    """
    ma_deals_12m = count of M&A items in the last 365 days
    """
    ref = _parse_date(reference_date) if reference_date else datetime.now(timezone.utc).date()
    count = 0
    for item in items:
        tag = _get_val(item, "tag")
        item_date = _get_val(item, "date")
        if tag == "M&A" and item_date is not None:
            dt = _parse_date(item_date)
            days_diff = (ref - dt).days
            if 0 <= days_diff <= 365:
                count += 1
    return count


def get_month_buckets(reference_date: date) -> List[Tuple[int, int]]:
    """Returns chronological list of 6 (year, month) buckets ending with reference_date's month."""
    buckets = []
    for offset in range(5, -1, -1):
        m = reference_date.month - offset
        y = reference_date.year
        while m <= 0:
            m += 12
            y -= 1
        buckets.append((y, m))
    return buckets


def calculate_activity_trend(items: Sequence[Any], reference_date: Union[date, datetime, None] = None) -> List[int]:
    """
    activity_trend = item counts per month for the last 6 months.
    Returns 6 integers chronologically (from 5 months ago up to current month).
    """
    ref = _parse_date(reference_date) if reference_date else datetime.now(timezone.utc).date()
    buckets = get_month_buckets(ref)
    counts = {b: 0 for b in buckets}

    for item in items:
        item_date = _get_val(item, "date")
        if item_date is not None:
            dt = _parse_date(item_date)
            bucket_key = (dt.year, dt.month)
            if bucket_key in counts:
                counts[bucket_key] += 1

    return [counts[b] for b in buckets]


def calculate_evidence_confidence(items: Sequence[Any]) -> int:
    """
    evidence_confidence = number of distinct source_urls
    """
    urls = set()
    for item in items:
        url = _get_val(item, "source_url")
        if url:
            urls.add(str(url).strip())
    return len(urls)


def calculate_metrics_summary(items: Sequence[Any], reference_date: Union[date, datetime, None] = None) -> Dict[str, Any]:
    """Computes all pure metrics for a set of items."""
    threat_score = calculate_threat_score(items, reference_date)
    severity = calculate_severity(threat_score)
    ma_deals = calculate_ma_deals_12m(items, reference_date)
    trend = calculate_activity_trend(items, reference_date)
    confidence = calculate_evidence_confidence(items)

    return {
        "threat_score": threat_score,
        "severity": severity,
        "metrics": {
            "ma_deals_12m": ma_deals,
            "activity_trend": trend,
            "evidence_confidence": confidence,
        },
    }
