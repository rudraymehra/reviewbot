# Testing Guide — Code Review Copilot

How the project is tested, what is already verified, and the exact steps to
verify the parts that need live credentials.

## 1. Test pyramid

| Layer | What | How | Needs keys? |
|---|---|---|---|
| Unit | diff parsing, line anchoring, fingerprints, schemas, URL parsing | `pytest` | No |
| Component | webhook (signature, event routing), SQLite storage roundtrip | `pytest` (FastAPI TestClient, tmp DB) | No |
| Smoke | CLI commands boot, dashboard compiles | commands below | No |
| Live integration | real Claude review of a real PR, posting to GitHub | manual checklist (§4) | **Yes** |
| Evaluation | detection rate / cost across models on seeded-bug PRs | manual protocol (§5) | **Yes** |

## 2. Automated tests

```bash
source .venv/bin/activate
pytest            # 26 tests
```

| File | Covers |
|---|---|
| `tests/test_diff_parser.py` | hunk parsing, added/context line tracking, commentable-line map, numbered-diff rendering, anchor snapping (exact / ±3 / un-anchorable) |
| `tests/test_poster.py` | fingerprint stability across line shifts, normalisation (case/punctuation), marker roundtrip, GitHub comment payload shape (`path`/`line`/`side`) |
| `tests/test_webhook.py` | health endpoint; 401 on missing/forged `X-Hub-Signature-256`; non-PR events and irrelevant actions ignored; `opened`/`synchronize`/`reopened` accepted and queued (review job stubbed — no network) |
| `tests/test_storage.py` | save → list → get roundtrip on a temp SQLite DB; missing-ID returns None |
| `tests/test_models.py` | severity enum validation, quality-score bounds, PR/repo URL parsing |

These cover every place a silent bug would corrupt a review (wrong line, wrong
file, forged webhook, lost data). The Claude calls themselves are *schema-guarded*
at runtime: `messages.parse()` rejects any response that doesn't match the
Pydantic models, so a malformed model response raises instead of posting garbage.

## 3. Smoke checks (no keys needed)

```bash
copilot --help                      # all 4 subcommands listed
copilot review --help
copilot history                     # "No reviews yet." on a fresh clone
python -m py_compile dashboard/app.py
```

## 4. Live integration checklist (needs .env)

Prerequisites: `cp .env.example .env` and fill in `ANTHROPIC_API_KEY`,
`GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`.

Tick these off in order — each one builds on the previous:

- [ ] **Dry run:** `copilot review <PR URL> --no-post`
      → terminal shows findings table, quality score, token usage. Nothing posted.
- [ ] **Line attribution:** `copilot review <PR URL>` (posting on)
      → open the PR on github.com; every inline comment sits on the exact line
      of the planted issue, with severity emoji + `suggestion` block.
- [ ] **Re-review dedup:** run the same `copilot review` again
      → output shows `↩ N comment(s) already on the PR, not re-posted`;
      no duplicate comments appear on GitHub.
- [ ] **Convention learning:** `copilot learn owner/repo` (repo with ≥3 merged PRs)
      → prints ≥3 rules; `.copilot/rules.json` created; next `review` enforces them.
- [ ] **Webhook end-to-end:**
      ```bash
      copilot serve --port 8000
      npx smee-client --url https://smee.io/<channel> --target http://localhost:8000/webhook
      # GitHub repo → Settings → Webhooks → smee URL, content type application/json,
      # secret = GITHUB_WEBHOOK_SECRET, event: Pull requests
      ```
      → open a new PR; the review appears automatically within ~1 min.
- [ ] **Webhook security (manual):** `curl -X POST localhost:8000/webhook -d '{}'`
      → `401` (missing signature).
- [ ] **Dashboard:** `streamlit run dashboard/app.py`
      → metrics, score trend, severity chart, review browser with severity filter.

## 5. Model evaluation protocol (for the report)

1. In the sandbox repo, open 4 PRs with planted issues (one per severity):
   SQL injection · unhandled `None` · query-in-loop (N+1) · naming violations.
2. Review all 4 with the default model, record per PR: planted issues detected,
   false positives posted, findings suppressed by the verifier, tokens in/out
   (printed after every run).
3. Repeat with `COPILOT_MODEL=claude-haiku-4-5` in `.env`.
4. Report table: detection rate, precision, cost per review, per model.
   The dashboard's cost metric gives the cumulative totals.

## 6. Current verification status

Last full run: 2026-06-10 (local machine, Python 3.14).

| Check | Status |
|---|---|
| `pytest` (26 tests) | ✅ pass |
| CLI: `review/learn/serve/history --help` | ✅ pass |
| `copilot history` on fresh DB | ✅ pass |
| Dashboard compiles | ✅ pass |
| Webhook signature enforcement (automated) | ✅ pass |
| Live Claude review / GitHub posting | ⬜ blocked — no `.env` keys yet (§4) |
| Convention learning live | ⬜ blocked — same |
| Webhook end-to-end via tunnel | ⬜ blocked — same |
| Model evaluation (§5) | ⬜ blocked — same |

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `401 Unauthorized` from Anthropic | `ANTHROPIC_API_KEY` missing/typo in `.env` |
| `404` fetching PR | `GITHUB_TOKEN` lacks access to the repo (private repo needs repo scope) |
| `422` posting review | comment on a line outside the diff — should be prevented by the anchor filter; if it recurs, the head SHA moved between fetch and post (re-run) |
| Webhook returns 401 | secret in GitHub webhook settings ≠ `GITHUB_WEBHOOK_SECRET` |
| Webhook 200 but no review | check `copilot serve` logs — review runs in background; errors are logged there |
| Empty dashboard | no reviews stored yet, or `COPILOT_DB_PATH` differs between CLI and dashboard |
