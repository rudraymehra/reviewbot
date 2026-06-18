"""Pass 1.5: adversarial false-positive filter.

The reviewer is prompted for coverage ("report everything, including
low-confidence"). This pass is the precision stage: a skeptical judge sees
every finding alongside the diff it points at and votes keep/suppress.
Suppressed findings are retained (CLI + dashboard show them) but never posted.
"""

from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from .config import get_settings
from .diff_parser import FileDiff
from .models import Finding
from .prompts import VERIFIER_SYSTEM
from .reviewer import Usage


class Verdict(BaseModel):
    index: int = Field(description="The [index] of the finding being judged.")
    keep: bool = Field(description="true if a senior reviewer would post this comment.")
    reason: str = Field(description="One sentence: why keep or suppress.")


class Verdicts(BaseModel):
    verdicts: list[Verdict] = Field(description="Exactly one verdict per finding index.")


def verify_findings(
    findings: list[Finding],
    file_diffs: list[FileDiff],
    usage: Usage,
) -> tuple[list[Finding], list[Finding]]:
    """Returns (kept, suppressed). Fails open: on any error, keep everything."""
    if not findings:
        return [], []
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    diffs_by_path = {fd.path: fd for fd in file_diffs}
    relevant_paths = {f.file for f in findings}
    diff_section = "\n\n".join(
        f"### {path}\n```\n{diffs_by_path[path].numbered_diff[:20_000]}\n```"
        for path in sorted(relevant_paths)
        if path in diffs_by_path
    )
    findings_section = "\n".join(
        f"[{i}] {f.file}:{f.line} [{f.severity}/{f.confidence}] {f.title}\n"
        f"    issue: {f.issue}\n    proposed fix: {f.suggested_fix[:300]}"
        for i, f in enumerate(findings)
    )

    try:
        response = client.messages.parse(
            model=settings.copilot_model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=VERIFIER_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"## Diffs under review\n{diff_section}\n\n"
                    f"## Candidate findings\n{findings_section}\n\n"
                    "Judge every finding by index."
                ),
            }],
            output_format=Verdicts,
        )
    except anthropic.APIError:
        return list(findings), []  # fail open — better a nit too many than a lost review
    usage.add(response.usage)

    verdicts = response.parsed_output
    if verdicts is None:
        # Truncated/refused output — honour the documented fail-open contract.
        return list(findings), []
    keep_by_index: dict[int, bool] = {
        v.index: v.keep for v in verdicts.verdicts
    }
    kept: list[Finding] = []
    suppressed: list[Finding] = []
    for i, f in enumerate(findings):
        # Findings the judge skipped default to kept (fail open).
        (kept if keep_by_index.get(i, True) else suppressed).append(f)
    return kept, suppressed
