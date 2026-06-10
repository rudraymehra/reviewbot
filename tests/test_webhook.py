"""Webhook tests: signature enforcement and event routing — no network needed."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

SECRET = "testsecret"


def sign(payload: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    from copilot.config import get_settings

    get_settings.cache_clear()
    from copilot.webhook import app

    yield TestClient(app)
    get_settings.cache_clear()


@pytest.fixture
def review_calls(monkeypatch):
    """Replace the real review job so accepted events don't hit the network."""
    calls: list[tuple] = []
    from copilot import webhook

    monkeypatch.setattr(webhook, "_review_in_background", lambda *a: calls.append(a))
    return calls


def pr_event(action: str = "opened") -> bytes:
    return json.dumps({
        "action": action,
        "repository": {"full_name": "octo/hello"},
        "pull_request": {"number": 7},
    }).encode()


def test_health(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_missing_signature_rejected(client):
    resp = client.post("/webhook", content=pr_event())
    assert resp.status_code == 401


def test_bad_signature_rejected(client):
    resp = client.post(
        "/webhook",
        content=pr_event(),
        headers={"X-Hub-Signature-256": sign(pr_event(), "wrong-secret")},
    )
    assert resp.status_code == 401


def test_non_pr_event_ignored(client, review_calls):
    body = pr_event()
    resp = client.post(
        "/webhook",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "push"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert review_calls == []


def test_irrelevant_action_ignored(client, review_calls):
    body = pr_event(action="labeled")
    resp = client.post(
        "/webhook",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "pull_request"},
    )
    assert resp.json()["status"] == "ignored"
    assert review_calls == []


@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened"])
def test_pr_event_accepted_and_queued(client, review_calls, action):
    body = pr_event(action=action)
    resp = client.post(
        "/webhook",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "accepted", "pr": "octo/hello#7", "action": action}
    assert review_calls == [("octo", "hello", 7)]
