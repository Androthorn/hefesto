# Experiment Findings — ADRS Scoring Analysis

> **Date**: 2026-02-28
> **Dataset**: 71 runs from `combined_summaries.csv` (gemini run 11 at t=0.5 excluded from analysis)
> **Scoring model**: Overload penalty disabled (was −0.20, always triggered because all workloads land on `member1`)

---

## Scoring Methodology

Each simulation run produces a set of time-series metrics collected from the Kubernetes cluster. These are aggregated into summary statistics (mean, min, max, std, median) per metric. We define a **composite performance score** that captures the overall quality of an agent's workload placement decisions.

### Metric Normalization

For each metric $i$, the raw mean value $v_i$ is normalized against a predefined baseline $b_i$ using target-based normalization:

$$s_i = \max\!\left(0,\; 1 - \frac{v_i}{b_i}\right)$$

where $s_i \in [0, 1]$. Lower raw values yield higher scores — a score of 1.0 indicates the metric reached its ideal value (zero), while a score of 0.0 indicates the metric met or exceeded the baseline.

### Composite Score

The composite score $S$ is the weighted average of normalized metric scores:

$$S = \sum_{i=1}^{n} w_i \cdot s_i$$

The metrics, weights, and baselines used are:

| Metric | Symbol | Weight ($w_i$) | Baseline ($b_i$) | Rationale |
|--------|--------|----------------|-------------------|-----------|
| Pending pods | $v_1$ | 0.35 | 100 | Primary indicator of scheduling quality — counts pods awaiting placement |
| Time with pending | $v_2$ | 0.25 | 1.0 | Fraction of time window where at least one pod was pending |
| Cost | $v_3$ | 0.25 | 0.1 | Normalized monetary cost of resource usage across clusters |
| Number of migrations | $v_4$ | 0.15 | 200 | Total inter-cluster workload migrations — proxy for system stability |

Higher weights are assigned to metrics that most directly reflect scheduling effectiveness. The baselines represent worst-case thresholds derived from preliminary experiments: values at or above the baseline receive a score of zero.

> **Note on overload penalty**: An optional penalty term for exceeding 80% CPU/memory utilization was disabled for this analysis. In the current experimental setup, all workloads are routed to a single cluster (`member1`), causing utilization to consistently exceed this threshold in every run. The penalty was therefore a constant bias ($-0.20$ applied uniformly) and did not contribute discriminative information.

---

## Results Summary

| Rank | Model | Temp | Runs | Mean Score | Std | Min | Max |
|------|-------|------|------|-----------|------|------|------|
| 1 | **google-gemini-2.5-flash** | 0.1 | 10 | **0.6651** | 0.0740 | 0.5240 | 0.7358 |
| 2 | **google-gemini-2.5-flash** | 0.5 | 10* | **~0.63** | ~0.07 | 0.5537 | 0.7364 |
| 3 | openai-gpt-5 | 0.5 | 10 | 0.5081 | 0.0977 | 0.4241 | 0.6680 |
| 4 | anthropic-claude-haiku-4.5 | 0.5 | 10 | 0.4702 | 0.1765 | 0.2304 | 0.7291 |
| 5 | openai-gpt-5-mini | 0.5 | 10 | 0.4516 | 0.0971 | 0.3533 | 0.6930 |
| 6 | openai-gpt-5-mini | 0.1 | 10 | 0.4439 | 0.0810 | 0.3535 | 0.6144 |
| 7 | anthropic-claude-haiku-4.5 | 0.1 | 10 | 0.4417 | 0.1228 | 0.3643 | 0.7239 |

*\*Excluding gemini run 11 (t=0.5) from the 11-run total*

---

## Key Findings

### 1. Gemini is the clear winner

Gemini-2.5-flash outperforms all other models by a wide margin (~0.15 points above GPT-5, the next best). It produces consistently good migration/keep decisions that balance pending pods against cost.

### 2. Temperature matters less for Gemini

