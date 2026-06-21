# Hefesto — Generalist Prompt-Refinement Tool

> **Date:** 2026-06-21
> **Status:** Design approved, pending implementation plan
> **Predecessor:** ADRS (WASP-coupled), preserved at git tag `v0.1.0`

## Summary

Hefesto generalizes the former ADRS system from a tool welded to the WASP
Kubernetes simulator into a **domain-agnostic prompt-refinement tool**: whenever
someone wants to improve a prompt, they use Hefesto. It runs an evaluation-first
loop — draft → run over test inputs → grade → score → refine → repeat — with
best-of-N rollback so a prompt's score never regresses.

The current "evaluation" (external K8s simulation metrics scored against fixed
baselines) is demoted from the center of the system to **one pluggable grader
plugin**. The default path requires no external system at all: Hefesto generates
test inputs from the objective, executes the prompt against an LLM, and an
LLM-judge turns outputs into metrics.

## Goals

- Refine **any** prompt in **any** scenario from just a prompt + an objective.
- Zero-setup default: no external metrics, dataset, or grader code required.
- Keep external/user-supplied metrics as a first-class option (WASP-style).
- Encode the lessons already learned (see `FINDINGS.md`): few-shot refinement
  over rule-stacking, and best-of-N rollback to prevent score degradation.
- Provider-agnostic: the user explicitly chooses provider + model; none baked in.
- Leave clean seams a future frontend can drive over the same core.

## Non-Goals

- Building the frontend (future work; this design only ensures the core exposes
  the right seams).
- Continuous/automated unattended looping beyond configurable stop criteria.
- Migrating or preserving the WASP integration as the primary path — it becomes
  one worked example plugin.

## Key Decisions (resolved during brainstorming)

| Decision | Choice |
|----------|--------|
| Evaluation model | Unify under pluggable graders; LLM-judge is the default |
| Signal source when no user metrics | Hefesto runs the prompt and judges it; judge scores **are** the metrics |
| Onboarding | Dataset generated from objective by default; user may supply instead |
| Provider default | **Provider-agnostic** — user must set provider + model; no baked-in default; fail fast if missing |
| Package/CLI name | Rename `adrs` → `hefesto` |
| Restructuring approach | Evolve in place + introduce 3 interface seams (DatasetSource, Runner, Grader) + Refiner |
| Old state preservation | Annotated git tag `v0.1.0` ("ADRS — WASP-coupled era"), pushed to origin |

## Concept & Data Flow

The user always brings a **prompt** and an **objective** (plain-English
description of "better"). Everything else Hefesto can produce itself.

```
        ┌─────────── one iteration ───────────┐
prompt ─┤                                      │
        │  1. DATASET   test inputs            │  generated from objective
obj. ───┤     (generate OR user-supplied)      │  (or loaded from file)
        │  2. RUNNER    run prompt over inputs  │  any provider/model
        │  3. GRADER    outputs → metrics       │  LLM-judge default
        │  4. SCORE     aggregate vs objective  │  composite score
        │  5. REFINER   propose next prompt     │  few-shot, not rule-stacking
        │  6. ROLLBACK  keep best-of-N          │  never promote a regression
        └──────────────────────────────────────┘
                         ↓ repeat until plateau / max iters
                  refined prompt + score history (versioned)
```

With no user-supplied metrics, the **LLM-judge scores ARE the metrics**.
User-supplied metrics replace or augment that judge.

## Architecture — Four Pluggable Interfaces

Four small interfaces are the seams. Each does one thing, is swappable, and is
what a frontend would later drive.

```
hefesto/
├── core/
│   └── loop.py          # orchestrator: wires the 4 interfaces, runs iterations,
│                        #   owns stopping criteria + rollback. No domain logic.
├── dataset/
│   ├── base.py          # DatasetSource: provide() -> list[TestCase]
│   ├── generate.py      #   generate cases from objective (via LLM)
│   └── load.py          #   load cases from jsonl/json/csv
├── runner/
│   ├── base.py          # Runner: run(prompt, case) -> Output
│   └── llm_runner.py    #   execute prompt-under-test on any provider
├── grader/
│   ├── base.py          # Grader: grade(case, output, objective) -> Metrics
│   ├── llm_judge.py     #   DEFAULT — rubric from objective, 1–10 per dimension
│   ├── code.py          #   exact / regex / schema / assertion checks
│   └── metric.py        #   ingest user-supplied numbers (old WASP-style)
├── refiner/
│   └── refiner.py       # Refiner: propose(prompt, scored_results, objective)
│                        #   -> candidate prompt  (was core/generator.py)
├── score/
│   └── aggregate.py     # Metrics[] -> composite score vs objective weights
├── store/  (was storage/)   # versions, evaluations, refinements, run history
├── llm/                 # provider layer (provider-agnostic; user sets in config)
├── diff/  (was differ.py)   # prompt-version diffs
└── plugins/
    └── wasp/            # the old K8s path: MetricGrader + CSV import + deploy,
                         #   re-expressed as plugins. Proof the seams generalize.
```

