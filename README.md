# 🔍 Code Review Copilot

> **GenAI Capstone — Assignment 2 (Code AI)** · An AI reviewer that catches bugs, explains decisions, and teaches as it reviews.

A GitHub-integrated AI code reviewer powered by **Anthropic Claude** that:

- 📌 posts **inline comments** directly on PR lines (issue + why it matters + a one-click `suggestion` fix),
- 📊 writes a **risk summary** at the top of every PR (quality score /100, highest-risk changes, merge recommendation with rationale),
- 🏷️ tags every comment with a **severity** (`bug` / `security` / `performance` / `style` / `suggestion`) you can filter on,
- 🧠 **learns your team's conventions** from past merged PRs and enforces them automatically,
- 🎓 explains every finding in **plain English for junior developers** — no external research needed.

---

## Architecture

```
                 ┌────────────────────────────────────────────────────────┐
 PR URL (CLI)    │                      pipeline.py                       │
 ──────────────► │                                                        │
                 │  github_client ─► diff_parser ─► reviewer (Claude #1)  │
 GitHub webhook  │      │               │    numbered diff,    per-file   │
 ──────────────► │      │               │    commentable-line  findings   │
   webhook.py    │      ▼               ▼    map                 │        │
   (HMAC verify) │  context_builder (full file @ head SHA)       ▼        │
                 │                              risk_summarizer (Claude #2)│
                 │                                      │                 │
                 │      poster ─► GitHub Review API ◄───┘                 │
                 │      storage (SQLite) ─► Streamlit dashboard           │
                 └────────────────────────────────────────────────────────┘
```

**Three-stage review.** Pass 1 reviews each file's diff (with the *full file* as background context — imports, class definitions, dependencies) and returns schema-validated findings, prompted for *coverage*. Pass 1.5 is an adversarial **verifier**: a skeptical judge re-reads each finding against the diff and suppresses false positives before anything reaches the PR (*precision*). Pass 2 turns the surviving findings + diff stats into the PR-level risk summary.

**Parallel file reviews.** The first file's call warms the prompt cache; the remaining files are reviewed concurrently (`AsyncAnthropic` + `asyncio.gather`, capped at `max_concurrent_reviews=4`) while reading the cached system prompt — a 10-file PR reviews ~4-5× faster than sequentially.

**Idempotent re-reviews.** Every inline comment embeds a hidden fingerprint (`<!-- copilot-fp:… -->`, hash of file + severity + normalised title — stable across line shifts). When the webhook re-reviews on `synchronize`, already-posted findings are detected and skipped instead of spamming duplicates.

**Line attribution is guaranteed, not hoped for.** The diff parser prefixes every diff line with its new-file line number (` 42 | + code`), so the model copies numbers instead of counting. Before posting, every finding is validated against a *commentable-line map*; off-by-a-few findings are snapped to the nearest diff line and un-anchorable ones are dropped (GitHub would 422 on them).

**Structured outputs everywhere.** Claude responses are parsed straight into Pydantic models via `client.messages.parse(...)` — no fragile JSON scraping.

**Prompt caching.** The system prompt + learned conventions carry a `cache_control` breakpoint, so every file after the first in a review reads the prefix from cache (~90% cheaper on input tokens).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET
```

## Usage

```bash
# 1. (optional but recommended) learn the repo's conventions first
copilot learn owner/repo

# 2. review a PR — posts the review to GitHub
copilot review https://github.com/owner/repo/pull/42

# dry run (prints to terminal, posts nothing)
copilot review https://github.com/owner/repo/pull/42 --no-post

# 3. automatic mode: webhook server
copilot serve --port 8000
# then: GitHub repo Settings → Webhooks → add your tunnel URL + /webhook,
# content type application/json, secret = GITHUB_WEBHOOK_SECRET,
# event: "Pull requests". Local tunnel: npx smee-client or ngrok http 8000

# 4. dashboard (history, score trend, severity filters)
streamlit run dashboard/app.py

# past runs in the terminal
copilot history
```

## Tests

```bash
pytest
```

Unit tests cover the diff parser (line attribution, commentable-line map, anchor snapping), comment fingerprinting/dedup, and the schema/URL validators, plus the three Claude passes (review/verify/risk), convention learning, and the full pipeline wiring — all with the model stubbed (no API key, no cost). See [TESTING.md](TESTING.md) for the layer-by-layer breakdown.

## How each rubric feature maps to code

| Rubric feature | Where |
|---|---|
| PR diff analysis (webhook or manual URL; context beyond changed lines) | `cli.py review` / `webhook.py`; `context_builder.py` ships the full file at head SHA |
| Inline comments (issue, why, concrete fix) | `reviewer.py` → `poster.py` → GitHub Reviews API (`line`/`side`, with ```suggestion blocks) |
| Risk summary (score, highest-risk, recommendation + rationale) | `risk_summarizer.py`, rendered by `poster.summary_to_markdown` |
| Convention learning (≥3 actionable rules from history) | `conventions.py` (`copilot learn`), rules injected into the review prompt |
| Severity tagging + filtering | severity enum in `models.py`, emoji labels in comments, filter in dashboard |
| Explanation mode for juniors | mandatory `why_it_matters` field, enforced by the system prompt + schema |

## Model & cost

Model is configurable via `COPILOT_MODEL` (default `claude-opus-4-8`, $5/$25 per MTok, 1M-token context). Every run prints token usage (input / cached / output), and the dashboard shows estimated cumulative cost. For the report's evaluation section, run the same seeded-bug PRs with `COPILOT_MODEL=claude-haiku-4-5` and compare detection rate vs cost.

## Demo / evaluation playbook

1. Create a **sandbox repo** and open 3–4 PRs with planted issues — e.g. SQL injection via string-formatted query (security), unhandled `None` (bug), N+1 query in a loop (performance), naming violations (style).
2. `copilot learn <sandbox repo>` → show the ≥3 extracted rules live.
3. `copilot review <PR URL>` → open the PR on github.com: inline comments sit on the exact planted lines, each with severity emoji + plain-English explanation + one-click suggested fix; risk summary at the top.
4. Open a fresh PR with `copilot serve` + a smee/ngrok tunnel running → the review appears automatically (webhook path).
5. `streamlit run dashboard/app.py` → history, score trend, severity filter.

## Team

5 students · 14-day build · suggested ownership: GitHub client + diff parser / review engine + prompts / risk + conventions / webhook + CLI / dashboard + eval harness.

⚠️ Secrets live only in `.env` (gitignored). Never commit API keys.
