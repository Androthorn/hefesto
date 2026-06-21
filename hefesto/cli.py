from pathlib import Path
import yaml
import typer
from hefesto.scaffold import CONFIG_YAML, OBJECTIVE_YAML, PROMPT_TXT
from hefesto.schemas.config import HefestoConfig
from hefesto.schemas.core import Objective, Rubric, RubricDimension
from hefesto.llm.factory import create_provider
from hefesto.dataset.generate import GeneratedDataset
from hefesto.dataset.load import LoadedDataset
from hefesto.runner.llm_runner import LLMRunner
from hefesto.grader.llm_judge import LLMJudge
from hefesto.refiner.refiner import Refiner
from hefesto.core.loop import RefineLoop
from hefesto.store.repository import Repository

app = typer.Typer(help="Hefesto — evaluation-first prompt refinement.")


def _load_objective(path: str) -> Objective:
    with open(path) as f:
        return Objective.model_validate(yaml.safe_load(f))


def _rubric_from(objective: Objective) -> Rubric:
    keys = list(objective.weights.keys()) or ["quality"]
    return Rubric(dimensions=[
        RubricDimension(name=k, description=f"quality dimension: {k}", weight=objective.weights.get(k, 1.0))
        for k in keys
    ])


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
    cfg = HefestoConfig.from_yaml(config)
    objective = _load_objective(cfg.objective)
    with open(cfg.prompt, encoding="utf-8") as f:
        seed_prompt = f.read()
    weights = objective.weights or {"quality": 1.0}
    rubric = _rubric_from(objective)

    runner_p = create_provider(cfg.provider_for("runner"))
    judge_p = create_provider(cfg.provider_for("judge"))
    refiner_p = create_provider(cfg.provider_for("refiner"))
    dataset_p = create_provider(cfg.provider_for("dataset"))

    if cfg.dataset.source == "generate":
        source = GeneratedDataset(dataset_p, objective, cfg.dataset.count, cfg.dataset.test_fraction)
    else:
        source = LoadedDataset(cfg.dataset.path, cfg.dataset.test_fraction)
    split = source.provide()

    repo = Repository(cfg.store_path)
    repo.init_db()

    loop = RefineLoop(
        runner=LLMRunner(runner_p),
        grader=LLMJudge(judge_p, rubric),
        refiner=Refiner(refiner_p),
        objective=objective, weights=weights, config=cfg.loop, repo=repo,
    )
    result = loop.run(seed_prompt, split)

    # Persist the champion prompt and its score
    promoted = [h for h in result.history if h.get("promoted")]
    champion_version = promoted[-1]["candidate_version"] if promoted else "v1"
    repo.save_prompt(name="prompt", version=champion_version,
                     prompt_text=result.champion, parent_version=None)
    repo.save_evaluation(prompt_version=champion_version,
                         composite_score=result.champion_score,
                         metrics={}, judge_agreement=None)

    typer.echo(f"Champion score: {result.champion_score:.3f}")
    typer.echo(f"Attempts: {len(result.history)} (promoted: "
               f"{sum(1 for h in result.history if h['promoted'])})")
    typer.echo("--- champion prompt ---")
    typer.echo(result.champion)


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