### The four contracts

| Interface | One job | Default impl | Swap for |
|-----------|---------|--------------|----------|
| `DatasetSource` | supply test inputs | generate-from-objective | load file / your own set |
| `Runner` | execute the prompt | LLM over any provider | non-LLM systems, sims |
| `Grader` | output → metrics | LLM-judge (rubric) | code checks / user metrics |
| `Refiner` | propose next prompt | few-shot strategy | custom strategies |

### Shared types (`hefesto/schemas/`)

Evolved from today's `schemas/input.py` + `schemas/evaluation.py`:

- `TestCase` — input + optional expected answer + optional metadata.
- `Output` — raw run result for one case (text/JSON + provider metadata).
- `Metrics` — named numeric scores + optional judge notes. A **generic map**,
  not fixed K8s columns.
- `ScoredResult` — case + output + metrics + composite score.
- `Objective` — `goal`, `weights` (per-metric importance), `success_criteria`,
  and a new `invariants` list (protected regions the refiner must preserve).

### Reuse map (from today → Hefesto)

- `core/generator.py` → `refiner/refiner.py` (largely intact; meta-prompt updated).
- `core/selector.py` → stays as-is, feeds high-contrast cases to the refiner.
- `core/differ.py` → `diff/`, `storage/` → `store/`, `llm/` → `llm/` (port intact).
- `core/evaluator.py` (WASP-specific) → **dissolved** into `grader/metric.py`
  (generic weighted-baseline scoring) + `plugins/wasp/` (K8s glue).
- `core/analyzer.py` → retained for statistical variance reporting over runs.

## Refiner Strategy & Best-of-N Rollback

Encodes the `FINDINGS.md` lessons so Hefesto does not repeat the v2/v3
degradation spiral.

### Refiner (how a better prompt is proposed)

The refiner receives the current prompt, the objective, and the *scored
results*, with `selector.py` surfacing the highest-contrast cases (best + worst
runs) so the LLM reasons from concrete failures. Its meta-prompt enforces:

- **Prefer few-shot examples over rules.** On a failing case, add a concrete
  input→correct-output example, not nested `1.a / 1.b` rules. (v5 beat the v1
  baseline doing exactly this: +6.6% mean score, −52% variance.)
- **Resist the yes-man loop.** Do not bolt a special-case rule onto every miss;
  generalize. A simplicity constraint caps rule-density.
- **Never touch protected regions.** The objective's `invariants` (e.g. an
  output JSON schema) must be preserved verbatim — the generalized form of the
  old "never alter `decisions` + `explanations`" rule.

### Best-of-N rollback (how regressions are blocked)

```
champion = v1 (score s1)
for each iteration:
    candidate = refiner.propose(champion, scored_results, objective)
    s_cand = evaluate(candidate)              # full dataset run + grade
    if s_cand > champion.score + ε:           # ε = significance margin
        champion = candidate                   # promote
        fails = 0
    else:
        discard candidate                      # branch from champion again,
        fails += 1                             #   NOT from the worse candidate
stop when: fails ≥ patience  OR  iter ≥ max_iter  OR  score ≥ target
return champion  +  full scored history
```

- **Branch-from-champion, not from-latest.** A rejected candidate is a dead end;
  the next attempt refines the *champion* again (optionally with a different
  strategy/temperature). Structural fix for the v1→v2→v3 linear decline.
- **`ε` significance margin.** Because LLM-judge scores are noisy, a candidate
  must beat the champion by a margin (optionally averaged over N judge samples)
  before promotion. Avoids promoting on noise.

`ε`, `patience`, `max_iter`, `target`, and `judge_samples` are all config.

## Config, CLI & Provider Model

### Config (`hefesto.yaml`)

```yaml
# --- providers: REQUIRED, no baked-in default ---
providers:
  runner:   { provider: <required>, model: <required>, temperature: 0.7 }
  judge:    { provider: <required>, model: <required>, temperature: 0.0 }
  refiner:  { provider: <required>, model: <required>, temperature: 0.7 }
  # each role can use a different provider/model; or set one `default:` block

objective: ./objective.yaml      # goal, weights, invariants, success criteria
prompt:    ./prompt.txt          # the prompt under test

dataset:
  source: generate               # generate | load
  count: 20                      # if generate
  path:  ./cases.jsonl           # if load

grader:  llm_judge               # llm_judge | code | metric | <plugin>

loop:
  max_iter: 5
  patience: 2                    # stop after N non-improving iterations
  epsilon: 0.02                  # promotion margin (noise guard)
  judge_samples: 1               # >1 = average judge over samples
  target: null                   # optional early-stop score

store: { type: sqlite, path: ./hefesto.db }
```

