import pytest
from pydantic import ValidationError

from copilot.github_client import parse_pr_url, parse_repo
from copilot.models import Finding, RiskSummary


def test_parse_pr_url():
    assert parse_pr_url("https://github.com/octo/hello/pull/42") == ("octo", "hello", 42)
    with pytest.raises(ValueError):
        parse_pr_url("https://github.com/octo/hello")


def test_parse_repo():
    assert parse_repo("octo/hello") == ("octo", "hello")
    assert parse_repo("https://github.com/octo/hello") == ("octo", "hello")
    assert parse_repo("https://github.com/octo/hello.git") == ("octo", "hello")


def test_finding_severity_validated():
    with pytest.raises(ValidationError):
        Finding(
            file="a.py", line=1, severity="catastrophic", title="t", issue="i",
            why_it_matters="w", suggested_fix="f", confidence="high",
        )


def test_quality_score_bounds():
    with pytest.raises(ValidationError):
        RiskSummary(
            quality_score=150, overall_assessment="x", highest_risk_changes=[],
            merge_recommendation="approve", rationale="r",
        )
