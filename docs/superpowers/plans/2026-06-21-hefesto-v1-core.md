# Hefesto v1 Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the WASP-coupled ADRS into Hefesto — a domain-agnostic, evaluation-first prompt-refinement CLI that improves any prompt with a checkable objective via a champion/challenger loop.

**Architecture:** Four pluggable seams (DatasetSource, Runner, Grader, Refiner) orchestrated by a loop that runs a prompt over a frozen dev/test split, grades outputs into a `[0,1]` composite score, proposes few-shot-based challengers, and promotes only provable improvements on the held-out test split. A Trust Model (signal-tier intake, judge calibration, judge≠runner) keeps the zero-setup LLM-judge path honest. Everything is persisted as a full audit trail.

**Tech Stack:** Python ≥3.10, Pydantic v2, Typer, SQLAlchemy 2.0, litellm, PyYAML, Rich, pytest.

## Global Constraints

- Python `requires-python = ">=3.10"`; use `X | Y` union syntax and `list[...]`/`dict[...]` generics.
- Package is `hefesto/` (renamed from `adrs/`); CLI entry point is `hefesto = "hefesto.cli:app"`.
- All scores normalized to `[0, 1]`; composite = weighted average of normalized dimensions.
- Provider-agnostic: NO baked-in provider/model defaults; config load fails fast (with the role name) if a required role's provider/model is missing.
- Pydantic v2 models everywhere for I/O types (`BaseModel`, `Field`).
- TDD: write the failing test first, watch it fail, minimal implementation, watch it pass, commit. One logical change per commit.
- No network in tests: all LLM calls go through `LLMProvider`, faked via `FakeLLMProvider`.
- WASP / K8s simulation support is OUT OF SCOPE for this plan (separate follow-on plan).

---

## File Structure

```
hefesto/
├── __init__.py
├── cli.py                     # Typer app: init/refine/calibrate/eval/gen-dataset/history/diff
├── schemas/
│   ├── __init__.py
│   ├── core.py                # TestCase, Output, Metrics, ScoredResult, Rubric, Objective
│   └── config.py              # HefestoConfig, ProviderConfig, JudgeConfig, LoopConfig, ...
├── llm/
│   ├── __init__.py
│   ├── base.py                # LLMProvider, LLMMessage, LLMResponse (PORT)
│   ├── direct.py              # DirectProvider via litellm (PORT)
│   ├── openrouter.py          # OpenRouterProvider (PORT)
│   ├── factory.py             # create_provider(ProviderConfig) — rewritten, per-role
│   └── fake.py                # FakeLLMProvider (test double)
├── dataset/
│   ├── __init__.py
│   ├── base.py                # DatasetSource protocol, DatasetSplit
│   ├── generate.py            # GeneratedDataset
│   ├── load.py                # LoadedDataset
│   └── split.py               # split_cases()
├── runner/
│   ├── __init__.py
│   ├── base.py                # Runner protocol
│   ├── echo_runner.py         # EchoRunner (non-LLM, seam-proof)
│   └── llm_runner.py          # LLMRunner ({{input}}/{{context}} substitution)
├── grader/
│   ├── __init__.py
│   ├── base.py                # Grader protocol
│   └── llm_judge.py           # LLMJudge (pairwise/absolute → normalized Metrics)
├── score/
│   ├── __init__.py
│   └── aggregate.py           # composite_score()
├── refiner/
│   ├── __init__.py
│   ├── select.py              # select_contrast()
│   ├── invariants.py          # check_invariants()
│   └── refiner.py             # Refiner.propose(), rule_density()
├── core/
│   ├── __init__.py
│   ├── intake.py              # classify_objective(), no_headroom()
│   ├── calibrate.py           # calibrate_judge()
│   └── loop.py                # RefineLoop.run()
├── store/
│   ├── __init__.py
│   ├── models.py              # PromptRecord, EvaluationRecord, RefinementRecord, RunRecord
│   └── repository.py          # Repository CRUD
└── diff/
    ├── __init__.py
    └── text_diff.py           # text_diff()
tests/
└── (mirrors hefesto/ layout)
```

---

## Task 1: Rename package to `hefesto`, port the LLM provider layer

**Files:**
- Rename: `adrs/` → `hefesto/` (git mv, whole tree)
- Modify: `pyproject.toml` (name, scripts, wheel packages)
- Modify: `hefesto/llm/base.py`, `hefesto/llm/direct.py`, `hefesto/llm/openrouter.py` (fix internal `adrs.` imports → `hefesto.`)
- Create: `tests/__init__.py`, `tests/llm/__init__.py`, `tests/llm/test_base.py`
- Delete (later tasks replace them): leave `hefesto/core/`, `hefesto/schemas/`, `hefesto/storage/` in place for now; they are overwritten/removed by their owning tasks.

**Interfaces:**
- Produces: `hefesto.llm.base.LLMProvider` (abstract: `complete(messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int = 4096) -> LLMResponse`, `get_model_name() -> str`), `LLMMessage(role, content)`, `LLMResponse(content, model, usage)`.

- [ ] **Step 1: Rename the package directory and storage dir**

```bash
git mv adrs hefesto
git mv hefesto/storage hefesto/store   # spec renames storage/ -> store/
```

- [ ] **Step 2: Rewrite internal imports `adrs.` → `hefesto.`**

```bash
grep -rl 'adrs' hefesto/ | xargs sed -i 's/\badrs\b/hefesto/g'
```

- [ ] **Step 3: Update `pyproject.toml`**

Set these exact values:

```toml
[project]
name = "hefesto"
version = "0.2.0"
description = "Hefesto - evaluation-first prompt-refinement tool"

[project.scripts]
hefesto = "hefesto.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["hefesto"]
```

- [ ] **Step 4: Reinstall editable and write the port smoke test**

Run: `pip install -e ".[dev]"`

```python
# tests/llm/test_base.py
from hefesto.llm.base import LLMMessage, LLMResponse, LLMProvider


def test_llm_message_roundtrips():
    m = LLMMessage(role="user", content="hi")
    assert m.role == "user" and m.content == "hi"


def test_llm_provider_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        LLMProvider()  # abstract, cannot instantiate
```

- [ ] **Step 5: Run the test**

Run: `pytest tests/llm/test_base.py -v`
Expected: PASS (2 passed). If import errors mention `adrs`, a file was missed in Step 2 — fix and rerun.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: rename adrs package to hefesto, port llm layer"
```

---

## Task 2: Shared schemas (`hefesto/schemas/core.py`)

**Files:**
- Create: `hefesto/schemas/core.py`
- Modify: `hefesto/schemas/__init__.py` (re-export)
- Delete: `hefesto/schemas/input.py`, `hefesto/schemas/output.py`, `hefesto/schemas/evaluation.py` (WASP-shaped, replaced here)
- Create: `tests/schemas/__init__.py`, `tests/schemas/test_core.py`

**Interfaces:**
- Produces:
  - `TestCase(input: str, expected: str | None = None, metadata: dict[str, Any] = {})`
  - `Output(text: str, model: str | None = None, metadata: dict[str, Any] = {})`
  - `Metrics(scores: dict[str, float], notes: dict[str, str] = {})` — `scores` values in `[0,1]`
  - `ScoredResult(case: TestCase, output: Output, metrics: Metrics, composite: float)`
  - `RubricDimension(name: str, description: str, weight: float)`; `Rubric(dimensions: list[RubricDimension])`
  - `Objective(goal: str, weights: dict[str, float] = {}, success_criteria: list[str] = [], invariants: list[str] = [])`

- [ ] **Step 1: Write the failing test**

```python
# tests/schemas/test_core.py
import pytest
from pydantic import ValidationError
from hefesto.schemas.core import (
    TestCase, Output, Metrics, ScoredResult,
    Rubric, RubricDimension, Objective,
)


def test_testcase_minimal():
    c = TestCase(input="2+2?")
    assert c.input == "2+2?" and c.expected is None and c.metadata == {}


def test_metrics_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        Metrics(scores={"clarity": 1.5})


def test_scored_result_composes():
    c = TestCase(input="x")
    o = Output(text="y")
    m = Metrics(scores={"clarity": 0.8})
    r = ScoredResult(case=c, output=o, metrics=m, composite=0.8)
    assert r.composite == 0.8 and r.metrics.scores["clarity"] == 0.8


def test_objective_defaults():
    obj = Objective(goal="be concise")
    assert obj.weights == {} and obj.invariants == []


def test_rubric_dimension_weight():
    rub = Rubric(dimensions=[RubricDimension(name="clarity", description="d", weight=1.0)])
    assert rub.dimensions[0].weight == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/schemas/test_core.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.schemas.core`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/schemas/core.py
"""Shared I/O types for the Hefesto refinement pipeline."""
from typing import Any
from pydantic import BaseModel, Field, field_validator


class TestCase(BaseModel):
    input: str
    expected: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Output(BaseModel):
    text: str
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Metrics(BaseModel):
    scores: dict[str, float] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)

    @field_validator("scores")
    @classmethod
    def _in_unit_range(cls, v: dict[str, float]) -> dict[str, float]:
        for k, s in v.items():
            if not (0.0 <= s <= 1.0):
                raise ValueError(f"score {k}={s} outside [0,1]")
        return v


class ScoredResult(BaseModel):
    case: TestCase
    output: Output
    metrics: Metrics
    composite: float


class RubricDimension(BaseModel):
    name: str
    description: str
    weight: float


class Rubric(BaseModel):
    dimensions: list[RubricDimension] = Field(default_factory=list)


class Objective(BaseModel):
    goal: str
    weights: dict[str, float] = Field(default_factory=dict)
    success_criteria: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
```

