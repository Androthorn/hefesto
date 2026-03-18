# ADRS — Automated Dynamic Refinement System

## Agent Guide

> **Audience**: LLM agents and developers working with this codebase.
> This guide explains the architecture, component responsibilities, data flow, and how to operate the system.

---

## Overview

ADRS is a **prompt refinement loop** that iteratively improves LLM agent prompts based on simulation results. It currently targets the **consolidator_agent** in the companion [simulator](../simulator/) project — a Kubernetes workload placement agent that decides whether to keep workloads on a private cluster or migrate them to the public cloud.

### The Core Loop

```
┌──────────────────────────────────────────────────────────────────┐
│  1. Run simulator with current prompt (vN)                      │
│  2. adrs evaluate-and-refine  →  scores vN, generates v(N+1)   │
│  3. Review v(N+1) prompt text                                   │
│  4. Deploy v(N+1) to the simulator                              │
│  5. Repeat from step 1                                          │
└──────────────────────────────────────────────────────────────────┘
```

The loop is **manually driven** — the user decides when to run each iteration, reviews the refined prompt before deployment, and controls the number of iterations.

---

## Project Structure

```
adrs/
├── adrs/
│   ├── cli.py              # Typer CLI — all user-facing commands
│   ├── core/
│   │   ├── analyzer.py      # Parses experiment runs into statistical analysis
│   │   ├── evaluator.py     # Collects metrics from CSVs, scores them, deploys prompts
│   │   ├── generator.py     # Builds refinement prompts, calls LLM, parses JSON response
│   │   ├── selector.py      # Selects past evaluations for context (best/worst/recent)
│   │   ├── differ.py        # Computes diffs between prompt versions
│   │   └── importer.py      # Imports experiment data
│   ├── llm/
│   │   ├── base.py          # LLMProvider abstract class + LLMMessage/LLMResponse
│   │   └── openrouter.py    # OpenRouter API implementation
│   ├── schemas/
│   │   ├── input.py          # AgentPrompt, ExperimentRun, Objective, MetricStats, etc.
│   │   ├── output.py         # RefinementResult, PromptDiff
│   │   └── evaluation.py     # ScoringWeights, ScoringResult, EvaluationResult
│   └── storage/
│       ├── models.py         # SQLAlchemy ORM models (prompts, evaluations, runs, refinements)
│       └── repository.py     # CRUD operations for all DB tables
├── test_run/
│   └── runs/                 # Imported test data (10 JSON files from simulator runs)
├── .env                      # OPENROUTER_API_KEY (required)
├── adrs.yaml                 # Default ADRS configuration
└── pyproject.toml            # Python project metadata
```

---

## Key Components

### 1. Evaluator (`core/evaluator.py`)

**Responsibility**: Collect metrics from simulator output and score them.

- `collect_metrics(analyzer_output_dir)` — Parses the analyzer's `summary_*.csv` file into a `dict[str, MetricStats]`.
- `score(metrics, objective)` — Applies a weighted scoring model to produce a composite score (0–1). Uses target-based normalization: `s_i = max(0, 1 - v_i / b_i)`.
- `deploy_prompt(text, simulator_path, prompt_file)` — Writes the refined prompt to the simulator's prompts directory, backing up the original.

**Scoring Weights** (configurable via `ScoringWeights`):
| Metric | Weight | Baseline |
|--------|--------|----------|
| `pending_pods` | 0.35 | 100.0 |
| `time_with_pending` | 0.25 | 1.0 |
| `cost` | 0.25 | 0.0776 |
| `number_of_migrations` | 0.15 | 200.0 |
| Overload penalty (>80% CPU/MEM) | 0.00 (disabled) | — |

> **Note**: The overload penalty is disabled by default because the current experiment scenario allocates all workloads to the `member1` cluster, causing every run to exceed 80% CPU/MEM usage. The penalty was acting as a constant bias rather than a meaningful differentiator. Set `overload_penalty` to a non-zero value in `ScoringWeights` to re-enable.

### 2. Generator (`core/generator.py`)

**Responsibility**: Refine prompts using an LLM.

- Takes the current prompt, analysis results, objective, and optionally past evaluations.
- Constructs a system prompt (`REFINEMENT_SYSTEM_PROMPT`) + user refinement request.
- Calls the LLM via `OpenRouterProvider`.
- Parses the JSON response using balanced-brace extraction (handles markdown code blocks in string values) + repair (handles literal newlines from Gemini).

**Critical constraint**: The refinement prompt explicitly tells the LLM:
> "The agent's output format (JSON schema, field names, value types) is consumed by an automated system and MUST remain EXACTLY the same."

This protects the consolidator's `{"decisions": [...], "explanations": [...]}` output schema.

### 3. Selector (`core/selector.py`)

**Responsibility**: Select past evaluations for context-aware refinement.

- `select(evaluations, strategy, top_k)` — Returns the most relevant past evaluations.
- Strategies: `best` (highest scores), `worst` (lowest), `recent` (most recent), `diverse` (mix).
- Formats selected evaluations into text context for the LLM prompt.

### 4. Analyzer (`core/analyzer.py`)

