"""Preflight checks: credential detection, secret masking, rules-file reporting.

These run without any network or token spend, so they're safe in CI.
"""

import json

import pytest

from copilot.config import get_settings
from copilot.doctor import _mask, overall, run_checks


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch):
    """Each test controls the environment; clear the cached Settings around it."""
    for var in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN", "GITHUB_WEBHOOK_SECRET", "COPILOT_DB_PATH"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _by_name(checks):
    return {c.name: c for c in checks}


def test_missing_keys_fail_overall(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "copilot.db"))
    get_settings.cache_clear()

    checks = run_checks(repo_dir=tmp_path)
    by_name = _by_name(checks)
    assert by_name["ANTHROPIC_API_KEY"].status == "fail"
    assert by_name["GITHUB_TOKEN"].status == "fail"
    assert overall(checks) == "fail"


def test_keys_present_clear_the_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-abcdef123456")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_abcdef123456")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "a-real-secret")
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "copilot.db"))
    get_settings.cache_clear()

    checks = run_checks(repo_dir=tmp_path)
    by_name = _by_name(checks)
    assert by_name["ANTHROPIC_API_KEY"].status == "ok"
    assert by_name["GITHUB_TOKEN"].status == "ok"
    assert by_name["GITHUB_WEBHOOK_SECRET"].status == "ok"
    # secrets must never appear verbatim in the rendered detail
    assert "sk-ant-abcdef123456" not in by_name["ANTHROPIC_API_KEY"].detail


def test_default_webhook_secret_warns(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "change-me")
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "copilot.db"))
    get_settings.cache_clear()

    by_name = _by_name(run_checks(repo_dir=tmp_path))
    assert by_name["GITHUB_WEBHOOK_SECRET"].status == "warn"


def test_learned_rules_are_counted(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "copilot.db"))
    get_settings.cache_clear()

    rules_file = tmp_path / ".copilot" / "rules.json"
    rules_file.parent.mkdir(parents=True)
    rules_file.write_text(json.dumps([{"rule": "a"}, {"rule": "b"}, {"rule": "c"}]))

    by_name = _by_name(run_checks(repo_dir=tmp_path))
    conv = by_name["learned conventions"]
    assert conv.status == "ok"
    assert "3 rule(s)" in conv.detail


def test_running_doctor_creates_no_db(tmp_path, monkeypatch):
    db = tmp_path / "copilot.db"
    monkeypatch.setenv("COPILOT_DB_PATH", str(db))
    get_settings.cache_clear()

    run_checks(repo_dir=tmp_path)
    assert not db.exists(), "doctor must not create the history DB as a side effect"


def test_mask_hides_secret_body():
    assert _mask("") == "(not set)"
    assert _mask("short") == "•••••"
    masked = _mask("sk-ant-1234567890")
    assert masked.startswith("sk-a") and masked.endswith("90")
    assert "1234567890" not in masked