Gemini's t=0.1 actually edges out t=0.5 (0.6651 vs ~0.63), suggesting its default behavior is already well-calibrated for this task. For other models, t=0.5 performs better — those agents need randomness to break out of conservative "keep everything on private" behavior.

### 3. Claude Haiku is the most unreliable

Haiku (t=0.5) has the highest variance by far (std=0.1765). Its scores swing between 0.23 and 0.73 — it can occasionally beat everyone but also produces the single worst run in the dataset. Not suitable when consistency matters.

### 4. GPT-5 > GPT-5-mini, but the gap is small

The full GPT-5 model scores ~0.05 points higher than the mini variant (0.5081 vs 0.4516). The mini model offers a reasonable cost/performance trade-off.

### 5. Low temperature (t=0.1) makes non-Gemini models too conservative

All t=0.1 configurations for non-gemini models cluster around 0.37–0.44. These agents default to keeping everything on the private cluster, resulting in near-zero migrations but maximal pending pods.

---

## Overload Penalty Note

The overload penalty was disabled for this analysis. In the current experiment scenario, all workloads are allocated to the `member1` cluster, causing `cpu_usage` and `mem_usage` to consistently exceed the 0.80 threshold across every single run. The penalty was acting as a constant −0.20 bias applied to all agents equally, depressing all scores without differentiating between them.

---

## DB Score Correction

The ADRS database (`adrs.db`) contained 2 evaluations from a prior `evaluate-and-refine` cycle, both with the old −0.20 penalty baked in:

| ID | Agent | Version | Old Score | Corrected Score |
|----|-------|---------|-----------|-----------------|
| 1 | consolidator_agent | v1 | 0.4281 | **0.6281** |
| 2 | consolidator_agent_v2 | v2 | 0.5364 | **0.7364** |

The v2 prompt (refined by ADRS) scored 0.7364 in a single evaluation — higher than any single unrefined gemini run (max 0.7358). However, this was a single data point and required further validation with a full batch of 10 runs.

---

## v2 Prompt Refinement Results

> **Date**: 2026-03-01
> **Setup**: 10 runs per configuration, gemini-2.5-flash, `consolidator_agent_v2` prompt

### Configuration Issue Discovered

An initial batch of 10 runs (gemini t=0.5, runs 11–20) was found to have used the **v1 prompt** due to a configuration oversight: the `run_repeated_simulations.sh` script reads from `simulator/data/config.yaml`, which was not updated to point to `consolidator_agent_v2`. After correcting this, a new batch of 10 runs was executed at t=0.1.

### v1 vs v2 Comparison — Gemini (t=0.1)

| Metric | v1 (runs 1–10) | v2 (runs 11–20) | Delta |
|--------|---------------|-----------------|-------|
| **Mean Score** | **0.6651** | 0.6219 | −0.043 |
| **Std** | **0.0740** | 0.0823 | +0.008 |
| **Min** | 0.5240 | 0.4747 | −0.049 |
| **Max** | 0.7358 | **0.7308** | −0.005 |

### Conclusion

The v2 refined prompt **did not improve** performance over v1. At t=0.1, the mean score dropped by 0.043 (from 0.6651 to 0.6219), and variance increased slightly. The top runs are comparable (~0.73), but v2 produced more weak runs (min dropped from 0.524 to 0.475).

**Interpretation**: Prompt-level refinement via ADRS did not yield systematic improvement for gemini-2.5-flash. This model already performs well with its base prompt, and the LLM-generated prompt modifications did not translate into better scheduling decisions. This suggests that for high-performing models, the bottleneck may not be in the prompt but in the model's inherent reasoning capabilities or the experimental scenario's structure.

---

## v3 Prompt Refinement Results

> **Date**: 2026-03-01 (initial), 2026-03-09 (extended)
> **Setup**: gemini-2.5-flash (t=0.1), `consolidator_agent_v3` prompt

A third iteration (v3) was generated by ADRS. Initially only 3 runs (21–23) were executed to observe the refinement trajectory. To enable statistically comparable evaluation with v1/v2/v4/v5 (all 10 runs), 7 additional runs are being executed.

