from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def _load_results(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("results", []))


def _mode_order(rows: list[dict[str, object]]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        mode = str(row.get("db_mode", "")).strip()
        if mode and mode not in seen:
            seen.append(mode)
    return seen


def _metric_map(rows: list[dict[str, object]], metric_key: str) -> tuple[list[str], dict[str, list[float]]]:
    scenarios = ["load_low", "load_high", "stress"]
    metrics: dict[str, list[float]] = {mode: [] for mode in _mode_order(rows)}

    for scenario in scenarios:
        for mode in metrics:
            row = next((r for r in rows if r.get("db_mode") == mode and r.get("run_name") == scenario), None)
            metrics[mode].append(float(row.get(metric_key, 0.0)) if row else 0.0)

    return scenarios, metrics


def _plot_grouped_bars(
    scenarios: list[str],
    metrics: dict[str, list[float]],
    *,
    title: str,
    y_label: str,
    output_path: Path,
) -> None:
    x = list(range(len(scenarios)))
    mode_names = list(metrics.keys())
    width = 0.8 / max(1, len(mode_names))
    colors = ["#f97316", "#0ea5e9", "#10b981", "#ef4444"]

    fig, ax = plt.subplots(figsize=(8.2, 4.8), dpi=120)
    for index, mode_name in enumerate(mode_names):
        offset = (index - (len(mode_names) - 1) / 2) * width
        label = mode_name.replace("_", " ")
        ax.bar([i + offset for i in x], metrics[mode_name], width=width, label=label, color=colors[index % len(colors)])

    ax.set_title(title)
    ax.set_xlabel("Scenario")
    ax.set_ylabel(y_label)
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.legend()

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot DB benchmark charts from JSON results")
    parser.add_argument("--input", required=True, help="Path to db_concurrency_results.json")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = input_path.parent

    rows = _load_results(input_path)

    scenarios, rps_metrics = _metric_map(rows, "rps")
    _plot_grouped_bars(
        scenarios,
        rps_metrics,
        title="RPS by Scenario",
        y_label="Requests per second",
        output_path=output_dir / "chart_rps_compare.png",
    )

    scenarios, p95_metrics = _metric_map(rows, "p95_ms")
    _plot_grouped_bars(
        scenarios,
        p95_metrics,
        title="P95 Latency by Scenario",
        y_label="P95 latency (ms)",
        output_path=output_dir / "chart_p95_compare.png",
    )

    scenarios, fail_metrics = _metric_map(rows, "failure_rate_pct")
    _plot_grouped_bars(
        scenarios,
        fail_metrics,
        title="Failure Rate by Scenario",
        y_label="Failure rate (%)",
        output_path=output_dir / "chart_fail_compare.png",
    )

    print(f"Charts written to: {output_dir}")


if __name__ == "__main__":
    main()
