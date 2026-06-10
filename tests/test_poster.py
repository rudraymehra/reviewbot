from copilot.models import Finding
from copilot.poster import (
    extract_fingerprints,
    finding_to_comment_body,
    findings_to_github_comments,
    fingerprint,
)


def make_finding(**overrides) -> Finding:
    base = dict(
        file="app/db.py", line=15, severity="security",
        title="SQL injection via string-formatted query",
        issue="user_id is interpolated into the SQL string",
        why_it_matters="An attacker can read or delete any row.",
        suggested_fix='conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
        confidence="high",
    )
    base.update(overrides)
    return Finding(**base)


def test_fingerprint_stable_across_line_shifts():
    # Same issue after a force-push moved it 30 lines: identical fingerprint.
    assert fingerprint(make_finding(line=15)) == fingerprint(make_finding(line=45))


def test_fingerprint_distinguishes_different_findings():
    assert fingerprint(make_finding()) != fingerprint(make_finding(file="app/other.py"))
    assert fingerprint(make_finding()) != fingerprint(make_finding(severity="bug"))
    assert fingerprint(make_finding()) != fingerprint(make_finding(title="Different problem"))


def test_fingerprint_ignores_title_punctuation_and_case():
    a = fingerprint(make_finding(title="SQL injection, via string-formatted query!"))
    b = fingerprint(make_finding(title="sql injection via string formatted query"))
    assert a == b


def test_marker_roundtrip():
    f = make_finding()
    body = finding_to_comment_body(f)
    assert extract_fingerprints([body]) == {fingerprint(f)}


def test_extract_ignores_unmarked_comments():
    assert extract_fingerprints(["just a human comment", "another one"]) == set()


def test_comment_payload_shape():
    [comment] = findings_to_github_comments([make_finding()])
    assert comment["path"] == "app/db.py"
    assert comment["line"] == 15
    assert comment["side"] == "RIGHT"
    assert "```suggestion" in comment["body"]
    assert "[SECURITY]" in comment["body"]
