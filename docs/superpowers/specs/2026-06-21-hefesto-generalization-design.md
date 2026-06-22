# Hefesto — Generalist Prompt-Refinement Tool

> **Date:** 2026-06-21
> **Status:** Design approved (revised after two tríade rounds — engineering + ideas), pending implementation plan
> **Predecessor:** ADRS (WASP-coupled), preserved at git tag `v0.1.0`

## Summary

Hefesto generalizes the former ADRS system from a tool welded to the WASP
Kubernetes simulator into a **domain-agnostic prompt-refinement tool** — a forge
for prompts. Its promise:

> *Bring raw ore — a prompt and a goal — and leave with a tempered one that
> provably outperforms what you came with.*

Hefesto runs an evaluation-first loop — run over test inputs → grade → score →
refine → repeat — and what makes it more than "ask a chatbot to fix my prompt"
is four earned strengths it leads with:

1. **It refines without bloating** — concrete few-shot examples from real
   failures, not stacked rules (the `docs/history/findings-wasp-era.md` lesson).
2. **It never ships a regression** — champion/challenger promotion on a held-out
   test set; a new version wins only if it provably beats the best so far.
3. **It shows its work** — a full audit trail of every attempt and why it lost.
4. **It never breaks your pipeline** — declared invariants (e.g. output format)
   are guaranteed to survive refinement.

**Signal trust ladder.** Hefesto always seeks the strongest available signal:
- **Tier 3 — real metrics (gold):** a simulation or production data the user
  brings (the WASP origin). Foregrounded as the most trustworthy path.
- **Tier 2 — verifiable judge:** an LLM judge backed by checks it cannot fake
  (regex/schema validators, "does the cited fact appear in the source", compiles/runs).
- **Tier 1 — calibrated judge (zero-setup fallback):** with nothing but a prompt
  and an objective, Hefesto generates test inputs and an LLM judge grades them.
  These scores are a **calibrated proxy**, not objective ground truth, and are
  labeled as such (see Trust Model). This is the easy on-ramp, not the headline.

The old K8s simulation scoring is demoted to **one follow-on example plugin**
(the Tier-3 worked example).

## Goals

- Refine **any prompt that has a checkable objective**, from just a prompt + an
  objective in the zero-setup case.
- Be honest about fit: detect at intake whether the objective is judge-gradable,
  needs an external oracle, or is subjective — and tell the user which signal
  tier applies (no silent over-promising).
- Know when to stop: detect "this prompt is already strong — nothing to forge"
  rather than shipping a worse prompt with a confident score.
- Treat user-supplied / real metrics as the **gold path**, not a footnote.
- Encode the lessons already learned (see `docs/history/findings-wasp-era.md`): few-shot refinement
  over rule-stacking, never promoting a candidate on noise, and never trusting a
  single data point.
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
| Evaluation model | Unify under pluggable graders; signal **trust ladder** (real metrics > verifiable judge > calibrated judge) |
| Signal source when no user metrics | Hefesto runs the prompt and judges it; judge scores are a **calibrated proxy**, explicitly not "objective metrics" |
| Judge independence | Judge defaults to a **different model** than the prompt-under-test; **calibrated** against a reference set and the agreement reported with every score; pairwise (A-vs-B) comparison supported |
| Signal-fit + headroom | At intake, classify the objective (judge-gradable \| needs-oracle \| subjective) and surface the tier; detect "already strong — nothing to forge" and stop |
| Positioning | Lead with the earned strengths (anti-bloat, never-regress, audit trail, invariants); judge + universality are honest, caveated fallbacks. Tagline bound to rigor, not method |
| Anti-overfit | **Dev/test split**: few-shot examples mined from a dev set; champion/challenger scored on a held-out test set; champion periodically re-validated |
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
  INTAKE: classify objective -> signal tier; if judge-tier, CALIBRATE judge
          vs a small reference set -> report agreement (gate scores)
  STEP 0: score the seed prompt on the TEST split  ->  champion + s1
          headroom check: "already strong, nothing to forge"? -> stop early
        ┌─────────── one iteration ───────────┐
prompt ─┤                                      │
        │  1. DATASET   dev split | test split  │  generated or user-supplied
