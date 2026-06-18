"""End-to-end pipeline wiring with Claude + GitHub + DB all stubbed.

This is the integration test for the orchestration in ``run_review``: pass 1
(review) -> 1.5 (verify) -> 2 (risk) -> dedup -> post -> persist. It proves the
stages are wired in the right order and that suppressed/duplicate findings never
reach GitHub.
"""

import copilot.pipeline as pipeline_mod
from copilot.models import FileReview, Finding, RiskSummary
from copilot.pipeline import run_review
from copilot.poster import finding_to_comment_body
from copilot.storage import list_reviews
from copilot.verifier import Verdict, Verdicts

from conftest import make_pr


def _finding(line, title):
    return Finding(
        file="x", line=line, severity="bug", title=title, issue="i",
        why_it_matters="w", suggested_fix="fix", confidence="medium",
    )


def _summary():
    return RiskSummary(
        quality_score=55, overall_assessment="ok", highest_risk_changes=["calc"],
        merge_recommendation="request_changes", rationale="a bug",
    )


class FakeGitHubClient:
    def __init__(self, existing_comments=None):
        # existing_comments: list of {"path","line","body"} dicts
        self.existing_comments = existing_comments or []
        self.posted = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_pull_request(self, owner, repo, number):
        return make_pr(number=number)

    def get_file_content(self, owner, repo, path, ref):
        return "def add(a, b):\n    return a - b\n"

    def get_review_comments(self, owner, repo, number):
        return self.existing_comments

    def get_review_comment_bodies(self, owner, repo, number):
        return [c["body"] for c in self.existing_comments]

    def get_review_summary_bodies(self, owner, repo, number):
        return []

    def post_review(self, owner, repo, number, body, comments):
        self.posted = {"body": body, "comments": comments}
        return {"id": 1}


def _install(monkeypatch, gh):
    monkeypatch.setattr(pipeline_mod, "GitHubClient", lambda *a, **k: gh)
    return gh


def test_pipeline_suppresses_and_persists_without_posting(fake_claude, tmp_db, monkeypatch):
    gh = _install(monkeypatch, FakeGitHubClient())
    # findings sort to [beta@2, alpha@4]; verifier keeps index0, suppresses index1.
    fake_claude.queue(
        FileReview(findings=[_finding(4, "alpha"), _finding(2, "beta")]),
        Verdicts(verdicts=[Verdict(index=0, keep=True, reason="real"),
                           Verdict(index=1, keep=False, reason="noise")]),
        _summary(),
    )

    result = run_review("octo", "hello", 7, post=False)

    assert [f.title for f in result.findings] == ["beta"]
    assert [f.title for f in result.suppressed] == ["alpha"]
    assert gh.posted is None                       # post=False posts nothing
    assert result.summary.quality_score == 55

    rows = list_reviews(db_path=tmp_db)            # persisted exactly once
    assert len(rows) == 1
    assert rows[0]["finding_count"] == 1


def test_pipeline_skips_already_posted_comments(fake_claude, tmp_db, monkeypatch):
    # An earlier review already posted the "beta" comment on this PR.
    already_posted = finding_to_comment_body(
        Finding(file="app/calc.py", line=2, severity="bug", title="beta",
                issue="i", why_it_matters="w", suggested_fix="fix", confidence="medium")
    )
    gh = _install(monkeypatch, FakeGitHubClient(existing_comments=[
        {"path": "app/calc.py", "line": 2, "body": already_posted},
    ]))
    fake_claude.queue(
        FileReview(findings=[_finding(4, "alpha"), _finding(2, "beta")]),
        Verdicts(verdicts=[Verdict(index=0, keep=True, reason="real"),
                           Verdict(index=1, keep=True, reason="real")]),
        _summary(),
    )

    result = run_review("octo", "hello", 7, post=True)

    assert result.skipped_duplicates == 1
    posted_titles = [c["body"] for c in gh.posted["comments"]]
    assert any("alpha" in b for b in posted_titles)        # fresh finding posted
    assert not any("beta" in b for b in posted_titles)     # duplicate skipped
