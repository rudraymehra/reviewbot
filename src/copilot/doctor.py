"""Preflight checks for `copilot doctor` — is this machine ready for a live run?

Answers "can I run a real review right now?" WITHOUT spending a token or hitting
the network: it inspects the loaded settings, the SQLite history DB, and any
learned-convention rules file, then reports what's ready and what's missing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import get_settings
from .pricing import estimate_cost
from .reviewer import RULES_PATH

Status = Literal["ok", "warn", "fail"]


@dataclass
class Check:
    name: str
    status: Status
    detail: str


def _mask(secret: str) -> str:
    """Show enough of a secret to recognise it, never enough to leak it."""
    if not secret:
        return "(not set)"
    if len(secret) <= 8:
        return "•" * len(secret)
    return f"{secret[:4]}…{secret[-2:]}"


def run_checks(repo_dir: Path = Path(".")) -> list[Check]:
    """Gather all preflight checks. Pure: no network, no token spend."""
    s = get_settings()
    checks: list[Check] = []

    # --- credentials required for a live review ---
    checks.append(
        Check(
            "ANTHROPIC_API_KEY",
            "ok" if s.anthropic_api_key else "fail",
            _mask(s.anthropic_api_key) if s.anthropic_api_key else "needed for Claude review calls",
        )
    )
    checks.append(
        Check(
            "GITHUB_TOKEN",
            "ok" if s.github_token else "fail",
            _mask(s.github_token) if s.github_token else "needed to fetch diffs / post comments",
        )
    )

    # --- webhook secret: only matters for `copilot serve` ---
    if not s.github_webhook_secret or s.github_webhook_secret == "change-me":
        checks.append(
            Check(
                "GITHUB_WEBHOOK_SECRET",
                "warn",
                "unset or default — only required for `copilot serve`",
            )
        )
    else:
        checks.append(Check("GITHUB_WEBHOOK_SECRET", "ok", _mask(s.github_webhook_secret)))

    checks.append(Check("model", "ok", s.copilot_model))

    # --- history DB (only read if it already exists, so we create nothing) ---
    db = Path(s.copilot_db_path)
    if db.exists():
        try:
            from .storage import list_reviews

            rows = list_reviews()
            cost = sum(
                estimate_cost(
                    r["input_tokens"], r["cached_tokens"], r["output_tokens"], r["model"]
                )
                for r in rows
            )
            checks.append(
                Check("history DB", "ok", f"{db} · {len(rows)} review(s) · ~${cost:.2f} spent")
            )
        except Exception as e:  # pragma: no cover - defensive
            checks.append(Check("history DB", "warn", f"{db} present but unreadable: {e}"))
    else:
        checks.append(Check("history DB", "ok", f"{db} (created on first review)"))

    # --- learned conventions (optional) ---
    rules_file = repo_dir / RULES_PATH
    if rules_file.exists():
        try:
            rules = json.loads(rules_file.read_text())
            checks.append(
                Check("learned conventions", "ok", f"{len(rules)} rule(s) in {rules_file}")
            )
        except (ValueError, OSError):
            checks.append(
                Check("learned conventions", "warn", f"{rules_file} present but unparseable")
            )
    else:
        checks.append(
            Check(
                "learned conventions",
                "warn",
                "none yet — run `copilot learn owner/repo` (optional)",
            )
        )

    return checks


def overall(checks: list[Check]) -> Status:
    """Worst status across all checks: fail > warn > ok."""
    if any(c.status == "fail" for c in checks):
        return "fail"
    if any(c.status == "warn" for c in checks):
        return "warn"
    return "ok"
