"""Convention learning with Claude + GitHub stubbed.

The rubric wants >=3 actionable rules from merged history. This checks the
module feeds the merged PRs (diffs + human review comments) into the prompt,
returns the parsed rules, and errors cleanly when there is nothing to learn from.
"""

import pytest

from copilot.conventions import learn_conventions
from copilot.models import ConventionRule, ConventionRules

from conftest import make_merged_pr


class FakeGitHub:
    def __init__(self, merged):
        self._merged = merged
        self.asked = None

    def get_merged_prs(self, owner, repo, limit):
        self.asked = (owner, repo, limit)
        return self._merged


def _rules():
    return ConventionRules(rules=[
        ConventionRule(rule="API routes use snake_case", evidence="PR #1", category="style"),
        ConventionRule(rule="handlers return JSONResponse", evidence="PR #2", category="bug"),
        ConventionRule(rule="every endpoint has a test", evidence="PR #3", category="suggestion"),
    ])


def test_learns_rules_from_merged_history(fake_claude):
    gh = FakeGitHub([make_merged_pr(1), make_merged_pr(2)])
    fake_claude.queue(_rules())

    rules = learn_conventions(gh, "octo", "hello")

    assert len(rules.rules) >= 3
    sent = fake_claude.calls[0]["messages"][0]["content"]
    assert "use snake_case for routes" in sent     # human review comment included
    assert "PR #1" in sent and "PR #2" in sent      # both merged PRs reach the prompt


def test_raises_when_no_merged_prs(fake_claude):
    gh = FakeGitHub([])
    with pytest.raises(RuntimeError, match="No merged PRs"):
        learn_conventions(gh, "octo", "hello")
    assert fake_claude.calls == []                  # never bothered Claude