```python
# hefesto/schemas/__init__.py
from hefesto.schemas.core import (
    TestCase, Output, Metrics, ScoredResult,
    Rubric, RubricDimension, Objective,
)

__all__ = [
    "TestCase", "Output", "Metrics", "ScoredResult",
    "Rubric", "RubricDimension", "Objective",
]
```

- [ ] **Step 4: Remove the obsolete WASP-shaped schema modules**

```bash
git rm hefesto/schemas/input.py hefesto/schemas/output.py hefesto/schemas/evaluation.py
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/schemas/test_core.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add shared Hefesto schemas, drop WASP-shaped schemas"
```

---

## Task 3: `FakeLLMProvider` test double (`hefesto/llm/fake.py`)

**Files:**
- Create: `hefesto/llm/fake.py`
- Create: `tests/llm/test_fake.py`

**Interfaces:**
- Consumes: `LLMProvider`, `LLMMessage`, `LLMResponse` (Task 1).
- Produces: `FakeLLMProvider(responses: list[str] | None = None, handler: Callable[[list[LLMMessage]], str] | None = None, model: str = "fake-model")`. Each `complete()` returns the next scripted response (cycling) or `handler(messages)`. Records `.calls: list[list[LLMMessage]]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_fake.py
from hefesto.llm.base import LLMMessage
from hefesto.llm.fake import FakeLLMProvider


def test_returns_scripted_responses_in_order():
    p = FakeLLMProvider(responses=["a", "b"])
    msgs = [LLMMessage(role="user", content="x")]
    assert p.complete(msgs).content == "a"
    assert p.complete(msgs).content == "b"
    assert p.complete(msgs).content == "a"  # cycles


def test_handler_sees_messages_and_records_calls():
    p = FakeLLMProvider(handler=lambda msgs: msgs[-1].content.upper())
    out = p.complete([LLMMessage(role="user", content="hi")])
    assert out.content == "HI"
    assert p.calls[-1][-1].content == "hi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_fake.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.llm.fake`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/llm/fake.py
"""Deterministic in-memory LLM provider for tests."""
from collections.abc import Callable
from itertools import cycle
from hefesto.llm.base import LLMProvider, LLMMessage, LLMResponse


class FakeLLMProvider(LLMProvider):
    def __init__(
        self,
        responses: list[str] | None = None,
        handler: Callable[[list[LLMMessage]], str] | None = None,
        model: str = "fake-model",
    ) -> None:
        self._cycle = cycle(responses) if responses else None
        self._handler = handler
        self._model = model
        self.calls: list[list[LLMMessage]] = []

    def complete(self, messages, temperature=0.7, max_tokens=4096) -> LLMResponse:
        self.calls.append(list(messages))
        if self._handler is not None:
            content = self._handler(messages)
        elif self._cycle is not None:
            content = next(self._cycle)
        else:
            content = ""
        return LLMResponse(content=content, model=self._model, usage=None)

    def get_model_name(self) -> str:
        return self._model
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/llm/test_fake.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: add FakeLLMProvider double"
```

---

## Task 4: Per-role config with fail-fast (`hefesto/schemas/config.py`, `hefesto/llm/factory.py`)

**Files:**
- Create/overwrite: `hefesto/schemas/config.py`
- Overwrite: `hefesto/llm/factory.py`
- Create: `tests/schemas/test_config.py`

**Interfaces:**
- Consumes: `LLMProvider`, `DirectProvider`, `OpenRouterProvider`.
- Produces:
  - `ProviderConfig(provider: str, model: str, temperature: float = 0.7, api_key_env: str | None = None)`
  - `JudgeConfig(mode: Literal["pairwise","absolute"] = "pairwise", require_different_model: bool = True, calibration_reference: str | None = None, min_agreement: float = 0.7)`
  - `DatasetConfig(source: Literal["generate","load"] = "generate", count: int = 20, path: str | None = None, freeze: bool = True, test_fraction: float = 0.4)`
  - `LoopConfig(max_iter: int = 5, patience: int = 2, k: int = 3, epsilon_k: float = 1.0, judge_samples: int = 1, target: float | None = None, headroom_min: float = 0.05)`
  - `HefestoConfig(providers: dict[str, ProviderConfig], objective: str, prompt: str, dataset: DatasetConfig, grader: str, judge: JudgeConfig, loop: LoopConfig, store_path: str)`
  - `HefestoConfig.provider_for(role: str) -> ProviderConfig` — resolves role block or `default`; raises `ConfigError(role)` if neither present.
  - `HefestoConfig.from_yaml(path: str) -> HefestoConfig`
  - `create_provider(cfg: ProviderConfig) -> LLMProvider`

- [ ] **Step 1: Write the failing test**

```python
# tests/schemas/test_config.py
import pytest
from hefesto.schemas.config import HefestoConfig, ProviderConfig, ConfigError


def _cfg(providers):
    return HefestoConfig(
        providers=providers, objective="o.yaml", prompt="p.txt",
        grader="llm_judge", store_path="h.db",
    )


def test_role_resolves_from_default():
    c = _cfg({"default": ProviderConfig(provider="openai", model="gpt-x")})
    assert c.provider_for("judge").model == "gpt-x"


def test_role_specific_overrides_default():
    c = _cfg({
        "default": ProviderConfig(provider="openai", model="gpt-x"),
        "judge": ProviderConfig(provider="anthropic", model="claude-y"),
    })
    assert c.provider_for("judge").model == "claude-y"


