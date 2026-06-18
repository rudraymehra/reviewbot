"""End-to-end review pipeline shared by the CLI and the webhook.

Stages: fetch -> review (parallel, pass 1) -> verify (precision filter,
pass 1.5) -> risk summary (pass 2) -> dedup vs already-posted comments ->
post -> persist.
"""

from .config import get_settings
from .github_client import GitHubClient
from .models import ReviewResult
from .poster import (
    extract_anchors,
    extract_fingerprints,
    findings_to_github_comments,
    fingerprint,
    is_near_duplicate,
    summary_to_markdown,
)
from .reviewer import review_pr
from .risk_summarizer import summarize_risk
from .storage import save_review
from .verifier import verify_findings


def run_review(
    owner: str,
    repo: str,
    number: int,
    post: bool = True,
    on_progress=None,
) -> ReviewResult:
    settings = get_settings()
    with GitHubClient() as gh:
        if on_progress:
            on_progress(f"Fetching PR #{number} from {owner}/{repo}…")
        pr = gh.get_pull_request(owner, repo, number)

        outcome = review_pr(gh, pr, on_progress=on_progress)
        if on_progress and outcome.dropped:
            on_progress(f"⚠ {len(outcome.dropped)} finding(s) could not be anchored to the diff and were dropped")

        # Pass 1.5: precision filter.
        if settings.verify_findings and outcome.findings:
            if on_progress:
                on_progress(f"Verifying {len(outcome.findings)} finding(s)…")
            kept, suppressed = verify_findings(outcome.findings, outcome.file_diffs, outcome.usage)
            outcome.findings, outcome.suppressed = kept, suppressed
            if on_progress and suppressed:
                on_progress(f"✂ Suppressed {len(suppressed)} likely false positive(s)")

        if on_progress:
            on_progress("Generating risk summary…")
        summary = summarize_risk(pr, outcome.findings, outcome.usage)

        # Dedup against comments we posted on an earlier review of this PR
        # (webhook `synchronize` would otherwise repeat every finding). Scan both
        # inline comments and review-summary bodies (where 422-fallbacks land).
        skipped_duplicates = 0
        to_post = outcome.findings
        if post:
            comments = gh.get_review_comments(owner, repo, number)
            existing = extract_fingerprints(
                [c["body"] for c in comments]
                + gh.get_review_summary_bodies(owner, repo, number)
            )
            # Coarse dedup too: the model can rephrase a finding's title on a
            # re-review (→ new fingerprint), so also skip a finding when the same
            # file+severity already has a comment on a nearby line.
            anchors = extract_anchors(comments)
            if existing or anchors:
                fresh = [
                    f for f in to_post
                    if fingerprint(f) not in existing and not is_near_duplicate(f, anchors)
                ]
                skipped_duplicates = len(to_post) - len(fresh)
                to_post = fresh
                if on_progress and skipped_duplicates:
                    on_progress(f"↩ Skipping {skipped_duplicates} comment(s) already posted on this PR")

        result = ReviewResult(
            repo=pr.full_repo,
            pr_number=pr.number,
            pr_title=pr.title,
            findings=outcome.findings,
            suppressed=outcome.suppressed,
            skipped_duplicates=skipped_duplicates,
            summary=summary,
            model=settings.copilot_model,
            input_tokens=outcome.usage.input_tokens,
            cached_tokens=outcome.usage.cached_tokens,
            output_tokens=outcome.usage.output_tokens,
        )

        if post:
            if on_progress:
                on_progress("Posting review to GitHub…")
            # Render the summary from the SAME set being posted, so the rendered
            # "Findings (N)" count matches the inline comments actually attached.
            gh.post_review(
                owner,
                repo,
                number,
                body=summary_to_markdown(summary, to_post),
                comments=findings_to_github_comments(to_post),
            )

        save_review(result)
        return result
