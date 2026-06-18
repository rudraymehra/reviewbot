"""Convention learning: extract the team's unwritten rules from merged PR history."""

import anthropic

from .config import get_settings
from .github_client import GitHubClient
from .models import ConventionRules
from .prompts import CONVENTIONS_SYSTEM


def learn_conventions(gh: GitHubClient, owner: str, repo: str, on_progress=None) -> ConventionRules:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    if on_progress:
        on_progress(f"Fetching up to {settings.convention_pr_sample} merged PRs from {owner}/{repo}…")
    merged = gh.get_merged_prs(owner, repo, limit=settings.convention_pr_sample)
    if not merged:
        raise RuntimeError(f"No merged PRs found in {owner}/{repo} — nothing to learn from.")

    sections = []
    for pr in merged:
        comments = "\n".join(f"  - {c[:500]}" for c in pr.review_comments) or "  (no review comments)"
        sections.append(
            f"### PR #{pr.number}: {pr.title}\n"
            f"Human review comments:\n{comments}\n"
            f"Diff (truncated):\n```\n{pr.diff}\n```"
        )

    if on_progress:
        on_progress(f"Analysing {len(merged)} merged PRs with {settings.copilot_model}…")

    response = client.messages.parse(
        model=settings.copilot_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=CONVENTIONS_SYSTEM,
        messages=[{
            "role": "user",
            "content": "## Merged PR history\n\n" + "\n\n".join(sections)
            + "\n\nExtract the team's conventions.",
        }],
        output_format=ConventionRules,
    )
    rules = response.parsed_output
    if rules is None:
        raise RuntimeError(
            "Convention extraction produced no parseable output (model output was "
            "likely truncated). Try a smaller convention_pr_sample or a higher max_tokens."
        )
    return rules
