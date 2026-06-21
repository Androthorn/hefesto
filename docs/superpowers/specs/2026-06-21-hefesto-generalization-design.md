# Hefesto — Generalist Prompt-Refinement Tool

> **Date:** 2026-06-21
> **Status:** Design approved (revised after tríade review), pending implementation plan
> **Predecessor:** ADRS (WASP-coupled), preserved at git tag `v0.1.0`

## Summary

Hefesto generalizes the former ADRS system from a tool welded to the WASP
Kubernetes simulator into a **domain-agnostic prompt-refinement tool**: whenever
someone wants to improve a prompt, they use Hefesto. It runs an evaluation-first
loop — draft → run over test inputs → grade → score → refine → repeat — with a
champion/challenger promotion rule so a prompt's score never regresses.

The current "evaluation" (external K8s simulation metrics scored against fixed
baselines) is demoted from the center of the system to **one follow-on example
plugin**. The default path requires no external system at all: Hefesto generates
test inputs from the objective, executes the prompt against an LLM, and an
LLM-judge turns outputs into metrics scored against the objective.

## Goals

- Refine **any** prompt in **any** scenario from just a prompt + an objective.
- Zero-setup default: no external metrics, dataset, or grader code required.
- Keep external/user-supplied metrics as a first-class option (WASP-style).
- Encode the lessons already learned (see `FINDINGS.md`): few-shot refinement
  over rule-stacking, and never promoting a candidate on noise.
- Provider-agnostic: the user explicitly chooses provider + model; none baked in.
- Leave clean seams a future frontend can drive over the same core.

## Non-Goals

- Building the frontend (future work; this design only ensures the core exposes
  the right seams).
- Continuous/automated unattended looping beyond configurable stop criteria.
- Shipping the WASP integration in v1. It is a **follow-on example plugin**, not
  on the v1 critical path.

## Key Decisions (resolved during brainstorming + tríade review)

| Decision | Choice |
|----------|--------|
| Evaluation model | Unify under pluggable graders; LLM-judge is the default |
| Signal source when no user metrics | Hefesto runs the prompt and judges it; judge scores **are** the metrics |
| Onboarding | Dataset generated from objective by default; user may supply instead |
| Rubric & weights | Judge **proposes** the rubric (dimensions + suggested weights) from the objective; user edits. Weights are **not** required user input |
| Prompt model | **Flat text** with a `{{input}}` (and optional `{{context}}`) placeholder the Runner fills. No structured system/user/variables template |
| Provider model | **Provider-agnostic** — user sets provider + model per role; no baked-in default; fail fast at config load if missing |
| Package/CLI name | Rename `adrs` → `hefesto` |
| Promotion rule | Champion/challenger hill-climb on a **frozen** dataset, paired per-case comparison, margin in std units |
| Invariants | **Hard-enforced**: frozen regions checked byte-for-byte; candidate discarded if altered |
| History | **Full audit trail**: every rejected candidate persisted with score, delta, and reason |
| WASP | Follow-on example plugin; seams proven in v1 by a trivial non-LLM runner fixture; FINDINGS parity test non-gating |
| Old state preservation | Annotated git tag `v0.1.0` ("ADRS — WASP-coupled era"), pushed to origin |

## Concept & Data Flow

The user always brings a **prompt** and an **objective** (plain-English
description of "better"). Everything else Hefesto can produce itself.

```
  STEP 0 (baseline): score the seed prompt  ->  champion + s1
        ┌─────────── one iteration ───────────┐
prompt ─┤                                      │
        │  1. DATASET   test inputs (frozen)   │  generated from objective
obj. ───┤     (generate OR user-supplied)      │  (or loaded from file)
        │  2. RUNNER    run prompt over inputs  │  fills {{input}}, any provider
        │  3. GRADER    outputs → metrics       │  LLM-judge default
        │  4. SCORE     aggregate vs weights    │  composite in [0,1]
        │  5. REFINER   propose challenger      │  few-shot, not rule-stacking
        │  6. INVARIANT check frozen regions    │  byte-equal or discard
        │  7. PROMOTE   challenger vs champion   │  paired, margin-gated
        └──────────────────────────────────────┘
                 ↓ repeat until plateau / max iters / target
        champion + full audit trail (every attempt, version-tracked)
```

