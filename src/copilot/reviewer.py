"""Pass 1: per-file review calls to Claude with structured output.

Performance design:
- File reviews run CONCURRENTLY via AsyncAnthropic (capped by a semaphore).
- The (system prompt + learned rules) prefix carries a cache_control
  breakpoint. The cache entry only becomes readable once the first response
  starts, so we review the first file alone (warming the cache), then fan
  out the rest in parallel — they all read the cached prefix (~90% cheaper).
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from .config import get_settings
from .context_builder import build_file_context
from .diff_parser import FileDiff, anchor_line, parse_diff
from .github_client import GitHubClient, PullRequest
from .models import FileReview, Finding
from .prompts import REVIEWER_SYSTEM, rules_block

RULES_PATH = Path(".copilot/rules.json")

# Files not worth reviewing (lockfiles, build output, vendored code).
SKIP_SUFFIXES = (".lock", ".min.js", ".map", ".svg", ".png", ".jpg", ".ico")
SKIP_NAMES = ("package-lock.json", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock")


@dataclass
class Usage:
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0

    def add(self, usage) -> None:
        self.input_tokens += usage.input_tokens
        self.cached_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.output_tokens += usage.output_tokens


@dataclass
class ReviewOutcome:
    findings: list[Finding] = field(default_factory=list)
    dropped: list[Finding] = field(default_factory=list)      # un-anchorable lines
    suppressed: list[Finding] = field(default_factory=list)   # filled by the verifier
    file_diffs: list[FileDiff] = field(default_factory=list)  # for the verifier
    usage: Usage = field(default_factory=Usage)


def load_rules_json(repo_dir: Path = Path(".")) -> str | None:
    path = repo_dir / RULES_PATH
    if path.exists():
        return path.read_text()
    return None


def reviewable_files(files: list[FileDiff]) -> list[FileDiff]:
    out = []
    for f in files:
        name = f.path.rsplit("/", 1)[-1]
        if f.is_deleted or name in SKIP_NAMES or name.endswith(SKIP_SUFFIXES):
            continue
        out.append(f)
    return out


def _build_user_msg(pr: PullRequest, fd: FileDiff, context: str, max_diff_chars: int) -> str:
    return (
        f"PR: {pr.title}\n"
        f"PR description: {pr.body[:2000] or '(none)'}\n\n"
        f"## Full file (read-only background): {fd.path}\n"
        f"```\n{context}\n```\n\n"
        f"## Diff to review (line numbers are NEW-file line numbers)\n"
        f"```\n{fd.numbered_diff[:max_diff_chars]}\n```\n\n"
        "Return your findings for this file."
    )


def review_pr(gh: GitHubClient, pr: PullRequest, on_progress=None) -> ReviewOutcome:
    """Review every file in the PR concurrently; returns anchored findings + usage."""
    settings = get_settings()
    files = reviewable_files(parse_diff(pr.diff))
    # Contexts are fetched up-front (sync, fast) so the async section is Claude-only.
    contexts = {fd.path: build_file_context(gh, pr, fd) for fd in files}
    return asyncio.run(_review_files(pr, files, contexts, on_progress, settings))


async def _review_files(pr, files, contexts, on_progress, settings) -> ReviewOutcome:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)
    system = [
        {
            "type": "text",
            "text": REVIEWER_SYSTEM + rules_block(load_rules_json()),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    sem = asyncio.Semaphore(settings.max_concurrent_reviews)
    outcome = ReviewOutcome(file_diffs=list(files))

    async def review_one(fd: FileDiff) -> None:
        async with sem:
            if on_progress:
                on_progress(f"Reviewing {fd.path}…")
            try:
                response = await client.messages.parse(
                    model=settings.copilot_model,
                    max_tokens=16000,
                    thinking={"type": "adaptive"},
                    system=system,
                    messages=[{
                        "role": "user",
                        "content": _build_user_msg(pr, fd, contexts[fd.path], settings.max_file_diff_chars),
                    }],
                    output_format=FileReview,
                )
            except anthropic.APIError as exc:
                # A transient blip on one file must not lose the whole PR's review.
                if on_progress:
                    on_progress(f"⚠ API error reviewing {fd.path}; skipping ({type(exc).__name__})")
                return
            outcome.usage.add(response.usage)
            parsed = response.parsed_output
            if parsed is None:
                # Output truncated at max_tokens or model returned no parseable block.
                if on_progress:
                    on_progress(f"⚠ No parseable output for {fd.path} (truncated/refused); skipping")
                return
            for finding in parsed.findings:
                finding.file = fd.path  # trust the parser, not the model, for paths
                anchored = anchor_line(fd, finding.line)
                if anchored is None:
                    outcome.dropped.append(finding)
                else:
                    finding.line = anchored
                    outcome.findings.append(finding)

    if not files:
        return outcome

    # Warm the prompt cache with the first file, then fan out the rest.
    # return_exceptions=True so one unexpected failure can't discard the others.
    await review_one(files[0])
    if len(files) > 1:
        await asyncio.gather(*(review_one(fd) for fd in files[1:]), return_exceptions=True)

    # Deterministic ordering regardless of completion order.
    outcome.findings.sort(key=lambda f: (f.file, f.line))
    return outcome


def save_rules(rules_json: str, repo_dir: Path = Path(".")) -> Path:
    path = repo_dir / RULES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rules_json)
    return path


def rules_to_json(rules) -> str:
    return json.dumps([r.model_dump() for r in rules], indent=2)
