"""
Generate paper figures for Phase 1 analysis.

Figure 1 – Per-model composite score distributions (box plots + jitter).
Figure 2 – Run-to-run migration timing variability for gemini-2.5-flash t=0.1.

Output: figures/fig1_model_comparison.pdf
        figures/fig2_gemini_migrations.pdf
"""

import csv
import os
from pathlib import Path
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
CSV_PATH = Path(
    os.path.expanduser(
        "~/Área de Trabalho/Projetos/simulator/analyzer/output/combined_summaries.csv"
    )
)
OUTPUT_DIR = Path(__file__).parent / "figures"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Scoring parameters (match adrs/core/evaluator.py) ────────────────────────
# Fixed cost of the always-on private cluster (10 nodes × t4g.2xlarge,
# $0.2688/hr per node, 30s intervals): (0.2688 * 10 * 30) / 3600
FIXED_COST = 0.0224

WEIGHTS    = {"pending_pods": 0.35, "time_with_pending": 0.25,
              "cost": 0.25, "number_of_migrations": 0.15}
BASELINES  = {"pending_pods": 100.0, "time_with_pending": 1.0,
              "cost": 0.1 - FIXED_COST, "number_of_migrations": 200.0}

# ── Groups to include (model, threshold, run_range) ──────────────────────────
GROUPS = [
    ("google-gemini-2.5-flash",    "0.1", range(1, 11)),
    ("google-gemini-2.5-flash",    "0.5", range(1, 11)),   # run 11 excluded below
    ("anthropic-claude-haiku-4.5", "0.1", range(1, 11)),
    ("anthropic-claude-haiku-4.5", "0.5", range(1, 11)),
    ("openai-gpt-5-mini",          "0.1", range(1, 11)),
    ("openai-gpt-5-mini",          "0.5", range(11, 21)),  # t=0.5 numbered 11-20
]

# ── Friendly labels for plot ──────────────────────────────────────────────────
MODEL_LABELS = {
    "google-gemini-2.5-flash":    "Gemini-2.5-Flash",
    "anthropic-claude-haiku-4.5": "Claude Haiku-4.5",
    "openai-gpt-5-mini":          "GPT-5-mini",
}

# ── 1. Load & score ───────────────────────────────────────────────────────────
def score_run(metric_means: dict[str, float]) -> float:
    s = 0.0
    for m, w in WEIGHTS.items():
        v = metric_means.get(m)
        if v is None:
            continue
        if m == "cost":
            v = max(0.0, v - FIXED_COST)
        b = BASELINES[m]
        s += w * max(0.0, 1.0 - v / b)
    return s


def load_scores() -> dict[tuple, list[float]]:
    """Return {(model, threshold): [composite_scores]} for each group."""

    # Build a lookup: (model, threshold, run_number) -> {metric: mean}
    raw: dict[tuple, dict[str, float]] = defaultdict(dict)
    with open(CSV_PATH) as fh:
        for row in csv.DictReader(fh):
            key = (row["model"], row["threshold"], int(row["run_number"]))
            raw[key][row["metric"]] = float(row["mean"])

    scores: dict[tuple, list[float]] = {}
    for model, threshold, run_range in GROUPS:
        group_key = (model, threshold)
        group_scores = []
        for r in run_range:
            key = (model, threshold, r)
            if key in raw:
                group_scores.append(score_run(raw[key]))
        if group_scores:
            scores[group_key] = group_scores
    return scores


