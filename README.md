# Hefesto

> Bring raw ore — a prompt and a goal — and leave with a tempered one that provably outperforms what you came with.

Hefesto is an evaluation-first prompt-refinement CLI. It scores before it ships, never promotes a regression, and leaves a full audit trail of every attempt — promoted or rejected.

## Four Earned Strengths

1. **Refines without bloating** — the refiner prefers a concrete few-shot example drawn from a real failing case over adding nested rules. Nested legalistic rule patterns are detected and discouraged.
2. **Never ships a regression** — every candidate is scored on a held-out test split. Promotion requires a statistically positive delta (paired mean in standard units). No delta, no promotion.
3. **Shows its work** — every iteration is persisted: parent version, candidate version, delta, promotion status, and reason. The full history survives across runs.
4. **Never breaks your pipeline** — provider, runner, grader, and refiner are seams. Any component can be swapped without touching the loop logic. A non-LLM echo runner ships in the box for smoke-testing.

## Signal Trust Ladder

Hefesto evaluates confidence from the most to least reliable signal:

| Tier | Signal | When available |
|------|--------|---------------|
| 1 | Real metrics (from your system) | When you can run the prompt against a live environment |
| 2 | Verifiable judge (ground-truth reference set) | When you have labelled examples |
| 3 | Calibrated LLM judge | Default — calibrated with `hefesto calibrate` before first use |

The loop runs at whichever tier you configure. The trust level is surfaced in the config (`grader` field) and reported in output.

## Quick Start

```bash
pip install -e .

# 1. Scaffold a new project
hefesto init --path ./my-project
cd my-project

# 2. Edit hefesto.yaml, objective.yaml, prompt.txt

# 3. Run the refinement loop
hefesto refine --config hefesto.yaml
```

**New here?** [docs/how-it-works.md](docs/how-it-works.md) walks one `hefesto refine`
end-to-end with concrete example values — dataset, scoring, a promoted iteration,
a rejected one, and the audit trail — so you can see exactly what the loop does.

## CLI Commands

| Command | Description |
|---------|-------------|
| `hefesto init` | Scaffold `hefesto.yaml`, `objective.yaml`, `prompt.txt` |
| `hefesto refine` | Run the full refinement loop — dataset, evaluation, champion/challenger |
| `hefesto calibrate` | Report judge agreement against a reference set (Tier 3 → Tier 2) |
| `hefesto eval` | Score the current prompt without refining |
| `hefesto gen-dataset` | Generate eval cases from the objective (useful for inspection) |
| `hefesto history` | List all versions, scores, and outcomes including rejected attempts |
| `hefesto diff` | Full-text diff between two prompt versions |

## Configuration (`hefesto.yaml`)

```yaml
providers:
  default:
    provider: openrouter        # openrouter | openai | anthropic | litellm
    model: anthropic/claude-sonnet-4-20250514
    temperature: 0.7
  judge:                        # optional — override the judge provider
    provider: openrouter
    model: google/gemini-2.5-flash

objective: ./objective.yaml
prompt: ./prompt.txt

dataset:
  source: generate              # generate | load
  count: 20
  test_fraction: 0.4

grader: llm_judge               # llm_judge | (future: verifiable_judge, real_metrics)

loop:
  max_iter: 5
  patience: 2
  k: 3                          # contrast cases sent to the refiner
  epsilon_k: 1.0                # promotion threshold in std units
  headroom_min: 0.05            # skip loop if champion is already close to ceiling

store_path: ./hefesto.db
```

## Objective (`objective.yaml`)

```yaml
goal: "Answer questions concisely and accurately."
weights:
  brevity: 0.4
  accuracy: 0.6
success_criteria:
  - "Average score >= 0.85"
invariants:
  - "{{input}}"                 # placeholder must be preserved in every candidate
```

## Environment Variables

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
export OPENAI_API_KEY=sk-...
```

## Installation

```bash
# From source
git clone <repo>
cd hefesto
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## License

MIT
