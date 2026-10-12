"""Summaries, reports and charts for experiment results."""

from __future__ import annotations

import csv
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import yaml

from .config import Config

if TYPE_CHECKING:
    from .experiment import ArmResult

ARM_LABELS = {
    "evolving": "Evolving (random start)",
    "static_random": "Static (random)",
    "static_tuned": "Static (hand-tuned)",
    "evolving_tuned": "Evolving (hand-tuned start)",
}

# Reference categorical palette (light, dark), validated for adjacent-pair CVD separation.
SERIES_COLORS = {
    "evolving": ("#2a78d6", "#3987e5"),
    "static_random": ("#eb6834", "#d95926"),
    "static_tuned": ("#1baf7a", "#199e70"),
    "evolving_tuned": ("#eda100", "#c98500"),
}

COMPARISONS = [
    ("evolving", "static_random"),
    ("evolving", "static_tuned"),
    ("evolving_tuned", "static_tuned"),
]


def _pct(v: float) -> str:
    return f"{v:.0%}"


METRICS: list[tuple[str, str, Callable[[float], str]]] = [
    ("capital_multiple", "Capital multiple", lambda v: f"x{v:.2f}"),
    ("operating_profit", "Operating profit", lambda v: f"{v:+.1f}"),
    ("late_profit_per_agent", "Profit per agent per gen (last quarter)", lambda v: f"{v:+.2f}"),
    ("success_rate", "Success rate", _pct),
    ("market_share", "Market share", _pct),
    ("revenue_to_cost", "Revenue / full cost", lambda v: f"{v:.2f}"),
    ("final_agents", "Agents at end", lambda v: f"{v:.1f}"),
]


