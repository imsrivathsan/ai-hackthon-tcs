from datetime import date, timedelta
import pytest

from app.services.metrics import (
    calculate_activity_trend,
    calculate_evidence_confidence,
    calculate_ma_deals_12m,
    calculate_metrics_summary,
    calculate_recency_weight,
    calculate_severity,
    calculate_threat_score,
)

REF_DATE = date(2026, 10, 15)


def test_recency_weight_tiers():
    # 0 to 30 days: 1.0
    assert calculate_recency_weight(REF_DATE, reference_date=REF_DATE) == 1.0
    assert calculate_recency_weight(REF_DATE - timedelta(days=15), reference_date=REF_DATE) == 1.0
    assert calculate_recency_weight(REF_DATE - timedelta(days=30), reference_date=REF_DATE) == 1.0

    # 31 to 90 days: 0.6
    assert calculate_recency_weight(REF_DATE - timedelta(days=31), reference_date=REF_DATE) == 0.6
    assert calculate_recency_weight(REF_DATE - timedelta(days=60), reference_date=REF_DATE) == 0.6
    assert calculate_recency_weight(REF_DATE - timedelta(days=90), reference_date=REF_DATE) == 0.6

    # 91 to 365 days: 0.3
    assert calculate_recency_weight(REF_DATE - timedelta(days=91), reference_date=REF_DATE) == 0.3
    assert calculate_recency_weight(REF_DATE - timedelta(days=200), reference_date=REF_DATE) == 0.3
    assert calculate_recency_weight(REF_DATE - timedelta(days=365), reference_date=REF_DATE) == 0.3

    # Beyond 365 days: 0.0
    assert calculate_recency_weight(REF_DATE - timedelta(days=366), reference_date=REF_DATE) == 0.0
    assert calculate_recency_weight(REF_DATE - timedelta(days=700), reference_date=REF_DATE) == 0.0

    # Future date: 0.0
    assert calculate_recency_weight(REF_DATE + timedelta(days=5), reference_date=REF_DATE) == 0.0


def test_threat_score_calculation():
    # Empty items
    assert calculate_threat_score([], reference_date=REF_DATE) == 0

    # Single item 10 days ago (weight 1.0), impact 5 -> (5 * 1.0) * 4 = 20
    items_1 = [{"impact_score": 5, "date": "2026-10-05"}]
    assert calculate_threat_score(items_1, reference_date=REF_DATE) == 20

    # Mixed items
    # item1: impact 4, 10 days ago (w=1.0) -> 4.0
    # item2: impact 5, 50 days ago (w=0.6) -> 3.0
    # item3: impact 3, 100 days ago (w=0.3) -> 0.9
    # total = 7.9 -> 7.9 * 4 = 31.6 -> round = 32
    items_2 = [
        {"impact_score": 4, "date": "2026-10-05"},
        {"impact_score": 5, "date": "2026-08-26"},
        {"impact_score": 3, "date": "2026-07-07"},
    ]
    assert calculate_threat_score(items_2, reference_date=REF_DATE) == 32

    # Capped at 100
    heavy_items = [
        {"impact_score": 5, "date": "2026-10-10"} for _ in range(10)
    ]  # 5 * 10 * 1.0 = 50 * 4 = 200 -> capped at 100
    assert calculate_threat_score(heavy_items, reference_date=REF_DATE) == 100


def test_severity_thresholds():
    # High >= 70
    assert calculate_severity(100) == "High"
    assert calculate_severity(75) == "High"
    assert calculate_severity(70) == "High"

    # Medium >= 40
    assert calculate_severity(69) == "Medium"
    assert calculate_severity(50) == "Medium"
    assert calculate_severity(40) == "Medium"

    # Low < 40
    assert calculate_severity(39) == "Low"
    assert calculate_severity(20) == "Low"
    assert calculate_severity(0) == "Low"


def test_ma_deals_12m():
    items = [
        {"tag": "M&A", "date": "2026-10-01"},  # 14 days ago - count
        {"tag": "M&A", "date": "2026-01-15"},  # ~9 months ago - count
        {"tag": "M&A", "date": "2025-10-16"},  # 364 days ago - count
        {"tag": "M&A", "date": "2025-10-14"},  # 366 days ago - DO NOT count
        {"tag": "Leadership", "date": "2026-10-01"},  # Not M&A - DO NOT count
        {"tag": "Product", "date": "2026-05-01"},  # Not M&A - DO NOT count
    ]
    assert calculate_ma_deals_12m(items, reference_date=REF_DATE) == 3


def test_activity_trend():
    # REF_DATE: 2026-10-15
    # The 6 months are: May, Jun, Jul, Aug, Sep, Oct 2026
    items = [
        {"date": "2026-05-10"},
        {"date": "2026-06-01"},
        {"date": "2026-06-20"},
        {"date": "2026-08-15"},
        {"date": "2026-10-02"},
        {"date": "2026-10-14"},
        {"date": "2026-04-10"},  # 6 months ago - outside the window
    ]
    trend = calculate_activity_trend(items, reference_date=REF_DATE)
    assert len(trend) == 6
    # May: 1, Jun: 2, Jul: 0, Aug: 1, Sep: 0, Oct: 2
    assert trend == [1, 2, 0, 1, 0, 2]


def test_activity_trend_year_boundary():
    # Reference date in February 2026
    # Months should be: Sep 2025, Oct 2025, Nov 2025, Dec 2025, Jan 2026, Feb 2026
    ref = date(2026, 2, 10)
    items = [
        {"date": "2025-09-12"},
        {"date": "2025-12-05"},
        {"date": "2026-01-20"},
        {"date": "2026-02-01"},
    ]
    trend = calculate_activity_trend(items, reference_date=ref)
    assert len(trend) == 6
    assert trend == [1, 0, 0, 1, 1, 1]


def test_evidence_confidence():
    items = [
        {"source_url": "https://example.com/item1"},
        {"source_url": "https://example.com/item2"},
        {"source_url": "https://example.com/item1"},  # duplicate
        {"source_url": "https://example.com/item3"},
        {"source_url": ""},  # empty
    ]
    assert calculate_evidence_confidence(items) == 3


def test_calculate_metrics_summary():
    items = [
        {
            "tag": "M&A",
            "date": "2026-10-01",
            "impact_score": 5,
            "source_url": "https://news.example.com/deal1",
        },
        {
            "tag": "Leadership",
            "date": "2026-09-01",
            "impact_score": 4,
            "source_url": "https://news.example.com/lead1",
        },
    ]
    summary = calculate_metrics_summary(items, reference_date=REF_DATE)
    assert "threat_score" in summary
    assert "severity" in summary
    assert "metrics" in summary
    assert summary["metrics"]["ma_deals_12m"] == 1
    assert len(summary["metrics"]["activity_trend"]) == 6
    assert summary["metrics"]["evidence_confidence"] == 2