**Responsibility**: Statistical analysis of experiment runs.

- Computes per-metric means, standard deviations, coefficient of variation.
- Identifies high-variance metrics and trends across runs.
- Produces an `AnalysisResult` with a human-readable summary.

### 5. Storage (`storage/`)

**SQLite database** with 4 tables:
- `prompts` — Version-controlled prompt texts (system + user fields).
- `evaluations` — Scores, metrics, reasoning, and suggestions per iteration.
- `refinements` — Links original → refined prompts with reasoning and diff.
- `runs` — Raw experiment run data.

Access via `Repository` class with methods like `save_evaluation()`, `save_prompt()`, `save_refinement()`, `get_evaluations()`, etc.

---

## CLI Commands

### `evaluate-and-refine` (primary command)

Runs one iteration of the ADRS loop:

```bash
cd ~/Área\ de\ Trabalho/Projetos/adrs && \
set -a && source .env && set +a && \
.venv/bin/python -m adrs.cli evaluate-and-refine \
  --analyzer-output <path-to-analyzer-csv-dir> \
  --simulator-path ~/Área\ de\ Trabalho/Projetos/simulator \
  --objective ~/Área\ de\ Trabalho/Projetos/simulator/adrs_objective.json \
  --prompt-file consolidator_agent.txt \
  --model google/gemini-2.5-flash \
  --no-deploy \
  --db /tmp/adrs_test.db
```

**Flags**:
| Flag | Purpose |
|------|---------|
| `--analyzer-output` | Path to directory containing `summary_*.csv` from the simulator's analyzer |
| `--simulator-path` | Root of the simulator project (for reading/writing prompts) |
| `--objective` | JSON file defining the optimization goal and success criteria |
| `--prompt-file` | Filename of the prompt to refine (in `simulator/ai-engine/prompts/`) |
| `--model` | LLM model to use (via OpenRouter) |
| `--no-deploy` | Don't write the refined prompt to the simulator (review first) |
| `--db` | SQLite database path for persistence |

### Other CLI commands

Run `python -m adrs.cli --help` for the full list, including `analyze`, `import-run`, `refine`, `diff`, and storage inspection commands.

---

## The Simulator Integration

### How the simulator works
The simulator runs Kubernetes workload placement scenarios. The `consolidator_agent` receives workload data + analyst reports and outputs placement decisions:

```json
{
  "decisions": [0, 1, 0, 1, -1],
  "explanations": ["reason for each decision..."]
}
```
- `0` = keep on private cluster
- `1` = migrate to public cloud
- `-1` = undecidable

**This output format is strict and immutable** — ADRS refinement must NEVER alter it.

### Simulator-side files
- `simulator/adrs_objective.json` — Defines goals, success criteria, priority metrics.
- `simulator/ai-engine/prompts/consolidator_agent.txt` — The prompt being refined.
- `simulator/analyzer/output/<run>/summary_*.csv` — Metrics output parsed by ADRS.
- `simulator/Makefile` — Targets `adrs-refine` and `setup-and-start-with-refinement`.

---

## Testing with Existing Data

You can test the pipeline without running the simulator by generating a mock CSV from existing test run JSONs:

```bash
# 1. Generate mock analyzer CSV
.venv/bin/python /tmp/generate_test_csv.py test_run/runs /tmp/adrs_test_analyzer_output

# 2. Run evaluate-and-refine (see command above, with --no-deploy)

# 3. Inspect the refined prompt in the DB
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('/tmp/adrs_test.db')
row = conn.execute('SELECT version, system_prompt, user_prompt FROM prompts WHERE version = \"v2\"').fetchone()
if row:
    print(f'=== {row[0]} ===')
    if row[1]: print(f'--- SYSTEM ---\n{row[1]}\n')
    print(f'--- USER ---\n{row[2]}')
conn.close()
"
```

Alternatively install a SQLite viewer: `sudo apt install sqlitebrowser` and open the DB file.

---

## Environment Setup

```bash
# 1. Create and activate venv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e .

# 3. Set up .env with your OpenRouter API key
echo "OPENROUTER_API_KEY=sk-or-v1-your-key-here" > .env
```

---

## Important Constraints for Agents

1. **Never modify the consolidator output format** (`decisions` + `explanations` arrays). The simulator parses this strictly.
2. **Always use `--no-deploy` first** to review the refined prompt before writing it to the simulator.
3. **Source `.env` before running** — the CLI reads `OPENROUTER_API_KEY` from the environment.
4. **JSON parsing pitfalls** — Gemini models return JSON with literal newlines and markdown code blocks inside string values. The `_extract_json_object()` (balanced-brace) and `_repair_json()` methods in `generator.py` handle this. Do not revert to regex-based extraction.
5. **Scoring model** — Lower metric values are better. The score formula is `s = max(0, 1 - value/baseline)`. The overload penalty is disabled by default (0.0) because the current scenario always triggers it.
6. **DB tables** — `evaluations` stores scores, `prompts` stores prompt texts, `refinements` stores reasoning/diffs. All three are populated by `evaluate-and-refine`.