def test_missing_role_and_default_fails_fast():
    c = _cfg({"runner": ProviderConfig(provider="openai", model="gpt-x")})
    with pytest.raises(ConfigError) as e:
        c.provider_for("judge")
    assert "judge" in str(e.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/schemas/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.schemas.config` (or missing symbols).

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/schemas/config.py
"""Configuration schema — provider-agnostic, fail-fast, per-role."""
from typing import Literal
import yaml
from pydantic import BaseModel, Field


class ConfigError(Exception):
    """Raised when a required provider role is unresolved."""


class ProviderConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.7
    api_key_env: str | None = None


class JudgeConfig(BaseModel):
    mode: Literal["pairwise", "absolute"] = "pairwise"
    require_different_model: bool = True
    calibration_reference: str | None = None
    min_agreement: float = 0.7


class DatasetConfig(BaseModel):
    source: Literal["generate", "load"] = "generate"
    count: int = 20
    path: str | None = None
    freeze: bool = True
    test_fraction: float = 0.4


class LoopConfig(BaseModel):
    max_iter: int = 5
    patience: int = 2
    k: int = 3
    epsilon_k: float = 1.0
    judge_samples: int = 1
    target: float | None = None
    headroom_min: float = 0.05


class HefestoConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    objective: str
    prompt: str
    dataset: DatasetConfig = Field(default_factory=DatasetConfig)
    grader: str = "llm_judge"
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    store_path: str = "hefesto.db"

    def provider_for(self, role: str) -> ProviderConfig:
        if role in self.providers:
            return self.providers[role]
        if "default" in self.providers:
            return self.providers["default"]
        raise ConfigError(f"no provider configured for role '{role}' (and no 'default')")

    @classmethod
    def from_yaml(cls, path: str) -> "HefestoConfig":
        with open(path) as f:
            return cls.model_validate(yaml.safe_load(f))
```

```python
# hefesto/llm/factory.py
"""Create an LLMProvider from a ProviderConfig. No baked-in defaults."""
from hefesto.llm.base import LLMProvider
from hefesto.llm.openrouter import OpenRouterProvider
from hefesto.llm.direct import DirectProvider
from hefesto.schemas.config import ProviderConfig


def create_provider(cfg: ProviderConfig) -> LLMProvider:
    if cfg.provider == "openrouter":
        return OpenRouterProvider(model=cfg.model, api_key_env=cfg.api_key_env)
    if cfg.provider in ("openai", "anthropic", "google", "litellm"):
        return DirectProvider(model=cfg.model, api_key_env=cfg.api_key_env)
    raise ValueError(f"Unsupported LLM provider: {cfg.provider}")
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/schemas/test_config.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: per-role provider config with fail-fast resolution"
```

---

## Task 5: Dataset split (`hefesto/dataset/split.py`)

**Files:**
- Create: `hefesto/dataset/__init__.py`, `hefesto/dataset/base.py`, `hefesto/dataset/split.py`
- Create: `tests/dataset/__init__.py`, `tests/dataset/test_split.py`

**Interfaces:**
- Consumes: `TestCase` (Task 2).
- Produces:
  - `DatasetSplit(dev: list[TestCase], test: list[TestCase])` (pydantic model)
  - `split_cases(cases: list[TestCase], test_fraction: float) -> DatasetSplit` — deterministic (no RNG): the last `round(n*test_fraction)` cases go to `test`, the rest to `dev`; guarantees ≥1 in each when `n >= 2`.
  - `DatasetSource` protocol: `provide() -> DatasetSplit`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dataset/test_split.py
import pytest
from hefesto.schemas.core import TestCase
from hefesto.dataset.split import split_cases


def _cases(n):
    return [TestCase(input=str(i)) for i in range(n)]


def test_split_fraction_sizes():
    s = split_cases(_cases(10), test_fraction=0.4)
    assert len(s.test) == 4 and len(s.dev) == 6


def test_split_is_deterministic_tail_is_test():
    s = split_cases(_cases(5), test_fraction=0.4)  # round(2.0)=2
    assert [c.input for c in s.test] == ["3", "4"]
    assert [c.input for c in s.dev] == ["0", "1", "2"]


def test_split_guarantees_one_each_for_small_sets():
    s = split_cases(_cases(2), test_fraction=0.9)
    assert len(s.dev) == 1 and len(s.test) == 1


def test_split_rejects_single_case():
    with pytest.raises(ValueError):
        split_cases(_cases(1), test_fraction=0.4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dataset/test_split.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.dataset.split`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/dataset/base.py
from typing import Protocol
from pydantic import BaseModel, Field
from hefesto.schemas.core import TestCase


class DatasetSplit(BaseModel):
    dev: list[TestCase] = Field(default_factory=list)
    test: list[TestCase] = Field(default_factory=list)


class DatasetSource(Protocol):
    def provide(self) -> DatasetSplit: ...
```

```python
# hefesto/dataset/split.py
from hefesto.schemas.core import TestCase
from hefesto.dataset.base import DatasetSplit


def split_cases(cases: list[TestCase], test_fraction: float) -> DatasetSplit:
    n = len(cases)
    if n < 2:
        raise ValueError("need at least 2 cases to form a dev/test split")
    n_test = round(n * test_fraction)
    n_test = max(1, min(n_test, n - 1))  # at least 1 in each split
    return DatasetSplit(dev=cases[: n - n_test], test=cases[n - n_test :])
```

```python
# hefesto/dataset/__init__.py
from hefesto.dataset.base import DatasetSplit, DatasetSource
from hefesto.dataset.split import split_cases

__all__ = ["DatasetSplit", "DatasetSource", "split_cases"]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/dataset/test_split.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: deterministic dev/test split"
```

---

## Task 6: Dataset loading (`hefesto/dataset/load.py`)

**Files:**
- Create: `hefesto/dataset/load.py`
- Create: `tests/dataset/test_load.py`

**Interfaces:**
- Consumes: `TestCase`, `DatasetSplit`, `split_cases` (Task 5).
- Produces: `LoadedDataset(path: str, test_fraction: float)` with `.provide() -> DatasetSplit`. Reads `.jsonl` (one JSON object per line, keys `input`, optional `expected`, `metadata`). Each line → `TestCase`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dataset/test_load.py
from hefesto.dataset.load import LoadedDataset


def test_loads_jsonl(tmp_path):
    p = tmp_path / "cases.jsonl"
    p.write_text(
        '{"input": "a", "expected": "1"}\n'
        '{"input": "b"}\n'
        '{"input": "c"}\n'
        '{"input": "d"}\n'
    )
    split = LoadedDataset(path=str(p), test_fraction=0.5).provide()
    assert len(split.dev) == 2 and len(split.test) == 2
    assert split.dev[0].input == "a" and split.dev[0].expected == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dataset/test_load.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.dataset.load`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/dataset/load.py
import json
from hefesto.schemas.core import TestCase
from hefesto.dataset.base import DatasetSplit
from hefesto.dataset.split import split_cases


class LoadedDataset:
    def __init__(self, path: str, test_fraction: float) -> None:
        self.path = path
        self.test_fraction = test_fraction

    def provide(self) -> DatasetSplit:
        cases: list[TestCase] = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                cases.append(TestCase.model_validate(json.loads(line)))
        return split_cases(cases, self.test_fraction)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/dataset/test_load.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: load eval cases from jsonl"
```

---

## Task 7: Dataset generation (`hefesto/dataset/generate.py`)

**Files:**
- Create: `hefesto/dataset/generate.py`
- Create: `tests/dataset/test_generate.py`

**Interfaces:**
- Consumes: `LLMProvider`, `LLMMessage`, `Objective`, `TestCase`, `DatasetSplit`, `split_cases`.
- Produces: `GeneratedDataset(provider: LLMProvider, objective: Objective, count: int, test_fraction: float)` with `.provide() -> DatasetSplit`. Prompts the provider for a JSON array of input strings; parses with `parse_cases(text: str) -> list[TestCase]` (tolerant of markdown code fences). Raises `ValueError` if fewer than 2 cases parse.

- [ ] **Step 1: Write the failing test**

```python
# tests/dataset/test_generate.py
import pytest
from hefesto.schemas.core import Objective
from hefesto.llm.fake import FakeLLMProvider
from hefesto.dataset.generate import GeneratedDataset, parse_cases


def test_parse_cases_strips_fences():
    text = '```json\n["what is 2+2?", "capital of France?"]\n```'
    cases = parse_cases(text)
    assert [c.input for c in cases] == ["what is 2+2?", "capital of France?"]


def test_generate_provides_split():
    fake = FakeLLMProvider(responses=['["a","b","c","d"]'])
    ds = GeneratedDataset(
        provider=fake, objective=Objective(goal="g"), count=4, test_fraction=0.5,
    )
    split = ds.provide()
    assert len(split.dev) == 2 and len(split.test) == 2


def test_generate_rejects_too_few():
    fake = FakeLLMProvider(responses=['["only one"]'])
    ds = GeneratedDataset(
        provider=fake, objective=Objective(goal="g"), count=4, test_fraction=0.5,
    )
    with pytest.raises(ValueError):
        ds.provide()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dataset/test_generate.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.dataset.generate`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/dataset/generate.py
import json
import re
from hefesto.llm.base import LLMProvider, LLMMessage
from hefesto.schemas.core import Objective, TestCase
from hefesto.dataset.base import DatasetSplit
from hefesto.dataset.split import split_cases

_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$", re.MULTILINE)


def parse_cases(text: str) -> list[TestCase]:
    cleaned = _FENCE.sub("", text).strip()
    data = json.loads(cleaned)
    return [TestCase(input=str(item)) for item in data]


class GeneratedDataset:
    def __init__(self, provider: LLMProvider, objective: Objective,
                 count: int, test_fraction: float) -> None:
        self.provider = provider
        self.objective = objective
        self.count = count
        self.test_fraction = test_fraction

    def provide(self) -> DatasetSplit:
        prompt = (
            f"Generate {self.count} diverse, realistic test inputs for a prompt "
            f"whose objective is: {self.objective.goal}\n"
            "Return ONLY a JSON array of input strings."
        )
        resp = self.provider.complete([LLMMessage(role="user", content=prompt)])
        cases = parse_cases(resp.content)
        if len(cases) < 2:
            raise ValueError("dataset generation produced fewer than 2 cases")
        return split_cases(cases, self.test_fraction)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/dataset/test_generate.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: generate eval dataset from objective via LLM"
```

---

## Task 8: Runner — base + echo + LLM (`hefesto/runner/`)

**Files:**
- Create: `hefesto/runner/__init__.py`, `hefesto/runner/base.py`, `hefesto/runner/echo_runner.py`, `hefesto/runner/llm_runner.py`
- Create: `tests/runner/__init__.py`, `tests/runner/test_runner.py`

**Interfaces:**
- Consumes: `LLMProvider`, `LLMMessage`, `TestCase`, `Output`.
- Produces:
  - `Runner` protocol: `run(prompt: str, case: TestCase) -> Output`.
  - `fill_placeholders(prompt: str, case: TestCase) -> str` — replaces `{{input}}` with `case.input` and `{{context}}` with `case.metadata.get("context", "")`.
  - `EchoRunner()` — returns `Output(text=fill_placeholders(prompt, case))` (non-LLM, seam-proof).
  - `LLMRunner(provider: LLMProvider)` — sends the filled prompt as a user message, returns `Output(text=resp.content, model=resp.model)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/runner/test_runner.py
from hefesto.schemas.core import TestCase
from hefesto.llm.fake import FakeLLMProvider
from hefesto.runner.base import fill_placeholders
from hefesto.runner.echo_runner import EchoRunner
from hefesto.runner.llm_runner import LLMRunner


def test_fill_placeholders_input_and_context():
    case = TestCase(input="42", metadata={"context": "ctx"})
    out = fill_placeholders("Q: {{input}} / {{context}}", case)
    assert out == "Q: 42 / ctx"


def test_echo_runner_returns_filled_prompt():
    out = EchoRunner().run("echo {{input}}", TestCase(input="hi"))
    assert out.text == "echo hi"


def test_llm_runner_sends_filled_prompt():
    fake = FakeLLMProvider(handler=lambda msgs: f"ANSWER<{msgs[-1].content}>")
    out = LLMRunner(provider=fake).run("solve {{input}}", TestCase(input="2+2"))
    assert out.text == "ANSWER<solve 2+2>"
    assert out.model == "fake-model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runner/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.runner.base`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/runner/base.py
from typing import Protocol
from hefesto.schemas.core import TestCase, Output


def fill_placeholders(prompt: str, case: TestCase) -> str:
    return (
        prompt
        .replace("{{input}}", case.input)
        .replace("{{context}}", str(case.metadata.get("context", "")))
    )


class Runner(Protocol):
    def run(self, prompt: str, case: TestCase) -> Output: ...
```

```python
# hefesto/runner/echo_runner.py
from hefesto.schemas.core import TestCase, Output
from hefesto.runner.base import fill_placeholders


class EchoRunner:
    def run(self, prompt: str, case: TestCase) -> Output:
        return Output(text=fill_placeholders(prompt, case))
```

```python
# hefesto/runner/llm_runner.py
from hefesto.llm.base import LLMProvider, LLMMessage
from hefesto.schemas.core import TestCase, Output
from hefesto.runner.base import fill_placeholders


class LLMRunner:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def run(self, prompt: str, case: TestCase) -> Output:
        filled = fill_placeholders(prompt, case)
        resp = self.provider.complete([LLMMessage(role="user", content=filled)])
        return Output(text=resp.content, model=resp.model)
```

```python
# hefesto/runner/__init__.py
from hefesto.runner.base import Runner, fill_placeholders
from hefesto.runner.echo_runner import EchoRunner
from hefesto.runner.llm_runner import LLMRunner

__all__ = ["Runner", "fill_placeholders", "EchoRunner", "LLMRunner"]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/runner/test_runner.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: runner layer (placeholder fill, echo, llm)"
```

---

## Task 9: Score aggregation (`hefesto/score/aggregate.py`)

**Files:**
- Create: `hefesto/score/__init__.py`, `hefesto/score/aggregate.py`
- Create: `tests/score/__init__.py`, `tests/score/test_aggregate.py`

**Interfaces:**
- Consumes: `Metrics` (Task 2).
- Produces: `composite_score(metrics: Metrics, weights: dict[str, float]) -> float` implementing the Grader↔Score contract: composite = Σ `weight[k]·score[k]` over weighted keys, renormalized so weights sum to 1; a weighted key missing from `metrics.scores` contributes 0; an unweighted metric key is ignored. If `weights` is empty, return the simple mean of `metrics.scores` (or 0.0 if no scores).

- [ ] **Step 1: Write the failing test**

```python
# tests/score/test_aggregate.py
from hefesto.schemas.core import Metrics
from hefesto.score.aggregate import composite_score


def test_weighted_average_renormalizes():
    m = Metrics(scores={"a": 1.0, "b": 0.0})
    assert composite_score(m, {"a": 3.0, "b": 1.0}) == 0.75  # (3*1+1*0)/4


def test_missing_weighted_key_scores_zero():
    m = Metrics(scores={"a": 1.0})
    assert composite_score(m, {"a": 1.0, "b": 1.0}) == 0.5  # b missing -> 0


def test_unweighted_metric_ignored():
    m = Metrics(scores={"a": 1.0, "junk": 0.0})
    assert composite_score(m, {"a": 1.0}) == 1.0


def test_no_weights_is_mean():
    m = Metrics(scores={"a": 0.4, "b": 0.6})
    assert composite_score(m, {}) == 0.5


def test_empty_everything_is_zero():
    assert composite_score(Metrics(scores={}), {}) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/score/test_aggregate.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.score.aggregate`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/score/aggregate.py
from hefesto.schemas.core import Metrics


def composite_score(metrics: Metrics, weights: dict[str, float]) -> float:
    if not weights:
        scores = list(metrics.scores.values())
        return sum(scores) / len(scores) if scores else 0.0
    total_w = sum(weights.values())
    if total_w == 0:
        return 0.0
    acc = sum(w * metrics.scores.get(k, 0.0) for k, w in weights.items())
    return acc / total_w
```

```python
# hefesto/score/__init__.py
from hefesto.score.aggregate import composite_score

__all__ = ["composite_score"]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/score/test_aggregate.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: composite score aggregation with key contract"
```

---

## Task 10: LLM judge grader (`hefesto/grader/llm_judge.py`)

**Files:**
- Create: `hefesto/grader/__init__.py`, `hefesto/grader/base.py`, `hefesto/grader/llm_judge.py`
- Create: `tests/grader/__init__.py`, `tests/grader/test_llm_judge.py`

**Interfaces:**
- Consumes: `LLMProvider`, `LLMMessage`, `TestCase`, `Output`, `Metrics`, `Objective`, `Rubric`.
- Produces:
  - `Grader` protocol: `grade(case: TestCase, output: Output, objective: Objective) -> Metrics`.
  - `normalize_absolute(raw: float) -> float` — `(raw-1)/9` clamped to `[0,1]`.
  - `LLMJudge(provider: LLMProvider, rubric: Rubric)` — `grade()` asks the provider to score each rubric dimension 1–10 as a JSON object keyed by dimension name; parses, normalizes each to `[0,1]`, returns `Metrics`. Dimensions not returned default to 0.

- [ ] **Step 1: Write the failing test**

```python
# tests/grader/test_llm_judge.py
from hefesto.schemas.core import TestCase, Output, Objective, Rubric, RubricDimension
from hefesto.llm.fake import FakeLLMProvider
from hefesto.grader.llm_judge import LLMJudge, normalize_absolute


def test_normalize_absolute():
    assert normalize_absolute(1) == 0.0
    assert normalize_absolute(10) == 1.0
    assert normalize_absolute(100) == 1.0  # clamped


def test_judge_returns_normalized_metrics():
    fake = FakeLLMProvider(responses=['{"clarity": 10, "accuracy": 1}'])
    rubric = Rubric(dimensions=[
        RubricDimension(name="clarity", description="d", weight=1.0),
        RubricDimension(name="accuracy", description="d", weight=1.0),
    ])
    m = LLMJudge(provider=fake, rubric=rubric).grade(
        TestCase(input="x"), Output(text="y"), Objective(goal="g"),
    )
    assert m.scores == {"clarity": 1.0, "accuracy": 0.0}


def test_missing_dimension_defaults_zero():
    fake = FakeLLMProvider(responses=['{"clarity": 10}'])
    rubric = Rubric(dimensions=[
        RubricDimension(name="clarity", description="d", weight=1.0),
        RubricDimension(name="accuracy", description="d", weight=1.0),
    ])
    m = LLMJudge(provider=fake, rubric=rubric).grade(
        TestCase(input="x"), Output(text="y"), Objective(goal="g"),
    )
    assert m.scores["accuracy"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/grader/test_llm_judge.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.grader.llm_judge`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/grader/base.py
from typing import Protocol
from hefesto.schemas.core import TestCase, Output, Objective, Metrics


class Grader(Protocol):
    def grade(self, case: TestCase, output: Output, objective: Objective) -> Metrics: ...
```

```python
# hefesto/grader/llm_judge.py
import json
import re
from hefesto.llm.base import LLMProvider, LLMMessage
from hefesto.schemas.core import TestCase, Output, Objective, Metrics, Rubric

_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$", re.MULTILINE)


def normalize_absolute(raw: float) -> float:
    return max(0.0, min(1.0, (raw - 1) / 9))


class LLMJudge:
    def __init__(self, provider: LLMProvider, rubric: Rubric) -> None:
        self.provider = provider
        self.rubric = rubric

    def grade(self, case: TestCase, output: Output, objective: Objective) -> Metrics:
        dims = ", ".join(d.name for d in self.rubric.dimensions)
        prompt = (
            f"Objective: {objective.goal}\n"
            f"Input: {case.input}\nOutput: {output.text}\n"
            f"Score each dimension ({dims}) from 1-10. "
            "Return ONLY a JSON object keyed by dimension name."
        )
        resp = self.provider.complete([LLMMessage(role="user", content=prompt)])
        raw = json.loads(_FENCE.sub("", resp.content).strip())
        scores = {
            d.name: normalize_absolute(float(raw.get(d.name, 1)))
            for d in self.rubric.dimensions
        }
        return Metrics(scores=scores)
```

```python
# hefesto/grader/__init__.py
from hefesto.grader.base import Grader
from hefesto.grader.llm_judge import LLMJudge, normalize_absolute

__all__ = ["Grader", "LLMJudge", "normalize_absolute"]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/grader/test_llm_judge.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: LLM-judge grader (absolute scoring, normalized)"
```

---

## Task 11: Intake — signal tier + headroom (`hefesto/core/intake.py`)

**Files:**
- Create: `hefesto/core/intake.py` (leave existing `hefesto/core/*.py` from the old package untouched for now; they are removed in Task 17)
- Create: `tests/core/__init__.py`, `tests/core/test_intake.py`

**Interfaces:**
- Consumes: `Objective`.
- Produces:
  - `classify_objective(objective: Objective, has_user_metrics: bool) -> str` returning `"real" | "verifiable" | "judge"`. Rules: if `has_user_metrics` → `"real"`; elif the goal text contains any oracle keyword (`compile`, `run`, `exact`, `regex`, `schema`, `valid json`, `cite`, `citation`, `fact`) → `"verifiable"`; else `"judge"`.
  - `no_headroom(champion_score: float, target: float | None, headroom_min: float) -> bool` — True when `target is not None and champion_score >= target - headroom_min`, OR `champion_score >= 1.0 - headroom_min`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_intake.py
from hefesto.schemas.core import Objective
from hefesto.core.intake import classify_objective, no_headroom


def test_real_when_user_metrics():
    assert classify_objective(Objective(goal="be nice"), has_user_metrics=True) == "real"


def test_verifiable_on_oracle_keyword():
    assert classify_objective(Objective(goal="must be valid json"), False) == "verifiable"


def test_judge_default():
    assert classify_objective(Objective(goal="be more persuasive"), False) == "judge"


def test_no_headroom_against_target():
    assert no_headroom(0.97, target=1.0, headroom_min=0.05) is True
    assert no_headroom(0.90, target=1.0, headroom_min=0.05) is False


def test_no_headroom_against_ceiling():
    assert no_headroom(0.98, target=None, headroom_min=0.05) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_intake.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.core.intake`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/core/intake.py
from hefesto.schemas.core import Objective

_ORACLE_KEYWORDS = (
    "compile", "run", "exact", "regex", "schema",
    "valid json", "cite", "citation", "fact",
)


def classify_objective(objective: Objective, has_user_metrics: bool) -> str:
    if has_user_metrics:
        return "real"
    goal = objective.goal.lower()
    if any(k in goal for k in _ORACLE_KEYWORDS):
        return "verifiable"
    return "judge"


def no_headroom(champion_score: float, target: float | None, headroom_min: float) -> bool:
    if target is not None and champion_score >= target - headroom_min:
        return True
    return champion_score >= 1.0 - headroom_min
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/core/test_intake.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: intake signal-tier classification + headroom check"
```

---

## Task 12: Judge calibration (`hefesto/core/calibrate.py`)

**Files:**
- Create: `hefesto/core/calibrate.py`
- Create: `tests/core/test_calibrate.py`

**Interfaces:**
- Consumes: `Grader`, `TestCase`, `Output`, `Objective`, `Metrics`, `composite_score`.
- Produces:
  - `ReferenceExample(case: TestCase, output: Output, label: Literal["good","bad"])` (pydantic).
  - `calibrate_judge(grader, objective, weights, reference, *, good_threshold=0.6, bad_threshold=0.4) -> float` — for each reference example, grade it and compute its composite; a "good" example "agrees" if composite ≥ good_threshold, a "bad" one if composite ≤ bad_threshold. Returns the agreement fraction in `[0,1]`. Empty reference → `0.0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_calibrate.py
from hefesto.schemas.core import TestCase, Output, Objective, Rubric, RubricDimension
from hefesto.llm.fake import FakeLLMProvider
from hefesto.grader.llm_judge import LLMJudge
from hefesto.core.calibrate import calibrate_judge, ReferenceExample


def _judge(scripted):
    rubric = Rubric(dimensions=[RubricDimension(name="q", description="d", weight=1.0)])
    return LLMJudge(provider=FakeLLMProvider(responses=scripted), rubric=rubric)


def test_perfect_agreement():
    # good example judged 10 -> 1.0 (agrees); bad judged 1 -> 0.0 (agrees)
    judge = _judge(['{"q": 10}', '{"q": 1}'])
    ref = [
        ReferenceExample(case=TestCase(input="a"), output=Output(text="good"), label="good"),
        ReferenceExample(case=TestCase(input="b"), output=Output(text="bad"), label="bad"),
    ]
    agree = calibrate_judge(judge, Objective(goal="g"), {"q": 1.0}, ref)
    assert agree == 1.0


def test_half_agreement():
    # good judged 1 -> 0.0 (disagrees); bad judged 1 -> 0.0 (agrees)
    judge = _judge(['{"q": 1}', '{"q": 1}'])
    ref = [
        ReferenceExample(case=TestCase(input="a"), output=Output(text="g"), label="good"),
        ReferenceExample(case=TestCase(input="b"), output=Output(text="b"), label="bad"),
    ]
    assert calibrate_judge(judge, Objective(goal="g"), {"q": 1.0}, ref) == 0.5


def test_empty_reference_is_zero():
    judge = _judge(['{"q": 5}'])
    assert calibrate_judge(judge, Objective(goal="g"), {"q": 1.0}, []) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_calibrate.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.core.calibrate`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/core/calibrate.py
from typing import Literal
from pydantic import BaseModel
from hefesto.schemas.core import TestCase, Output, Objective
from hefesto.grader.base import Grader
from hefesto.score.aggregate import composite_score


class ReferenceExample(BaseModel):
    case: TestCase
    output: Output
    label: Literal["good", "bad"]


def calibrate_judge(
    grader: Grader,
    objective: Objective,
    weights: dict[str, float],
    reference: list[ReferenceExample],
    *,
    good_threshold: float = 0.6,
    bad_threshold: float = 0.4,
) -> float:
    if not reference:
        return 0.0
    agree = 0
    for ex in reference:
        metrics = grader.grade(ex.case, ex.output, objective)
        score = composite_score(metrics, weights)
        if ex.label == "good" and score >= good_threshold:
            agree += 1
        elif ex.label == "bad" and score <= bad_threshold:
            agree += 1
    return agree / len(reference)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/core/test_calibrate.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: judge calibration vs reference set"
```

---

## Task 13: Contrast selection (`hefesto/refiner/select.py`)

**Files:**
- Create: `hefesto/refiner/__init__.py`, `hefesto/refiner/select.py`
- Create: `tests/refiner/__init__.py`, `tests/refiner/test_select.py`

**Interfaces:**
- Consumes: `ScoredResult`.
- Produces: `select_contrast(results: list[ScoredResult], k: int) -> list[ScoredResult]` — sorts by `composite`, returns the top-k (best) followed by the bottom-k (worst), de-duplicated by identity when the lists overlap (small datasets). Order: best→worst, no case appears twice.

- [ ] **Step 1: Write the failing test**

```python
# tests/refiner/test_select.py
from hefesto.schemas.core import TestCase, Output, Metrics, ScoredResult
from hefesto.refiner.select import select_contrast


def _r(name, score):
    return ScoredResult(
        case=TestCase(input=name), output=Output(text=name),
        metrics=Metrics(scores={"q": score}), composite=score,
    )


def test_returns_best_then_worst():
    results = [_r("a", 0.1), _r("b", 0.9), _r("c", 0.5), _r("d", 0.3)]
    out = select_contrast(results, k=1)
    assert [r.case.input for r in out] == ["b", "a"]


def test_dedups_when_overlap():
    results = [_r("a", 0.1), _r("b", 0.9)]
    out = select_contrast(results, k=2)  # best 2 + worst 2 overlap fully
    assert [r.case.input for r in out] == ["b", "a"]  # each once
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/refiner/test_select.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.refiner.select`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/refiner/select.py
from hefesto.schemas.core import ScoredResult


def select_contrast(results: list[ScoredResult], k: int) -> list[ScoredResult]:
    ranked = sorted(results, key=lambda r: r.composite, reverse=True)
    best = ranked[:k]
    worst = ranked[-k:] if k < len(ranked) else ranked
    ordered: list[ScoredResult] = []
    seen: set[int] = set()
    for r in best + list(reversed(worst)):
        if id(r) not in seen:
            seen.add(id(r))
            ordered.append(r)
    return ordered
```

```python
# hefesto/refiner/__init__.py
from hefesto.refiner.select import select_contrast

__all__ = ["select_contrast"]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/refiner/test_select.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: select_contrast best/worst case picker"
```

---

## Task 14: Invariant checking (`hefesto/refiner/invariants.py`)

**Files:**
- Create: `hefesto/refiner/invariants.py`
- Create: `tests/refiner/test_invariants.py`

**Interfaces:**
- Produces: `check_invariants(candidate: str, invariants: list[str]) -> bool` — True iff every invariant string appears verbatim (substring, byte-for-byte) in `candidate`. Empty invariants → True.

- [ ] **Step 1: Write the failing test**

```python
# tests/refiner/test_invariants.py
from hefesto.refiner.invariants import check_invariants


def test_passes_when_all_present():
    assert check_invariants("foo BAR baz", ["BAR"]) is True


def test_fails_when_altered():
    assert check_invariants("foo Bar baz", ["BAR"]) is False


def test_empty_invariants_pass():
    assert check_invariants("anything", []) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/refiner/test_invariants.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.refiner.invariants`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/refiner/invariants.py
def check_invariants(candidate: str, invariants: list[str]) -> bool:
    return all(inv in candidate for inv in invariants)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/refiner/test_invariants.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: hard invariant byte-check"
```

---

## Task 15: Refiner (`hefesto/refiner/refiner.py`)

**Files:**
- Create: `hefesto/refiner/refiner.py`
- Modify: `hefesto/refiner/__init__.py` (re-export `Refiner`, `rule_density`)
- Create: `tests/refiner/test_refiner.py`

**Interfaces:**
- Consumes: `LLMProvider`, `LLMMessage`, `ScoredResult`, `Objective`.
- Produces:
  - `rule_density(text: str) -> int` — counts nested-rule markers matching `\d+\.[a-z]` (e.g. `1.a`).
  - `Refiner(provider: LLMProvider)` with `propose(champion_prompt: str, selected_cases: list[ScoredResult], objective: Objective) -> str`. Builds a meta-prompt (system text = `REFINEMENT_SYSTEM_PROMPT`, which mandates few-shot examples over rules and forbids growing nested rule density), embeds each selected case's `(input, output, composite)`, calls the provider, returns the candidate text. `REFINEMENT_SYSTEM_PROMPT` is a module constant.

- [ ] **Step 1: Write the failing test**

```python
# tests/refiner/test_refiner.py
from hefesto.schemas.core import TestCase, Output, Metrics, ScoredResult, Objective
from hefesto.llm.fake import FakeLLMProvider
from hefesto.refiner.refiner import Refiner, rule_density, REFINEMENT_SYSTEM_PROMPT


def test_rule_density_counts_nested_markers():
    assert rule_density("1.a do this 2.b do that") == 2
    assert rule_density("plain guidance, no nesting") == 0


def test_propose_returns_candidate_and_uses_system_prompt():
    captured = {}

    def handler(msgs):
        captured["system"] = msgs[0].content
        captured["user"] = msgs[-1].content
        return "REFINED PROMPT"

    fake = FakeLLMProvider(handler=handler)
    cases = [ScoredResult(
        case=TestCase(input="2+2"), output=Output(text="5"),
        metrics=Metrics(scores={"q": 0.0}), composite=0.0,
    )]
    out = Refiner(provider=fake).propose("OLD PROMPT", cases, Objective(goal="be correct"))
    assert out == "REFINED PROMPT"
    assert captured["system"] == REFINEMENT_SYSTEM_PROMPT
    assert "2+2" in captured["user"] and "OLD PROMPT" in captured["user"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/refiner/test_refiner.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.refiner.refiner`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/refiner/refiner.py
import re
from hefesto.llm.base import LLMProvider, LLMMessage
from hefesto.schemas.core import ScoredResult, Objective

REFINEMENT_SYSTEM_PROMPT = (
    "You improve prompts. Prefer adding a concrete few-shot example drawn from a "
    "real failing case over adding rules. Do NOT add nested legalistic rules "
    "(e.g. 1.a, 1.b); prefer conceptual guidance or examples. Keep edits concise. "
    "Return ONLY the full revised prompt text."
)

_NESTED_RULE = re.compile(r"\d+\.[a-z]")


def rule_density(text: str) -> int:
    return len(_NESTED_RULE.findall(text))


class Refiner:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def propose(
        self,
        champion_prompt: str,
        selected_cases: list[ScoredResult],
        objective: Objective,
    ) -> str:
        examples = "\n".join(
            f"- input={r.case.input!r} output={r.output.text!r} score={r.composite:.2f}"
            for r in selected_cases
        )
        user = (
            f"Objective: {objective.goal}\n\n"
            f"Current prompt:\n{champion_prompt}\n\n"
            f"Best/worst cases:\n{examples}\n\n"
            "Propose an improved prompt."
        )
        resp = self.provider.complete([
            LLMMessage(role="system", content=REFINEMENT_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user),
        ])
        return resp.content
```

```python
# hefesto/refiner/__init__.py
from hefesto.refiner.select import select_contrast
from hefesto.refiner.invariants import check_invariants
from hefesto.refiner.refiner import Refiner, rule_density, REFINEMENT_SYSTEM_PROMPT

__all__ = [
    "select_contrast", "check_invariants",
    "Refiner", "rule_density", "REFINEMENT_SYSTEM_PROMPT",
]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/refiner/test_refiner.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: refiner with few-shot meta-prompt and rule-density lint"
```

---

## Task 16: Text diff (`hefesto/diff/text_diff.py`)

**Files:**
- Create: `hefesto/diff/__init__.py`, `hefesto/diff/text_diff.py`
- Delete: `hefesto/core/differ.py` (structured PromptDiff, replaced)
- Create: `tests/diff/__init__.py`, `tests/diff/test_text_diff.py`

**Interfaces:**
- Produces: `text_diff(old: str, new: str) -> str` — unified diff string (using `difflib.unified_diff`, `fromfile="champion"`, `tofile="candidate"`, `lineterm=""`). Identical inputs → empty string.

- [ ] **Step 1: Write the failing test**

```python
# tests/diff/test_text_diff.py
from hefesto.diff.text_diff import text_diff


def test_identical_is_empty():
    assert text_diff("same\n", "same\n") == ""


def test_shows_added_and_removed_lines():
    d = text_diff("a\nb\n", "a\nc\n")
    assert "-b" in d and "+c" in d
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/diff/test_text_diff.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.diff.text_diff`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/diff/text_diff.py
import difflib


def text_diff(old: str, new: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile="champion", tofile="candidate", lineterm="",
    )
    return "\n".join(lines)
```

```python
# hefesto/diff/__init__.py
from hefesto.diff.text_diff import text_diff

__all__ = ["text_diff"]
```

- [ ] **Step 4: Remove the obsolete structured differ**

```bash
git rm hefesto/core/differ.py
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/diff/test_text_diff.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: flat full-text prompt diff, drop structured differ"
```

---

## Task 17: Storage models + repository (`hefesto/store/`)

**Files:**
- Overwrite: `hefesto/store/models.py`
- Overwrite: `hefesto/store/repository.py`
- Delete the now-orphaned old core modules replaced by this plan: `hefesto/core/analyzer.py`, `hefesto/core/evaluator.py`, `hefesto/core/generator.py`, `hefesto/core/selector.py`, `hefesto/core/importer.py`
- Create: `tests/store/__init__.py`, `tests/store/test_repository.py`

**Interfaces:**
- Produces:
  - SQLAlchemy models (`Base`): `PromptRecord(id, name, version, parent_version, prompt_text, created_at)`; `EvaluationRecord(id, prompt_version, composite_score, metrics_json, judge_agreement, created_at)`; `RefinementRecord(id, parent_version, candidate_version, promoted, delta, reason, reasoning, diff, created_at)`; `RunRecord(id, prompt_version, case_input, output_text, metrics_json, created_at)`.
  - `Repository(db_path: str)` with `init_db()`, `save_prompt(name, version, prompt_text, parent_version=None) -> int`, `save_evaluation(prompt_version, composite_score, metrics, judge_agreement=None)`, `save_refinement(parent_version, candidate_version, promoted, delta, reason, reasoning="", diff="")`, `get_refinements() -> list[RefinementRecord]`, `get_evaluations() -> list[EvaluationRecord]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/store/test_repository.py
from hefesto.store.repository import Repository


def test_persists_prompt_and_refinements(tmp_path):
    repo = Repository(db_path=str(tmp_path / "h.db"))
    repo.init_db()
    repo.save_prompt(name="p", version="v1", prompt_text="hello")
    repo.save_refinement(
        parent_version="v1", candidate_version="v2",
        promoted=False, delta=-0.1, reason="no_improvement",
    )
    repo.save_refinement(
        parent_version="v1", candidate_version="v3",
        promoted=True, delta=0.2, reason="promoted",
    )
    refs = repo.get_refinements()
    assert len(refs) == 2
    assert {r.promoted for r in refs} == {True, False}  # rejected attempts persisted


def test_saves_evaluation_with_agreement(tmp_path):
    repo = Repository(db_path=str(tmp_path / "h.db"))
    repo.init_db()
    repo.save_evaluation(prompt_version="v1", composite_score=0.7,
                         metrics={"clarity": 0.7}, judge_agreement=0.82)
    ev = repo.get_evaluations()
    assert ev[0].composite_score == 0.7 and ev[0].judge_agreement == 0.82
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_repository.py -v`
Expected: FAIL (old `store/repository.py` lacks these methods / models mismatch).

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/store/models.py
from datetime import datetime
from typing import Any
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PromptRecord(Base):
    __tablename__ = "prompts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[str] = mapped_column(String(50))
    parent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvaluationRecord(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prompt_version: Mapped[str] = mapped_column(String(50), index=True)
    composite_score: Mapped[float] = mapped_column(Float)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    judge_agreement: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RefinementRecord(Base):
    __tablename__ = "refinements"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_version: Mapped[str] = mapped_column(String(50), index=True)
    candidate_version: Mapped[str] = mapped_column(String(50))
    promoted: Mapped[bool] = mapped_column(Boolean)
    delta: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(64))
    reasoning: Mapped[str] = mapped_column(Text, default="")
    diff: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RunRecord(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prompt_version: Mapped[str] = mapped_column(String(50), index=True)
    case_input: Mapped[str] = mapped_column(Text)
    output_text: Mapped[str] = mapped_column(Text)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

```python
# hefesto/store/repository.py
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from hefesto.store.models import (
    Base, PromptRecord, EvaluationRecord, RefinementRecord,
)


class Repository:
    def __init__(self, db_path: str) -> None:
        self.engine = create_engine(f"sqlite:///{db_path}")

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)

    def save_prompt(self, name, version, prompt_text, parent_version=None) -> int:
        with Session(self.engine) as s:
            rec = PromptRecord(name=name, version=version,
                               prompt_text=prompt_text, parent_version=parent_version)
            s.add(rec)
            s.commit()
            return rec.id

    def save_evaluation(self, prompt_version, composite_score, metrics,
                        judge_agreement=None) -> None:
        with Session(self.engine) as s:
            s.add(EvaluationRecord(
                prompt_version=prompt_version, composite_score=composite_score,
                metrics_json=metrics, judge_agreement=judge_agreement,
            ))
            s.commit()

    def save_refinement(self, parent_version, candidate_version, promoted,
                        delta, reason, reasoning="", diff="") -> None:
        with Session(self.engine) as s:
            s.add(RefinementRecord(
                parent_version=parent_version, candidate_version=candidate_version,
                promoted=promoted, delta=delta, reason=reason,
                reasoning=reasoning, diff=diff,
            ))
            s.commit()

    def get_refinements(self) -> list[RefinementRecord]:
        with Session(self.engine) as s:
            return list(s.scalars(select(RefinementRecord)))

    def get_evaluations(self) -> list[EvaluationRecord]:
        with Session(self.engine) as s:
            return list(s.scalars(select(EvaluationRecord)))
```

- [ ] **Step 4: Remove orphaned old core modules**

```bash
git rm hefesto/core/analyzer.py hefesto/core/evaluator.py hefesto/core/generator.py hefesto/core/selector.py hefesto/core/importer.py
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/store/test_repository.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: flat-prompt store with full-audit refinements; drop WASP core modules"
```

---

## Task 18: The refinement loop (`hefesto/core/loop.py`) — headline test

**Files:**
- Create: `hefesto/core/loop.py`
- Create: `tests/core/test_loop.py`

**Interfaces:**
- Consumes: `Runner`, `Grader`, `Refiner` (via duck-typed callables), `composite_score`, `select_contrast`, `check_invariants`, `no_headroom`, `DatasetSplit`, `Objective`, `LoopConfig`, `Repository`.
- Produces:
  - `evaluate(prompt, cases, runner, grader, objective, weights) -> list[ScoredResult]`.
  - `paired_mean(cand: list[ScoredResult], champ: list[ScoredResult]) -> float` — mean of per-index `cand.composite - champ.composite`.
  - `pooled_std(cand, champ) -> float` — std of those per-index deltas (population std; 0.0 if <2).
  - `RefineLoop(runner, grader, refiner, objective, weights, config, repo=None, judge_agreement=None)` with `run(seed_prompt: str, split: DatasetSplit) -> LoopResult`. `LoopResult(champion: str, champion_score: float, history: list[dict])`.
  - Promotion: candidate promoted iff `check_invariants` passes AND `paired_mean(cand_test, champ_test) > epsilon_k * pooled_std(...)`. On rejection, branch from the same champion next iteration. Every attempt appended to `history` and (if `repo`) persisted via `save_refinement`. Stops on `patience`, `max_iter`, `target`, or `no_headroom` at STEP 0.

- [ ] **Step 1: Write the failing test (headline: never promote a regression)**

```python
# tests/core/test_loop.py
from hefesto.schemas.core import Objective
from hefesto.dataset.base import DatasetSplit
from hefesto.schemas.core import TestCase
from hefesto.schemas.config import LoopConfig
from hefesto.runner.echo_runner import EchoRunner
from hefesto.core.loop import RefineLoop


class ScriptedGrader:
    """Scores an output by a fixed table keyed on substring of the prompt echo."""
    def __init__(self, table):
        self.table = table

    def grade(self, case, output, objective):
        from hefesto.schemas.core import Metrics
        for key, score in self.table.items():
            if key in output.text:
                return Metrics(scores={"q": score})
        return Metrics(scores={"q": 0.0})


class ScriptedRefiner:
    """Emits a fixed sequence of candidate prompts."""
    def __init__(self, candidates):
        self._candidates = iter(candidates)

    def propose(self, champion_prompt, selected_cases, objective):
        return next(self._candidates)


def _split():
    cases = [TestCase(input="1"), TestCase(input="2"),
             TestCase(input="3"), TestCase(input="4")]
    return DatasetSplit(dev=cases[:2], test=cases[2:])


def test_worse_candidate_is_never_promoted():
    # Echo runner makes output text == prompt with {{input}} filled.
    # Seed prompt "GOOD {{input}}" -> grader sees "GOOD" -> 0.8
    # Candidate "BAD {{input}}"   -> grader sees "BAD"  -> 0.2 (worse, rejected)
    grader = ScriptedGrader({"GOOD": 0.8, "BAD": 0.2})
    refiner = ScriptedRefiner(["BAD {{input}}", "BAD {{input}}"])
    cfg = LoopConfig(max_iter=2, patience=5, epsilon_k=0.0, target=None, headroom_min=0.0)
    loop = RefineLoop(
        runner=EchoRunner(), grader=grader, refiner=refiner,
        objective=Objective(goal="g"), weights={"q": 1.0}, config=cfg,
    )
    result = loop.run("GOOD {{input}}", _split())
    assert result.champion == "GOOD {{input}}"        # never replaced
    assert all(h["promoted"] is False for h in result.history)
    assert len(result.history) == 2                    # both attempts logged


def test_better_candidate_is_promoted():
    grader = ScriptedGrader({"BEST": 1.0, "OKAY": 0.5})
    refiner = ScriptedRefiner(["BEST {{input}}"])
    cfg = LoopConfig(max_iter=1, patience=5, epsilon_k=0.0, target=None, headroom_min=0.0)
    loop = RefineLoop(
        runner=EchoRunner(), grader=grader, refiner=refiner,
        objective=Objective(goal="g"), weights={"q": 1.0}, config=cfg,
    )
    result = loop.run("OKAY {{input}}", _split())
    assert result.champion == "BEST {{input}}"
    assert result.history[-1]["promoted"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_loop.py -v`
Expected: FAIL with `ModuleNotFoundError: hefesto.core.loop`.

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/core/loop.py
import statistics
from pydantic import BaseModel
from hefesto.schemas.core import ScoredResult, Objective
from hefesto.dataset.base import DatasetSplit
from hefesto.schemas.config import LoopConfig
from hefesto.score.aggregate import composite_score
from hefesto.refiner.select import select_contrast
from hefesto.refiner.invariants import check_invariants
from hefesto.core.intake import no_headroom


class LoopResult(BaseModel):
    champion: str
    champion_score: float
    history: list[dict]


def evaluate(prompt, cases, runner, grader, objective, weights) -> list[ScoredResult]:
    results = []
    for case in cases:
        output = runner.run(prompt, case)
        metrics = grader.grade(case, output, objective)
        results.append(ScoredResult(
            case=case, output=output, metrics=metrics,
            composite=composite_score(metrics, weights),
        ))
    return results


def paired_mean(cand: list[ScoredResult], champ: list[ScoredResult]) -> float:
    deltas = [c.composite - p.composite for c, p in zip(cand, champ)]
    return sum(deltas) / len(deltas) if deltas else 0.0


def pooled_std(cand: list[ScoredResult], champ: list[ScoredResult]) -> float:
    deltas = [c.composite - p.composite for c, p in zip(cand, champ)]
    return statistics.pstdev(deltas) if len(deltas) >= 2 else 0.0


def _mean_composite(results: list[ScoredResult]) -> float:
    return sum(r.composite for r in results) / len(results) if results else 0.0


class RefineLoop:
    def __init__(self, runner, grader, refiner, objective: Objective,
                 weights: dict[str, float], config: LoopConfig,
                 repo=None, judge_agreement=None) -> None:
        self.runner = runner
        self.grader = grader
        self.refiner = refiner
        self.objective = objective
        self.weights = weights
        self.config = config
        self.repo = repo
        self.judge_agreement = judge_agreement

    def _eval(self, prompt, cases):
        return evaluate(prompt, cases, self.runner, self.grader,
                        self.objective, self.weights)

    def run(self, seed_prompt: str, split: DatasetSplit) -> LoopResult:
        champion = seed_prompt
        champ_dev = self._eval(champion, split.dev)
        champ_test = self._eval(champion, split.test)
        champ_score = _mean_composite(champ_test)
        history: list[dict] = []

        if no_headroom(champ_score, self.config.target, self.config.headroom_min):
            return LoopResult(champion=champion, champion_score=champ_score, history=history)

        fails = 0
        version = 1
        for _ in range(self.config.max_iter):
            selected = select_contrast(champ_dev, self.config.k)
            candidate = self.refiner.propose(champion, selected, self.objective)
            version += 1
            cand_version = f"v{version}"

            if not check_invariants(candidate, self.objective.invariants):
                self._log(history, cand_version, False, 0.0, "invariant_violation")
                fails += 1
            else:
                cand_test = self._eval(candidate, split.test)
                delta = paired_mean(cand_test, champ_test)
                if delta > self.config.epsilon_k * pooled_std(cand_test, champ_test):
                    champion = candidate
                    champ_dev = self._eval(candidate, split.dev)
                    champ_test = cand_test
                    champ_score = _mean_composite(champ_test)
                    self._log(history, cand_version, True, delta, "promoted")
                    fails = 0
                else:
                    self._log(history, cand_version, False, delta, "no_improvement")
                    fails += 1

            if fails >= self.config.patience:
                break
            if self.config.target is not None and champ_score >= self.config.target:
                break

        return LoopResult(champion=champion, champion_score=champ_score, history=history)

    def _log(self, history, cand_version, promoted, delta, reason):
        entry = {"candidate_version": cand_version, "promoted": promoted,
                 "delta": delta, "reason": reason}
        history.append(entry)
        if self.repo is not None:
            self.repo.save_refinement(
                parent_version="champion", candidate_version=cand_version,
                promoted=promoted, delta=delta, reason=reason,
            )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/core/test_loop.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: champion/challenger refine loop with rollback (headline)"
```

---

## Task 19: Seam-proof end-to-end test (echo runner, no LLM)

**Files:**
- Create: `tests/test_seam_e2e.py`

**Interfaces:**
- Consumes: everything wired together (no new production code). Proves the seams generalize beyond LLM prompts.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seam_e2e.py
from hefesto.schemas.core import Objective, TestCase
from hefesto.dataset.base import DatasetSplit
from hefesto.schemas.config import LoopConfig
from hefesto.runner.echo_runner import EchoRunner
from hefesto.core.loop import RefineLoop


class LengthGrader:
    """Non-LLM grader: shorter echoed output scores higher (cap at 20 chars)."""
    def grade(self, case, output, objective):
        from hefesto.schemas.core import Metrics
        score = max(0.0, 1.0 - len(output.text) / 20.0)
        return Metrics(scores={"brevity": score})


class TrimRefiner:
    """Non-LLM refiner: proposes a shorter prompt each call."""
    def __init__(self):
        self._n = 0

    def propose(self, champion_prompt, selected_cases, objective):
        self._n += 1
        return "{{input}}"  # minimal prompt -> shortest echo


def test_full_loop_runs_without_any_llm():
    cases = [TestCase(input="ab"), TestCase(input="cd"),
             TestCase(input="ef"), TestCase(input="gh")]
    split = DatasetSplit(dev=cases[:2], test=cases[2:])
    cfg = LoopConfig(max_iter=2, patience=5, epsilon_k=0.0, target=None, headroom_min=0.0)
    loop = RefineLoop(
        runner=EchoRunner(), grader=LengthGrader(), refiner=TrimRefiner(),
        objective=Objective(goal="be brief"), weights={"brevity": 1.0}, config=cfg,
    )
    result = loop.run("VERBOSE PROMPT PREFIX {{input}}", split)
    assert result.champion == "{{input}}"  # the shorter prompt won
    assert result.history[0]["promoted"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_seam_e2e.py -v`
Expected: FAIL initially only if wiring is wrong; if all prior tasks are done it should pass. If it fails on import, complete earlier tasks first.

- [ ] **Step 3: (No new code)** — if the test fails on logic, fix the responsible module from its own task, not here.

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: PASS (all tests green).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: seam-proof end-to-end loop with no LLM"
```

---

## Task 20: CLI (`hefesto/cli.py`)

**Files:**
- Overwrite: `hefesto/cli.py` (replace the entire 1261-line ADRS CLI)
- Create: `hefesto/scaffold.py` (init templates)
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `HefestoConfig`, `Repository`, `create_provider`, `GeneratedDataset`, `LoadedDataset`, `LLMRunner`, `LLMJudge`, `Refiner`, `RefineLoop`, `calibrate_judge`, `text_diff`, `classify_objective`.
- Produces a Typer `app` with commands: `init`, `refine`, `calibrate`, `eval`, `gen-dataset`, `history`, `diff`. For this task, implement `init` fully and `refine` end-to-end wiring; the others may print a structured summary. `init` writes `hefesto.yaml` (providers as `<required>` sentinels), `objective.yaml`, `prompt.txt`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from typer.testing import CliRunner
from hefesto.cli import app

runner = CliRunner()


def test_init_scaffolds_files(tmp_path):
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "hefesto.yaml").exists()
    assert (tmp_path / "objective.yaml").exists()
    assert (tmp_path / "prompt.txt").exists()
    assert "<required>" in (tmp_path / "hefesto.yaml").read_text()


def test_help_lists_core_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "refine", "calibrate", "eval", "history", "diff"):
        assert cmd in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — old `hefesto/cli.py` is the ADRS app (no `init --path`, different commands).

- [ ] **Step 3: Write minimal implementation**

```python
# hefesto/scaffold.py
CONFIG_YAML = """\
providers:
  default: { provider: <required>, model: <required> }
  runner:  { provider: <required>, model: <required>, temperature: 0.7 }
  judge:   { provider: <required>, model: <required>, temperature: 0.0 }
  refiner: { provider: <required>, model: <required>, temperature: 0.7 }
  dataset: { provider: <required>, model: <required>, temperature: 1.0 }

objective: ./objective.yaml
prompt: ./prompt.txt

dataset:
  source: generate
  count: 20
  test_fraction: 0.4

grader: llm_judge

judge:
  mode: pairwise
  require_different_model: true
  min_agreement: 0.7

loop:
  max_iter: 5
  patience: 2
  k: 3
  epsilon_k: 1.0
  judge_samples: 1
  headroom_min: 0.05

store_path: ./hefesto.db
"""

OBJECTIVE_YAML = """\
goal: "Describe what 'better' means for this prompt, in plain language."
weights: {}
success_criteria: []
invariants: []
"""

PROMPT_TXT = "You are a helpful assistant.\n\nUser request: {{input}}\n"
```

```python
# hefesto/cli.py
from pathlib import Path
import typer
from hefesto.scaffold import CONFIG_YAML, OBJECTIVE_YAML, PROMPT_TXT

app = typer.Typer(help="Hefesto — evaluation-first prompt refinement.")


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
    typer.echo("refine: wire HefestoConfig -> RefineLoop here")  # see Step 4


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
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: hefesto CLI skeleton with full init scaffolding"
```

> **Note for executor:** the `refine`/`calibrate`/`eval`/`gen-dataset`/`history`/`diff` command *bodies* are intentionally stubs in this task. Wiring them to `HefestoConfig.from_yaml` → `create_provider` per role → `GeneratedDataset`/`LoadedDataset` → `LLMRunner` + `LLMJudge` + `Refiner` → `RefineLoop`, plus persisting via `Repository`, is the final integration task (Task 21).

---

## Task 21: Wire `refine` end-to-end + README/GUIDE rewrite

**Files:**
- Modify: `hefesto/cli.py` (`refine`, `calibrate`, `eval`, `gen-dataset`, `history`, `diff` bodies)
- Modify: `README.md`, `GUIDE.md`
- Create: `tests/test_cli_refine.py`

**Interfaces:**
- Consumes: all prior tasks. `refine` builds providers per role (`create_provider(cfg.provider_for("runner"))`, etc.), constructs the dataset source (`GeneratedDataset` if `dataset.source == "generate"`, else `LoadedDataset`), builds a `Rubric` from `objective.weights` keys (judge-seeded rubric: one `RubricDimension` per weight key, or a single `quality` dimension if weights empty), runs `RefineLoop.run`, prints champion + history, and persists via `Repository`.

- [ ] **Step 1: Write the failing test (refine end-to-end via fakes injected through config)**

```python
# tests/test_cli_refine.py
# Strategy: monkeypatch create_provider to return FakeLLMProvider instances so
# `hefesto refine` runs with no network. Build a real config + files in tmp_path.
import yaml
from typer.testing import CliRunner
import hefesto.cli as cli
from hefesto.llm.fake import FakeLLMProvider

runner = CliRunner()


def _write_project(tmp_path):
    (tmp_path / "objective.yaml").write_text(
        "goal: be brief\nweights: {brevity: 1.0}\nsuccess_criteria: []\ninvariants: []\n"
    )
    (tmp_path / "prompt.txt").write_text("Answer briefly: {{input}}\n")
    cfg = {
        "providers": {"default": {"provider": "openai", "model": "x"}},
        "objective": str(tmp_path / "objective.yaml"),
        "prompt": str(tmp_path / "prompt.txt"),
        "dataset": {"source": "generate", "count": 4, "test_fraction": 0.5},
        "grader": "llm_judge",
        "loop": {"max_iter": 1, "patience": 1, "k": 1, "epsilon_k": 0.0,
                 "headroom_min": 0.0},
        "store_path": str(tmp_path / "h.db"),
    }
    (tmp_path / "hefesto.yaml").write_text(yaml.safe_dump(cfg))
    return str(tmp_path / "hefesto.yaml")


def test_refine_runs_offline(tmp_path, monkeypatch):
    cfg_path = _write_project(tmp_path)

    def fake_provider(_cfg):
        # dataset gen -> 4 inputs; judge -> score; refiner -> a candidate prompt
        return FakeLLMProvider(handler=lambda msgs: _route(msgs))

    def _route(msgs):
        text = msgs[-1].content
        if "JSON array" in text:
            return '["a","b","c","d"]'
        if "JSON object" in text:
            return '{"brevity": 8}'
        return "Answer: {{input}}"

    monkeypatch.setattr(cli, "create_provider", fake_provider)
    result = runner.invoke(cli.app, ["refine", "--config", cfg_path])
    assert result.exit_code == 0, result.output
    assert "champion" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_refine.py -v`
Expected: FAIL — `refine` is still the stub from Task 20.

- [ ] **Step 3: Write the `refine` wiring**

```python
# hefesto/cli.py  (replace the refine stub; add imports at top of file)
# add near the top:
import yaml
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


def _load_objective(path: str) -> Objective:
    with open(path) as f:
        return Objective.model_validate(yaml.safe_load(f))


def _rubric_from(objective: Objective) -> Rubric:
    keys = list(objective.weights.keys()) or ["quality"]
    return Rubric(dimensions=[
        RubricDimension(name=k, description=f"quality dimension: {k}", weight=objective.weights.get(k, 1.0))
        for k in keys
    ])
```

```python
# hefesto/cli.py  (the new refine body)
@app.command()
def refine(config: str = typer.Option("hefesto.yaml", "--config")):
    """Run the refinement loop (intake -> STEP 0 -> champion/challenger)."""
    cfg = HefestoConfig.from_yaml(config)
    objective = _load_objective(cfg.objective)
    seed_prompt = open(cfg.prompt).read()
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
    typer.echo(f"Champion score: {result.champion_score:.3f}")
    typer.echo(f"Attempts: {len(result.history)} (promoted: "
               f"{sum(1 for h in result.history if h['promoted'])})")
    typer.echo("--- champion prompt ---")
    typer.echo(result.champion)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_cli_refine.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Rewrite `README.md` and `GUIDE.md`**

Replace the ADRS-centric content with Hefesto's identity. README must open with the forge promise (*"Bring raw ore — a prompt and a goal — and leave with a tempered one that provably outperforms what you came with."*), list the four earned strengths (refines without bloating, never ships a regression, shows its work, never breaks your pipeline), document the signal trust ladder (real metrics > verifiable judge > calibrated judge), and the CLI commands. GUIDE must describe the four seams (DatasetSource, Runner, Grader, Refiner), the Trust Model, and the champion/challenger loop. Remove all WASP/Kubernetes/consolidator-agent operating instructions (WASP is a future plugin).

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS (all green).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: wire hefesto refine end-to-end; rewrite docs for generalist identity"
```

---

## Self-Review Notes (coverage map)

- Trust ladder / tiers → Task 11 (`classify_objective`), surfaced in README (Task 21).
- Judge independence (judge≠runner) → config flag `require_different_model` carried in Task 4. **Enforcement is deferred** (see deferred list) so the Task 21 offline test can share one provider; wiring the fail-fast guard is a follow-on once multi-provider test fixtures exist.
- Calibration + agreement reporting → Task 12 (`calibrate_judge`); `calibrate` CLI body wired in Task 21.
- Headroom/stop → Task 11 (`no_headroom`), used in Task 18 loop.
- Dev/test split → Task 5; mined-from-dev / scored-on-test enforced in Task 18.
- Few-shot over rules + rule-density lint → Task 15.
- Hard invariants → Task 14, enforced in Task 18.
- Full audit trail (rejected persisted) → Task 17 + Task 18 `_log`.
- Champion/challenger, paired margin in std units, branch-from-champion → Task 18.
- Pinned [0,1] scale, key contract → Tasks 9, 10.
- Provider-agnostic fail-fast → Task 4.
- Flat prompt + {{input}} → Tasks 8, 17.
- Seam-proof (non-LLM) → Task 19.
- CLI surface → Tasks 20, 21.

**Deferred to follow-on plans (out of scope here):**
- Judge≠runner fail-fast enforcement (`require_different_model` flag exists in Task 4; the guard that raises `ConfigError` when they resolve identical is a follow-on, needing multi-provider test fixtures).
- Pairwise judge mode implementation (Task 10 ships absolute; `JudgeConfig.mode` exists but pairwise grading is a follow-on).
- Verifiable-judge (Tier 2) grader, `gen-dataset`/`eval`/`calibrate`/`history`/`diff` full command bodies beyond stubs.
- `plugins/wasp/` (CSV import, metric presets, sim runner, FINDINGS-parity test).
- `judge_samples > 1` averaging in the loop (`LoopConfig.judge_samples` exists; multi-sample averaging is a follow-on).
