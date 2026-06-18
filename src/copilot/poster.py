"""Render findings + risk summary into GitHub review payloads and markdown."""

import hashlib
import re
from typing import Any

from .models import SEVERITY_EMOJI, Finding, RiskSummary

# Hidden marker embedded in every inline comment so re-reviews of the same PR
# (webhook `synchronize`) can detect what's already posted and skip it.
FP_MARKER_RE = re.compile(r"<!-- copilot-fp:([0-9a-f]{12}) -->")


def fingerprint(f: Finding) -> str:
    """Stable identity for a finding across re-reviews.

    Line numbers shift between pushes, so the fingerprint is built from the
    file, severity and normalised title instead.
    """
    norm_title = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", f.title.lower())).strip()
    raw = f"{f.file}|{f.severity}|{norm_title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def extract_fingerprints(comment_bodies: list[str]) -> set[str]:
    found: set[str] = set()
    for body in comment_bodies:
        found.update(FP_MARKER_RE.findall(body))
    return found


# Severity tag rendered into every comment body, e.g. "**[BUG]**".
SEVERITY_TAG_RE = re.compile(r"\*\*\[([A-Z]+)\]\*\*")


def extract_anchors(comments: list[dict[str, Any]]) -> list[tuple[str, str, int]]:
    """(path, severity, line) for existing inline comments, for coarse dedup.

    The exact fingerprint misses a finding when the model rephrases its title on
    a re-review. This coarser key lets us also skip a finding when the same file
    already has a comment of the same severity on a nearby line.
    """
    anchors: list[tuple[str, str, int]] = []
    for c in comments:
        body = c.get("body") or ""
        line = c.get("line") or c.get("original_line")
        path = c.get("path")
        m = SEVERITY_TAG_RE.search(body)
        if m and path and line is not None:
            anchors.append((path, m.group(1).lower(), int(line)))
    return anchors


def is_near_duplicate(f: Finding, anchors: list[tuple[str, str, int]], line_window: int = 3) -> bool:
    """True if an existing comment of the same file+severity sits within line_window lines."""
    return any(
        path == f.file and severity == f.severity and abs(line - f.line) <= line_window
        for path, severity, line in anchors
    )

RECOMMENDATION_LABEL = {
    "approve": "✅ Approve",
    "approve_with_nits": "✅ Approve (with nits)",
    "request_changes": "🔶 Request changes",
    "block": "⛔ Block",
}


def finding_to_comment_body(f: Finding) -> str:
    emoji = SEVERITY_EMOJI[f.severity]
    parts = [
        f"{emoji} **[{f.severity.upper()}]** {f.title}",
        "",
        f"**Issue:** {f.issue}",
        "",
        f"**Why it matters:** {f.why_it_matters}",
    ]
    if f.suggested_fix.strip():
        parts += ["", "**Suggested fix:**", "```suggestion", f.suggested_fix.rstrip(), "```"]
    parts += [
        "",
        f"<sub>confidence: {f.confidence} · by Code Review Copilot</sub>",
        f"<!-- copilot-fp:{fingerprint(f)} -->",
    ]
    return "\n".join(parts)


def findings_to_github_comments(findings: list[Finding]) -> list[dict[str, Any]]:
    return [
        {"path": f.file, "line": f.line, "side": "RIGHT", "body": finding_to_comment_body(f)}
        for f in findings
    ]


def summary_to_markdown(summary: RiskSummary, findings: list[Finding]) -> str:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    severity_line = " · ".join(
        f"{SEVERITY_EMOJI[s]} {s}: {n}" for s, n in sorted(counts.items(), key=lambda kv: -kv[1])
    ) or "no issues found"

    risks = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(summary.highest_risk_changes)) or "—"

    return f"""## 🔍 Code Review Copilot

**Quality score: {summary.quality_score}/100** · **{RECOMMENDATION_LABEL[summary.merge_recommendation]}**

{summary.overall_assessment}

### Highest-risk changes
{risks}

### Rationale
{summary.rationale}

### Findings ({len(findings)})
{severity_line}

<sub>Inline comments below explain each finding and how to fix it.</sub>
"""
