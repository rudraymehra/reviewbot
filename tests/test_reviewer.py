"""Pass 1 (per-file review) with Claude stubbed.

Covers the file-skipping rules and the line-anchoring contract: a model finding
on a real diff line is kept, an off-by-a-few one is snapped, and one outside the
diff is dropped (never posted) rather than 422'd by GitHub.
"""

from copilot.diff_parser import FileDiff, parse_diff
from copilot.models import FileReview, Finding
from copilot.reviewer import reviewable_files, review_pr

from conftest import make_pr


def _finding(line, **kw):
    base = dict(
        file="ignored-by-reviewer", line=line, severity="bug",
        title="t", issue="i", why_it_matters="w", suggested_fix="x", confidence="low",
    )
    base.update(kw)
    return Finding(**base)


class FakeGitHub:
    def get_file_content(self, owner, repo, path, ref):
        return "def add(a, b):\n    return a - b\n"


def test_reviewable_files_skips_lockfiles_binaries_and_deletions():
    files = [
        FileDiff(path="app/main.py", is_new=False, is_deleted=False),
        FileDiff(path="poetry.lock", is_new=False, is_deleted=False),
        FileDiff(path="static/logo.svg", is_new=True, is_deleted=False),
        FileDiff(path="old.py", is_new=False, is_deleted=True),
        FileDiff(path="bundle.min.js", is_new=False, is_deleted=False),
    ]
    assert [f.path for f in reviewable_files(files)] == ["app/main.py"]


def test_review_pr_anchors_snaps_and_drops_findings(fake_claude):
    # exact (4), off-by-2 (6 -> snaps to 4), and un-anchorable (50 -> dropped).
    fake_claude.queue(FileReview(findings=[_finding(4), _finding(6), _finding(50)]))

    outcome = review_pr(FakeGitHub(), make_pr())

    kept_lines = sorted(f.line for f in outcome.findings)
    assert kept_lines == [4, 4]                      # exact + snapped
    assert all(f.file == "app/calc.py" for f in outcome.findings)  # path from parser, not model
    assert [f.line for f in outcome.dropped] == [50]


def test_review_pr_accumulates_token_usage(fake_claude):
    fake_claude.queue(FileReview(findings=[]))
    outcome = review_pr(FakeGitHub(), make_pr())
    assert outcome.usage.input_tokens == 100
    assert outcome.usage.output_tokens == 50
    assert outcome.usage.cached_tokens == 10


def test_review_pr_with_no_reviewable_files_makes_no_claude_call(fake_claude):
    pr = make_pr(diff="")
    # An empty diff parses to zero files; the async section is skipped entirely.
    assert parse_diff(pr.diff) == []
    outcome = review_pr(FakeGitHub(), pr)
    assert outcome.findings == []
    assert fake_claude.calls == []