# ── 2. Figure 1 – Model comparison ───────────────────────────────────────────
def fig1_model_comparison(scores: dict[tuple, list[float]]):
    models = ["google-gemini-2.5-flash",
              "anthropic-claude-haiku-4.5",
              "openai-gpt-5-mini"]
    temps  = ["0.1", "0.5"]

    # Color by temperature, hatching/position by model
    COLORS = {"0.1": "#2166ac", "0.5": "#d6604d"}   # blue / red
    ALPHA  = 0.85
    WIDTH  = 0.30
    MODEL_GAP = 1.0

    fig, ax = plt.subplots(figsize=(7.5, 4.0))

    positions_all = []
    labels_all    = []

    for mi, model in enumerate(models):
        base_x = mi * MODEL_GAP
        for ti, temp in enumerate(temps):
            key = (model, temp)
            data = scores.get(key, [])
            if not data:
                continue
            x = base_x + (ti - 0.5) * WIDTH * 1.1

            bp = ax.boxplot(
                data,
                positions=[x],
                widths=WIDTH,
                patch_artist=True,
                notch=False,
                showfliers=False,
                medianprops=dict(color="white", linewidth=2.0),
                whiskerprops=dict(color=COLORS[temp], linewidth=1.2),
                capprops=dict(color=COLORS[temp], linewidth=1.2),
                boxprops=dict(facecolor=COLORS[temp], alpha=ALPHA, linewidth=0),
            )

            # Jitter
            jitter = np.random.default_rng(42).uniform(-WIDTH * 0.28, WIDTH * 0.28, len(data))
            ax.scatter(
                [x + j for j in jitter],
                data,
                color="white",
                edgecolors=COLORS[temp],
                s=22,
                zorder=5,
                linewidth=0.7,
                alpha=0.9,
            )

        positions_all.append(base_x)
        labels_all.append(MODEL_LABELS[model])

    ax.set_xticks(positions_all)
    ax.set_xticklabels(labels_all, fontsize=10)
    ax.set_ylabel("Composite Score", fontsize=11)
    ax.set_ylim(0.15, 0.82)
    ax.yaxis.set_major_locator(plt.MultipleLocator(0.1))
    ax.grid(axis="y", linestyle="--", alpha=0.4, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)

    legend_handles = [
        mpatches.Patch(facecolor=COLORS["0.1"], alpha=ALPHA, label="$T = 0.1$"),
        mpatches.Patch(facecolor=COLORS["0.5"], alpha=ALPHA, label="$T = 0.5$"),
    ]
    ax.legend(handles=legend_handles, fontsize=9, framealpha=0.85,
              loc="upper right", edgecolor="0.8")

    fig.suptitle(
        "Inter-Model Comparison — Composite Score Distribution\n"
        "Baseline Prompt (v0), First 10 Runs per Configuration",
        fontsize=10.5,
        y=1.03,
    )
    fig.tight_layout()
    out = OUTPUT_DIR / "fig1_model_comparison.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=200, bbox_inches="tight")
    print(f"Saved {out}")
    plt.close(fig)