| Batch | Runs | Status |
|-------|------|--------|
| Initial (2026-03-01) | 21–23 |  Complete |
| Extended (2026-03-09) | 48–54 |  Complete |  Metrics haven't been registered yet for these runs.
 
### Preliminary Results (3 runs only)

| Prompt Version | Runs | Mean Score | Std |
|----------------|------|------------|-----|
| **v1 (Baseline)** | 1–10 | **0.6651** | 0.0740 |
| **v2 (Refinement 1)** | 11–20 | 0.6219 | 0.0823 |
| **v3 (Refinement 2)** | 21–23 | 0.5879 | 0.1247 |

*Scores above use the old cost baseline (pre-correction). Full 10-run v3 results (runs 21–23 + 48–54) will be re-scored with the corrected cost metric.*

### Conclusion on Iterative Refinement

The score dropped linearly across each iteration. The v3 prompt performed the worst so far. Upon inspection, the prompt refinements exhibited classic LLM zero-shot failure modes:
1. **Over-constraint**: The baseline (v1) was a loose guideline. v2 and v3 added massive walls of highly specific rules ("1.a. If Analyst decision is 0 AND explicit confirmation -> MUST be 0"). This rigidity trips up fast reasoning models.
2. **The "Yes-Man" Loop**: ADRS critiques the LLM stringently based on the score. The LLM responds by adding more rules to handle whatever edge case it hallucinates caused the penalty, leading to an overly dense and unparseable prompt.

---

## Recommendations for ADRS Refinement Improvements

To prevent prompt degradation, the ADRS loop needs the following enhancements:

1. **Few-Shot Examples Instead of Rules**: Instead of telling the generator LLM to "add rules to fix this", instruct it to *add a concrete few-shot example* of a failed scenario and how it should be handled. Models learn better from explicit I/O pairs than dense legalistic rules.
2. **Prompt Simplicity Constraint**: Add a constraint to the meta-prompt (`REFINEMENT_SYSTEM_PROMPT`) explicitly discouraging overly long pseudo-code rules: *"Keep modifications concise. Do not add complex nested logical rules (e.g., 1.a, 1.b). Prefer conceptual guidelines or examples."*
3. **Rollback Mechanism (Best-of-N)**: Implement automated rollback. If v(N) scores lower than v(N-1) with statistical significance, the system should discard v(N) and attempt a different refinement strategy from v(N-1) rather than building upon the degraded v(N) state.

---

## v4 Prompt Results

> **Date**: 2026-03-01
> **Setup**: 10 runs, gemini-2.5-flash (t=0.1), `consolidator_agent_v4` prompt

v4 was generated by ADRS (`gemini-3.1-pro-preview`) branching from the v1 baseline (runs 1–10), with two changes applied before refinement: (1) `adrs_objective.json` was updated to explicitly prioritize pending pod resolution over cost and to accept CPU/memory overloads as unavoidable; (2) the `REFINEMENT_SYSTEM_PROMPT` in `generator.py` was updated to discourage nested pseudo-code rules and prefer concise heuristics. The resulting prompt uses four high-level directives and simple if/then decision heuristics.

### Per-Run Scores

| Run | Composite | pending_pods | time_w_pending | cost   | migrations |
|-----|-----------|--------------|----------------|--------|------------|
| 24  | 0.6554    | 0.8112       | 0.6000         | 0.4060 | 0.8000     |
| 25  | 0.5324    | 0.7020       | 0.3667         | 0.3911 | 0.6480     |
| 26  | 0.7210    | 0.8310       | 0.7667         | 0.4441 | 0.8500     |
| 27  | 0.7010    | 0.7978       | 0.7500         | 0.4273 | 0.8500     |
| 28  | 0.7246    | 0.8228       | 0.7833         | 0.4351 | 0.8800     |
| 29  | 0.4962    | 0.6964       | 0.1803         | 0.4216 | 0.6800     |
| 30  | 0.6103    | 0.6337       | 0.5667         | 0.4605 | 0.8780     |
| 31  | 0.5090    | 0.6837       | 0.0000         | 0.5345 | 0.9075     |
| 32  | 0.7092    | 0.8078       | 0.7667         | 0.4292 | 0.8500     |
| 33  | 0.6695    | 0.7907       | 0.6167         | 0.4359 | 0.8640     |