obj. ───┤     (both frozen for the run)         │  dev = mine examples; test = score
        │  2. RUNNER    run prompt over inputs  │  fills {{input}}, any provider
        │  3. GRADER    outputs → metrics       │  judge (≠ runner model) or real signal
        │  4. SCORE     aggregate vs weights    │  composite in [0,1] (proxy if judge)
        │  5. REFINER   propose challenger      │  few-shot from DEV split, not rules
        │  6. INVARIANT check frozen regions    │  byte-equal or discard
        │  7. PROMOTE   challenger vs champion   │  on TEST split, paired, margin-gated
        └──────────────────────────────────────┘
                 ↓ repeat until plateau / max iters / target / no-headroom
        champion + full audit trail (every attempt, version-tracked)
```

The signal depends on the tier (see Trust Model). With no user-supplied metrics
(Tier 1), the LLM-judge produces a **calibrated proxy** score — never presented
as objective ground truth. User-supplied / real metrics (Tier 3) replace the
judge and are the gold path. The **dev split** is where few-shot examples are
mined; the **test split** is held out and is the only thing promotion scores
against — so the loop cannot train on its own eval set.

**Score scale (pinned).** Every metric dimension is normalized to `[0, 1]`
(absolute judge 1–10 → `(x-1)/9`; pairwise judging yields a win-rate already in
`[0, 1]`; a WASP `v/b` ratio uses `max(0, 1 - v/b)`). The composite score is the
weighted average of normalized dimensions, also in `[0, 1]`. All margins and
thresholds below are expressed on this scale.

## Architecture — Four Pluggable Interfaces

Four small interfaces are the seams. Each does one thing, is swappable, and is
what a frontend would later drive.

```
hefesto/
├── schemas/             # shared types: TestCase, Output, Metrics,
│                        #   ScoredResult, Objective, Rubric  (Pydantic)
├── core/
│   ├── loop.py          # orchestrator: intake, STEP 0 baseline + iterations,
│   │                    #   stop criteria, invariant check, promotion. No domain logic.
│   ├── intake.py        #   classify objective -> signal tier; headroom check
│   └── calibrate.py     #   judge vs reference set -> agreement score (gates judge)
├── dataset/
│   ├── base.py          # DatasetSource: provide() -> dev + test splits
│   ├── generate.py      #   generate cases from objective (via LLM)
│   ├── split.py         #   dev / held-out test partition
│   └── load.py          #   load cases from jsonl/json/csv
├── runner/
│   ├── base.py          # Runner: run(prompt, case) -> Output
│   ├── llm_runner.py    #   fill {{input}}/{{context}}, call any provider
│   └── echo_runner.py   #   trivial non-LLM runner (seam-proof fixture/tests)
├── grader/
│   ├── base.py          # Grader: grade(case, output, objective) -> Metrics
│   ├── llm_judge.py     #   Tier 1 — pairwise/absolute judge, normalized proxy
│   ├── verifiable.py    #   Tier 2 — judge + code checks it can't fake
│   ├── code.py          #   exact / regex / schema / assertion checks
│   └── metric.py        #   Tier 3 — GENERIC weighted-baseline over dict[str,float]
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

## Trust Model

The tríade's sharpest finding: the zero-setup judge path is the *least*
trustworthy and must not masquerade as objective measurement. The design answers
this with four commitments.

### 1. Signal tiers (intake classification)

`core/intake.py` classifies the objective before any refinement:

| Tier | Signal | When | Honesty label |
|------|--------|------|---------------|
| 3 — real metrics (gold) | user-supplied / simulation / production | user brings metrics | "objective" |
| 2 — verifiable judge | judge + checks the model can't fake (regex, schema, fact-in-source, compiles) | objective has machine-checkable parts | "partially verified" |
| 1 — calibrated judge | LLM judge on generated inputs | nothing but prompt + objective | **"proxy — judge agreement N%"** |

