"""
Compute stability scores from combined_summaries.csv and produce
LaTeX snippets for the paper (Section V figures/tables).

Formula (from paper Table I):
  si = max(0, 1 - vi / bi)
  S  = sum(wi * si)

For the cost metric, the fixed private-cluster infrastructure cost
(C_fixed = 0.0224 USD/interval, from 10 nodes × t4g.2xlarge @ $0.2688/hr,
30s intervals) is subtracted before normalization to isolate agent-driven
cost from the structural floor:
  si_cost = max(0, 1 - (vi - C_fixed) / bi_adjusted)

Metrics used:
  metric               weight (w)  baseline (b)
  ──────────────────── ──────────  ────────────
  pending_pods          0.35        100
  time_with_pending     0.25        1.0
  cost                  0.25        0.0776  (0.1 - C_fixed)
  number_of_migrations  0.15        200
"""

import csv
import statistics
from collections import defaultdict

CSV_PATH = (
    "/home/andrecunha/Área de Trabalho/Projetos/simulator/analyzer/output/combined_summaries.csv"
)

# Fixed cost of the always-on private cluster (10 nodes × t4g.2xlarge,
# $0.2688/hr per node, 30-second intervals): (0.2688 * 10 * 30) / 3600
FIXED_COST = 0.0224

WEIGHTS = {
    "pending_pods":        (0.35, 100.0),
    "time_with_pending":   (0.25, 1.0),
    "cost":                (0.25, 0.1 - FIXED_COST),
    "number_of_migrations":(0.15, 200.0),
}

# ── 1. Load raw per-run metric means ─────────────────────────────────────────
# key: (model, threshold, run_number)  →  {metric: mean_value}
run_metrics: dict[tuple, dict[str, float]] = defaultdict(dict)

with open(CSV_PATH, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["metric"] not in WEIGHTS:
            continue
        key = (row["model"], row["threshold"], row["run_number"])
        run_metrics[key][row["metric"]] = float(row["mean"])

# ── 2. Compute S for each run ─────────────────────────────────────────────────
# key: (model, threshold)  →  list[S]
group_scores: dict[tuple, list[float]] = defaultdict(list)

for (model, threshold, run_num), metrics in run_metrics.items():
    if len(metrics) < len(WEIGHTS):
        continue  # skip incomplete runs
    S = 0.0
    for metric_name, (w, b) in WEIGHTS.items():
        v = metrics[metric_name]
        if metric_name == "cost":
            v = max(0.0, v - FIXED_COST)
        si = max(0.0, 1.0 - v / b)
        S += w * si
    group_scores[(model, threshold)].append(S)

# ── 3. Summarise ─────────────────────────────────────────────────────────────
print("=" * 72)
print(f"{'Model':<35} {'T':>4}  {'N':>3}  {'Mean':>7}  {'Std':>7}  {'Min':>7}  {'Max':>7}")
print("-" * 72)

ORDER = [
    ("google-gemini-2.5-flash",   "0.1"),
    ("google-gemini-2.5-flash",   "0.5"),
    ("anthropic-claude-haiku-4.5","0.1"),
    ("anthropic-claude-haiku-4.5","0.5"),
    ("openai-gpt-5-mini",          "0.1"),
    ("openai-gpt-5-mini",          "0.5"),
    ("openai-gpt-5",               "0.1"),
    ("openai-gpt-5",               "0.5"),
]

results = {}
for key in ORDER:
    scores = group_scores.get(key, [])
    if not scores:
        continue
    mean = statistics.mean(scores)
    std  = statistics.stdev(scores) if len(scores) > 1 else 0.0
    mn   = min(scores)
    mx   = max(scores)
    results[key] = (len(scores), mean, std, mn, mx)
    print(
        f"{key[0]:<35} {key[1]:>4}  {len(scores):>3}  "
        f"{mean:>7.4f}  {std:>7.4f}  {mn:>7.4f}  {mx:>7.4f}"
    )

print("=" * 72)

# ── 4. Emit LaTeX table (cross-model summary) ─────────────────────────────────
DISPLAY = {
    "google-gemini-2.5-flash":    "gemini-2.5-flash",
    "anthropic-claude-haiku-4.5": "claude-haiku-4.5",
    "openai-gpt-5-mini":           "gpt-5-mini",
    "openai-gpt-5":                "gpt-5",
}

print("\n\n% ── LaTeX table ──────────────────────────────────────────────────────")
print(r"""\begin{table}[t]
\centering
\caption{Stability scores per model and temperature ($N$ runs each).
         Scores range from 0 (worst) to 1 (best).}
\label{tab:phase1-stability}
\begin{tabular}{llccc}
\toprule
\textbf{Model} & \textbf{T} & \textbf{N} & \textbf{Mean $\pm$ Std} & \textbf{[Min, Max]} \\
\midrule""")

for key in ORDER:
    if key not in results:
        continue
    n, mean, std, mn, mx = results[key]
    model_disp = DISPLAY.get(key[0], key[0])
    print(
        f"\\texttt{{{model_disp}}} & {key[1]} & {n} & "
        f"${mean:.4f} \\pm {std:.4f}$ & [{mn:.4f}, {mx:.4f}] \\\\"
    )

print(r"""\bottomrule
\end{tabular}
\end{table}""")

# ── 5. Emit per-metric breakdown for the best group ──────────────────────────
best_key = max(results, key=lambda k: results[k][1])
print(f"\n\n% Best group: {best_key}  (mean={results[best_key][1]:.4f})")
print("\n% Per-run S scores for best group:")
for s in sorted(group_scores[best_key]):
    print(f"%   {s:.6f}")

# ── 6. Per-metric sub-scores for each run in the best group ──────────────────
print(f"\n\n% Sub-metric breakdown for {best_key}")
print(f"{'Run':>4}  {'pending_pods':>12}  {'time_w_pend':>11}  {'cost':>8}  {'migrations':>10}  {'S':>8}")
for (model, threshold, run_num), metrics in sorted(run_metrics.items(), key=lambda x: int(x[0][2])):
    if (model, threshold) != best_key:
        continue
    if len(metrics) < len(WEIGHTS):
        continue
    sub = {}
    S = 0.0
    for mname, (w, b) in WEIGHTS.items():
        v = metrics[mname]
        if mname == "cost":
            v = max(0.0, v - FIXED_COST)
        si = max(0.0, 1.0 - v / b)
        sub[mname] = si
        S += w * si
    print(
        f"{run_num:>4}  {sub['pending_pods']:>12.4f}  "
        f"{sub['time_with_pending']:>11.4f}  {sub['cost']:>8.4f}  "
        f"{sub['number_of_migrations']:>10.4f}  {S:>8.4f}"
    )
