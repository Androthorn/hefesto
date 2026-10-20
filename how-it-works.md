# How Hefesto Works — A Typical Run

This walks one `hefesto refine` from start to finish with concrete example
values, so you can see exactly what happens at each stage. For the component
reference (the four seams, interfaces, persistence schema) see
[GUIDE.md](GUIDE.md).

> The numbers below are illustrative — a realistic shape of one run, not output
> from a fixed seed.

---

## 1. The setup

Three files (created by `hefesto init`, then edited):

**`prompt.txt`** — the prompt you want to improve. `{{input}}` is where each test
case is injected:

```
You are a helpful assistant.

User request: {{input}}
```

**`objective.yaml`** — what "better" means. `weights` names the scoring
dimensions; `invariants` are substrings that must survive every refinement:

```yaml
goal: "Answer questions concisely and accurately."
weights:
  brevity: 0.4
  accuracy: 0.6
invariants:
  - "{{input}}"        # a candidate that drops this is rejected unscored
```

**`hefesto.yaml`** — providers (per role) and loop knobs. The relevant ones:

```yaml
dataset: { source: generate, count: 20, test_fraction: 0.4 }
grader: llm_judge
loop:   { max_iter: 5, patience: 2, k: 12, delta_min: 0.05, alpha: 0.05, headroom_min: 0.05 }
```

You run:

```bash
hefesto refine --config hefesto.yaml
```

---

## 2. What `hefesto refine` does, step by step

### Step 0a — build the four providers

One LLM client is created per role from your config: **runner** (runs the prompt
under test), **judge** (grades outputs), **refiner** (proposes new prompts), and
**dataset** (generates test inputs). Any role falls back to `providers.default`.
A `Rubric` is built from your `weights` keys — here, two dimensions: `brevity`
and `accuracy`.

### Step 0b — get the eval dataset

`source: generate` → the dataset LLM is asked to invent 20 realistic inputs for
your objective, e.g.:

```
"What's 2+2?", "How do I make oatmeal?", "How far away is the Moon?",
"Explain photosynthesis in one line.", ... (20 total)
```

These are split **deterministically**: with `test_fraction: 0.4`, the last 8 go
to the **test** split, the first 12 to the **dev** split. The split is frozen for
the whole run.

> Why split? The **dev** cases are what the refiner is allowed to look at. The
> **test** cases are held out and are the *only* thing promotion is judged on — so
> the loop can't "study the answers" it's being graded against.

### Step 0c — score the seed prompt (the first champion)

The runner fills `{{input}}` for each **test** case and calls the LLM; the judge
scores each output 1–10 on every rubric dimension, normalized to `[0,1]`
(`(x-1)/9`). The composite is the weighted average:

| Test case | output (abbrev.) | brevity | accuracy | composite (0.4·b + 0.6·a) |
|-----------|------------------|---------|----------|----------------------------|
| "What's 2+2?" | "2 + 2 = 4." | 1.00 | 1.00 | **1.00** |
| "How do I make oatmeal?" | *(3 rambling paragraphs)* | 0.22 | 0.89 | **0.62** |
| "How far away is the Moon?" | "About 384,400 km." | 0.89 | 1.00 | **0.96** |
| … (8 test cases) | | | | |

Mean of the 8 test composites → **champion score = 0.78**. This seed is now
**v1**, the reigning champion.

### Step 0d — headroom check

