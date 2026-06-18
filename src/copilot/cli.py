"""Typer CLI: `copilot review`, `copilot learn`, `copilot serve`."""

import typer
from rich.console import Console
from rich.table import Table

from .models import SEVERITY_EMOJI

app = typer.Typer(help="Code Review Copilot — AI reviewer for GitHub PRs.", no_args_is_help=True)
console = Console()


@app.command()
def review(
    pr_url: str = typer.Argument(help="GitHub PR URL, e.g. https://github.com/owner/repo/pull/42"),
    post: bool = typer.Option(True, help="Post the review to GitHub (use --no-post for a dry run)."),
):
    """Review a pull request and post inline comments + a risk summary."""
    from .github_client import parse_pr_url
    from .pipeline import run_review

    owner, repo, number = parse_pr_url(pr_url)
    with console.status("Reviewing…") as status:
        result = run_review(
            owner, repo, number, post=post,
            on_progress=lambda msg: status.update(f"[cyan]{msg}"),
        )

    console.print(f"\n[bold]## {result.pr_title}[/bold] ({result.repo}#{result.pr_number})")
    console.print(
        f"Quality score: [bold]{result.summary.quality_score}/100[/bold] · "
        f"Recommendation: [bold]{result.summary.merge_recommendation}[/bold]"
    )
    console.print(result.summary.overall_assessment + "\n")

    if result.findings:
        table = Table(title=f"{len(result.findings)} finding(s)")
        table.add_column("Sev")
        table.add_column("Location")
        table.add_column("Title")
        table.add_column("Conf")
        for f in result.findings:
            table.add_row(
                f"{SEVERITY_EMOJI[f.severity]} {f.severity}",
                f"{f.file}:{f.line}",
                f.title,
                f.confidence,
            )
        console.print(table)
    else:
        console.print("[green]No issues found — clean diff![/green]")

    if result.suppressed:
        console.print(
            f"[dim]✂ {len(result.suppressed)} finding(s) suppressed as likely false positives: "
            + ", ".join(f"{f.file}:{f.line}" for f in result.suppressed)
            + "[/dim]"
        )
    if result.skipped_duplicates:
        console.print(f"[dim]↩ {result.skipped_duplicates} comment(s) already on the PR, not re-posted[/dim]")

    console.print(
        f"\n[dim]tokens — input: {result.input_tokens:,} "
        f"(cached: {result.cached_tokens:,}) · output: {result.output_tokens:,} · "
        f"model: {result.model}[/dim]"
    )
    if post:
        console.print(f"[green]✔ Review posted:[/green] https://github.com/{result.repo}/pull/{result.pr_number}")


@app.command()
def learn(
    repo: str = typer.Argument(help="Repo to learn conventions from: 'owner/repo' or URL."),
):
    """Learn team conventions from merged PR history and save them for future reviews."""
    from .conventions import learn_conventions
    from .github_client import GitHubClient, parse_repo
    from .reviewer import rules_to_json, save_rules

    owner, name = parse_repo(repo)
    with console.status("Learning…") as status, GitHubClient() as gh:
        rules = learn_conventions(
            gh, owner, name,
            on_progress=lambda msg: status.update(f"[cyan]{msg}"),
        )

    path = save_rules(rules_to_json(rules.rules))
    console.print(f"[green]✔ Learned {len(rules.rules)} conventions → {path}[/green]\n")
    for i, r in enumerate(rules.rules, 1):
        console.print(f"[bold]{i}. {r.rule}[/bold]")
        console.print(f"   [dim]evidence: {r.evidence} · violation severity: {r.category}[/dim]")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8000),
):
    """Run the GitHub webhook server (reviews PRs automatically when opened/updated)."""
    import uvicorn

    console.print(f"[cyan]Webhook server on http://{host}:{port}/webhook — "
                  f"point a GitHub webhook (or smee/ngrok tunnel) here.[/cyan]")
    uvicorn.run("copilot.webhook:app", host=host, port=port)


@app.command()
def doctor():
    """Check local config & credentials are ready for a review (no network calls)."""
    from .doctor import overall, run_checks

    checks = run_checks()
    icon = {
        "ok": "[green]✓ ok[/green]",
        "warn": "[yellow]⚠ warn[/yellow]",
        "fail": "[red]✗ fail[/red]",
    }
    table = Table(title="copilot doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for c in checks:
        table.add_row(c.name, icon[c.status], c.detail)
    console.print(table)

    status = overall(checks)
    if status == "fail":
        console.print(
            "\n[red]Not ready[/red] — set the missing keys in .env "
            "(copy .env.example), then re-run [bold]copilot doctor[/bold]."
        )
        raise typer.Exit(code=1)
    if status == "warn":
        console.print("\n[yellow]Ready for `copilot review`[/yellow] — optional items noted above.")
    else:
        console.print("\n[green]All checks passed — ready to go.[/green]")


@app.command()
def history():
    """Show past reviews stored locally."""
    from .storage import list_reviews

    rows = list_reviews()
    if not rows:
        console.print("[dim]No reviews yet.[/dim]")
        return
    table = Table(title="Review history")
    for col in ("when", "PR", "score", "recommendation", "findings", "model"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["created_at"][:16],
            f"{r['repo']}#{r['pr_number']}",
            str(r["quality_score"]),
            r["recommendation"],
            str(r["finding_count"]),
            r["model"],
        )
    console.print(table)


if __name__ == "__main__":
    app()