def run_metrics(result: ArmResult) -> dict[str, Any]:
    rows = result.rows
    tail = rows[-max(1, len(rows) // 4):]
    offered = sum(r["tasks_offered"] for r in rows)
    assigned = sum(r["tasks_assigned"] for r in rows)
    succeeded = sum(r["tasks_succeeded"] for r in rows)
    revenue = sum(r["revenue"] for r in rows)
    full_cost = sum(r["compute_cost"] + r["sales_cost"] + r["upkeep"] + r["spawn_fees"] for r in rows)
    final = rows[-1]
    return {
        "arm": result.arm,
        "seed": result.seed,
        "capital_multiple": final["wealth"] / result.initial_capital,
        "operating_profit": sum(r["net_profit"] for r in rows),
        "late_profit_per_agent": statistics.fmean(r["profit_per_agent"] for r in tail),
        "success_rate": succeeded / assigned if assigned else 0.0,
        "market_share": assigned / offered if offered else 0.0,
        "revenue_to_cost": revenue / full_cost if full_cost else 0.0,
        "final_agents": final["alive_after"],
        "births": sum(r["births"] for r in rows),
        "deaths": sum(r["bankrupt"] + r["defunded"] + r["outcompeted"] for r in rows),
    }


def _stats(values: list[float]) -> dict[str, float]:
    return {
        "mean": statistics.fmean(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def summarize(results: list[ArmResult], cfg: Config) -> dict[str, Any]:
    per_run = [run_metrics(r) for r in results]
    arms = [a for a in cfg.experiment.arms if any(r.arm == a for r in results)]
    by_arm = {}
    for arm in arms:
        runs = [p for p in per_run if p["arm"] == arm]
        by_arm[arm] = {key: _stats([p[key] for p in runs]) for key, _, _ in METRICS}

    comparisons = []
    for a, b in COMPARISONS:
        if a not in arms or b not in arms:
            continue
        pa = {p["seed"]: p for p in per_run if p["arm"] == a}
        pb = {p["seed"]: p for p in per_run if p["arm"] == b}
        seeds = sorted(set(pa) & set(pb))
        diffs = [pa[s]["capital_multiple"] - pb[s]["capital_multiple"] for s in seeds]
        late = [pa[s]["late_profit_per_agent"] - pb[s]["late_profit_per_agent"] for s in seeds]
        comparisons.append(
            {
                "arm": a,
                "baseline": b,
                "seeds": len(seeds),
                "wins": sum(d > 0 for d in diffs),
                "capital_multiple_diff": _stats(diffs),
                "late_profit_per_agent_diff": _stats(late),
            }
        )

    by_generation: dict[str, list[dict[str, float]]] = {}
    traits: dict[str, dict[str, dict[str, float]]] = {}
    for arm in arms:
        runs = [r for r in results if r.arm == arm]
        generations = len(runs[0].rows)
        series = []
        for g in range(generations):
            rows = [r.rows[g] for r in runs]
            series.append(
                {
                    "generation": g,
                    "capital_multiple": statistics.fmean(
                        r.rows[g]["wealth"] / r.initial_capital for r in runs
                    ),
                    "profit_per_agent": statistics.fmean(row["profit_per_agent"] for row in rows),
                    "success_rate": statistics.fmean(row["success_rate"] for row in rows),
                    "population": statistics.fmean(row["population"] for row in rows),
                }
            )
        by_generation[arm] = series
        traits[arm] = {
            "first": _mean_traits([r.rows[0] for r in runs]),
            "last": _mean_traits([r.rows[-1] for r in runs]),
        }

    return {
        "experiment": cfg.experiment.name,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "seeds": sorted({r.seed for r in results}),
        "generations": cfg.experiment.generations,
        "population_size": cfg.experiment.population_size,
        "arms": by_arm,
        "comparisons": comparisons,
        "per_run": per_run,
        "by_generation": by_generation,
        "traits": traits,
    }


def _mean_traits(rows: list[dict[str, Any]]) -> dict[str, float]:
    prefixes = ("gene:", "model:", "focus:", "demand:", "specialization")
    keys = [k for k in rows[0] if k.startswith(prefixes)]
    return {k: statistics.fmean(row.get(k, 0.0) for row in rows) for k in keys}


# ---------------------------------------------------------------------------
# Output files


def write_results(out: Path, cfg: Config, results: list[ArmResult], summary: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.yaml").write_text(yaml.safe_dump(cfg.to_dict(), sort_keys=False), encoding="utf-8")
    _write_csv(out / "generations.csv", [row for r in results for row in r.rows])
    _write_jsonl(out / "agents.jsonl", [a for r in results for a in r.agents])
    attempts = [a for r in results for a in r.attempts]
    if attempts:
        _write_jsonl(out / "attempts.jsonl", attempts)
    ledger = [t for r in results for t in r.ledger]
    if ledger:
        _write_csv(out / "ledger.csv", ledger)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    series = {arm: [p["capital_multiple"] for p in s] for arm, s in summary["by_generation"].items()}
    (out / "capital.svg").write_text(
        render_line_chart("Capital multiple by generation (mean over seeds)", series, reference=1.0),
        encoding="utf-8",
    )
    (out / "report.md").write_text(render_report(summary), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: dict[str, None] = {}
    for row in rows:
        fields.update(dict.fromkeys(row))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fields))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: round(v, 6) if isinstance(v, float) else v for k, v in row.items()})


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item) + "\n")


# ---------------------------------------------------------------------------
# Text report


def _fmt_stats(stats: dict[str, float], fmt: Callable[[float], str], n_seeds: int) -> str:
    if n_seeds < 2:
        return fmt(stats["mean"])
    spread = fmt(stats["std"]).lstrip("x+")
    return f"{fmt(stats['mean'])} ± {spread}"


TIE = 0.02  # capital multiple differences smaller than this count as no difference


def _judge(comparisons: list[dict[str, Any]]) -> str:
    """'Yes', 'No', 'No clear difference' or 'Not consistently', plus a caveat for one seed."""
    diffs = [c["capital_multiple_diff"]["mean"] for c in comparisons]
    if all(abs(d) < TIE for d in diffs):
        verdict = "No clear difference"
    elif all(d >= TIE and c["wins"] > c["seeds"] / 2 for d, c in zip(diffs, comparisons)):
        verdict = "Yes"
    elif all(d <= -TIE and c["wins"] < c["seeds"] / 2 for d, c in zip(diffs, comparisons)):
        verdict = "No"
    else:
        verdict = "Not consistently"
    if max(c["seeds"] for c in comparisons) == 1:
        verdict += " (one seed: a demonstration, not evidence)"
    return verdict + ": "