### CLI surface (`hefesto` command; Typer, evolved from `cli.py`)

| Command | Purpose |
|---------|---------|
| `hefesto init` | scaffold `hefesto.yaml`, `objective.yaml`, `prompt.txt` |
| `hefesto refine` | **primary** — run the full loop, emit best prompt + score history |
| `hefesto eval` | one-shot: score the current prompt, no refinement (baseline) |
| `hefesto gen-dataset` | generate test cases from the objective and write them out |
| `hefesto history` | list versions + scores for a prompt |
| `hefesto diff --from --to` | diff two prompt versions |

`refine` flags mirror config keys (`--max-iter`, `--grader`, `--dataset`, review
gates) so anything in YAML is overridable on the CLI — and these are exactly the
parameters a future frontend form would set.

### Provider-agnostic model

The `llm/` factory resolves `(provider, model)` per role at call time;
OpenRouter / OpenAI / Anthropic / Google all remain available, none privileged.
If a required provider block is missing, Hefesto **fails fast at config load**
with a clear message rather than silently picking one.

## Storage Schema

Today's four SQLite/SQLAlchemy tables generalize; only WASP assumptions drop.

| Table | Holds | Change from today |
|-------|-------|-------------------|
| `prompts` | versioned prompt text + lineage | add `parent_version` (branch-from-champion) |
| `evaluations` | composite score, per-metric breakdown, judge notes | metrics become a generic JSON map, not fixed K8s columns |
| `refinements` | champion→candidate, reasoning, diff | add `promoted: bool` + `delta` so rollback history is queryable |
| `runs` | raw per-case outputs (input, output, metrics) | stores Hefesto's own executor outputs, not imported sim runs |

This makes the rollback lineage fully reconstructable — every rejected candidate
and *why* — which `FINDINGS.md` had to reconstruct by hand.

## The WASP Plugin (`plugins/wasp/`)

Proof the seams hold. The old `evaluator.py` splits into:

- `MetricGrader` (`grader/metric.py`, generic) — ingests user-supplied numbers +
  weighted-baseline scoring (`s = max(0, 1 - v/b)`, now config-driven).
- `plugins/wasp/` — K8s-specific glue: `summary_*.csv` import, the
  `pending_pods`/`migrations` weights as a *preset config*, the simulator
  prompt-deploy step, and a `Runner` variant that reads sim output instead of
  calling an LLM.

WASP becomes a worked example wiring `MetricGrader` + a custom `Runner` —
demonstrating the same loop serves both "judge an arbitrary prompt" and
"optimize against an external simulation."

## Testing Strategy

TDD throughout, with a `FakeLLMProvider` so the loop is deterministic without API
calls.

- **Unit:** each interface in isolation — `DatasetSource.generate` (mock LLM
  returns N cases), `LLMJudge.grade` (fake judge → known metrics),
  `score/aggregate` (pure function, table-driven), `diff`.
- **Loop integration (headline test):** feed a scripted sequence where candidate
  2 is worse; assert the champion is **never** replaced and the next candidate
  branches from the champion. Regression guard for the v1→v2→v3 decline.
- **Plugin smoke test:** WASP preset runs end-to-end on the existing `test_run/`
  JSON fixtures, asserting parity with known scores from `FINDINGS.md`.
- **CLI:** Typer `CliRunner` over `init` / `eval` / `refine --max-iter 1`.

## Open Questions / Risks

- **Judge reliability.** LLM-judge noise drives the `ε` + `judge_samples`
  guards; defaults are conservative but may need tuning per task type.
- **Generated-dataset quality.** Auto-generated cases may not represent real
  production inputs; `gen-dataset` writes editable output so users can curate.
- **Cost.** Each iteration runs the full dataset through runner + judge; `count`,
  `max_iter`, and `patience` bound spend. Worth surfacing an estimate.

## Rollout

1. Tag `v0.1.0` (done).
2. Rename `adrs` → `hefesto`; port intact modules (`llm`, `diff`, `store`,
   `selector`, `analyzer`).
3. Introduce the four interfaces + shared schemas (TDD).
4. Build the loop engine with best-of-N rollback (headline test first).
5. Implement defaults: generate-dataset, llm-runner, llm-judge, few-shot refiner.
6. Re-express WASP as `plugins/wasp/` + `grader/metric.py`; smoke-test parity.
7. New CLI surface; update docs (README/GUIDE) for the generalist identity.
