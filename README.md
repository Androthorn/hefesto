# Hefesto

Hefesto is an evaluation-first prompt-refinement CLI. Given a prompt and an objective, it proposes candidate prompts, scores each one on a held-out test split, and promotes a candidate to champion only if a statistical gate says it beats the current champion by a stated margin. Every attempt, promoted or rejected, is stored with its parent version, delta and reason. Provider, runner, grader and refiner are separate seams, so each can be replaced without touching the loop; a non-LLM echo runner is included for smoke tests.

## Hefesto in the UCC 2026 paper

Hefesto is the instrument of the live experiment in "When a Better Prompt Is Just Noise in LLM-Driven Cloud Orchestration" (UCC 2026). The paper argues that promoting a stochastic agent's prompt on raw scores from a few runs promotes noise.

- The paper's Phase 2 refinement loop ran on an earlier, ADRS-based version of this repository, tag `v0.1.0`. Its contemporaneous notes are in the git history at commit `dd2011e` (`FINDINGS.md`).
- The promotion gate described below (`hefesto/core/gate.py`) and the false-promotion resampling (`hefesto/core/resample.py`) were added afterwards, on top of that history.
- The experiment code and data live in https://github.com/Androthorn/simulator-ucc.

### How to cite

```
Andre Cunha, Giovanni Farias, Fabio Morais.
"When a Better Prompt Is Just Noise in LLM-Driven Cloud Orchestration."
IEEE/ACM Utility and Cloud Computing (UCC 2026), Federal University of Campina Grande.
DOI: TODO. Pages: TODO.
```

## Promotion rule

`should_promote` in `hefesto/core/gate.py` runs an unpaired, one-sided Welch test with a margin. It promotes a candidate if and only if the lower bound of the one-sided (1 - alpha) confidence interval on `mean(cand) - mean(champ)` is greater than `delta_min`:

```
lower bound = (mean_c - mean_p) - t_{1-alpha, nu} * sqrt(s_c^2/n_c + s_p^2/n_p)
promote iff lower bound > delta_min
```

`nu` is the Welch-Satterthwaite degrees of freedom (`welch_lower_bound`). The two arms are independent samples, so the verdict does not depend on the order of the replicas. Each arm needs at least 2 samples. `RefineLoop` (`hefesto/core/loop.py`) applies it to the per-case composite scores of the candidate and the champion on the test split.

| Parameter | Meaning | Paper value |
|-----------|---------|-------------|
| samples per arm | test-split cases scored per prompt (`test_fraction` of the dataset); each is one replica | 12 |
| `delta_min` | minimum gain the lower bound must exceed | 0.05 |
| `alpha` | one-sided significance level | 0.05 |

The previous rule was `paired_mean(cand, champ) > epsilon_k * pooled_std`. It paired independent replicas by order (`zip`) and its threshold contained no `n`, so more replicas never bought confidence, and its false-promotion rate was an uncontrolled function of `k`. It is kept as `legacy_epsilon_sigma_rule` only so `hefesto/core/resample.py` can estimate false-promotion rates of the naive, legacy and gate rules on the same null replicas (`false_promotion_rates`). Do not use it to promote.

`loop.k` in `hefesto.yaml` is not the sample size: it is how many best and worst dev cases `select_contrast` shows the refiner. The gate's n per arm is the number of test-split cases, so with the WASP runner, where each case is one simulation replica, the paper's 12 replicas per arm means 12 test cases.

## Running with the WASP simulator

`WASPRunner` (`hefesto/runner/wasp_runner.py`) and `StabilityGrader` (`hefesto/grader/stability_grader.py`) need a checkout of simulator-ucc (https://github.com/Androthorn/simulator-ucc).

`WASPRunner(simulatormeu_root, config_path, runs_dir, reset_mode="full")`, one call to `run(prompt, case)` runs one replica:

- It writes the candidate prompt to `<root>/ai-engine/prompts/workshop/cand_<sha8>.txt`, where `sha8` is the first 8 hex digits of the SHA-256 of the prompt. An empty prompt raises `RunnerError`.
- It runs `bash <root>/run_one_replica.sh workshop/cand_<sha8> <config_path> <dest>` with `RESET_MODE` in the environment, where `<dest>` is `<runs_dir>/<case.input or "r">_<sha8>_<replica>` (`replica` and `reset_mode` come from `case.metadata`, defaulting to 0 and the constructor value).
- A non-zero exit code, or no `<dest>/analyzer/summary/summary_metrics_*.csv`, raises `RunnerError`. Otherwise it returns an `Output` whose `text` and `metadata["csv"]` are the path of the last such CSV; `metadata` also carries `run_dir` and `provenance`, and `model` is read from `<dest>/provenance.json` if present.

`StabilityGrader.grade(case, output, objective)` reads `output.metadata["csv"]` (columns: unnamed metric-name index, and `mean`) and needs the rows `pending_pods`, `time_with_pending`, `cost` and `number_of_migrations`; a missing row raises `KeyError`. It returns `Metrics(scores={"stability": S})`, where `S = stability_score(means)` from `hefesto/scoring/ucc_scoring.py`:

```
S = sum over metrics of  w * max(0, 1 - v / b)
pending_pods          w=0.35  b=100
time_with_pending     w=0.25  b=1.0
cost                  w=0.25  b=0.1 - 0.0224   (v = max(0, cost - 0.0224))
number_of_migrations  w=0.15  b=200
```

## Signal trust ladder

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

**New here?** [how-it-works.md](how-it-works.md) walks one `hefesto refine`
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
  k: 3                          # best and worst dev cases sent to the refiner (select_contrast)
  delta_min: 0.05               # promotion margin on the gain, in score units
  alpha: 0.05                   # one-sided significance level of the promotion gate
  headroom_min: 0.05            # skip loop if champion is already close to ceiling

store_path: ./hefesto.db
```

`epsilon_k` is still accepted by the config schema but the promotion gate does not
use it.

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

Apache License 2.0. See [LICENSE](LICENSE).
