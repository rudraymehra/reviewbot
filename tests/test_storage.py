"""SQLite storage roundtrip tests using a temp database."""

from copilot.models import Finding, ReviewResult, RiskSummary
from copilot.storage import get_review, list_reviews, save_review


def make_result() -> ReviewResult:
    return ReviewResult(
        repo="octo/hello",
        pr_number=7,
        pr_title="Add login endpoint",
        findings=[
            Finding(
                file="app/auth.py", line=12, severity="security",
                title="Password compared with ==",
                issue="Plain comparison leaks timing information.",
                why_it_matters="Attackers can guess passwords faster.",
                suggested_fix="hmac.compare_digest(stored, provided)",
                confidence="high",
            )
        ],
        suppressed=[],
        skipped_duplicates=0,
        summary=RiskSummary(
            quality_score=62,
            overall_assessment="One security issue must be fixed.",
            highest_risk_changes=["timing-unsafe password check"],
            merge_recommendation="request_changes",
            rationale="High-confidence security finding.",
        ),
        model="claude-opus-4-8",
        input_tokens=1000,
        cached_tokens=400,
        output_tokens=200,
    )


def test_save_list_get_roundtrip(tmp_path):
    db = str(tmp_path / "test.db")
    review_id = save_review(make_result(), db_path=db)

    rows = list_reviews(db_path=db)
    assert len(rows) == 1
    assert rows[0]["repo"] == "octo/hello"
    assert rows[0]["quality_score"] == 62
    assert rows[0]["finding_count"] == 1

    full = get_review(review_id, db_path=db)
    assert full is not None
    assert full["result"]["summary"]["merge_recommendation"] == "request_changes"
    assert full["result"]["findings"][0]["severity"] == "security"


def test_get_missing_review_returns_none(tmp_path):
    db = str(tmp_path / "empty.db")
    assert get_review(999, db_path=db) is None
    assert list_reviews(db_path=db) == []
