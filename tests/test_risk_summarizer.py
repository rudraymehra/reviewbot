"""Pass 2 (PR-level risk summary) with Claude stubbed.

Checks the call is shaped correctly (findings + diff stats reach the prompt),
usage is accumulated, and the clean-PR path is handled.
"""

from copilot.models import Finding, RiskSummary
from copilot.reviewer import Usage
from copilot.risk_summarizer import summarize_risk

from conftest import make_pr


def _finding():
    return Finding(
        file="app/calc.py", line=4, severity="security",
        title="eval on user input", issue="arbitrary code execution",
        why_it_matters="An attacker runs any code.", suggested_fix="ast.literal_eval(...)",
        confidence="high",
    )


def _summary(**kw):
    base = dict(
        quality_score=40, overall_assessment="risky", highest_risk_changes=["eval"],
        merge_recommendation="request_changes", rationale="security finding",
    )
    base.update(kw)
    return RiskSummary(**base)


def test_summary_passes_findings_and_stats_into_prompt(fake_claude):
    fake_claude.queue(_summary())
    usage = Usage()

    result = summarize_risk(make_pr(), [_finding()], usage)

    assert result.merge_recommendation == "request_changes"
    sent = fake_claude.calls[0]["messages"][0]["content"]
    assert "eval on user input" in sent          # the finding is summarised
    assert "+3 / -1 across 1 files" in sent       # diff stats reach the model
    assert usage.input_tokens == 100              # usage accumulated


def test_clean_pr_reports_no_findings(fake_claude):
    fake_claude.queue(_summary(quality_score=95, merge_recommendation="approve"))

    summarize_risk(make_pr(), [], Usage())

    sent = fake_claude.calls[0]["messages"][0]["content"]
    assert "(no findings — the diff looked clean)" in sent
