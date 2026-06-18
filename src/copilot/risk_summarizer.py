"""Pass 2: one Claude call that turns all findings + diff stats into a RiskSummary."""

import anthropic

from .config import get_settings
from .github_client import PullRequest
from .models import Finding, RiskSummary
from .prompts import RISK_SYSTEM
from .reviewer import Usage


def summarize_risk(pr: PullRequest, findings: list[Finding], usage: Usage) -> RiskSummary:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    findings_md = "\n".join(
        f"- [{f.severity}/{f.confidence}] {f.file}:{f.line} — {f.title}: {f.issue}"
        for f in findings
    ) or "(no findings — the diff looked clean)"

    user_msg = (
        f"PR: {pr.title} by @{pr.author} into {pr.base_branch}\n"
        f"Description: {pr.body[:2000] or '(none)'}\n"
        f"Stats: +{pr.additions} / -{pr.deletions} across {pr.changed_files} files\n\n"
        f"## Inline findings already made\n{findings_md}\n\n"
        "Write the PR-level risk summary."
    )

    response = client.messages.parse(
        model=settings.copilot_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=RISK_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        output_format=RiskSummary,
    )
    usage.add(response.usage)
    parsed = response.parsed_output
    if parsed is None:
        # Output truncated at max_tokens (thinking eats the budget) or no parseable
        # block. Fall back to a neutral summary so the (already-paid-for) inline
        # findings still get posted instead of crashing the whole review.
        return RiskSummary(
            quality_score=50,
            overall_assessment="Risk summary could not be generated (model output was truncated). See the inline findings below for the actionable detail.",
            highest_risk_changes=[],
            merge_recommendation="approve_with_nits",
            rationale="Summary generation did not complete; judge this PR from the inline findings rather than this placeholder.",
        )
    return parsed
