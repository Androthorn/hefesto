# Hefesto — Developer Guide

> **Audience**: contributors, plugin authors, and agents working with this codebase.
>
> For a narrated end-to-end walkthrough of a typical run (with example values at
> every stage), see [how-it-works.md](how-it-works.md). This guide is
> the component reference.

---

## Overview

Hefesto is an evaluation-first prompt-refinement loop. The core contract is simple: every candidate prompt must beat the champion on a held-out test split before it can be promoted. The loop never guesses — it measures.

---

## The Four Seams

Hefesto is built around four swappable interfaces. Swapping any seam does not touch the loop.

### 1. DatasetSource

**Interface** (`hefesto/dataset/base.py`): `.provide() -> DatasetSplit`

| Implementation | When to use |
|----------------|-------------|
| `GeneratedDataset` | You have no existing cases; Hefesto generates them from the objective using an LLM. |
| `LoadedDataset` | You have a JSONL file of `{"input": ..., "expected": ...}` records. |

The split always reserves a held-out `test` fraction. Only `dev` cases flow to the refiner for contrast selection; only `test` cases determine promotion.

### 2. Runner

**Interface** (`hefesto/runner/base.py`): `.run(prompt, case) -> Output`

| Implementation | When to use |
|----------------|-------------|
| `LLMRunner` | Standard LLM inference — fills `{{input}}` placeholder and calls the provider. |
| `EchoRunner` | Returns the filled prompt verbatim; useful for seam-isolation tests. |

Custom runners (e.g. a live simulator, a code-execution harness) implement the same one-method interface.

### 3. Grader

**Interface** (`hefesto/grader/base.py`): `.grade(case, output, objective) -> Metrics`

| Implementation | Trust tier | When to use |
|----------------|------------|-------------|
| `LLMJudge` | Tier 3 (calibrated) | Default — an LLM scores each output against the rubric dimensions. Calibrate first with `hefesto calibrate`. |

All scores are pinned to `[0, 1]` by a normalizer (`normalize_absolute` maps a 1–10 scale). The key contract: the same input always produces comparable scores (the judge is stateless and consistent).

### 4. Refiner

**Interface** (`hefesto/refiner/refiner.py`): `.propose(champion_prompt, selected_cases, objective) -> str`

The `Refiner` receives the champion prompt and a list of contrast cases — the `k` **best** and `k` **worst**-performing dev cases (`select_contrast`), so it sees both what works and what fails. It is instructed to:

- Prefer a concrete few-shot example drawn from a real failing case over adding rules.
- Not add nested legalistic rules (patterns like `1.a`, `1.b` are detected and penalised).
- Return only the full revised prompt text.

---

## Trust Model

```
Tier 1 — Real metrics
  Your system runs the prompt and emits a numeric outcome.
  No LLM judge involved. Highest confidence.

Tier 2 — Verifiable judge
  A reference set of (input, expected_output) pairs exists.
  The judge is verified against ground truth before use.
  Run `hefesto calibrate` to measure agreement; target >= 0.7.

Tier 3 — Calibrated LLM judge
  No reference set. An LLM grades on a rubric.
  Still useful — but run `hefesto calibrate` first to understand
  how stable the judge is across repeated calls.
```

The active tier is determined by the `grader` field in `hefesto.yaml`. The loop works identically at every tier — only the `Grader` implementation changes.

---

## The Champion/Challenger Loop

```
seed_prompt  →  evaluate on dev  →  evaluate on test  →  champ_score
                                                              │
                    ┌─────────────────────────────────────────┘
                    ▼
              select_contrast(dev_results, k)
                    │
                    ▼
              refiner.propose(champion, contrast_cases, objective)
                    │
                    ▼
              candidate_prompt
                    │
                    ▼
              evaluate candidate on test
                    │
              paired_mean(candidate, champion) > epsilon_k * pooled_std ?
                    │
              YES → promote candidate to champion
              NO  → discard; increment patience counter
                    │
              patience >= max_patience ?  →  STOP
              champion_score >= target ?  →  STOP
```

Key properties:

- **Branch-from-champion**: every candidate is proposed starting from the current champion, never from a rejected attempt.
- **Paired scoring**: delta is computed per test-case pair, not mean vs mean. This eliminates case-difficulty confounds.
- **Headroom guard**: if the champion already scores within `headroom_min` of the ceiling, the loop exits immediately. There is nothing to improve.
- **Invariant check**: any candidate that violates a declared invariant (e.g. drops the `{{input}}` placeholder) is rejected before evaluation — no LLM call wasted.
- **Full audit trail**: every attempt (promoted and rejected) is persisted to the `refinements` table with `parent_version`, `candidate_version`, `delta`, and `reason`. In v1, query it directly via `sqlite3` (the `hefesto history`/`diff` commands are scaffolded stubs slated for a follow-on).

---

## Persistence

All data is written to a SQLite database (`store_path` in config) via `Repository`:

| Table | Contents |
|-------|----------|
| `prompts` | Version-controlled prompt texts |
| `evaluations` | Composite scores, per-dimension metrics, judge agreement |
| `refinements` | Parent → candidate links, delta, promotion status, reason |

---

## Project Layout

```
hefesto/
├── cli.py                  # Typer CLI entry point
├── schemas/
│   ├── config.py           # HefestoConfig, ProviderConfig, LoopConfig, ...
│   └── core.py             # TestCase, Output, Metrics, Rubric, Objective, ...
├── llm/
│   ├── base.py             # LLMProvider, LLMMessage, LLMResponse
│   ├── factory.py          # create_provider(config) -> LLMProvider
│   ├── fake.py             # FakeLLMProvider for offline tests
│   ├── direct.py           # LiteLLM-backed provider (openai, anthropic, ...)
│   └── openrouter.py       # OpenRouter-specific provider
├── dataset/
│   ├── base.py             # DatasetSplit dataclass
│   ├── generate.py         # GeneratedDataset
│   ├── load.py             # LoadedDataset
│   └── split.py            # split_cases(cases, test_fraction)
├── runner/
│   ├── base.py             # fill_placeholders util
│   ├── llm_runner.py       # LLMRunner
│   └── echo_runner.py      # EchoRunner
├── grader/
│   ├── base.py             # Grader ABC
│   └── llm_judge.py        # LLMJudge (Tier 3)
├── refiner/
│   ├── refiner.py          # Refiner (proposes candidates)
│   ├── select.py           # select_contrast (k worst dev cases)
│   └── invariants.py       # check_invariants
├── core/
│   ├── loop.py             # RefineLoop — the champion/challenger engine
│   ├── intake.py           # no_headroom check
│   └── calibrate.py        # calibrate_judge
├── score/
│   └── aggregate.py        # composite_score(metrics, weights)
├── store/
│   ├── models.py           # SQLAlchemy ORM models
│   └── repository.py       # Repository CRUD
└── scaffold.py             # Template strings for `hefesto init`
```

---

## Writing Tests

All tests run offline by default. Use `FakeLLMProvider` from `hefesto.llm.fake`:

```python
from hefesto.llm.fake import FakeLLMProvider

provider = FakeLLMProvider(responses=["output text"])
# or with a routing handler:
provider = FakeLLMProvider(handler=lambda msgs: route(msgs))
```

When testing CLI commands end-to-end, monkeypatch `create_provider` on the `cli` module:

```python
import hefesto.cli as cli
monkeypatch.setattr(cli, "create_provider", lambda _cfg: FakeLLMProvider(...))
```

Run the suite:

```bash
.venv/bin/python -m pytest -q
```