### Progression: v1 -> v2 -> v3 -> v4

| Prompt Version | Runs  | Mean Score | Std    | Min    | Max    |
|----------------|-------|------------|--------|--------|--------|
| **v1 (Baseline)**    | 1–10  | **0.6651** | 0.0740 | 0.5240 | 0.7358 |
| v2 (Refinement 1)    | 11–20 | 0.6219     | 0.0823 | 0.4747 | 0.7308 |
| v3 (Refinement 2)    | 21–23 | 0.5879     | 0.1247 | 0.5107 | 0.7318 |
| **v4 (ADRS from v1, updated objective)** | 24–33 | **0.6329** | 0.0901 | 0.4962 | 0.7246 |

All 10 v4 runs triggered the overload warning (⚠), consistent with the known experimental setup in which all workloads are concentrated on `member1`.

---

## v5 Prompt Results

> **Date**: 2026-03-02
> **Setup**: 10 runs (38–47), gemini-2.5-flash (t=0.1), `consolidator_agent_v5` prompt

v5 was generated by ADRS (`gemini-3.1-pro-preview`) branching from the v1 baseline, using the updated objective and a modified `REFINEMENT_SYSTEM_PROMPT` that enforces **few-shot examples over abstract rules** as the primary refinement technique. The `--runs 5,29,31` flag was used to feed the generator with the best-performing run (run 5, score 0.7358) alongside two worst outliers (runs 29 and 31), providing high-contrast data for example generation. Three few-shot examples were embedded in the prompt:

1. **Pending Pods vs. Cost Savings** — migrate to public when pods are pending, even if cost analyst disagrees.
2. **CPU Overload without Pending Pods** — stay on private; overloads are acceptable when no pods are pending.
3. **Workload Already on Public with No Pending Pods** — keep on public for stability; avoid flip-flopping back to private.


### Per-Run Scores

| Run | Composite | pending_pods | time_w_pending | cost   | migrations |
|-----|-----------|--------------|----------------|--------|------------|
| 38  | 0.7304    | 0.8337       | 0.8000         | 0.4266 | 0.8800     |
| 39  | 0.7129    | 0.8318       | 0.7705         | 0.4007 | 0.8600     |
| 40  | 0.7227    | 0.8267       | 0.8000         | 0.4057 | 0.8800     |
| 41  | 0.7333    | 0.8340       | 0.7833         | 0.4486 | 0.8900     |
| 42  | 0.7306    | 0.8302       | 0.7833         | 0.4463 | 0.8840     |
| 43  | 0.6955    | 0.8038       | 0.7500         | 0.4269 | 0.8000     |
| 44  | 0.6154    | 0.6387       | 0.5833         | 0.4564 | 0.8800     |
| 45  | 0.7239    | 0.8195       | 0.7667         | 0.4512 | 0.8840     |
| 46  | 0.6984    | 0.8352       | 0.8000         | 0.3190 | 0.8420     |
| 47  | 0.7243    | 0.8282       | 0.7833         | 0.4266 | 0.8800     |

All 10 v5 runs triggered the overload warning (⚠), consistent with the known experimental setup.

### Progression: v1 -> v2 -> v3 -> v4 -> v5

| Prompt Version | Runs  | Mean Score | Std    | Min    | Max    |
|----------------|-------|------------|--------|--------|--------|
| v1 (Baseline)  | 1–10  | 0.6651     | 0.0740 | 0.5240 | 0.7358 |
| v2 (Refinement 1) | 11–20 | 0.6219  | 0.0823 | 0.4747 | 0.7308 |
| v3 (Refinement 2) | 21–23 | 0.5879  | 0.1247 | 0.5107 | 0.7318 |
| v4 (ADRS from v1, updated objective) | 24–33 | 0.6329 | 0.0901 | 0.4962 | 0.7246 |
| **v5 (Few-shot, 3 examples)** | **38–47** | **0.7087** | **0.0353** | **0.6154** | **0.7333** |

