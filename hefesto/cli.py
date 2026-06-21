from pathlib import Path
import typer
from hefesto.scaffold import CONFIG_YAML, OBJECTIVE_YAML, PROMPT_TXT

app = typer.Typer(help="Hefesto — evaluation-first prompt refinement.")


@app.command()
def init(path: str = typer.Option(".", "--path", help="Target directory")):
    """Scaffold hefesto.yaml, objective.yaml, prompt.txt."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    (target / "hefesto.yaml").write_text(CONFIG_YAML)
    (target / "objective.yaml").write_text(OBJECTIVE_YAML)
    (target / "prompt.txt").write_text(PROMPT_TXT)
    typer.echo(f"Scaffolded Hefesto project in {target}")


@app.command()
def refine(config: str = typer.Option("hefesto.yaml", "--config")):
    """Run the refinement loop (intake -> STEP 0 -> champion/challenger)."""
    typer.echo("refine: wire HefestoConfig -> RefineLoop here")  # see Step 4


@app.command()
def calibrate(config: str = typer.Option("hefesto.yaml", "--config")):
    """Report judge agreement against the reference set."""
    typer.echo("calibrate: not yet wired")


@app.command()
def eval(config: str = typer.Option("hefesto.yaml", "--config")):
    """Score the current prompt without refining."""
    typer.echo("eval: not yet wired")


@app.command("gen-dataset")
def gen_dataset(config: str = typer.Option("hefesto.yaml", "--config")):
    """Generate eval cases from the objective."""
    typer.echo("gen-dataset: not yet wired")


@app.command()
def history(config: str = typer.Option("hefesto.yaml", "--config")):
    """List versions and scores, including rejected attempts."""
    typer.echo("history: not yet wired")


@app.command()
def diff(
    from_version: str = typer.Option(..., "--from"),
    to_version: str = typer.Option(..., "--to"),
):
    """Full-text diff between two prompt versions."""
    typer.echo("diff: not yet wired")


if __name__ == "__main__":
    app()
