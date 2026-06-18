"""FastAPI webhook: GitHub calls us on PR open/update, we review in the background.

Demo locally:  copilot serve  +  smee.io or ngrok tunnel pointed at /webhook.
"""

import hashlib
import hmac
import logging

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from .config import get_settings

logger = logging.getLogger("copilot.webhook")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Code Review Copilot")


def verify_signature(payload: bytes, signature_header: str | None) -> None:
    secret = get_settings().github_webhook_secret
    if not secret:
        raise HTTPException(500, "GITHUB_WEBHOOK_SECRET is not configured")
    if not signature_header:
        raise HTTPException(401, "Missing X-Hub-Signature-256 header")
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(401, "Invalid webhook signature")


def _review_in_background(owner: str, repo: str, number: int) -> None:
    from .pipeline import run_review

    try:
        result = run_review(owner, repo, number, post=True, on_progress=logger.info)
        logger.info(
            "Reviewed %s/%s#%s: score=%s rec=%s findings=%s",
            owner, repo, number,
            result.summary.quality_score,
            result.summary.merge_recommendation,
            len(result.findings),
        )
    except Exception:
        logger.exception("Review failed for %s/%s#%s", owner, repo, number)


@app.get("/")
def health() -> dict:
    return {"status": "ok", "service": "code-review-copilot"}


@app.post("/webhook")
async def webhook(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    payload = await request.body()
    verify_signature(payload, x_hub_signature_256)

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event {x_github_event!r} not handled"}

    data = await request.json()
    action = data.get("action")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"action {action!r} not handled"}

    repo_full = data.get("repository", {}).get("full_name")
    number = data.get("pull_request", {}).get("number")
    if not repo_full or "/" not in repo_full or number is None:
        return {"status": "ignored", "reason": "payload missing repository/pull_request fields"}
    owner, repo = repo_full.split("/", 1)

    background.add_task(_review_in_background, owner, repo, number)
    return {"status": "accepted", "pr": f"{repo_full}#{number}", "action": action}
