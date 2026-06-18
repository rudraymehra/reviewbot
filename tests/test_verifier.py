"""Pass 1.5 (false-positive filter) with Claude stubbed.

The verifier must split findings into kept/suppressed by the judge's verdicts,
and — critically — fail OPEN: any missing verdict or API error keeps the finding
rather than silently dropping a real review comment.
"""

import anthropic
import httpx

from copilot.diff_parser import parse_diff
from copilot.models import Finding
from copilot.verifier import Verdict, Verdicts, verify_findings

from conftest import ONE_FILE_DIFF


def _finding(title, line=4):
    return Finding(
        file="app/calc.py", line=line, severity="bug", title=title,
        issue="i", why_it_matters="w", suggested_fix="x", confidence="medium",
    )


def _usage():
    from copilot.reviewer import Usage
    return Usage()


def test_empty_findings_short_circuit_without_calling_claude(fake_claude):
    kept, suppressed = verify_findings([], [], _usage())
    assert kept == [] and suppressed == []
    assert fake_claude.calls == []


def test_keeps_and_suppresses_per_verdict(fake_claude):
    findings = [_finding("real bug"), _finding("noise")]
    diffs = parse_diff(ONE_FILE_DIFF)
    fake_claude.queue(Verdicts(verdicts=[
        Verdict(index=0, keep=True, reason="genuine"),
        Verdict(index=1, keep=False, reason="platitude"),
    ]))

    kept, suppressed = verify_findings(findings, diffs, _usage())

    assert [f.title for f in kept] == ["real bug"]
    assert [f.title for f in suppressed] == ["noise"]


def test_missing_verdict_defaults_to_kept(fake_claude):
    findings = [_finding("a"), _finding("b")]
    diffs = parse_diff(ONE_FILE_DIFF)
    # Judge only returns a verdict for index 0; index 1 must fail open (kept).
    fake_claude.queue(Verdicts(verdicts=[Verdict(index=0, keep=False, reason="x")]))

    kept, suppressed = verify_findings(findings, diffs, _usage())

    assert [f.title for f in suppressed] == ["a"]
    assert [f.title for f in kept] == ["b"]


def test_api_error_fails_open(fake_claude):
    findings = [_finding("a"), _finding("b")]
    diffs = parse_diff(ONE_FILE_DIFF)
    fake_claude.error = anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))

    kept, suppressed = verify_findings(findings, diffs, _usage())

    assert len(kept) == 2 and suppressed == []
