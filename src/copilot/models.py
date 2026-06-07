"""Pydantic schemas — the contract between the diff parser, Claude, and GitHub.

These models double as the structured-output schemas passed to
``client.messages.parse``, so every field description here is read by the
model and directly shapes review quality.
"""

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["bug", "security", "performance", "style", "suggestion"]

SEVERITY_EMOJI: dict[str, str] = {
    "bug": "🔴",
    "security": "🛑",
    "performance": "🟠",
    "style": "🟡",
    "suggestion": "🔵",
}


class Finding(BaseModel):
    """One review comment anchored to a single line of the diff."""

    file: str = Field(description="Path of the file exactly as it appears in the diff header.")
    line: int = Field(
        description=(
            "Line number in the NEW version of the file. Must be one of the "
            "numbered lines shown in the diff — never a line outside the diff."
        )
    )
    severity: Severity = Field(
        description=(
            "bug: incorrect behaviour or crash. security: vulnerability or unsafe "
            "handling of data/secrets. performance: measurable slowdown (N+1 query, "
            "O(n^2) on large input, blocking IO). style: violates conventions or "
            "readability. suggestion: optional improvement, not a defect."
        )
    )
    title: str = Field(description="One-line summary of the problem, max 80 chars.")
    issue: str = Field(description="What is wrong, referencing the specific code.")
    why_it_matters: str = Field(
        description=(
            "Plain-English explanation for a junior developer of what goes wrong "
            "in production if this ships. No jargon without a one-phrase definition."
        )
    )
    suggested_fix: str = Field(
        description=(
            "Concrete replacement code for the flagged line(s) only — valid code, "
            "no surrounding commentary. Used inside a GitHub suggestion block."
        )
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="How certain you are this is a real issue. Report low-confidence findings too."
    )


class FileReview(BaseModel):
    """Findings for a single file. Empty list means the file is clean."""

    findings: list[Finding]


class RiskSummary(BaseModel):
    """PR-level assessment posted at the top of the review."""

    quality_score: int = Field(ge=0, le=100, description="Overall code quality, 100 = flawless.")
    overall_assessment: str = Field(description="2-3 sentence summary of the PR's health.")
    highest_risk_changes: list[str] = Field(
        description="The riskiest specific changes in this PR, most severe first (max 5)."
    )
    merge_recommendation: Literal["approve", "approve_with_nits", "request_changes", "block"]
    rationale: str = Field(description="Why this recommendation, citing the key findings.")


class ConventionRule(BaseModel):
    """A team convention learned from merged PR history."""

    rule: str = Field(description="A specific, checkable rule, e.g. 'API routes use snake_case'.")
    evidence: str = Field(description="Which PRs / examples this was observed in.")
    category: Severity = Field(description="Severity to use when this rule is violated.")


class ConventionRules(BaseModel):
    rules: list[ConventionRule] = Field(description="At least 3 distinct, actionable rules.")


class ReviewResult(BaseModel):
    """Everything produced by one review run (stored in SQLite, shown in dashboard)."""

    repo: str
    pr_number: int
    pr_title: str
    findings: list[Finding]
    suppressed: list[Finding] = []      # judged false-positive by the verifier; never posted
    skipped_duplicates: int = 0         # already posted in an earlier review of this PR
    summary: RiskSummary
    model: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
