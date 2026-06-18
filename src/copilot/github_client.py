"""Thin GitHub REST client: fetch PR data, post reviews, sample merged PRs."""

import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import get_settings

API = "https://api.github.com"

PR_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")
REPO_URL_RE = re.compile(r"(?:github\.com/)?([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """'https://github.com/owner/repo/pull/42' -> ('owner', 'repo', 42)."""
    m = PR_URL_RE.search(url)
    if not m:
        raise ValueError(f"Not a GitHub PR URL: {url}")
    return m.group(1), m.group(2), int(m.group(3))


def parse_repo(repo: str) -> tuple[str, str]:
    """Accepts 'owner/repo' or a full repo URL."""
    m = REPO_URL_RE.search(repo)
    if not m:
        raise ValueError(f"Not a GitHub repo: {repo}")
    return m.group(1), m.group(2)


@dataclass
class PullRequest:
    owner: str
    repo: str
    number: int
    title: str
    body: str
    author: str
    head_sha: str
    base_branch: str
    additions: int
    deletions: int
    changed_files: int
    diff: str = ""

    @property
    def full_repo(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass
class MergedPR:
    number: int
    title: str
    diff: str
    review_comments: list[str] = field(default_factory=list)


class GitHubClient:
    def __init__(self, token: str | None = None):
        token = token or get_settings().github_token
        self._client = httpx.Client(
            base_url=API,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------- reading ----------

    def get_pull_request(self, owner: str, repo: str, number: int) -> PullRequest:
        meta = self._get(f"/repos/{owner}/{repo}/pulls/{number}")
        diff = self._get_text(
            f"/repos/{owner}/{repo}/pulls/{number}",
            accept="application/vnd.github.v3.diff",
        )
        return PullRequest(
            owner=owner,
            repo=repo,
            number=number,
            title=meta["title"],
            body=meta.get("body") or "",
            author=meta["user"]["login"],
            head_sha=meta["head"]["sha"],
            base_branch=meta["base"]["ref"],
            additions=meta["additions"],
            deletions=meta["deletions"],
            changed_files=meta["changed_files"],
            diff=diff,
        )

    def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        """Full text of a file at a given commit; None if missing/binary/too big."""
        try:
            resp = self._client.get(
                f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": ref},
                headers={"Accept": "application/vnd.github.raw+json"},
            )
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPStatusError, UnicodeDecodeError):
            return None

    def get_merged_prs(self, owner: str, repo: str, limit: int = 15) -> list[MergedPR]:
        """Recent merged PRs with their diffs and human review comments."""
        pulls = self._get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 50},
        )
        merged: list[MergedPR] = []
        for p in pulls:
            if not p.get("merged_at"):
                continue
            number = p["number"]
            diff = self._get_text(
                f"/repos/{owner}/{repo}/pulls/{number}",
                accept="application/vnd.github.v3.diff",
            )
            comments = self._get(f"/repos/{owner}/{repo}/pulls/{number}/comments")
            merged.append(
                MergedPR(
                    number=number,
                    title=p["title"],
                    diff=diff[:20_000],
                    review_comments=[c["body"] for c in comments][:30],
                )
            )
            if len(merged) >= limit:
                break
        return merged

    def get_review_comment_bodies(self, owner: str, repo: str, number: int) -> list[str]:
        """Bodies of all existing inline review comments on a PR (for dedup).

        Paginated: a long-lived PR can accumulate >100 comments, and missing the
        tail would make dedup re-post old findings on every push.
        """
        return [c["body"] for c in self.get_review_comments(owner, repo, number)]

    def get_review_comments(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        """Full inline review-comment objects (path/line/body) for dedup."""
        return self._get_paginated(f"/repos/{owner}/{repo}/pulls/{number}/comments")

    def get_review_summary_bodies(self, owner: str, repo: str, number: int) -> list[str]:
        """Bodies of all review summaries on a PR (where 422-fallback comments land)."""
        reviews = self._get_paginated(f"/repos/{owner}/{repo}/pulls/{number}/reviews")
        return [r["body"] for r in reviews if r.get("body")]

    # ---------- writing ----------

    def post_review(
        self,
        owner: str,
        repo: str,
        number: int,
        body: str,
        comments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Post one PR review: summary body + inline comments.

        Each comment: {"path", "line", "side": "RIGHT", "body"}.
        """
        payload: dict[str, Any] = {"body": body, "event": "COMMENT"}
        if comments:
            payload["comments"] = comments
        resp = self._client.post(f"/repos/{owner}/{repo}/pulls/{number}/reviews", json=payload)
        if resp.status_code == 422 and comments:
            # A comment GitHub rejected (e.g. line left the diff between fetch and
            # post). Fall back to posting the summary alone rather than losing it.
            resp = self._client.post(
                f"/repos/{owner}/{repo}/pulls/{number}/reviews",
                json={"body": body + _fallback_comments_md(comments), "event": "COMMENT"},
            )
        resp.raise_for_status()
        return resp.json()

    # ---------- internals ----------

    def _get(self, path: str, params: dict | None = None) -> Any:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def _get_paginated(self, path: str, params: dict | None = None) -> list[Any]:
        """Follow GitHub's Link header to fetch every page of a list endpoint."""
        params = {**(params or {}), "per_page": 100}
        items: list[Any] = []
        url: str | None = path
        next_params: dict | None = params
        while url:
            resp = self._client.get(url, params=next_params)
            resp.raise_for_status()
            items.extend(resp.json())
            # Subsequent page URLs from the Link header already carry their params.
            url = resp.links.get("next", {}).get("url")
            next_params = None
        return items

    def _get_text(self, path: str, accept: str) -> str:
        resp = self._client.get(path, headers={"Accept": accept})
        resp.raise_for_status()
        return resp.text


def _fallback_comments_md(comments: list[dict[str, Any]]) -> str:
    parts = ["\n\n---\n### Inline comments (could not be anchored)\n"]
    for c in comments:
        # Body is emitted verbatim — it ends with the <!-- copilot-fp:… --> marker.
        # Dedup picks these up via get_review_summary_bodies() on a later re-review,
        # so fallback-posted findings aren't re-posted as duplicates.
        parts.append(f"\n**`{c['path']}:{c['line']}`**\n\n{c['body']}\n")
    return "".join(parts)