With no user-supplied metrics, the **LLM-judge scores ARE the metrics**.
User-supplied metrics replace or augment that judge.

**Score scale (pinned).** Every metric dimension is normalized to `[0, 1]` (a
judge's 1–10 becomes `(x-1)/9`; a WASP `v/b` ratio uses `max(0, 1 - v/b)`). The
composite score is the weighted average of normalized dimensions, also in
`[0, 1]`. All margins and thresholds below are expressed on this scale.

## Architecture — Four Pluggable Interfaces

Four small interfaces are the seams. Each does one thing, is swappable, and is
what a frontend would later drive.

```
hefesto/
├── schemas/             # shared types: TestCase, Output, Metrics,
│                        #   ScoredResult, Objective, Rubric  (Pydantic)
├── core/
│   └── loop.py          # orchestrator: STEP 0 baseline + iterations,
│                        #   stop criteria, invariant check, promotion. No domain logic.
├── dataset/
│   ├── base.py          # DatasetSource: provide() -> list[TestCase]
│   ├── generate.py      #   generate cases from objective (via LLM)
│   └── load.py          #   load cases from jsonl/json/csv
├── runner/
│   ├── base.py          # Runner: run(prompt, case) -> Output
│   ├── llm_runner.py    #   fill {{input}}/{{context}}, call any provider
│   └── echo_runner.py   #   trivial non-LLM runner (seam-proof fixture/tests)
├── grader/
│   ├── base.py          # Grader: grade(case, output, objective) -> Metrics
│   ├── llm_judge.py     #   DEFAULT — scores each rubric dimension, normalized
│   ├── code.py          #   exact / regex / schema / assertion checks
│   └── metric.py        #   GENERIC weighted-baseline scoring over dict[str,float]
├── refiner/
│   ├── refiner.py       # Refiner: propose(champion, selected_cases, objective)
│   │                    #   -> challenger prompt  (few-shot meta-prompt)
│   ├── select.py        #   select_contrast(scored_results, k) -> best+worst cases
│   └── invariants.py    #   extract + byte-compare frozen regions
├── score/
│   └── aggregate.py     # Metrics[] -> composite in [0,1] vs objective weights
├── store/               # versions, evaluations, refinements (full audit), runs
├── llm/                 # provider layer: base + per-provider impls + factory
├── diff/                # flat full-text prompt-version diff
└── plugins/
    └── wasp/            # FOLLOW-ON: K8s CSV import, metric presets, sim runner.
                         #   Wires metric.py + a custom Runner. Not in v1 critical path.
```

### The four contracts

| Interface | One job | Default impl | Swap for |
|-----------|---------|--------------|----------|
| `DatasetSource` | supply test inputs | generate-from-objective | load file / your own set |
| `Runner` | execute the prompt | LLM, fills `{{input}}` | echo fixture / sims / non-LLM |
| `Grader` | output → metrics | LLM-judge (rubric) | code checks / user metrics |
| `Refiner` | propose next prompt | few-shot strategy | custom strategies |

### Shared types (`hefesto/schemas/`)

- `TestCase` — `input` + optional `expected` + optional metadata.
- `Output` — raw run result for one case (text/JSON + provider metadata).
- `Metrics` — a **generic map** `dict[str, float]` (normalized to `[0,1]`) +
  optional judge notes per dimension.
- `ScoredResult` — case + output + metrics + composite score.
- `Rubric` — judge-proposed dimensions, each with a description + suggested
  weight; editable by the user.
- `Objective` — `goal`, `weights` (`dict[str, float]`, judge-seeded), optional
  `success_criteria`, and `invariants` (list of frozen prompt regions).

### Grader ↔ Score key contract

The LLM-judge emits exactly the dimension keys named in the `Rubric` / objective
`weights` — it does **not** invent free-form keys. `aggregate.py` then:
- composite = Σ `weight[k] · metric[k]` over weighted keys, renormalized so
  weights sum to 1;
- a weighted key **missing** from `Metrics` scores `0` for that dimension;
- a metric key with **no weight** is reported in the audit but not scored.

This closes the chicken-and-egg gap: the judge proposes the rubric+weights
during `init`/`gen-dataset`, the user edits `objective.yaml`, and from then on
judge keys and weight keys are guaranteed to align.

### Reuse map (honest tiers)

The product spine — `loop`, `runner`, `dataset/generate`, `llm_judge`,
`score/aggregate` — is **net-new**; the current system has no runner and no loop
(it imports external metrics and does a single pass). Classified honestly:

- **True ports (intact):** `llm/base.py`, `llm/direct.py`, `llm/openrouter.py`,
  `differ.py` → `diff/` (adapted to flat full-text).
- **Adapt (signature/type/schema changes):** `store/` models (flat `prompt_text`
  column; new audit columns; persist rejected candidates).
- **Rewrites (mislabeled as ports in the prior draft):**
  - `core/generator.py` → `refiner/refiner.py`. **Keep** the few-shot /
    anti-over-constraint wording of `REFINEMENT_SYSTEM_PROMPT` (already correct);
    **replace** its plumbing — the new refiner takes `list[ScoredResult]` with
    concrete case I/O, not aggregate variance prose.
  - `core/selector.py` → `refiner/select.py`. The old `SolutionSelector` picks
    *past prompt versions* from the DB; the refiner needs *within-run best/worst
    test cases*. New pure function `select_contrast(scored_results, k)`.
  - `core/config.py` + `llm/factory.py` → per-role config, defaults removed (see
    Provider model).
- **Cut from core:** `core/analyzer.py` (426 lines of K8s multi-run variance over
  `ExperimentRun`). No consumer in the new flow; per-case variance, if wanted,
  is computed fresh from `judge_samples`. May reappear inside `plugins/wasp/`.

## Refiner Strategy & Champion/Challenger Loop

Encodes the `FINDINGS.md` lessons so Hefesto does not repeat the v2/v3
degradation spiral.

### Refiner (how a better prompt is proposed)

`refiner.propose(champion_prompt, selected_cases, objective)` where
`selected_cases = select_contrast(scored_results, k)` = the top-k best + bottom-k
worst cases of the current evaluation, each carrying concrete
`(input, output, metrics, judge_notes)`. The meta-prompt enforces:

- **Prefer few-shot examples over rules.** On a failing case, add a concrete
  input→correct-output example, not nested `1.a / 1.b` rules. (v5 beat the v1
  baseline doing exactly this: +6.6% mean score, −52% variance.)
- **Resist the yes-man loop.** Do not bolt a special-case rule onto every miss;
  generalize. A programmatic **rule-density lint** (count nested `\d\.[a-z]`
  patterns) penalizes/rejects candidates that grow them.
- **Preserve invariants.** The meta-prompt instructs the model to leave frozen
  regions untouched; this is then **hard-verified** (below), not trusted.

### Invariant enforcement (hard)

After `propose`, `invariants.py` extracts each frozen region from the candidate
and asserts byte-for-byte equality with the objective's `invariants`. On any
mismatch the candidate is **discarded** (counts as a non-improving attempt and is
logged to the audit trail with reason `invariant_violation`).

### Promotion rule (never regress on noise)

```
# STEP 0
champion       = seed prompt
champion_score = evaluate(champion, dataset)        # frozen dataset, judge_samples each

for each iteration:
    candidate = refiner.propose(champion, select_contrast(champion_results, k), objective)
    if not invariants_ok(candidate):                # hard byte-check
        log_rejected(candidate, reason="invariant_violation"); fails += 1; continue
    cand_results = evaluate(candidate, dataset)      # SAME frozen dataset, judge_samples each
    delta = paired_mean(cand_results, champion_results)   # per-case composite deltas
    if delta > epsilon_k * pooled_std(...):          # margin in std units
        champion, champion_results, champion_score = candidate, cand_results, cand_results.score
        log_promoted(candidate, delta); fails = 0
    else:
        log_rejected(candidate, reason="no_improvement", delta=delta); fails += 1
stop when: fails ≥ patience  OR  iter ≥ max_iter  OR  champion_score ≥ target
return champion + full audit trail
```

Design choices that fix the tríade findings:

- **Frozen dataset.** The dataset is generated/loaded once at STEP 0 and reused
  for every comparison, so scores are comparable across iterations. Regeneration
  only via an explicit flag.
- **Paired, same-dataset comparison.** Champion and candidate are both scored on
  the same cases; promotion uses the mean of per-case deltas, not two
  independently-measured scalars.
- **Margin in std units.** `epsilon_k` (default tunable, e.g. `1.0`) times the
  pooled per-case std — because `FINDINGS.md` measured run-to-run std of
  0.07–0.18 even on a deterministic scorer. A fixed `0.02` absolute margin would
  both promote on noise and reject real gains.
- **`judge_samples`.** Each case is judged N times and averaged (default N=1 for
  runner, ≥1 for judge); both champion and candidate use the same N.
- **Branch-from-champion.** A rejected candidate is a dead end; the next attempt
  refines the *champion* again, never the worse candidate. Structural fix for the
  v1→v2→v3 linear decline.

`k`, `epsilon_k`, `patience`, `max_iter`, `target`, `judge_samples` are all config.

## Config, CLI & Provider Model

### Config (`hefesto.yaml`)

```yaml
# --- providers: REQUIRED, no baked-in default; fail fast at load if missing ---
providers:
  default:  { provider: <required>, model: <required> }   # fallback for all roles
  runner:   { provider: <required>, model: <required>, temperature: 0.7 }
  judge:    { provider: <required>, model: <required>, temperature: 0.0 }
  refiner:  { provider: <required>, model: <required>, temperature: 0.7 }
  dataset:  { provider: <required>, model: <required>, temperature: 1.0 }
  # each role resolves from its own block or falls back to `default`

objective: ./objective.yaml      # goal, weights (judge-seeded), invariants, criteria
prompt:    ./prompt.txt          # flat text with {{input}} / {{context}} placeholders

dataset:
  source: generate               # generate | load
  count: 20                      # if generate
  path:  ./cases.jsonl           # if load
  freeze: true                   # generated/loaded once, reused across iterations

grader:  llm_judge               # llm_judge | code | metric | <plugin>

loop:
  max_iter: 5
  patience: 2                    # stop after N non-improving iterations
  k: 3                           # best-k + worst-k cases fed to the refiner
  epsilon_k: 1.0                 # promotion margin in pooled-std units
  judge_samples: 1               # judge each case N times, average
  target: null                   # optional early-stop composite score (0–1)

store: { type: sqlite, path: ./hefesto.db }
```

There are **four** LLM roles (runner, judge, refiner, dataset), each with a
config slot; the fail-fast check covers all four.

### CLI surface (`hefesto` command; Typer)

| Command | Purpose |
|---------|---------|
| `hefesto init` | scaffold `hefesto.yaml` (providers as `<required>` sentinels), `objective.yaml`, `prompt.txt`; **judge proposes a starter rubric + weights** for the user to edit |
| `hefesto refine` | **primary** — run STEP 0 + the loop, emit best prompt + audit trail |
| `hefesto eval` | one-shot: score the current prompt on the dataset, no refinement (also reusable as a holdout validator via `--dataset`) |
| `hefesto gen-dataset` | generate test cases from the objective and write them out to edit |
| `hefesto history` | list versions + scores (incl. rejected attempts) for a prompt |
| `hefesto diff --from --to` | full-text diff two prompt versions |

`refine` flags mirror config keys (`--max-iter`, `--grader`, `--dataset`,
`--target`, review gates) so anything in YAML is overridable on the CLI — and
these are exactly the parameters a future frontend form would set.

### Provider-agnostic model

The `llm/` factory resolves `(provider, model)` per role at call time;
OpenRouter / OpenAI / Anthropic / Google all remain available, none privileged.
The current `LLMConfig` Pydantic **defaults are removed** (incl. the stale
`anthropic/claude-sonnet-4-20250514`); a missing required role raises at config
load with the role name. This is a small config rewrite, not a port.

## Storage Schema (full audit trail)

| Table | Holds | Change from today |
|-------|-------|-------------------|
| `prompts` | versioned **flat** prompt text + `parent_version` lineage | single `prompt_text` column (drop system/user split) |
| `evaluations` | composite score (0–1) + per-dimension `Metrics` JSON + judge notes | generic metric map, not fixed K8s columns |
| `refinements` | **accepted AND rejected** candidates: `parent_version`, `promoted`, `delta`, `reason`, reasoning, diff | persist rejected attempts (was: only accepted) |
| `runs` | raw per-case outputs (input, output, metrics) | stores Hefesto's own executor outputs |

Persisting rejected candidates is what makes the rollback lineage fully
reconstructable — the automated form of what `FINDINGS.md` did by hand, and the
data a future frontend "refinement journey" view would read.

## Testing Strategy

TDD throughout (the repo currently has **no tests** — this harness is new), with
a `FakeLLMProvider` so the loop is deterministic without API calls.

- **Unit:** each interface in isolation — `dataset/generate` (mock LLM returns N
  cases), `llm_judge.grade` (fake judge → known normalized metrics),
  `score/aggregate` (pure, table-driven, incl. missing-key / unweighted-key
  rules), `refiner/select.select_contrast`, `invariants` byte-check, `diff`.
- **Loop integration (headline test):** scripted sequence where candidate 2 is
  worse → assert the champion is **never** replaced, the next candidate branches
  from the champion, and both rejected attempts are logged. Regression guard for
  the v1→v2→v3 decline. A second case asserts an invariant-violating candidate is
  discarded.
- **Seam-proof fixture:** the `echo_runner` (non-LLM) drives a full `refine` run,
  proving the seams generalize beyond LLM prompts **without** reviving WASP.
- **CLI:** Typer `CliRunner` over `init` / `eval` / `refine --max-iter 1`.

## Open Questions / Risks

- **Closed-loop proxy risk.** The zero-setup default optimizes LLM-generated
  inputs graded by an LLM judge against a judge-seeded rubric — no external
  ground truth. Mitigation: `eval --dataset <holdout>` re-scores the final
  champion on a separate, user-supplied set (the automated form of FINDINGS'
  manual 10-run validation). The docs must state plainly that the no-dataset
  result optimizes a proxy.
- **Judge reliability.** Drives `judge_samples` + `epsilon_k`; defaults
  conservative, may need per-task tuning.
- **Cost.** Each iteration runs the full frozen dataset through runner + judge
  (×`judge_samples`); `count`, `max_iter`, `patience` bound spend. Surface an
  estimate before running.

## Rollout (sequenced for a usable core first)

1. Tag `v0.1.0` (done).
2. Rename `adrs` → `hefesto`; port the genuinely-intact modules (`llm/base|direct|
   openrouter`, `diff`); add `schemas/` + `FakeLLMProvider`.
3. Build the spine: `dataset/generate` → `llm_runner` (+`echo_runner`) →
   `llm_judge` → `score/aggregate`, with the Grader↔weights contract (TDD).
4. Build `loop.py`: STEP 0 baseline, champion/challenger promotion, hard invariant
   check, full-audit persistence — headline test first.
5. Refiner: `refiner/refiner.py` (keep few-shot wording) + `select_contrast` +
   rule-density lint.
6. CLI `init` (with judge-seeded rubric) / `eval` / `refine` / `history` / `diff`;
   update README/GUIDE for the generalist identity. **Usable core — ship here.**
7. **Follow-on:** `plugins/wasp/` (CSV import, metric presets, sim runner wiring
   `grader/metric.py`); FINDINGS-parity smoke test pinned to `FIXED_COST=0.0224`
   + `overload_penalty=0.0`, non-gating.
