# Contributing — Code Review Copilot

Thanks for hacking on the reviewer! This is the short version of how to get set
up, what to run before you push, and how the pieces fit together.

## Setup

```bash
make install          # creates .venv and installs the package + dev deps
cp .env.example .env   # fill in ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET
make doctor            # confirms your config is ready (no network calls)
```

`make doctor` (a.k.a. `copilot doctor`) tells you exactly which keys are missing
before you spend a token — run it first whenever a live command misbehaves.

## Everyday commands

| Command | What it does |
|---|---|
| `make test` | run the 38-test suite (`pytest`) |
| `make doctor` | check local config & credentials |
| `make dashboard` | launch the Streamlit dashboard |
| `make serve` | run the webhook server on `:8000` |
| `make help` | list all targets |

## Before you push

1. `make test` — all tests green.
2. `make doctor` — no unexpected `fail`/`warn`.
3. Keep secrets in `.env` only (it's gitignored). Never commit a real key.

CI (`.github/workflows/ci.yml`) runs the suite + CLI smoke checks on Python
3.10–3.12 for every push and PR, so the same two commands gate `main`.

## Project layout

```
src/copilot/
  cli.py            Typer CLI: review / learn / serve / doctor / history
  pipeline.py       orchestrates a full review run
  github_client.py  GitHub REST: fetch PRs/diffs, post reviews
  diff_parser.py    numbered diff + commentable-line map (line attribution)
  context_builder.py full-file context at the PR head SHA
  reviewer.py       Pass 1  — per-file findings (structured output, prompt cache)
  verifier.py       Pass 1.5 — adversarial false-positive filter
  risk_summarizer.py Pass 2  — PR-level risk summary
  conventions.py    learn team rules from merged PR history
  poster.py         render comments + post via the GitHub Reviews API
  storage.py        SQLite history (read by the dashboard)
  pricing.py        token-cost estimation (shared by dashboard + doctor)
  doctor.py         preflight config checks
dashboard/app.py    Streamlit history / trends / severity filter
tests/              unit + component tests (no keys required)
```

## Testing notes

- Unit and component tests need **no** API keys — Claude calls are schema-guarded
  at runtime, and the webhook/storage tests stub the network.
- Anything needing live credentials is documented as a manual checklist in
  [TESTING.md](TESTING.md) §4.
- When you add a module that can silently corrupt a review (line numbers, file
  paths, dedup, persisted data), add a unit test for it — that's the bar the
  existing `tests/` set.
