"""Coarse re-review dedup: skip same file+severity on a nearby line.

The exact fingerprint misses a finding when the model rephrases its title on a
re-review, so these guard the anchor-based fallback in poster.py.
"""

from copilot.models import Finding
from copilot.poster import extract_anchors, finding_to_comment_body, is_near_duplicate


def _finding(line, title, severity="bug", file="a.py"):
    return Finding(
        file=file, line=line, severity=severity, title=title,
        issue="x", why_it_matters="y", suggested_fix="z", confidence="high",
    )


def test_extract_anchors_parses_path_severity_line():
    body = finding_to_comment_body(_finding(10, "SQL injection", severity="security"))
    anchors = extract_anchors([{"path": "a.py", "line": 10, "body": body}])
    assert anchors == [("a.py", "security", 10)]


def test_extract_anchors_falls_back_to_original_line():
    body = finding_to_comment_body(_finding(5, "bug here"))
    anchors = extract_anchors([{"path": "a.py", "line": None, "original_line": 5, "body": body}])
    assert anchors == [("a.py", "bug", 5)]


def test_extract_anchors_skips_comments_without_severity_tag():
    anchors = extract_anchors([{"path": "a.py", "line": 3, "body": "just a human comment"}])
    assert anchors == []


def test_near_duplicate_same_file_severity_within_window():
    anchors = [("a.py", "bug", 10)]
    # different title (→ different fingerprint) but same file+severity, 2 lines away
    assert is_near_duplicate(_finding(12, "totally reworded title"), anchors) is True


def test_not_duplicate_when_outside_line_window():
    anchors = [("a.py", "bug", 10)]
    assert is_near_duplicate(_finding(20, "x"), anchors) is False


def test_not_duplicate_when_severity_differs():
    anchors = [("a.py", "bug", 10)]
    assert is_near_duplicate(_finding(10, "x", severity="security"), anchors) is False


def test_not_duplicate_when_file_differs():
    anchors = [("a.py", "bug", 10)]
    assert is_near_duplicate(_finding(10, "x", file="b.py"), anchors) is False
