from pathlib import Path

import httpx
import typer
import yaml

from agentgenome.config import Settings
from agentgenome.genome import Manifest

app = typer.Typer(no_args_is_help=True)
genome_app = typer.Typer(no_args_is_help=True)
app.add_typer(genome_app, name="genome")


@genome_app.command("validate")
def validate(path: Path) -> None:
    """Validate a local manifest without executing any content."""
    try:
        if path.stat().st_size > 1048576:
            raise ValueError("manifest exceeds 1 MiB")
        manifest = Manifest.model_validate(yaml.safe_load(path.read_text()))
    except Exception as exc:
        typer.echo("Invalid manifest: " + type(exc).__name__, err=True)
        raise typer.Exit(1) from exc
    typer.echo(manifest.digest())


@app.command()
def doctor(url: str = "http://127.0.0.1:8080") -> None:
    """Check actual control-plane readiness."""
    try:
        response = httpx.get(url + "/readyz", timeout=6)
        typer.echo(response.text)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        typer.echo("Readiness failed", err=True)
        raise typer.Exit(1) from exc


@app.command()
def config_check() -> None:
    Settings()
    typer.echo("Configuration valid")