def verdicts(summary: dict[str, Any]) -> list[tuple[str, str]]:
    """The questions the first prototype has to answer, from whichever arms ran."""
    arms = summary["arms"]
    label = lambda a: ARM_LABELS.get(a, a)  # noqa: E731
    evolving = [a for a in arms if a.startswith("evolving")]
    comps = {(c["arm"], c["baseline"]): c for c in summary["comparisons"]}
    out = []

    if evolving:
        parts = [f"{label(a)} {arms[a]['revenue_to_cost']['mean']:.2f}" for a in evolving]
        ok = all(arms[a]["revenue_to_cost"]["mean"] > 1 for a in evolving)
        out.append(
            (
                "Do evolving agents earn more than their full cost (compute + sales + upkeep + spawning)?",
                f"{'Yes' if ok else 'Not in every arm'}: revenue / full cost = " + ", ".join(parts) + ".",
            )
        )

    same_start = [comps[k] for k in (("evolving", "static_random"), ("evolving_tuned", "static_tuned")) if k in comps]
    if same_start:
        parts = [
            f"{label(c['arm'])} vs {label(c['baseline'])}: wins in {c['wins']}/{c['seeds']} seeds, "
            f"capital multiple {c['capital_multiple_diff']['mean']:+.2f}"
            for c in same_start
        ]
        out.append(("Does evolution improve on the same strategies kept unchanged?", _judge(same_start) + "; ".join(parts) + "."))

    if ("evolving", "static_tuned") in comps:
        c = comps[("evolving", "static_tuned")]
        out.append(
            (
                "Does evolution from a random start match a strategy tuned offline by grid search?",
                _judge([c]) + f"wins in {c['wins']}/{c['seeds']} seeds "
                f"(capital multiple {c['capital_multiple_diff']['mean']:+.2f}).",
            )
        )

    if evolving:
        parts = [f"{label(a)} x{arms[a]['capital_multiple']['mean']:.2f}" for a in evolving]
        ok = all(arms[a]["capital_multiple"]["mean"] > 1 for a in evolving)
        out.append(
            (
                "Does the evolving population grow its capital?",
                f"{'Yes' if ok else 'Not in every arm'}: " + ", ".join(parts)
                + f" after {summary['generations']} generations.",
            )
        )
    return out


