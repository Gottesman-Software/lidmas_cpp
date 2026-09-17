#!/usr/bin/env python3
"""Analyze paper_05 live compact CSS/Steane syndrome correction results."""

from __future__ import annotations

import argparse
import collections
import csv
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from paper05_plot_style import (
    HEATMAP_CMAP,
    apply_journal_style,
    compact_source_label,
    half_panel_size,
    horizontal_heatmap_size,
    metric_color,
    save_journal_figure,
    short_dataset_label,
    source_linestyle,
    source_marker,
    style_bar_axis,
    style_heatmap_axis,
    style_rate_axis,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decoded-csv", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--manuscript-dir")
    parser.add_argument("--decoder", default="mwpm")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def select_decoder_rows(rows: list[dict[str, str]], decoder: str) -> list[dict[str, str]]:
    if not rows or "decoder" not in rows[0]:
        return rows
    selected = [row for row in rows if row.get("decoder", "mwpm") == decoder]
    if not selected:
        raise SystemExit(f"no decoded rows found for decoder={decoder!r}")
    return selected


def f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fobj:
        writer = csv.DictWriter(fobj, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return (float("nan"), float("nan"))
    phat = successes / total
    denom = 1.0 + (z * z / total)
    center = (phat + (z * z) / (2.0 * total)) / denom
    radius = (z / denom) * math.sqrt((phat * (1.0 - phat) / total) + ((z * z) / (4.0 * total * total)))
    return (max(0.0, center - radius), min(1.0, center + radius))


def save_fig(fig: Any, prefix: Path, manuscript_dir: Path | None) -> None:
    save_journal_figure(fig, prefix, manuscript_dir)


def dataset_label(dataset: str, backend: str = "") -> str:
    return short_dataset_label(dataset, backend)


def circuit_label(circuit_id: str) -> str:
    if circuit_id == "clean":
        return "clean"
    if circuit_id.startswith("x_data_"):
        return f"X{circuit_id.removeprefix('x_data_')}"
    return circuit_id.replace("_", " ")


def circuit_sort_key(circuit_id: str) -> tuple[int, int | str]:
    if circuit_id == "clean":
        return (0, 0)
    if circuit_id.startswith("x_data_"):
        try:
            return (1, int(circuit_id.removeprefix("x_data_")))
        except ValueError:
            pass
    return (2, circuit_id)


def summarize(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = collections.defaultdict(list)
    for row in rows:
        groups[(row["dataset"], row["circuit_id"])].append(row)

    out: list[dict[str, Any]] = []
    for (dataset, circuit_id), group in sorted(groups.items()):
        injected_values = {r.get("injected_x", "") for r in group if r.get("injected_x", "") != ""}
        injected = sorted(injected_values)[0] if injected_values else ""
        syndrome_weights = np.asarray([f(r["syndrome_weight"]) for r in group], dtype=float)
        correction_weights = np.asarray([f(r["correction_weight"]) for r in group], dtype=float)
        exact_values = np.asarray([f(r["exact_intended_match"]) for r in group], dtype=float)
        contain_values = np.asarray([f(r["contains_intended_target"]) for r in group], dtype=float)
        exact_count = int(np.sum(exact_values))
        contain_count = int(np.sum(contain_values))
        exact_low, exact_high = wilson_ci(exact_count, len(group))
        contain_low, contain_high = wilson_ci(contain_count, len(group))
        syndromes = collections.Counter(r["measured_syndrome"] for r in group)
        corrections = collections.Counter(r["correction_indices"] for r in group)
        out.append(
            {
                "dataset": dataset,
                "source": group[0].get("source", ""),
                "backend": group[0].get("backend", ""),
                "circuit_id": circuit_id,
                "injected_x": injected,
                "shots": len(group),
                "mean_syndrome_weight": f"{float(np.mean(syndrome_weights)):.6f}",
                "nonempty_syndrome_rate": f"{float(np.mean(syndrome_weights > 0)):.6f}",
                "mean_correction_weight": f"{float(np.mean(correction_weights)):.6f}",
                "exact_intended_match_count": exact_count,
                "exact_intended_match_rate": f"{float(np.mean(exact_values)):.6f}",
                "exact_intended_match_ci95_low": f"{exact_low:.6f}",
                "exact_intended_match_ci95_high": f"{exact_high:.6f}",
                "contains_intended_target_count": contain_count,
                "contains_intended_target_rate": f"{float(np.mean(contain_values)):.6f}",
                "contains_intended_target_ci95_low": f"{contain_low:.6f}",
                "contains_intended_target_ci95_high": f"{contain_high:.6f}",
                "most_common_syndrome": syndromes.most_common(1)[0][0] if syndromes else "",
                "most_common_syndrome_count": syndromes.most_common(1)[0][1] if syndromes else 0,
                "most_common_correction": corrections.most_common(1)[0][0] if corrections else "",
                "most_common_correction_count": corrections.most_common(1)[0][1] if corrections else 0,
            }
        )
    return out


def plot_syndrome_heatmap(rows: list[dict[str, str]], out_dir: Path, manuscript_dir: Path | None) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    groups: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    meta: dict[tuple[str, str], str] = {}
    max_checks = 0
    for row in rows:
        syndrome = row["measured_syndrome"]
        key = (row["dataset"], row["circuit_id"])
        groups[key].append(syndrome)
        meta[key] = row.get("backend", "")
        max_checks = max(max_checks, len(syndrome))
    ordered = sorted(groups, key=lambda key: (0 if key[0].startswith("ibm_") else 1, circuit_sort_key(key[1])))
    labels = [
        compact_source_label(dataset, circuit, meta.get((dataset, circuit), ""))
        for dataset, circuit in ordered
    ]
    mat = np.zeros((len(labels), max_checks), dtype=float)
    for ridx, key in enumerate(ordered):
        syndromes = groups[key]
        for cidx in range(max_checks):
            vals = [int(s[cidx]) for s in syndromes if cidx < len(s)]
            mat[ridx, cidx] = float(np.mean(vals)) if vals else 0.0

    fig, ax = plt.subplots(figsize=horizontal_heatmap_size(len(labels), max_checks), constrained_layout=True)
    im = ax.imshow(mat.T, aspect="auto", cmap=HEATMAP_CMAP, vmin=0.0, vmax=1.0, interpolation="nearest")
    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", rotation_mode="anchor")
    ax.set_yticks(np.arange(max_checks))
    ax.set_yticklabels([f"Z{i}" for i in range(max_checks)])
    ax.set_xlabel("stream (I=IBM, L=local)")
    ax.set_ylabel("Z-check bit")
    for idx in range(1, len(ordered)):
        if ordered[idx][0] != ordered[idx - 1][0]:
            ax.axvline(idx - 0.5, color="white", linewidth=1.1)
    style_heatmap_axis(ax)
    cbar = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
    cbar.set_label("activation rate")
    save_fig(fig, out_dir / "figure_qldpc_syndrome_heatmap", manuscript_dir)
    plt.close(fig)


def plot_correction_match(summary_rows: list[dict[str, Any]], out_dir: Path, manuscript_dir: Path | None) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    inj_rows = [r for r in summary_rows if str(r.get("injected_x", "")) != ""]
    if not inj_rows:
        return
    targets = sorted({int(str(r["injected_x"])) for r in inj_rows})
    dataset_keys = sorted({str(r["dataset"]) for r in inj_rows}, key=lambda d: (0 if d.startswith("ibm_") else 1, d))
    row_by_key = {(str(r["dataset"]), int(str(r["injected_x"]))): r for r in inj_rows}
    meta = {str(r["dataset"]): str(r.get("backend", "")) for r in inj_rows}
    x = np.arange(len(targets))

    fig, ax = plt.subplots(figsize=half_panel_size("rate"), constrained_layout=True)
    contains_same_as_exact = all(
        str(row.get("exact_intended_match_rate", "")) == str(row.get("contains_intended_target_rate", ""))
        for row in inj_rows
    )
    if contains_same_as_exact:
        metric_styles = [
            (
                "exact_intended_match_rate",
                "exact_intended_match_ci95_low",
                "exact_intended_match_ci95_high",
                "localization",
                "#2563EB",
                "o",
            ),
        ]
    else:
        metric_styles = [
            (
                "exact_intended_match_rate",
                "exact_intended_match_ci95_low",
                "exact_intended_match_ci95_high",
                "exact",
                "#2563EB",
                "o",
            ),
            (
                "contains_intended_target_rate",
                "contains_intended_target_ci95_low",
                "contains_intended_target_ci95_high",
                "contains",
                "#059669",
                "s",
            ),
        ]
    for didx, dataset in enumerate(dataset_keys):
        linestyle = "-" if didx == 0 else "--"
        for field, low_field, high_field, metric_name, color, marker in metric_styles:
            values = np.asarray([f(row_by_key[(dataset, target)][field]) for target in targets], dtype=float)
            lows = np.asarray([f(row_by_key[(dataset, target)][low_field]) for target in targets], dtype=float)
            highs = np.asarray([f(row_by_key[(dataset, target)][high_field]) for target in targets], dtype=float)
            ax.errorbar(
                x,
                values,
                yerr=np.vstack([values - lows, highs - values]),
                color=metric_color(metric_name),
                linestyle=source_linestyle(dataset),
                marker=source_marker(dataset, marker),
                linewidth=1.45,
                markersize=4.2,
                capsize=2.6,
                capthick=0.8,
                label=f"{dataset_label(dataset, meta.get(dataset, ''))} {metric_name}",
            )

    ax.set_ylabel("localization rate")
    ax.set_xticks(x)
    ax.set_xticklabels([f"X{target}" for target in targets])
    style_rate_axis(ax, ymin=0.75)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, handlelength=1.4, columnspacing=0.8)
    save_fig(fig, out_dir / "figure_qldpc_correction_localization", manuscript_dir)
    plt.close(fig)


def plot_correction_volume(summary_rows: list[dict[str, Any]], out_dir: Path, manuscript_dir: Path | None) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    circuit_ids = sorted({str(r["circuit_id"]) for r in summary_rows}, key=circuit_sort_key)
    dataset_keys = sorted({str(r["dataset"]) for r in summary_rows}, key=lambda d: (0 if d.startswith("ibm_") else 1, d))
    row_by_key = {(str(r["dataset"]), str(r["circuit_id"])): r for r in summary_rows}
    meta = {str(r["dataset"]): str(r.get("backend", "")) for r in summary_rows}
    x = np.arange(len(circuit_ids))
    width = min(0.36, 0.75 / max(1, len(dataset_keys)))
    colors = ["#2563EB", "#7C3AED", "#F59E0B", "#059669"]

    fig, ax = plt.subplots(figsize=half_panel_size("bar"), constrained_layout=True)
    for didx, dataset in enumerate(dataset_keys):
        offset = (didx - (len(dataset_keys) - 1) / 2) * width
        values = np.asarray([f(row_by_key[(dataset, circuit)]["mean_correction_weight"]) for circuit in circuit_ids], dtype=float)
        ax.bar(
            x + offset,
            values,
            width=width,
            color=colors[didx % len(colors)],
            label=dataset_label(dataset, meta.get(dataset, "")),
        )
    ax.set_ylabel("mean correction weight")
    ax.set_xticks(x)
    ax.set_xticklabels([circuit_label(circuit) for circuit in circuit_ids])
    style_bar_axis(ax)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=len(dataset_keys))
    save_fig(fig, out_dir / "figure_qldpc_correction_volume", manuscript_dir)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    decoded_csv = Path(args.decoded_csv)
    out_dir = Path(args.out_dir)
    manuscript_dir = Path(args.manuscript_dir) if args.manuscript_dir else None
    out_dir.mkdir(parents=True, exist_ok=True)
    if manuscript_dir is not None:
        manuscript_dir.mkdir(parents=True, exist_ok=True)

    rows = select_decoder_rows(read_csv(decoded_csv), args.decoder)
    summary_rows = summarize(rows)
    write_csv(
        out_dir / "table_qldpc_syndrome_summary.csv",
        summary_rows,
        [
            "dataset",
            "source",
            "backend",
            "circuit_id",
            "injected_x",
            "shots",
            "mean_syndrome_weight",
            "nonempty_syndrome_rate",
            "mean_correction_weight",
            "exact_intended_match_count",
            "exact_intended_match_rate",
            "exact_intended_match_ci95_low",
            "exact_intended_match_ci95_high",
            "contains_intended_target_count",
            "contains_intended_target_rate",
            "contains_intended_target_ci95_low",
            "contains_intended_target_ci95_high",
            "most_common_syndrome",
            "most_common_syndrome_count",
            "most_common_correction",
            "most_common_correction_count",
        ],
    )

    import matplotlib  # type: ignore

    matplotlib.use("Agg", force=True)
    apply_journal_style()
    plot_syndrome_heatmap(rows, out_dir, manuscript_dir)
    plot_correction_match(summary_rows, out_dir, manuscript_dir)
    plot_correction_volume(summary_rows, out_dir, manuscript_dir)
    print(f"Wrote paper_05 compact CSS/Steane analysis to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
