"""ADRS Command Line Interface."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hefesto import MODULE_NAME, __version__
from hefesto.core.analyzer import Analyzer
from hefesto.core.differ import Differ
from hefesto.core.evaluator import Evaluator
from hefesto.core.generator import Generator
from hefesto.core.selector import SolutionSelector
from hefesto.llm.factory import create_provider
from hefesto.schemas.config import ADRSConfig, LLMConfig
from hefesto.schemas.evaluation import EvaluationResult, ScoringWeights
from hefesto.schemas.input import (
    AgentPrompt,
    ExperimentRun,
    LogEntry,
    MetricStats,
    Objective,
    PromptTemplate,
    SuccessCriterion,
)
from hefesto.storage.repository import Repository
from hefesto.core.importer import BaseImporter
import importlib.util
import sys
import inspect

app = typer.Typer(
    name=MODULE_NAME.lower(),
    help=f"{MODULE_NAME} - Automated Dynamic Refinement System for LLM prompts",
    add_completion=False,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"{MODULE_NAME} v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """ADRS - Automated Dynamic Refinement System for LLM prompts."""
    pass


@app.command()
def init(
    path: Path = typer.Option(
        Path("."), "--path", "-p",
        help="Path to initialize ADRS project",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing configuration",
    ),
) -> None:
    """Initialize a new ADRS project with configuration and database."""
    config_path = path / "hefesto.yaml"
    db_path = path / "adrs_history.db"
    
    # Check if already initialized
    if config_path.exists() and not force:
        console.print(
            f"[yellow]ADRS already initialized at {path}[/yellow]"
        )
        console.print("Use --force to reinitialize")
        raise typer.Exit(1)
    
    # Create default config
    config = ADRSConfig()
    
    try:
        import yaml
        with open(config_path, "w") as f:
            yaml.dump(config.model_dump(), f, default_flow_style=False)
    except ImportError:
        # Fallback to JSON if yaml not available
        config_path = path / "hefesto.json"
        with open(config_path, "w") as f:
            json.dump(config.model_dump(), f, indent=2)
    
    # Initialize database
    repo = Repository(db_path)
    repo.initialize()
    
    # Create example directories
    (path / "prompts").mkdir(exist_ok=True)
    (path / "runs").mkdir(exist_ok=True)
    (path / "refined_prompts").mkdir(exist_ok=True)
    
    console.print(Panel(
        f"[green]✓ {MODULE_NAME} initialized successfully![/green]\n\n"
        f"Configuration: {config_path}\n"
        f"Database: {db_path}\n\n"
        "Created directories:\n"
        "  • prompts/         - Place your agent prompts here\n"
        "  • runs/            - Place experiment run data here\n"
        "  • refined_prompts/ - Refined prompts will be saved here",
        title=f"{MODULE_NAME} Setup",
    ))


@app.command()
def refine(
    objective: Path = typer.Option(
        ..., "--objective", "-o",
        help="Path to objective JSON file",
    ),
    runs: Path = typer.Option(
        ..., "--runs", "-r",
        help="Path to runs directory or JSON file",
    ),
    prompts: Path = typer.Option(
        ..., "--prompts", "-p",
        help="Path to prompts directory or JSON file",
    ),
    output: Path = typer.Option(
        Path("./refined_prompts"), "--output",
        help="Output directory for refined prompts",
    ),
    provider: str = typer.Option(
        "openrouter", "--provider",
        help="LLM provider (openrouter, openai, anthropic)",
    ),
    model: str = typer.Option(
        "anthropic/claude-sonnet-4-20250514", "--model", "-m",
        help="Model to use for refinement",
    ),
    save_history: bool = typer.Option(
        True, "--save-history/--no-save-history",
        help="Save refinement to history database",
    ),
) -> None:
    """Refine agent prompts based on experiment runs and objective."""
    console.print(f"[bold]{MODULE_NAME} Prompt Refinement[/bold]\n")
    
    # Load objective
    console.print(f"Loading objective from {objective}...")
    objective_data = _load_objective(objective)
    console.print(f"  Goal: [cyan]{objective_data.goal}[/cyan]")
    
    # Load runs
    console.print(f"\nLoading runs from {runs}...")
    runs_data = _load_runs(runs)
    console.print(f"  Loaded [cyan]{len(runs_data)}[/cyan] run(s)")
    
    # Load prompts
    console.print(f"\nLoading prompts from {prompts}...")
    prompts_data = _load_prompts(prompts)
    console.print(f"  Loaded [cyan]{len(prompts_data)}[/cyan] prompt(s)")
    
    # Create LLM provider
    console.print(f"\nInitializing LLM provider: [cyan]{provider}/{model}[/cyan]")
    llm_config = LLMConfig(provider=provider, model=model)
    llm_provider = create_provider(llm_config)
    
    # Create components
    analyzer = Analyzer(priority_metrics=objective_data.priority_metrics)
    generator = Generator(llm_provider)
    differ = Differ()
    
    # Ensure output directory exists
    output.mkdir(parents=True, exist_ok=True)
    
    # Process each agent
    results = []
    for prompt in prompts_data:
        console.print(f"\n[bold]Processing agent: {prompt.agent_name}[/bold]")
        
        # Filter runs for this agent
        agent_runs = [r for r in runs_data if r.agent_name == prompt.agent_name]
        if not agent_runs:
            console.print(f"  [yellow]No runs found for {prompt.agent_name}, skipping[/yellow]")
            continue
        
        console.print(f"  Analyzing {len(agent_runs)} run(s)...")
        
        # Analyze
        analysis = analyzer.analyze(agent_runs, objective_data)
        
        if analysis.key_issues:
            console.print("  Key issues identified:")
            for issue in analysis.key_issues[:3]:
                console.print(f"    • {issue}")
        
        # Generate refined prompt
        console.print("  Generating refined prompt...")
        result = generator.refine(prompt, analysis, objective_data)
        results.append(result)
        
        # Save refined prompt
        output_file = output / f"{prompt.agent_name}.json"
        refined_prompt = AgentPrompt(
            agent_name=result.agent_name,
            version=result.refined_version,
            template=result.refined_template,
            constraints=result.refined_constraints,
        )
        with open(output_file, "w") as f:
            json.dump(refined_prompt.model_dump(), f, indent=2)
        
        console.print(f"  [green]✓ Saved refined prompt to {output_file}[/green]")
        
        # Show diff
        console.print(f"\n  [bold]Changes ({prompt.version} → {result.refined_version}):[/bold]")
        diff_text = differ.format_diff_text(result.diff)
        for line in diff_text.split("\n")[:10]:  # Limit output
            if line.startswith("+"):
                console.print(f"    [green]{line}[/green]")
            elif line.startswith("-"):
                console.print(f"    [red]{line}[/red]")
            else:
                console.print(f"    {line}")
        
        console.print(f"\n  [bold]Reasoning:[/bold]")
        console.print(f"    {result.reasoning[:200]}...")
    
    # Save to history if requested
    if save_history:
        try:
            repo = Repository()
            repo.initialize()
            for result in results:
                run_ids = [r.run_id for r in runs_data if r.agent_name == result.agent_name]
                repo.save_refinement(result, objective_data.goal, run_ids)
            console.print("\n[green]✓ Saved refinement history[/green]")
        except Exception as e:
            console.print(f"\n[yellow]Warning: Could not save history: {e}[/yellow]")
    
    console.print(f"\n[bold green]✓ Refinement complete![/bold green]")
    console.print(f"Refined prompts saved to: {output}")


@app.command()
def history(
    agent: str = typer.Option(
        None, "--agent", "-a",
        help="Filter by agent name",
    ),
    limit: int = typer.Option(
        10, "--limit", "-n",
        help="Maximum number of records to show",
    ),
    db_path: Path = typer.Option(
        Path("./adrs_history.db"), "--db",
        help="Path to history database",
    ),
) -> None:
    """View refinement history."""
    if not db_path.exists():
        console.print("[yellow]No history database found. Run 'hefesto init' first.[/yellow]")
        raise typer.Exit(1)
    
    repo = Repository(db_path)
    
    if agent:
        records = repo.get_refinement_history(agent, limit=limit)
    else:
        # Get all agents and their histories
        records = []
        # For simplicity, we'll need to query all
        console.print("[yellow]Specify --agent to filter by agent name[/yellow]")
        raise typer.Exit(1)
    
    if not records:
        console.print(f"No refinement history found for agent '{agent}'")
        raise typer.Exit(0)
    
    table = Table(title=f"Refinement History: {agent}")
    table.add_column("Date", style="cyan")
    table.add_column("From", style="red")
    table.add_column("To", style="green")
    table.add_column("Goal", style="white", max_width=40)
    
    for record in records:
        table.add_row(
            record["timestamp"][:19],
            record["original_version"],
            record["refined_version"],
            record["objective_goal"][:40] + "..." if len(record["objective_goal"]) > 40 else record["objective_goal"],
        )
    
    console.print(table)


@app.command()
def diff(
    agent: str = typer.Option(
        ..., "--agent", "-a",
        help="Agent name",
    ),
    from_version: str = typer.Option(
        ..., "--from", "-f",
        help="Original version",
    ),
    to_version: str = typer.Option(
        ..., "--to", "-t",
        help="Target version",
    ),
    db_path: Path = typer.Option(
        Path("./adrs_history.db"), "--db",
        help="Path to history database",
    ),
) -> None:
    """Compare two prompt versions."""
    if not db_path.exists():
        console.print("[yellow]No history database found. Run 'hefesto init' first.[/yellow]")
        raise typer.Exit(1)
    
    repo = Repository(db_path)
    
    from_prompt = repo.get_prompt(agent, from_version)
    to_prompt = repo.get_prompt(agent, to_version)
    
    if not from_prompt:
        console.print(f"[red]Version '{from_version}' not found for agent '{agent}'[/red]")
        raise typer.Exit(1)
    
    if not to_prompt:
        console.print(f"[red]Version '{to_version}' not found for agent '{agent}'[/red]")
        raise typer.Exit(1)
    
    differ = Differ()
    diff_result = differ.diff_prompts(from_prompt.template, to_prompt.template)
    diff_text = differ.format_diff_text(diff_result)
    
    console.print(Panel(
        diff_text,
        title=f"Diff: {agent} ({from_version} → {to_version})",
    ))


@app.command(name="import-data")
def import_data(
    importer: Path = typer.Option(
        ..., "--importer", "-i",
        help="Path to python file containing the importer implementation",
    ),
    source: Path = typer.Option(
        ..., "--source", "-s",
        help="Path to the data source (directory or file)",
    ),
    output: Path = typer.Option(
        Path("./runs"), "--output", "-o",
        help="Directory to save imported runs as JSON",
    ),
    class_name: str = typer.Option(
        None, "--class", "-c",
        help="Name of the importer class (optional, detects automatically)",
    ),
    pattern: str = typer.Option(
        None, "--pattern", "-p",
        help="Optional glob pattern to filter runs (e.g., 'google-gemini*0.5*')",
    ),
    prompt_file: Path = typer.Option(
        None, "--prompt-file",
        help="Optional path to prompt text file to import alongside runs",
    ),
    prompt_output: Path = typer.Option(
        None, "--prompt-output",
        help="Directory to save imported prompt (defaults to output/prompts)",
    ),
) -> None:
    """Import experiment runs using a custom importer script."""
    if not importer.exists():
        console.print(f"[red]Importer file not found: {importer}[/red]")
        raise typer.Exit(1)
        
    if not source.exists():
        console.print(f"[red]Source path not found: {source}[/red]")
        raise typer.Exit(1)
        
    # Dynamically load the importer module
    try:
        spec = importlib.util.spec_from_file_location("custom_importer", importer)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec from {importer}")
            
        module = importlib.util.module_from_spec(spec)
        sys.modules["custom_importer"] = module
        spec.loader.exec_module(module)
        
        # Find the importer class
        importer_cls = None
        if class_name:
            if hasattr(module, class_name):
                importer_cls = getattr(module, class_name)
            else:
                console.print(f"[red]Class '{class_name}' not found in {importer}[/red]")
                raise typer.Exit(1)
        else:
            # Auto-detect subclass of BaseImporter
            for name, obj in inspect.getmembers(module):
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, BaseImporter)
                    and obj is not BaseImporter
                    and obj.__module__ == "custom_importer"
                ):
                    importer_cls = obj
                    break
        
        if not importer_cls:
            console.print("[red]No subclass of BaseImporter found in file[/red]")
            raise typer.Exit(1)
            
        # Instantiate and run
        console.print(f"Using importer: [cyan]{importer_cls.__name__}[/cyan]")
        instance = importer_cls()
        
        # Build kwargs for the importer
        kwargs = {}
        if pattern:
            kwargs['pattern'] = pattern
            console.print(f"Filtering with pattern: [cyan]{pattern}[/cyan]")
        if prompt_file:
            kwargs['prompt_file'] = prompt_file
            kwargs['prompt_output'] = prompt_output or (output.parent / "prompts")
            console.print(f"Will import prompt from: [cyan]{prompt_file}[/cyan]")
        
        console.print(f"Importing from: {source}...")
        runs = instance.import_runs(source, **kwargs)
        
        if not runs:
            console.print("[yellow]No runs imported.[/yellow]")
            return
            
        # Save results
        output.mkdir(parents=True, exist_ok=True)
        count = 0
        for run in runs:
            # Sanitize filename
            if run.run_id.startswith(run.agent_name):
                filename = f"{run.run_id}.json".replace("/", "_")
            else:
                filename = f"{run.agent_name}_{run.run_id}.json".replace("/", "_")
            
            out_file = output / filename
            
            with open(out_file, "w") as f:
                json.dump(run.model_dump(), f, indent=2, default=str)
            count += 1
            
        console.print(f"[green]✓ Successfully imported {count} runs to {output}[/green]")
        
    except Exception as e:
        console.print(f"[red]Import failed: {e}[/red]")
        # print stack trace for debugging
        import traceback
        traceback.print_exc()
        raise typer.Exit(1)


@app.command(name="import-prompt")
def import_prompt(
    file: Path = typer.Option(
        ..., "--file", "-f",
        help="Path to plain text prompt file",
    ),
    agent: str = typer.Option(
        ..., "--agent", "-a",
        help="Agent name",
    ),
    version: str = typer.Option(
        ..., "--version", "-v",
        help="Prompt version (e.g. v1.0)",
    ),
    output: Path = typer.Option(
        Path("./prompts"), "--output", "-o",
        help="Output directory for generic prompt JSON",
    ),
    constraints: list[str] = typer.Option(
        [], "--constraint", "-c",
        help="Add a constraint (can be used multiple times)",
    ),
) -> None:
    """Import a plain text file as an ADRS prompt."""
    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)
        
    try:
        content = file.read_text()
        
        # Create prompt object
        prompt = AgentPrompt(
            agent_name=agent,
            version=version,
            template=PromptTemplate(
                system="", # Text files usually don't verify system vs user, assume user
                user=content,
                variables=[], # Variables need manual extraction or specification in text
            ),
            constraints=constraints,
        )
        
        output.mkdir(parents=True, exist_ok=True)
        out_file = output / f"{agent}.json"
        
        with open(out_file, "w") as f:
            json.dump(prompt.model_dump(), f, indent=2)
            
        console.print(f"[green]✓ Converted {file} to {out_file}[/green]")
        
    except Exception as e:
        console.print(f"[red]Failed to import prompt: {e}[/red]")
        raise typer.Exit(1)

@app.command(name="evaluate-and-refine")
def evaluate_and_refine(
    analyzer_output: Optional[Path] = typer.Option(
        None, "--analyzer-output", "-a",
        help="Path to the analyzer output directory for a single run",
    ),
    csv_path: Optional[Path] = typer.Option(
        None, "--csv", "-c",
        help="Path to combined_summaries.csv for multi-run aggregation",
    ),
    min_run: Optional[int] = typer.Option(
        None, "--min-run",
        help="Only include runs with run_number >= this value (CSV mode)",
    ),
    max_run: Optional[int] = typer.Option(
        None, "--max-run",
        help="Only include runs with run_number <= this value (CSV mode)",
    ),
    runs: Optional[str] = typer.Option(
        None, "--runs",
        help="Comma-separated list of specific run numbers to include (CSV mode). "
             "Overrides --min-run/--max-run when provided. E.g. --runs 5,29,31",
    ),
    filter_model: Optional[str] = typer.Option(
        None, "--filter-model",
        help="Only include runs matching this model name (CSV mode, substring match)",
    ),
    filter_threshold: Optional[str] = typer.Option(
        None, "--filter-threshold",
        help="Only include runs with this threshold/temperature value (CSV mode)",
    ),
    simulator_path: Path = typer.Option(
        ..., "--simulator-path", "-s",
        help="Path to the simulator project root",
    ),
    objective: Path = typer.Option(
        ..., "--objective", "-o",
        help="Path to objective JSON file",
    ),
    prompt_file: str = typer.Option(
        "consolidator_agent.txt", "--prompt-file",
        help="Name of the prompt file to refine (in ai-engine/prompts/)",
    ),
    provider: str = typer.Option(
        "openrouter", "--provider",
        help="LLM provider (openrouter, openai, anthropic)",
    ),
    model: str = typer.Option(
        "google/gemini-3.1-pro-preview", "--model", "-m",
        help="Model to use for refinement",
    ),
    deploy: bool = typer.Option(
        True, "--deploy/--no-deploy",
        help="Deploy the refined prompt to the simulator",
    ),
    db_path: Path = typer.Option(
        Path("./adrs_history.db"), "--db",
        help="Path to history database",
    ),
) -> None:
    """Evaluate a simulation run and refine the prompt.

    This is the core ADRS command for the iterative refinement workflow.
    It performs a single evaluate-and-refine cycle:

    1. Collects metrics from the analyzer output (single run or aggregated from CSV)
    2. Scores the simulation run
    3. Selects past solutions for context
    4. Refines the prompt using an LLM
    5. Optionally deploys the new prompt to the simulator
    6. Saves everything to storage

    Use --csv with --min-run/--max-run/--filter-model to aggregate metrics
    across multiple runs for more robust refinement.
    """
    console.print(f"[bold]{MODULE_NAME} Evaluate & Refine[/bold]\n")

    # --- Validate inputs ---
    if not csv_path and not analyzer_output:
        console.print("[red]Provide either --analyzer-output or --csv[/red]")
        raise typer.Exit(1)

    if not simulator_path.exists():
        console.print(f"[red]Simulator path not found: {simulator_path}[/red]")
        raise typer.Exit(1)

    # --- Initialize components ---
    evaluator = Evaluator()
    repo = Repository(db_path)
    repo.initialize()

    iteration = repo.get_iteration_count("consolidator_agent") + 1
    console.print(f"Iteration: [cyan]{iteration}[/cyan]")

    # --- Step 1: Collect metrics ---
    if csv_path:
        # Multi-run aggregation from CSV
        console.print(f"\n[bold]Step 1:[/bold] Aggregating metrics from {csv_path}...")
        if not csv_path.exists():
            console.print(f"[red]CSV file not found: {csv_path}[/red]")
            raise typer.Exit(1)

        import csv as csv_mod
        from collections import defaultdict

        # Parse --runs into a set for O(1) lookup
        runs_set: set[int] | None = None
        if runs:
            try:
                runs_set = {int(r.strip()) for r in runs.split(",") if r.strip()}
            except ValueError:
                console.print("[red]--runs must be a comma-separated list of integers (e.g. --runs 5,29,31)[/red]")
                raise typer.Exit(1)

        # Collect per-run metrics
        run_metrics: dict[tuple, dict[str, float]] = defaultdict(dict)
        with open(csv_path, newline="") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                m = row.get("model", "").strip()
                t = row.get("threshold", "").strip()
                r = row.get("run_number", "").strip()
                metric = row.get("metric", "").strip()
                if not all([m, t, r, metric]):
                    continue
                try:
                    run_num = int(r)
                except ValueError:
                    continue
                # --runs takes priority over min/max range
                if runs_set is not None:
                    if run_num not in runs_set:
                        continue
                else:
                    if min_run is not None and run_num < min_run:
                        continue
                    if max_run is not None and run_num > max_run:
                        continue
                if filter_model and filter_model.lower() not in m.lower():
                    continue
                if filter_threshold and t != filter_threshold:
                    continue
                try:
                    run_metrics[(m, t, run_num)][metric] = float(row["mean"])
                except (ValueError, KeyError):
                    continue

        if not run_metrics:
            console.print("[yellow]No matching runs found in CSV.[/yellow]")
            raise typer.Exit(1)

        n_runs = len(run_metrics)
        console.print(f"  Found [cyan]{n_runs}[/cyan] matching runs")

        # Aggregate: compute mean of means, min of mins, max of maxes, std across runs
        all_metric_names: set[str] = set()
        for rm in run_metrics.values():
            all_metric_names.update(rm.keys())

        metrics: dict[str, MetricStats] = {}
        for metric_name in all_metric_names:
            values = [rm[metric_name] for rm in run_metrics.values()
                      if metric_name in rm]
            if not values:
                continue
            n = len(values)
            mean_val = sum(values) / n
            min_val = min(values)
            max_val = max(values)
            if n > 1:
                std_val = (sum((v - mean_val) ** 2 for v in values) / (n - 1)) ** 0.5
            else:
                std_val = 0.0
            median_val = sorted(values)[n // 2]

            metrics[metric_name] = MetricStats(
                mean=mean_val, min=min_val, max=max_val,
                std=std_val, median=median_val,
            )

        console.print(f"  Aggregated [cyan]{len(metrics)}[/cyan] metrics across "
                      f"[cyan]{n_runs}[/cyan] runs\n")
    else:
        # Single directory mode
        if not analyzer_output.exists():
            console.print(f"[red]Analyzer output not found: {analyzer_output}[/red]")
            raise typer.Exit(1)

        console.print(f"\n[bold]Step 1:[/bold] Collecting metrics from {analyzer_output}...")
        try:
            metrics = evaluator.collect_metrics(analyzer_output)
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Failed to collect metrics: {e}[/red]")
            raise typer.Exit(1)

    metrics_table = Table(title="Simulation Metrics")
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Mean", style="white")
    metrics_table.add_column("Std", style="yellow")
    metrics_table.add_column("Min", style="green")
    metrics_table.add_column("Max", style="red")
    for name, stats in metrics.items():
        metrics_table.add_row(
            name,
            f"{stats.mean:.4f}",
            f"{stats.std:.4f}",
            f"{stats.min:.4f}",
            f"{stats.max:.4f}",
        )
    console.print(metrics_table)

    # --- Step 2: Score ---
    console.print(f"\n[bold]Step 2:[/bold] Scoring simulation run...")
    objective_data = _load_objective(objective)
    scoring = evaluator.score(metrics, objective_data)

    score_table = Table(title="Scoring Breakdown")
    score_table.add_column("Metric", style="cyan")
    score_table.add_column("Value", style="white")
    score_table.add_column("Baseline", style="yellow")
    score_table.add_column("Score", style="green")
    score_table.add_column("Weight", style="blue")
    score_table.add_column("Weighted", style="magenta")
    for ms in scoring.metric_scores:
        score_table.add_row(
            ms.metric_name,
            f"{ms.raw_value:.4f}",
            f"{ms.baseline_value:.4f}",
            f"{ms.normalized_score:.4f}",
            f"{ms.weight:.4f}",
            f"{ms.weighted_score:.4f}",
        )
    console.print(score_table)

    if scoring.overload_detected:
        console.print(
            f"  [yellow]⚠ Cluster overload detected! "
            f"Penalty applied: -{scoring.overload_penalty_applied:.4f}[/yellow]"
        )

    console.print(
        f"  [bold]Composite Score: "
        f"{'[green]' if scoring.composite_score > 0.5 else '[yellow]'}"
        f"{scoring.composite_score:.4f}[/]\n"
    )

    # --- Step 3: Read current prompt ---
    console.print(f"[bold]Step 3:[/bold] Reading current prompt...")
    try:
        current_prompt_text = evaluator.read_current_prompt(simulator_path, prompt_file)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    agent_name = prompt_file.replace(".txt", "")

    # Derive current version from the prompt filename (e.g. consolidator_agent_v2 → v2)
    import re
    version_match = re.search(r"_v(\d+)$", agent_name)
    if version_match:
        current_version_num = int(version_match.group(1))
        prompt_version = f"v{current_version_num}"
        next_version = f"v{current_version_num + 1}"
        # Use the base agent name (without version suffix) for consistent tracking
        base_agent_name = agent_name[:version_match.start()]
    else:
        prompt_version = f"v{iteration}"
        next_version = f"v{iteration + 1}"
        base_agent_name = agent_name

    # Wrap the plain-text prompt into an AgentPrompt for the Generator
    agent_prompt = AgentPrompt(
        agent_name=agent_name,
        version=prompt_version,
        template=PromptTemplate(
            system="",
            user=current_prompt_text,
            variables=[],
        ),
        constraints=[],
    )

    # --- Step 4: Select past solutions for context ---
    console.print(f"[bold]Step 4:[/bold] Selecting past solutions for context...")
    selector = SolutionSelector(repo)
    past_evals = selector.select_for_refinement(agent_name)
    past_context = selector.format_for_prompt(past_evals) if past_evals else None

    if past_evals:
        console.print(f"  Including [cyan]{len(past_evals)}[/cyan] past solution(s) for context")
        for pe in past_evals:
            console.print(
                f"    • Iteration {pe.get('iteration', '?')} "
                f"(score: {pe.get('composite_score', '?')})"
            )
    else:
        console.print("  [dim]No past evaluations available (first iteration)[/dim]")

    # --- Step 5: Build analysis from current metrics ---
    console.print(f"\n[bold]Step 5:[/bold] Generating refined prompt via LLM...")

    # Build a synthetic analysis from the evaluation metrics
    analyzer = Analyzer(priority_metrics=objective_data.priority_metrics)
    # Create a minimal ExperimentRun for the analyzer
    from hefesto.schemas.input import ExperimentRun as ER
    synth_run = ER(
        run_id=f"eval_iter_{iteration}",
        timestamp=datetime.now(),
        prompt_version=prompt_version,
        agent_name=agent_name,
        metrics=metrics,
        logs=[],
    )
    analysis = analyzer.analyze([synth_run], objective_data)

    # Create LLM provider and generator
    llm_config = LLMConfig(provider=provider, model=model)
    llm_provider = create_provider(llm_config)
    generator = Generator(llm_provider)

    result = generator.refine(
        agent_prompt, analysis, objective_data,
        past_evaluations_context=past_context,
    )

    console.print(f"  [green]✓ Refinement generated[/green]")
    console.print(f"  Version: {result.original_version} → {result.refined_version}")
    console.print(f"\n  [bold]Reasoning:[/bold]")
    console.print(f"  {result.reasoning[:300]}{'...' if len(result.reasoning) > 300 else ''}")

    # --- Step 6: Deploy the refined prompt ---
    # Extract the refined prompt text (use the user field since these are plain-text prompts)
    refined_prompt_text = result.refined_template.user

    if deploy:
        console.print(f"\n[bold]Step 6:[/bold] Deploying refined prompt to simulator...")
        deployed_path = evaluator.deploy_prompt(
            refined_prompt_text, simulator_path, prompt_file
        )
        console.print(f"  [green]✓ Deployed to {deployed_path}[/green]")
        console.print(f"  [dim]Backup saved as {prompt_file}.backup[/dim]")
    else:
        console.print(f"\n[bold]Step 6:[/bold] [dim]Skipping deployment (--no-deploy)[/dim]")

    # --- Step 7: Save evaluation to storage ---
    console.print(f"\n[bold]Step 7:[/bold] Saving evaluation to storage...")
    evaluation = EvaluationResult(
        iteration=iteration,
        agent_name=agent_name,
        prompt_version=prompt_version,
        prompt_text=current_prompt_text,
        metrics=metrics,
        scoring=scoring,
        reasoning=result.reasoning,
        suggestions=result.suggestions,
        analyzer_output_dir=str(analyzer_output),
    )
    repo.save_evaluation(evaluation)

    # Save the refined prompt for review
    refined_prompt = AgentPrompt(
        agent_name=agent_name,
        version=result.refined_version,
        template=result.refined_template,
        constraints=result.refined_constraints,
    )
    repo.save_prompt(refined_prompt)

    # Save the refinement record (links original → refined, with reasoning)
    repo.save_refinement(
        result,
        objective_goal=objective_data.goal,
        analyzed_run_ids=[f"eval_iter_{iteration}"],
    )

    console.print(f"  [green]✓ Saved evaluation (iteration {iteration})[/green]")
    console.print(f"  [green]✓ Saved refined prompt {result.refined_version}[/green]")

    # --- Summary ---
    console.print(Panel(
        f"[bold green]✓ Evaluate & Refine complete![/bold green]\n\n"
        f"Iteration:        {iteration}\n"
        f"Composite Score:  {scoring.composite_score:.4f}\n"
        f"Prompt Version:   {prompt_version} → {result.refined_version}\n"
        f"Deployed:         {'Yes' if deploy else 'No'}\n"
        f"Suggestions:      {len(result.suggestions)}",
        title=f"{MODULE_NAME} Summary",
    ))


@app.command(name="score-runs")
def score_runs(
    csv_path: Path = typer.Option(
        ..., "--csv", "-c",
        help="Path to combined_summaries.csv from the simulator analyzer",
    ),
    objective: Optional[Path] = typer.Option(
        None, "--objective", "-o",
        help="Path to objective JSON file (optional, for context)",
    ),
    sort_by_score: bool = typer.Option(
        False, "--sort", "-s",
        help="Sort output by composite score (descending)",
    ),
    min_run: Optional[int] = typer.Option(
        None, "--min-run",
        help="Only include runs with run_number >= this value",
    ),
    max_run: Optional[int] = typer.Option(
        None, "--max-run",
        help="Only include runs with run_number <= this value",
    ),
    runs: Optional[str] = typer.Option(
        None, "--runs",
        help="Comma-separated list of specific run numbers to include. "
             "Overrides --min-run/--max-run when provided. E.g. --runs 5,29,31",
    ),
    model_filter: Optional[str] = typer.Option(
        None, "--model", "-m",
        help="Only include runs matching this model name (substring match)",
    ),
    threshold_filter: Optional[str] = typer.Option(
        None, "--threshold", "-t",
        help="Only include runs matching this threshold/temperature value (exact match, e.g. 0.1)",
    ),
) -> None:
    """Score all experiment runs from a combined summaries CSV.

    Reads the analyzer's combined_summaries.csv, groups rows by
    (model, threshold, run_number), scores each run using the ADRS
    scoring model, and outputs per-run scores and per-agent summaries.
    """
    console.print(f"[bold]{MODULE_NAME} Batch Scoring[/bold]\n")

    if not csv_path.exists():
        console.print(f"[red]CSV file not found: {csv_path}[/red]")
        raise typer.Exit(1)

    # Load objective if provided
    objective_data = None
    if objective and objective.exists():
        objective_data = _load_objective(objective)
        console.print(f"Objective: [cyan]{objective_data.goal}[/cyan]\n")

    # Parse the combined CSV
    import csv as csv_mod
    from collections import defaultdict

    # Group: (model, threshold, run_number) -> {metric_name: MetricStats}
    RunKey = tuple  # (model, threshold, run_number)
    grouped: dict[RunKey, dict[str, MetricStats]] = defaultdict(dict)

    # Parse --runs into a set for O(1) lookup
    runs_set: set[int] | None = None
    if runs:
        try:
            runs_set = {int(r.strip()) for r in runs.split(",") if r.strip()}
        except ValueError:
            console.print("[red]--runs must be a comma-separated list of integers (e.g. --runs 5,29,31)[/red]")
            raise typer.Exit(1)

    with open(csv_path, newline="") as f:
        reader = csv_mod.DictReader(f)
        for row in reader:
            model = row.get("model", "").strip()
            threshold = row.get("threshold", "").strip()
            run_number = row.get("run_number", "").strip()
            metric = row.get("metric", "").strip()

            if not all([model, threshold, run_number, metric]):
                continue

            # Apply filters
            try:
                run_num_int = int(run_number)
            except ValueError:
                continue
            # --runs takes priority over min/max range
            if runs_set is not None:
                if run_num_int not in runs_set:
                    continue
            else:
                if min_run is not None and run_num_int < min_run:
                    continue
                if max_run is not None and run_num_int > max_run:
                    continue
            if model_filter and model_filter.lower() not in model.lower():
                continue
            if threshold_filter and threshold != threshold_filter.strip():
                continue

            try:
                mean_val = float(row["mean"])
                min_val = float(row["min"])
                max_val = float(row["max"])
                std_str = row.get("std", "").strip()
                std_val = float(std_str) if std_str else 0.0
                median_val = float(row["median"])
            except (ValueError, KeyError):
                continue

            key = (model, threshold, run_number)
            grouped[key][metric] = MetricStats(
                mean=mean_val,
                min=min_val,
                max=max_val,
                std=std_val,
                median=median_val,
            )

    if not grouped:
        console.print("[yellow]No valid run data found in CSV.[/yellow]")
        raise typer.Exit(1)

    console.print(f"Parsed [cyan]{len(grouped)}[/cyan] runs from CSV\n")

    # Score each run
    evaluator = Evaluator()

    scored_runs: list[dict] = []
    for (model, threshold, run_num), metrics in grouped.items():
        scoring = evaluator.score(metrics, objective_data)
        scored_runs.append({
            "model": model,
            "threshold": threshold,
            "run": run_num,
            "composite": scoring.composite_score,
            "overload": scoring.overload_detected,
            "penalty": scoring.overload_penalty_applied,
            "metric_scores": {
                ms.metric_name: ms.normalized_score
                for ms in scoring.metric_scores
            },
        })

    # Sort
    if sort_by_score:
        scored_runs.sort(key=lambda r: r["composite"], reverse=True)
    else:
        scored_runs.sort(key=lambda r: (r["model"], r["threshold"], int(r["run"])))

    # Build per-run table
    run_table = Table(title="Per-Run Scores")
    run_table.add_column("Model", style="cyan", no_wrap=True)
    run_table.add_column("Temp", style="blue")
    run_table.add_column("Run", style="white")
    run_table.add_column("Composite", style="bold green")
    run_table.add_column("pending_pods", style="white")
    run_table.add_column("time_w_pending", style="white")
    run_table.add_column("cost", style="white")
    run_table.add_column("migrations", style="white")
    run_table.add_column("Overload", style="yellow")

    for r in scored_runs:
        ms = r["metric_scores"]
        run_table.add_row(
            r["model"],
            r["threshold"],
            r["run"],
            f"{r['composite']:.4f}",
            f"{ms.get('pending_pods', 0):.4f}",
            f"{ms.get('time_with_pending', 0):.4f}",
            f"{ms.get('cost', 0):.4f}",
            f"{ms.get('number_of_migrations', 0):.4f}",
            "⚠" if r["overload"] else "✓",
        )

    console.print(run_table)

    # Build per-agent summary
    from collections import defaultdict as dd
    agent_scores: dict[str, list[float]] = dd(list)
    for r in scored_runs:
        agent_key = f"{r['model']} (t={r['threshold']})"
        agent_scores[agent_key].append(r["composite"])

    summary_table = Table(title="\nPer-Agent Summary")
    summary_table.add_column("Agent", style="cyan", no_wrap=True)
    summary_table.add_column("Runs", style="white")
    summary_table.add_column("Mean Score", style="bold green")
    summary_table.add_column("Std", style="yellow")
    summary_table.add_column("Min", style="red")
    summary_table.add_column("Max", style="green")

    summary_items = []
    for agent_key, scores in agent_scores.items():
        n = len(scores)
        mean = sum(scores) / n
        if n > 1:
            var = sum((s - mean) ** 2 for s in scores) / (n - 1)
            std = var ** 0.5
        else:
            std = 0.0
        summary_items.append({
            "agent": agent_key,
            "n": n,
            "mean": mean,
            "std": std,
            "min": min(scores),
            "max": max(scores),
        })

    # Sort summaries by mean score descending
    summary_items.sort(key=lambda x: x["mean"], reverse=True)

    for item in summary_items:
        summary_table.add_row(
            item["agent"],
            str(item["n"]),
            f"{item['mean']:.4f}",
            f"{item['std']:.4f}",
            f"{item['min']:.4f}",
            f"{item['max']:.4f}",
        )

    console.print(summary_table)

    console.print(f"\n[bold green]✓ Scored {len(scored_runs)} runs across "
                  f"{len(agent_scores)} agent configurations[/bold green]")


# =============================================================================
# Helper Functions
# =============================================================================

def _load_objective(path: Path) -> Objective:
    """Load objective from JSON file."""
    with open(path) as f:
        data = json.load(f)
    
    # Convert success criteria if present
    if "success_criteria" in data and data["success_criteria"]:
        criteria = []
        for c in data["success_criteria"]:
            if isinstance(c, str):
                # Parse string format like "std(cost) < 0.005"
                # For now, skip string parsing
                continue
            else:
                criteria.append(SuccessCriterion(**c))
        data["success_criteria"] = criteria
    
    return Objective(**data)


def _load_runs(path: Path) -> list[ExperimentRun]:
    """Load experiment runs from directory or file."""
    runs = []
    
    if path.is_file():
        files = [path]
    else:
        files = list(path.glob("*.json"))
    
    for file in files:
        with open(file) as f:
            data = json.load(f)
        
        # Handle list of runs or single run
        if isinstance(data, list):
            for item in data:
                runs.append(_parse_run(item))
        else:
            runs.append(_parse_run(data))
    
    return runs


def _parse_run(data: dict) -> ExperimentRun:
    """Parse a run dictionary into ExperimentRun."""
    # Convert metrics
    metrics = {}
    for name, stats in data.get("metrics", {}).items():
        metrics[name] = MetricStats(**stats)
    
    # Convert logs
    logs = []
    for log in data.get("logs", []):
        logs.append(LogEntry(**log))
    
    # Parse timestamp
    timestamp = data.get("timestamp")
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    elif timestamp is None:
        timestamp = datetime.now()
    
    return ExperimentRun(
        run_id=data["run_id"],
        timestamp=timestamp,
        prompt_version=data["prompt_version"],
        agent_name=data["agent_name"],
        metrics=metrics,
        logs=logs,
        metadata=data.get("metadata"),
    )


def _load_prompts(path: Path) -> list[AgentPrompt]:
    """Load prompts from directory or file."""
    prompts = []
    
    if path.is_file():
        files = [path]
    else:
        files = list(path.glob("*.json"))
    
    for file in files:
        with open(file) as f:
            data = json.load(f)
        
        # Handle list of prompts or single prompt
        if isinstance(data, list):
            for item in data:
                prompts.append(_parse_prompt(item))
        else:
            prompts.append(_parse_prompt(data))
    
    return prompts


def _parse_prompt(data: dict) -> AgentPrompt:
    """Parse a prompt dictionary into AgentPrompt."""
    template = PromptTemplate(**data["template"])
    
    return AgentPrompt(
        agent_name=data["agent_name"],
        version=data.get("version", "v1.0"),
        template=template,
        constraints=data.get("constraints", []),
        metadata=data.get("metadata"),
    )


if __name__ == "__main__":
    app()
