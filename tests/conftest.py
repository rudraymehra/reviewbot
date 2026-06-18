"""Shared test doubles for the Claude-backed modules.

The reviewer/verifier/risk/conventions modules all instantiate an
``anthropic`` client and call ``messages.parse(...)``. None of that should hit
the network in a unit test. ``fake_claude`` patches both the sync and async
clients with a stub that returns queued Pydantic outputs (or raises a queued
error), and records every call so tests can assert on the prompt that was sent.
"""

import anthropic
import pytest

from copilot.config import get_settings
from copilot.github_client import MergedPR, PullRequest


class FakeUsage:
    """Mimics ``response.usage`` as read by ``reviewer.Usage.add``."""

    def __init__(self, input_tokens=100, output_tokens=50, cache_read_input_tokens=10):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class FakeResponse:
    def __init__(self, parsed_output, usage):
        self.parsed_output = parsed_output
        self.usage = usage


class FakeClaude:
    """Programmable stand-in for ``anthropic.Anthropic`` / ``AsyncAnthropic``.

    Queue outputs with ``queue(...)``; set ``error`` to make the next call raise;
    set ``responder`` to compute the output from the call kwargs (handy when
    several files are reviewed in one run). ``calls`` records every parse kwarg.
    """

    def __init__(self):
        self.outputs = []
        self.responder = None
        self.error = None
        self.usage = FakeUsage()
        self.calls = []

    def queue(self, *outputs):
        self.outputs.extend(outputs)
        return self

    def _produce(self, kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.responder is not None:
            return FakeResponse(self.responder(kwargs), self.usage)
        return FakeResponse(self.outputs.pop(0), self.usage)


@pytest.fixture
def fake_claude(monkeypatch):
    stub = FakeClaude()

    class _SyncMessages:
        def parse(self, **kwargs):
            return stub._produce(kwargs)

    class _AsyncMessages:
        async def parse(self, **kwargs):
            return stub._produce(kwargs)

    class _SyncClient:
        def __init__(self, **_):
            self.messages = _SyncMessages()

    class _AsyncClient:
        def __init__(self, **_):
            self.messages = _AsyncMessages()

    monkeypatch.setattr(anthropic, "Anthropic", _SyncClient)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _AsyncClient)
    return stub


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Point every ``get_settings().copilot_db_path`` at a throwaway file."""
    db = tmp_path / "reviews.db"
    monkeypatch.setenv("COPILOT_DB_PATH", str(db))
    get_settings.cache_clear()
    yield str(db)
    get_settings.cache_clear()


# --- diff used by reviewer / pipeline tests ---------------------------------
# Hunk targets new-file lines 1-4, so commentable_lines == {1, 2, 3, 4}.
ONE_FILE_DIFF = """\
diff --git a/app/calc.py b/app/calc.py
index 1111111..2222222 100644
--- a/app/calc.py
+++ b/app/calc.py
@@ -1,2 +1,4 @@
 def add(a, b):
-    return a + b
+    return a - b
+
+result = eval(user_input)
"""


def make_pr(diff=ONE_FILE_DIFF, **overrides) -> PullRequest:
    base = dict(
        owner="octo", repo="hello", number=7, title="Tweak calc",
        body="", author="dev", head_sha="abc123", base_branch="main",
        additions=3, deletions=1, changed_files=1, diff=diff,
    )
    base.update(overrides)
    return PullRequest(**base)


def make_merged_pr(number=1, **overrides) -> MergedPR:
    base = dict(
        number=number, title=f"PR {number}", diff="diff text",
        review_comments=["use snake_case for routes"],
    )
    base.update(overrides)
    return MergedPR(**base)
