# ADRS - Automated Dynamic Refinement System

ADRS is a Python CLI tool for iteratively optimizing LLM agent prompts based on experimental metrics and feedback.

## Overview

ADRS implements an automated feedback loop that:
1. Takes structured input (metrics, logs, prompts) from your experiments/simulations
2. Analyzes performance variance and reliability issues
3. Uses an LLM to generate refined prompts
4. Persists history for future loop-based optimization

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ADRS Single Pass                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. USER provides:                                                  │
│     ├── objective.json    (what they want to achieve)               │
│     ├── runs/             (experiment results)                      │
│     └── prompts/          (current agent prompts)                   │
│                                                                     │
│  2. ADRS analyzes:                                                  │
│     ├── Variance/instability in metrics                             │
│     ├── Patterns in logs                                            │
│     └── Current prompt structure                                    │
│                                                                     │
│  3. ADRS generates:                                                 │
│     └── refined_prompts/  (improved prompts + reasoning)            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Clone or navigate to the project
cd adrs

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode
pip install -e .

# Or install with dev dependencies (for testing)
pip install -e ".[dev]"
```

## Quick Start

### 1. Initialize a new project

```bash
adrs init --path ./my-project
```

This creates:
- `adrs.yaml` - Configuration file
- `adrs_history.db` - SQLite database for history
- `prompts/` - Directory for agent prompts
- `runs/` - Directory for experiment data
- `refined_prompts/` - Output directory

### 2. Prepare your input files

**Objective (`objective.json`):**
```json
{
  "goal": "Reduce variance in pending_pods across identical runs",
  "success_criteria": [
    {"metric": "pending_pods", "operator": "<", "threshold": 20.0}
  ],
  "priority_metrics": ["pending_pods", "number_of_migrations"],
  "focus_areas": ["consistency", "reliability"]
}
```

**Prompts (`prompts/cost_agent.json`):**
```json
{
  "agent_name": "cost_agent",
  "version": "v1.0",
  "template": {
    "system": "You are a cost optimization agent...",
    "user": "Current metrics: {{metrics}}\n\nProvide recommendation.",
    "variables": ["metrics"]
  },
  "constraints": ["Must output valid JSON"]
}
```

**Runs (`runs/cost_agent_runs.json`):**
```json
[
  {
    "run_id": "run_001",
    "timestamp": "2025-01-30T10:00:00Z",
    "prompt_version": "v1.0",
    "agent_name": "cost_agent",
    "metrics": {
      "pending_pods": {"mean": 34.17, "min": 0.0, "max": 94.0, "std": 43.65, "median": 0.0}
    },
    "logs": [
      {"level": "INFO", "message": "Agent started"}
    ]
  }
]
```

### 3. Run refinement

```bash
adrs refine \
  --objective ./objective.json \
  --runs ./runs/ \
  --prompts ./prompts/ \
  --output ./refined_prompts/ \
  --provider openrouter \
  --model anthropic/claude-sonnet-4-20250514
```

### 4. View history

```bash
adrs history --agent cost_agent
```

### 5. Compare versions

```bash
adrs diff --agent cost_agent --from v1.0 --to v1.1
```

## Configuration

Create `adrs.yaml` to customize behavior:

```yaml
llm:
  provider: openrouter  # openrouter | openai | anthropic | google | litellm
  model: anthropic/claude-sonnet-4-20250514
  temperature: 0.7
  max_tokens: 4096

storage:
  type: sqlite
  path: ./adrs_history.db

analyzer:
  priority_metrics:
    - pending_pods
    - number_of_migrations
  variance_threshold: 0.1

output_dir: ./refined_prompts
include_reasoning: true
include_diff: true
```

## Environment Variables

Set your API keys:

```bash
# For OpenRouter
export OPENROUTER_API_KEY=your_key_here

# For direct OpenAI
export OPENAI_API_KEY=your_key_here

# For direct Anthropic
export ANTHROPIC_API_KEY=your_key_here

# For Google (Gemini models)
export GOOGLE_API_KEY=your_key_here
```

## LLM Providers

ADRS supports multiple LLM providers:

| Provider | Models | Notes |
|----------|--------|-------|
| `openrouter` | Any model on OpenRouter | Recommended for flexibility |
| `openai` | gpt-4, gpt-4-turbo, etc. | Direct OpenAI API |
| `anthropic` | claude-3-opus, claude-3-sonnet, etc. | Direct Anthropic API |
| `google` | gemini-pro, gemini-1.5-pro, etc. | Direct Google AI API |
| `litellm` | 100+ models | Universal interface |

## Project Structure

```
adrs/
├── pyproject.toml          # Project metadata
├── adrs/
│   ├── __init__.py         # Package init, module name config
│   ├── cli.py              # CLI commands
│   ├── schemas/            # Pydantic models for I/O
│   │   ├── input.py        # Metrics, Logs, Prompts, Objectives
│   │   ├── output.py       # RefinementResult, Diff
│   │   └── config.py       # Configuration schema
│   ├── core/               # Core components
│   │   ├── analyzer.py     # Metrics/logs analysis
│   │   ├── generator.py    # LLM-based prompt refinement
│   │   └── differ.py       # Prompt diff generation
│   ├── llm/                # LLM providers
│   │   ├── base.py         # Abstract interface
│   │   ├── openrouter.py   # OpenRouter implementation
│   │   ├── direct.py       # Direct API via LiteLLM
│   │   └── factory.py      # Provider factory
│   └── storage/            # Persistence layer
│       ├── models.py       # SQLAlchemy models
│       └── repository.py   # CRUD operations
└── examples/               # Example input files
```

## Future Features

- [ ] Continuous loop mode (`adrs loop`)
- [ ] Parallel candidate evaluation
- [ ] Web dashboard
- [ ] Integration with popular MLOps platforms

## License

MIT