`no_headroom(0.78, target=null, headroom_min=0.05)` asks: is the champion already
within 0.05 of the ceiling (≥ 0.95)? No (0.78). There is room to improve, so the
loop begins. *(If the seed had already scored ≥ 0.95, Hefesto would stop here and
tell you there's nothing to forge.)*

---

## 3. Iteration 1 — a candidate is promoted

**Select contrast cases.** `select_contrast(dev_results, k)` picks the **k best
and k worst** dev cases (here the 12-case dev split is small enough that the two
sets overlap; the walkthrough shows 3 of each for brevity) — high-contrast examples of what works and what doesn't.
The worst include the rambling oatmeal-style answers (~0.55); the best include
the crisp factual ones (~0.97).

**Propose a challenger.** The refiner gets the current champion, the objective,
and those contrast cases (each shown as `input / output / score`), with a
system instruction to *prefer adding a concrete few-shot example from a failing
case over stacking rules*. It returns a full new prompt — **v2** — e.g. the seed
plus a short worked example:

```
You are a helpful assistant. Answer in as few words as correctness allows.

Example — Q: How do I boil an egg? A: Boil water, lower in the egg, cook 8 min.

User request: {{input}}
```

**Invariant check (before spending any judge calls).** Does v2 still contain
`{{input}}`? Yes → it proceeds. *(If it had dropped the placeholder, v2 would be
rejected immediately as `invariant_violation`, no evaluation run.)*

**Score on the held-out test split & compare — unpaired.** v2 is scored on the same
8 test cases. The two arms are treated as independent samples (`should_promote`
in `hefesto/core/gate.py`); nothing is matched case-to-case. The scores below are
the actual `[r.composite for r in cand_test]` and `[... champ_test]` lists, and
the numbers are what `welch_lower_bound` returns for them:

```
champion (v1) test composites: [1.00, 0.62, 0.96, 0.80, 0.70, 0.75, 0.66, 0.75]
v2 test composites:            [1.00, 0.90, 1.00, 0.95, 0.92, 0.94, 0.88, 0.91]

mean_c − mean_p = 0.9375 − 0.7800 = +0.1575
s_c = 0.0443, s_p = 0.1360
se  = sqrt(s_c²/8 + s_p²/8)       = 0.0506
nu  = Welch–Satterthwaite         = 8.47
t_{0.95, 8.47}                    = 1.846
lower bound = 0.1575 − 1.846 · 0.0506 = 0.0642
promote iff lower bound > delta_min  →  0.0642 > 0.05  →  YES
```

v2 is **promoted**. The champion is now v2; champion score rises 0.78 → **0.94**
(0.9375). The next candidate will branch from v2 (never from a rejected attempt).

> The test is on the *lower confidence bound* of the gain, not its point estimate:
> judge scores are noisy, so a candidate has to be better than `delta_min` even
> at the pessimistic end of the one-sided 95% interval. More test cases shrink
> `se`, so more evaluation does buy confidence.
>
> This replaced the rule `paired_mean > epsilon_k * pooled_std`. That rule paired
> independent replicas by position (`zip`), so its verdict depended on the order
> the replicas happened to come in, and its threshold had no `n` in it, so running
> more replicas never bought confidence. Its false-promotion rate was therefore an
> uncontrolled function of the number of replicas.

---

## 4. Iteration 2 — a candidate is rejected

The refiner proposes **v3**, which (despite the instruction) stacks terse rules
like "always answer in ≤ 2 sentences; if a list, max 3 items." On the test split
the rigidity costs accuracy on the harder questions:

```
v3 test composites: [0.98, 0.91, 0.95, 0.95, 0.89, 0.86, 0.90, 0.87]   (mean 0.9138)

mean_c − mean_p = 0.9138 − 0.9375 = −0.0238
se = 0.0217, nu = 13.97, t_{0.95, 13.97} = 1.762
lower bound = −0.0238 − 1.762 · 0.0217 = −0.0620
−0.0620 is not > delta_min (0.05)   →   REJECTED  (reason: no_improvement)
```

v2 stays champion; the failure counter increments. This is the **"refines without
bloating"** guarantee in action — not enforced by a lint, but by the score gate:
a regression simply can't win. A third attempt also fails to clear the margin, so
`fails (2) ≥ patience (2)` and the loop **stops**.

---

## 5. The result

The CLI prints:

```
Champion score: 0.938
Attempts: 3 (promoted: 1)
--- champion prompt ---
You are a helpful assistant. Answer in as few words as correctness allows.

Example — Q: How do I boil an egg? A: Boil water, lower in the egg, cook 8 min.

User request: {{input}}
```

You came in with a prompt scoring 0.78 and leave with one scoring 0.94 — and you
can see it took 3 attempts, 1 of which won.

---

## 6. Reading the audit trail

Everything is persisted to the SQLite database at `store_path`:

| Table | After this run |
|-------|----------------|
| `prompts` | the champion text (v2) |
| `evaluations` | the champion's composite score (0.94) |
| `refinements` | **every attempt** — v2 *promoted* (Δ +0.158), v3 *rejected* (Δ −0.024), v4 *rejected* — each with `parent_version`, `delta`, and `reason` |

The `refinements` table is the full forensic record of the run: which candidate
branched from which champion, by how much it won or lost, and why each one was
kept or discarded. You can query it directly:

```bash
sqlite3 hefesto.db \
  "select parent_version, candidate_version, promoted, round(delta,3), reason
     from refinements order by id;"
```

> **v1 status note:** `hefesto refine` currently persists only the final champion
> prompt + its score in `prompts`/`evaluations`; the `refinements` table holds the
> complete attempt history. The `history`, `diff`, `eval`, and `calibrate`
> commands are scaffolded stubs in v1 — query the database directly until they're
> wired in a follow-on.

---

## The whole run in one picture

```
prompt + objective
      │
      ▼
generate 20 cases ─► split: 12 dev (refiner sees) | 8 test (held out, scores)
      │
      ▼
score seed on test ─► champion v1 = 0.78 ──► headroom? no ──► loop
      │
      ▼  iteration
select k best + k worst dev cases
      │
      ▼
refiner proposes candidate ─► invariant ok? ─► score on test ─► Welch LB
      │                                                            │
      ▼                                          LB > delta_min ?
   promote (new champion, branch from it)  ◄─ yes      no ─►  reject, patience++
      │
      ▼
stop on patience / max_iter / target ─► champion + full audit trail
```