# ── 3. Figure 2 – Gemini run-to-run scoring patterns ─────────────────────────
def fig2_scoring_patterns(scores_raw: dict):
    """
    Dot-and-line chart showing the composite score and its four sub-metric
    scores for each of the 10 gemini-2.5-flash t=0.1 runs.

    Top panel  : composite score per run with mean ± std band.
    Bottom panel: sub-metric scores (pending_pods, time_w_pending, cost,
                  migrations) as grouped dots per run, making it easy to see
                  which component drives each run's outcome.
    """
    MODEL = "google-gemini-2.5-flash"
    TEMP  = "0.1"
    RUNS  = list(range(1, 11))

    # ── build per-run score breakdown from raw CSV ────────────────────────────
    raw: dict[tuple, dict[str, float]] = defaultdict(dict)
    with open(CSV_PATH) as fh:
        for row in csv.DictReader(fh):
            key = (row["model"], row["threshold"], int(row["run_number"]))
            raw[key][row["metric"]] = float(row["mean"])

    composite, sub = [], {m: [] for m in WEIGHTS}
    for r in RUNS:
        metrics = raw.get((MODEL, TEMP, r), {})
        composite.append(score_run(metrics))
        for m, b in BASELINES.items():
            v = metrics.get(m)
            if v is not None and m == "cost":
                v = max(0.0, v - FIXED_COST)
            sub[m].append(max(0.0, 1.0 - v / b) if v is not None else 0.0)

    run_labels = [str(r) for r in RUNS]
    x = np.arange(len(RUNS))
    mean_c = np.mean(composite)
    std_c  = np.std(composite)

    # ── colours / display names for sub-metrics ───────────────────────────────
    SUB_STYLE = {
        "pending_pods":      {"color": "#2166ac", "marker": "o", "label": "Pending Pods ($w$=0.35)"},
        "time_with_pending": {"color": "#4dac26", "marker": "s", "label": "Time w/ Pending ($w$=0.25)"},
        "cost":              {"color": "#d6604d", "marker": "^", "label": "Cost ($w$=0.25)"},
        "number_of_migrations": {"color": "#a020f0", "marker": "D", "label": "Migrations ($w$=0.15)"},
    }

    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1,
        figsize=(7.5, 5.2),
        gridspec_kw={"height_ratios": [1, 1.15]},
        layout="constrained",
    )

    # ── top: composite score ──────────────────────────────────────────────────
    ax_top.axhspan(mean_c - std_c, mean_c + std_c,
                   color="#bbbbbb", alpha=0.25, label=f"Mean ± 1 std ({mean_c:.3f} ± {std_c:.3f})")
    ax_top.axhline(mean_c, color="#555555", linewidth=1.2, linestyle="--", zorder=2)
    ax_top.plot(x, composite, color="#222222", linewidth=1.4,
                marker="o", markersize=6, zorder=3, label="Composite score")

    # Annotate each point
    for i, (xi, yi) in enumerate(zip(x, composite)):
        ax_top.text(xi, yi + 0.012, f"{yi:.3f}", ha="center", va="bottom",
                    fontsize=6.5, color="#222222")

    ax_top.set_xticks(x)
    ax_top.set_xticklabels(run_labels, fontsize=8.5)
    ax_top.set_xlim(-0.5, len(RUNS) - 0.5)
    ax_top.set_ylim(0.42, 0.82)
    ax_top.set_ylabel("Composite Score", fontsize=10)
    ax_top.set_xlabel("Run", fontsize=10)
    ax_top.yaxis.set_major_locator(plt.MultipleLocator(0.05))
    ax_top.grid(axis="y", linestyle="--", alpha=0.4, linewidth=0.7)
    ax_top.set_axisbelow(True)
    ax_top.spines[["top", "right"]].set_visible(False)
    ax_top.legend(fontsize=7.5, loc="lower right", framealpha=0.9, edgecolor="0.8")

    # ── bottom: sub-metric scores ─────────────────────────────────────────────
    for metric, vals in sub.items():
        sty = SUB_STYLE[metric]
        ax_bot.plot(x, vals, color=sty["color"], linewidth=1.0,
                    linestyle=":", alpha=0.55, zorder=2)
        ax_bot.scatter(x, vals, color=sty["color"], marker=sty["marker"],
                       s=38, zorder=3, label=sty["label"], alpha=0.9)

    ax_bot.set_xticks(x)
    ax_bot.set_xticklabels(run_labels, fontsize=8.5)
    ax_bot.set_xlim(-0.5, len(RUNS) - 0.5)
    ax_bot.set_ylim(-0.02, 1.05)
    ax_bot.set_ylabel("Sub-metric Score", fontsize=10)
    ax_bot.set_xlabel("Run", fontsize=10)
    ax_bot.yaxis.set_major_locator(plt.MultipleLocator(0.2))
    ax_bot.grid(axis="y", linestyle="--", alpha=0.4, linewidth=0.7)
    ax_bot.set_axisbelow(True)
    ax_bot.spines[["top", "right"]].set_visible(False)
    ax_bot.legend(fontsize=7.5, loc="lower right", framealpha=0.9,
                  edgecolor="0.8", ncol=2)

    fig.suptitle(
        "Intra-Model Variability — Gemini-2.5-Flash, $T=0.1$, Baseline Prompt (v0)\n"
        "Per-Run Composite and Sub-Metric Score Breakdown (Runs 1–10)",
        fontsize=10.5,
    )
    out = OUTPUT_DIR / "fig2_gemini_scoring.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=200, bbox_inches="tight")
    print(f"Saved {out}")
    plt.close(fig)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    np.random.seed(0)
    scores = load_scores()

    print("\nLoaded scores per group:")
    for (model, temp), vals in scores.items():
        m = np.mean(vals)
        s = np.std(vals)
        print(f"  {MODEL_LABELS.get(model, model)} t={temp}  "
              f"n={len(vals)}  mean={m:.4f}  std={s:.4f}  "
              f"min={min(vals):.4f}  max={max(vals):.4f}")

    fig1_model_comparison(scores)
    fig2_scoring_patterns(scores)
    print("\nDone. Figures written to:", OUTPUT_DIR)