Intake reports which tier applies and warns when the objective needs an external
oracle the judge cannot supply (e.g. "does this code compile", "is this citation
real"). It never silently grades what it cannot grade.

### 2. Judge independence

The judge defaults to a **different model** than the prompt-under-test (config
fails fast if they're identical without an explicit override), to avoid a model
rewarding its own blind spots / self-preference bias.

### 3. Judge calibration (scores must earn authority)

Before judge scores are allowed to gate promotion, `core/calibrate.py` checks the
judge against a small reference set of known good/bad outputs (the user's, or —
neatly — Hefesto's own FINDINGS best/worst examples as a built-in fixture). It
computes a **judge-agreement score** and:
- reports it alongside every composite score (`proxy — judge agreement 82%`);
- warns loudly when agreement is low (the judge can't tell good from bad here);
- prefers **pairwise (A-vs-B)** judgments over absolute 1–10 scoring, which are
  substantially more reliable for LLM judges.

### 4. Headroom / stop

`intake.py` (and the loop's stop criteria) detect when the seed prompt is already
strong enough that refinement only adds noise — Hefesto says *"already strong,
nothing to forge"* and stops, rather than promoting a marginal, possibly-worse
prompt. This is FINDINGS' gemini-base-beats-refinements result turned into a
feature.

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

Encodes the `docs/history/findings-wasp-era.md` lessons so Hefesto does not repeat the v2/v3
degradation spiral.

### Refiner (how a better prompt is proposed)

`refiner.propose(champion_prompt, selected_cases, objective)` where
`selected_cases = select_contrast(dev_results, k)` = the top-k best + bottom-k
worst cases **from the dev split**, each carrying concrete
`(input, output, metrics, judge_notes)`. Examples are mined from the dev split
only; the test split stays unseen by refinement. The meta-prompt enforces:

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
# INTAKE
tier = intake.classify(objective)                   # 3 real | 2 verifiable | 1 judge
if tier == judge: agreement = calibrate(judge, reference_set)   # gate + report
dev, test = split(dataset)                           # both frozen for the run

# STEP 0
champion       = seed prompt
champion_dev   = evaluate(champion, dev)             # for example mining
champion_test  = evaluate(champion, test)            # for promotion comparison
if intake.no_headroom(champion_test): stop("already strong — nothing to forge")

for each iteration:
    candidate = refiner.propose(champion, select_contrast(champion_dev, k), objective)
    if not invariants_ok(candidate):                # hard byte-check
        log_rejected(candidate, reason="invariant_violation"); fails += 1; continue
    cand_test = evaluate(candidate, test)            # SAME held-out test split, judge_samples each
    delta = paired_mean(cand_test, champion_test)    # per-case composite deltas
    if delta > epsilon_k * pooled_std(...):          # margin in std units
        champion = candidate
        champion_dev, champion_test = evaluate(candidate, dev), cand_test
        log_promoted(candidate, delta, agreement); fails = 0
    else:
        log_rejected(candidate, reason="no_improvement", delta=delta); fails += 1
stop when: fails ≥ patience  OR  iter ≥ max_iter  OR  champion_test.score ≥ target
return champion + full audit trail
```

Design choices that fix the tríade findings:

- **Dev/test split.** Examples are mined from `dev`; promotion is scored only on
  the held-out `test` split — so the loop can't overfit its own eval set. Both
  splits are frozen for the run; the champion is re-validated on promotion.
- **Frozen dataset.** Generated/loaded once at intake and reused for every
  comparison, so scores are comparable across iterations. Regeneration only via
  an explicit flag.
- **Paired, same-dataset comparison.** Champion and candidate are both scored on
  the same cases; promotion uses the mean of per-case deltas, not two
  independently-measured scalars.
- **Margin in std units.** `epsilon_k` (default tunable, e.g. `1.0`) times the
  pooled per-case std — because `docs/history/findings-wasp-era.md` measured run-to-run std of
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
  judge:    { provider: <required>, model: <required>, temperature: 0.0 }   # must differ from runner
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
  test_fraction: 0.4             # held-out test split; remainder is the dev split

grader:  llm_judge               # llm_judge | verifiable | metric | code | <plugin>

judge:
  mode: pairwise                 # pairwise (A-vs-B, preferred) | absolute
  require_different_model: true  # judge model must differ from runner
  calibration:
    reference: ./reference.jsonl # known good/bad outputs; falls back to FINDINGS fixture
    min_agreement: 0.7           # warn / refuse to gate below this

loop:
  max_iter: 5
  patience: 2                    # stop after N non-improving iterations
  k: 3                           # best-k + worst-k DEV cases fed to the refiner
  epsilon_k: 1.0                 # promotion margin in pooled-std units
  judge_samples: 1               # judge each case N times, average
  target: null                   # optional early-stop composite score (0–1)
  headroom_min: 0.05             # stop if seed already within this of target/ceiling

store: { type: sqlite, path: ./hefesto.db }
```

There are **four** LLM roles (runner, judge, refiner, dataset), each with a
config slot; the fail-fast check covers all four.

### CLI surface (`hefesto` command; Typer)

| Command | Purpose |
|---------|---------|
| `hefesto init` | scaffold `hefesto.yaml` (providers as `<required>` sentinels), `objective.yaml`, `prompt.txt`; **judge proposes a starter rubric + weights** for the user to edit |
| `hefesto refine` | **primary** — intake (tier + headroom) → STEP 0 → the loop, emit best prompt + audit trail |
| `hefesto calibrate` | check the judge against a reference set, report judge-agreement, before trusting its scores |
| `hefesto eval` | one-shot: score the current prompt on the dataset, no refinement (also a holdout validator via `--dataset`) |
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
reconstructable — the automated form of what `docs/history/findings-wasp-era.md` did by hand, and the
data a future frontend "refinement journey" view would read.

## Testing Strategy

TDD throughout (the repo currently has **no tests** — this harness is new), with
a `FakeLLMProvider` so the loop is deterministic without API calls.

- **Unit:** each interface in isolation — `dataset/generate` (mock LLM returns N
  cases), `dataset/split` (dev/test partition, no leakage), `llm_judge.grade`
  (fake judge → known normalized metrics), `intake.classify` (tier + headroom on
  fixtures), `calibrate` (agreement on a known good/bad reference; refuses to
  gate below `min_agreement`), `score/aggregate` (pure, table-driven, incl.
  missing-key / unweighted-key rules), `refiner/select.select_contrast`,
  `invariants` byte-check, `diff`.
- **Loop integration (headline test):** scripted sequence where candidate 2 is
  worse → assert the champion is **never** replaced, the next candidate branches
  from the champion, and both rejected attempts are logged. Regression guard for
  the v1→v2→v3 decline. A second case asserts an invariant-violating candidate is
  discarded.
- **Seam-proof fixture:** the `echo_runner` (non-LLM) drives a full `refine` run,
  proving the seams generalize beyond LLM prompts **without** reviving WASP.
- **CLI:** Typer `CliRunner` over `init` / `eval` / `refine --max-iter 1`.

## Open Questions / Risks

- **Closed-loop proxy risk (mitigated, not eliminated).** The zero-setup default
  optimizes LLM-generated inputs graded by an LLM judge. The Trust Model attacks
  this from four sides — judge ≠ runner model, calibration with a reported
  agreement score, dev/test split, and explicit proxy labeling — but Tier-1
  scores remain a proxy. Docs must say so plainly, and `eval --dataset <holdout>`
  on real data is the recommended final validation.
- **Calibration reference availability.** Calibration needs a few known good/bad
  examples; when the user has none, Hefesto falls back to the FINDINGS fixture,
  which is K8s-flavored and may not generalize. Open question: how to bootstrap a
  reference set for a brand-new domain (candidate: ask the user to label ~5
  generated outputs during `init`).
- **Judge reliability.** Drives `judge_samples`, `epsilon_k`, and the calibration
  gate; defaults conservative, may need per-task tuning.
- **Cost.** Each iteration runs dev + test splits through runner + judge
  (×`judge_samples`), plus calibration; `count`, `max_iter`, `patience` bound
  spend. Surface an estimate before running.

## Rollout (sequenced for a usable core first)

1. Tag `v0.1.0` (done).
2. Rename `adrs` → `hefesto`; port the genuinely-intact modules (`llm/base|direct|
   openrouter`, `diff`); add `schemas/` + `FakeLLMProvider`.
3. Build the spine: `dataset/generate` + `split` → `llm_runner` (+`echo_runner`)
   → `llm_judge` → `score/aggregate`, with the Grader↔weights contract (TDD).
4. Trust Model: `intake.classify` (signal tier + headroom) + `calibrate` (judge
   agreement, pairwise mode, judge ≠ runner enforcement).
5. Build `loop.py`: intake → STEP 0 baseline → champion/challenger on the test
   split, hard invariant check, full-audit persistence — headline test first.
6. Refiner: `refiner/refiner.py` (keep few-shot wording) + `select_contrast` over
   the dev split + rule-density lint.
7. CLI `init` (judge-seeded rubric) / `calibrate` / `eval` / `refine` / `history`
   / `diff`; update README/GUIDE for the generalist identity, leading with the
   four earned strengths. **Usable core — ship here.**
8. **Follow-on:** `plugins/wasp/` (CSV import, metric presets, sim runner wiring
   `grader/metric.py`); FINDINGS-parity smoke test pinned to `FIXED_COST=0.0224`
   + `overload_penalty=0.0`, non-gating.