def render_report(summary: dict[str, Any]) -> str:
    n_seeds = len(summary["seeds"])
    arms = summary["arms"]
    lines = [
        f"# Astra Evolution: {summary['experiment']}",
        "",
        f"{n_seeds} seed(s) x {summary['generations']} generations, "
        f"{summary['population_size']} agents per arm at the start. Generated {summary['created']}.",
        "Every arm of a seed sees exactly the same tasks. Values are mean ± standard deviation over seeds.",
        "",
        "## Verdict",
        "",
    ]
    for question, answer in verdicts(summary):
        lines += [f"- **{question}** {answer}"]
    if "api" in summary:
        api = summary["api"]
        lines += [
            "",
            f"Paid API: {api['calls']} calls, ${api['spent_usd']:.4f} of real money "
            "(priced from the token usage the API reported).",
        ]

    lines += ["", "## Results by arm", ""]
    lines.append("| Arm | " + " | ".join(label for _, label, _ in METRICS) + " |")
    lines.append("|---|" + "---:|" * len(METRICS))
    for arm, stats in arms.items():
        cells = [_fmt_stats(stats[key], fmt, n_seeds) for key, _, fmt in METRICS]
        lines.append(f"| {ARM_LABELS.get(arm, arm)} | " + " | ".join(cells) + " |")

    if summary["comparisons"]:
        lines += [
            "",
            "## Paired comparisons",
            "",
            "Same seed, same tasks; a win means a higher final capital.",
            "",
            "| Arm | Baseline | Wins | Capital multiple difference | Profit per agent difference (last quarter) |",
            "|---|---|---:|---:|---:|",
        ]
        for c in summary["comparisons"]:
            d, p = c["capital_multiple_diff"], c["late_profit_per_agent_diff"]
            lines.append(
                f"| {ARM_LABELS.get(c['arm'], c['arm'])} | {ARM_LABELS.get(c['baseline'], c['baseline'])} | "
                f"{c['wins']}/{c['seeds']} | {d['mean']:+.2f} (min {d['min']:+.2f}, max {d['max']:+.2f}) | "
                f"{p['mean']:+.2f} |"
            )

    lines += ["", "## Capital over time", "", "![Capital multiple by generation](capital.svg)", ""]
    generations = summary["generations"]
    step = max(1, generations // 10)
    picks = sorted(set(range(0, generations, step)) | {generations - 1})
    names = list(arms)
    lines.append("| Generation | " + " | ".join(ARM_LABELS.get(a, a) for a in names) + " |")
    lines.append("|---:|" + "---:|" * len(names))
    for g in picks:
        cells = [f"x{summary['by_generation'][a][g]['capital_multiple']:.2f}" for a in names]
        lines.append(f"| {g} | " + " | ".join(cells) + " |")

    for arm, traits in summary["traits"].items():
        if not arm.startswith("evolving"):
            continue
        first, last = traits["first"], traits["last"]
        lines += [
            "",
            f"## What evolution selected: {ARM_LABELS.get(arm, arm)}",
            "",
            "Average strategy of working agents in the first and the last generation.",
            "",
            "| Trait | First generation | Last generation |",
            "|---|---:|---:|",
        ]
        for key in first:
            if key.startswith("demand:"):
                continue
            lines.append(f"| {key} | {first[key]:.2f} | {last.get(key, 0.0):.2f} |")
        demand = [k for k in last if k.startswith("demand:")]
        if demand:
            lines += [
                "",
                "Market demand in the last generation, to compare with `focus:*` above: "
                + ", ".join(f"{k.split(':', 1)[1]} {last[k]:.0%}" for k in demand)
                + ".",
            ]

    lines += [
        "",
        "## How to read this",
        "",
        "- **Capital multiple**: (all agent balances, debts of bankrupt agents included, + money taken back"
        " from defunded agents) / initial funding. Above 1 means the population earned more than it spent.",
        "- **Operating profit**: revenue minus compute, sales and upkeep costs, summed over all agents and generations.",
        "- **Revenue / full cost**: revenue divided by compute + sales + upkeep + spawn fees.",
        "- **Static** arms never reproduce or mutate; agents only leave them by going bankrupt.",
        "- Beating *Static (random)* is easy. Beating *Static (hand-tuned)* is the meaningful test.",
        "",
    ]
    return "\n".join(lines)


def format_summary(summary: dict[str, Any]) -> str:
    """Compact terminal version of the report."""
    n_seeds = len(summary["seeds"])
    keys = ["capital_multiple", "late_profit_per_agent", "success_rate", "revenue_to_cost", "final_agents"]
    fmts = {key: fmt for key, _, fmt in METRICS}
    header = f"{'arm':<30}" + "".join(f"{k:>24}" for k in keys)
    lines = [header, "-" * len(header)]
    for arm, stats in summary["arms"].items():
        cells = "".join(f"{_fmt_stats(stats[k], fmts[k], n_seeds):>24}" for k in keys)
        lines.append(f"{ARM_LABELS.get(arm, arm):<30}{cells}")
    lines.append("")
    for question, answer in verdicts(summary):
        lines.append(f"{question}\n  {answer}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SVG chart (no plotting dependency; renders on GitHub, follows light/dark mode)


def _nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    if hi - lo < 1e-9:
        lo, hi = lo - 0.5, hi + 0.5
    raw = (hi - lo) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    start = math.floor(lo / step) * step
    ticks = []
    value = start
    while value < hi + step * 0.999:
        ticks.append(round(value, 10))
        value += step
    return ticks


def _spread_labels(ys: list[float], gap: float, lo: float, hi: float) -> list[float]:
    """Move label positions apart so they never overlap, keeping their order."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    placed = [ys[i] for i in order]
    for i in range(1, len(placed)):
        placed[i] = max(placed[i], placed[i - 1] + gap)
    overflow = placed[-1] - hi if placed else 0
    if overflow > 0:
        placed = [max(lo, y - overflow) for y in placed]
    out = [0.0] * len(ys)
    for rank, i in enumerate(order):
        out[i] = placed[rank]
    return out


def render_line_chart(title: str, series: dict[str, list[float]], reference: float | None = None) -> str:
    width, height = 820, 400
    left, right, top, bottom = 56, 210, 70, 44
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [v for vs in series.values() for v in vs] + ([reference] if reference is not None else [])
    ticks = _nice_ticks(min(values), max(values))
    y_lo, y_hi = ticks[0], ticks[-1]
    n = max(len(vs) for vs in series.values())

    def x(i: int) -> float:
        return left + plot_w * (i / max(1, n - 1))

    def y(v: float) -> float:
        return top + plot_h * (1 - (v - y_lo) / (y_hi - y_lo))

    light = "".join(f"--s-{a}:{c[0]};" for a, c in SERIES_COLORS.items())
    dark = "".join(f"--s-{a}:{c[1]};" for a, c in SERIES_COLORS.items())
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="{title}">',
        "<style>",
        f"svg{{--surface:#fcfcfb;--text:#0b0b0b;--muted:#52514e;--grid:#e8e7e3;--axis:#b5b3ad;{light}}}",
        "@media (prefers-color-scheme: dark){"
        f"svg{{--surface:#1a1a19;--text:#f0efec;--muted:#c3c2b7;--grid:#2e2e2c;--axis:#5c5b57;{dark}}}}}",
        "text{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;font-size:12px;fill:var(--muted)}",
        ".title{font-size:15px;font-weight:600;fill:var(--text)}",
        ".label{fill:var(--text)}",
        "</style>",
        f'<rect width="{width}" height="{height}" fill="var(--surface)"/>',
        f'<text class="title" x="{left}" y="24">{title}</text>',
    ]
    # Legend row (identity is never carried by color alone: line-key + name).
    lx = left
    for arm in series:
        name = ARM_LABELS.get(arm, arm)
        out.append(
            f'<line x1="{lx}" y1="44" x2="{lx + 16}" y2="44" stroke="var(--s-{arm})" '
            'stroke-width="2" stroke-linecap="round"/>'
        )
        out.append(f'<text x="{lx + 22}" y="48">{name}</text>')
        lx += 30 + 6.6 * len(name)
    for t in ticks:
        out.append(
            f'<line x1="{left}" y1="{y(t):.1f}" x2="{left + plot_w}" y2="{y(t):.1f}" '
            'stroke="var(--grid)" stroke-width="1"/>'
        )
        out.append(f'<text x="{left - 8}" y="{y(t) + 4:.1f}" text-anchor="end">x{t:g}</text>')
    if reference is not None:
        out.append(
            f'<line x1="{left}" y1="{y(reference):.1f}" x2="{left + plot_w}" y2="{y(reference):.1f}" '
            'stroke="var(--axis)" stroke-width="1"/>'
        )
    x_ticks = sorted({int(t) for t in _nice_ticks(0, max(1, n - 1), 8) if t <= n - 1 and float(t).is_integer()})
    for i in x_ticks:
        out.append(f'<text x="{x(i):.1f}" y="{top + plot_h + 18}" text-anchor="middle">{i}</text>')
    out.append(
        f'<text x="{left + plot_w / 2:.1f}" y="{height - 6}" text-anchor="middle">generation</text>'
    )
    for arm, vs in series.items():
        points = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vs))
        out.append(
            f'<polyline points="{points}" fill="none" stroke="var(--s-{arm})" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        )
    ends = {arm: vs[-1] for arm, vs in series.items()}
    label_ys = _spread_labels([y(v) for v in ends.values()], 16, top, top + plot_h)
    for (arm, value), ly in zip(ends.items(), label_ys):
        ex, ey = x(len(series[arm]) - 1), y(value)
        out.append(
            f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="var(--s-{arm})" '
            'stroke="var(--surface)" stroke-width="2"/>'
        )
        out.append(
            f'<line x1="{ex + 10:.1f}" y1="{ly:.1f}" x2="{ex + 22:.1f}" y2="{ly:.1f}" '
            f'stroke="var(--s-{arm})" stroke-width="2" stroke-linecap="round"/>'
        )
        out.append(
            f'<text class="label" x="{ex + 28:.1f}" y="{ly + 4:.1f}">x{value:.2f} '
            f"{ARM_LABELS.get(arm, arm)}</text>"
        )
    out.append("</svg>")
    return "\n".join(out)