### v5 vs v1 Improvement

| Metric     | v1     | v5     | Change  |
|------------|--------|--------|---------|
| Mean Score | 0.6651 | 0.7087 | **+6.6%**  |
| Std Dev    | 0.0740 | 0.0353 | **−52.3%** |
| Min Score  | 0.5240 | 0.6154 | **+17.4%** |
| Max Score  | 0.7358 | 0.7333 | −0.3%   |

v5 is the first prompt variant to meaningfully surpass the v1 baseline. Few-shot examples simultaneously improved both performance and consistency, while rule-based refinement (v2, v3) degraded both. The three concrete examples grounded the agent's reasoning in a way that abstract rules could not.

---

## Cost Metric Correction

> **Date**: 2026-03-09

### Problem

The cost metric $v_3$ used in the composite score was computed as the total infrastructure cost across both clusters per interval. Since both clusters always start with 10 fixed nodes (8 vCPU, 16 GB each), the cost included a **structural floor** unrelated to agent behavior: the always-on private cluster contributes a constant base cost regardless of migration decisions.

This created two issues:
1. **Compressed discriminative range**: cost sub-scores clustered in a narrow ~0.32–0.53 band across all runs.
2. **Misleading attribution**: agents were penalized for infrastructure they had no control over.

### Fix

The fixed private-cluster cost was computed from the experimental configuration:

- **Instance match**: 8 vCPU / 16 GB → `t4g.2xlarge` ($0.2688/hr)
- **Per-interval cost**: $(0.2688 \times 10 \times 30) / 3600 = 0.0224$ USD

The corrected normalization subtracts this constant before scoring:

$$s_3 = \max\!\left(0,\; 1 - \frac{v_3 - C_{\text{fixed}}}{b_3'}\right)$$

where $C_{\text{fixed}} = 0.0224$ and $b_3' = 0.1 - C_{\text{fixed}} = 0.0776$.

This isolates the agent-driven marginal cost (public cloud usage) from the invariant private infrastructure. Raw metric values in `combined_summaries.csv` remain unchanged; the correction is applied at scoring time only in `compute_stability_scores.py`.

### Re-Scored Results (Phase 1)

| Model | T | Runs | Old Mean | New Mean | Δ Mean |
|-------|---|------|----------|----------|--------|
| gemini-2.5-flash | 0.1 | 47 | 0.6651* | **0.6748** | +0.010 |
| gemini-2.5-flash | 0.5 | 20 | ~0.63* | **0.6495** | +0.020 |
| gpt-5 | 0.5 | 10 | 0.5081 | **0.5468** | +0.039 |
| claude-haiku-4.5 | 0.5 | 10 | 0.4702 | **0.4985** | +0.028 |
| gpt-5-mini | 0.5 | 10 | 0.4516 | **0.4900** | +0.038 |
| gpt-5-mini | 0.1 | 11 | 0.4439 | **0.4769** | +0.033 |
| claude-haiku-4.5 | 0.1 | 15 | 0.4417 | **0.4677** | +0.026 |

*\*Old means computed on first 10 runs only; new means include all available runs.*

### Effect on Cost Sub-Scores

Cost sub-scores now span **~0.41–0.69** (previously ~0.32–0.53), increasing discriminative power. Models that kept workloads on the private cluster (e.g., GPT-5 runs with cost ≈ 0.0448) now receive near-perfect cost sub-scores (~0.69 vs ~0.55 before), correctly reflecting minimal marginal expenditure.

Model ranking is preserved. The correction uniformly increases all scores by ~0.01–0.04 points, with greater uplift for conservative (low-cost) agents.

