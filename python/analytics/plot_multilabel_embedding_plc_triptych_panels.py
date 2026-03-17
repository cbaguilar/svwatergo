#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D


ACTUATORS = (
    "ropumprun",
    "wellpumprun",
    "feedpumprun",
    "deliveryrun",
    "inletrun",
    "flushrun",
    "concbypassrun",
    "proddiversionrun",
)

ACTUATOR_ABBREV = {
    "ropumprun": "P2",
    "wellpumprun": "WP",
    "feedpumprun": "P1",
    "deliveryrun": "P3",
    "inletrun": "IN",
    "flushrun": "AV2",
    "concbypassrun": "CB",
    "proddiversionrun": "PD",
}

STATE_COLORS = {
    "off": "#4c78a8",
    "transition": "#f58518",
    "on": "#54a24b",
    "unknown": "#9d9da1",
}

BIT_ABBREV = {
    "0": "0",
    "1": "T",
    "2": "1",
    "u": "U",
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render triptych actuation panels across embedding PCA and PLC aux PCA.")
    p.add_argument("--embedding-parquet", required=True)
    p.add_argument("--plc-parquet", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--projection", default="3d", choices=["2d", "3d"])
    p.add_argument("--combo-col", default="actuation_bits")
    p.add_argument("--actuators", default="ropumprun,wellpumprun,feedpumprun,deliveryrun,flushrun")
    p.add_argument("--combo-top-k", type=int, default=0)
    p.add_argument("--drop-unknown", default="yes", choices=["yes", "no"])
    p.add_argument("--quantile-limits", default="1,99")
    p.add_argument("--point-size", type=float, default=10.0)
    p.add_argument("--alpha", type=float, default=0.6)
    p.add_argument("--title-prefix", default="Actuation Triptych")
    p.add_argument("--metrics-json", default=None)
    p.add_argument("--metrics-split", default="test_metrics")
    return p.parse_args()


def _parse_actuators(text: str) -> list[str]:
    vals = [x.strip() for x in str(text).split(",") if x.strip()]
    if not vals:
        raise SystemExit("--actuators must include at least one actuator")
    return vals


def _state_to_bit(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .fillna("unknown")
        .astype(str)
        .map({"off": "0", "transition": "1", "on": "2", "unknown": "u"})
        .fillna("u")
        .astype("string")
    )


def _resolve_combo_series(df: pd.DataFrame, combo_col: str, actuators: list[str]) -> pd.Series:
    if combo_col in df.columns:
        return df[combo_col].astype("string").fillna("<NA>").astype(str)
    parts = []
    for actuator in actuators:
        state_col = f"{actuator}_state"
        if state_col not in df.columns:
            raise SystemExit(f"missing state column: {state_col}")
        parts.append(_state_to_bit(df[state_col]))
    return pd.concat(parts, axis=1).agg("".join, axis=1).astype("string").astype(str)


def _axis_limits(df: pd.DataFrame, cols: list[str], q0: float, q1: float):
    x0, x1 = np.percentile(pd.to_numeric(df[cols[0]], errors="coerce").dropna(), [q0, q1])
    y0, y1 = np.percentile(pd.to_numeric(df[cols[1]], errors="coerce").dropna(), [q0, q1])
    if len(cols) >= 3:
        z0, z1 = np.percentile(pd.to_numeric(df[cols[2]], errors="coerce").dropna(), [q0, q1])
        return float(x0), float(x1), float(y0), float(y1), float(z0), float(z1)
    return float(x0), float(x1), float(y0), float(y1), None, None


def _apply_limits(ax, limits, projection: str) -> None:
    x0, x1, y0, y1, z0, z1 = limits
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    if projection == "3d" and z0 is not None and z1 is not None:
        ax.set_zlim(z0, z1)


def _load_metrics_lines(metrics_json: str | None, metrics_split: str, actuators: list[str]) -> list[str]:
    if not metrics_json:
        return []
    path = Path(metrics_json)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return []
    split_node = payload.get(metrics_split, {})
    if not isinstance(split_node, dict):
        return []
    per_target = split_node.get("per_target", {})
    if not isinstance(per_target, dict):
        return []
    lines: list[str] = []
    for actuator in actuators:
        target_node = None
        for key, value in per_target.items():
            if key == actuator or key == f"{actuator}_duty_target" or str(key).startswith(f"{actuator}_"):
                target_node = value
                break
        if not isinstance(target_node, dict):
            continue
        acc = float(target_node.get("accuracy", 0.0))
        precision = float(target_node.get("precision", 0.0))
        recall = float(target_node.get("recall", 0.0))
        f1 = float(target_node.get("f1", 0.0))
        lines.append(
            f"{ACTUATOR_ABBREV.get(actuator, actuator)} acc={acc:.3f} P={precision:.3f} R={recall:.3f} F1={f1:.3f}"
        )
    return lines


def _draw_combo_grid(
    ax,
    top_labels: list[str],
    counts: list[int],
    colors: list,
    combo_col: str,
    actuators: list[str],
    metrics_lines: list[str],
    metrics_split: str,
) -> None:
    ax.axis("off")
    headers = [combo_col, "n"] + [ACTUATOR_ABBREV.get(a, a) for a in actuators]
    rows = []
    for idx, label in enumerate(top_labels):
        bits = str(label)
        row = [bits, str(int(counts[idx]))]
        for i, _a in enumerate(actuators):
            ch = bits[i] if i < len(bits) else "u"
            row.append(BIT_ABBREV.get(ch, ch))
        rows.append(row)
    tbl = ax.table(
        cellText=rows,
        colLabels=headers,
        bbox=[0.0, 0.34 if metrics_lines else 0.0, 1.0, 0.66 if metrics_lines else 1.0],
        cellLoc="center",
        colLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1.0, 1.35)
    for c in range(len(headers)):
        cell = tbl[(0, c)]
        cell.set_facecolor("#e9eef7")
        cell.set_text_props(weight="bold")
    for r in range(1, len(rows) + 1):
        rgb = np.array(to_rgb(colors[r - 1]), dtype=float)
        fill = tuple((0.82 * 1.0) + (0.18 * rgb))
        for c in range(len(headers)):
            tbl[(r, c)].set_facecolor(fill)
    ax.set_title("Top Combination Grid", fontsize=11, pad=10)
    if metrics_lines:
        ax.text(
            0.02,
            0.28,
            f"{metrics_split.replace('_', ' ')} per-actuator metrics",
            transform=ax.transAxes,
            va="bottom",
            ha="left",
            fontsize=10,
            weight="bold",
        )
        ax.text(
            0.02,
            0.02,
            "\n".join(metrics_lines),
            transform=ax.transAxes,
            va="bottom",
            ha="left",
            fontsize=9,
            family="monospace",
            bbox={"facecolor": "#f8f8f8", "edgecolor": "#d0d0d0", "boxstyle": "round,pad=0.4"},
        )


def _metrics_suffix(metrics_lines: list[str], actuator: str) -> str:
    prefix = f"{ACTUATOR_ABBREV.get(actuator, actuator)} "
    for line in metrics_lines:
        if line.startswith(prefix):
            return line[len(prefix):]
    return ""


def _scatter(ax, x, y, z, mask, *, color, point_size: float, alpha: float, projection: str):
    if projection == "3d":
        ax.scatter(x[mask], y[mask], z[mask], s=point_size, alpha=alpha, color=color, linewidths=0.0)
    else:
        ax.scatter(x[mask], y[mask], s=point_size, alpha=alpha, color=color, linewidths=0.0)


def main() -> int:
    args = _parse_args()
    emb_df = pd.read_parquet(Path(args.embedding_parquet))
    plc_df = pd.read_parquet(Path(args.plc_parquet))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    projection = str(args.projection)
    actuators = _parse_actuators(str(args.actuators))
    metrics_lines = _load_metrics_lines(args.metrics_json, str(args.metrics_split), actuators)

    if str(args.drop_unknown) == "yes" and "actuation_combo" in emb_df.columns:
        keep_mask = ~emb_df["actuation_combo"].astype(str).str.contains("unknown", na=False)
        emb_df = emb_df.loc[keep_mask].reset_index(drop=True)
        plc_df = plc_df.loc[keep_mask].reset_index(drop=True)

    combo_series = _resolve_combo_series(emb_df, str(args.combo_col), actuators)
    cats = combo_series.astype("string").fillna("<NA>").astype(str)
    if int(args.combo_top_k) <= 0:
        top_labels = cats.value_counts().index.tolist()
        plot_label = cats
    else:
        top_labels = cats.value_counts().head(max(1, int(args.combo_top_k))).index.tolist()
        plot_label = cats.where(cats.isin(top_labels), other="OTHER")
    uniq = sorted(plot_label.unique().tolist())
    color_map = {str(label): plt.get_cmap("tab20", max(len(uniq), 1))(i) for i, label in enumerate(uniq)}

    q0, q1 = [float(x.strip()) for x in str(args.quantile_limits).split(",")]
    emb_cols = ["pann_true_pc1", "pann_true_pc2"] + (["pann_true_pc3"] if projection == "3d" else [])
    plc_pred_cols = ["plc_pred_pc1", "plc_pred_pc2"] + (["plc_pred_pc3"] if projection == "3d" else [])
    plc_true_cols = ["plc_true_pc1", "plc_true_pc2"] + (["plc_true_pc3"] if projection == "3d" else [])
    emb_limits = _axis_limits(emb_df, emb_cols, q0, q1)
    plc_merge = pd.DataFrame(
        {
            "pc1": pd.concat([plc_df[plc_pred_cols[0]], plc_df[plc_true_cols[0]]], ignore_index=True),
            "pc2": pd.concat([plc_df[plc_pred_cols[1]], plc_df[plc_true_cols[1]]], ignore_index=True),
        }
    )
    plc_limit_cols = ["pc1", "pc2"]
    if projection == "3d":
        plc_merge["pc3"] = pd.concat([plc_df[plc_pred_cols[2]], plc_df[plc_true_cols[2]]], ignore_index=True)
        plc_limit_cols.append("pc3")
    plc_limits = _axis_limits(plc_merge, plc_limit_cols, q0, q1)

    # Joint actuation bits triptych + grid.
    fig = plt.figure(figsize=(16, 12), dpi=160)
    ax0 = fig.add_subplot(3, 2, 1, projection=("3d" if projection == "3d" else None))
    ax1 = fig.add_subplot(3, 2, 3, projection=("3d" if projection == "3d" else None))
    ax2 = fig.add_subplot(3, 2, 5, projection=("3d" if projection == "3d" else None))
    axg = fig.add_subplot(1, 2, 2)
    rows = [
        ("Audio Embedding PCA", emb_df, emb_cols, ax0, emb_limits),
        ("Learned PLC PCA Aux", plc_df, plc_pred_cols, ax1, plc_limits),
        ("Real PLC PCA Aux", plc_df, plc_true_cols, ax2, plc_limits),
    ]
    for row_title, df_row, cols_row, ax, limits in rows:
        x = pd.to_numeric(df_row[cols_row[0]], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(df_row[cols_row[1]], errors="coerce").to_numpy(dtype=float)
        z = pd.to_numeric(df_row[cols_row[2]], errors="coerce").to_numpy(dtype=float) if projection == "3d" else None
        for label in uniq:
            mask = plot_label.to_numpy() == label
            _scatter(ax, x, y, z, mask, color=color_map[str(label)], point_size=float(args.point_size), alpha=float(args.alpha), projection=projection)
        ax.set_title(f"{row_title} | top actuation bit patterns")
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
        if projection == "3d":
            ax.set_zlabel("PC3")
        _apply_limits(ax, limits, projection)
        ax.grid(alpha=0.2)
    counts = [int((cats == label).sum()) for label in top_labels]
    top_colors = [color_map[str(label)] for label in top_labels]
    _draw_combo_grid(
        axg,
        top_labels=top_labels,
        counts=counts,
        colors=top_colors,
        combo_col=str(args.combo_col),
        actuators=actuators,
        metrics_lines=metrics_lines,
        metrics_split=str(args.metrics_split),
    )
    fig.suptitle(f"{args.title_prefix} | top actuation bit patterns")
    fig.tight_layout()
    fig.savefig(out_dir / "actuation_bits_triptych_with_grid.png", bbox_inches="tight")
    plt.close(fig)

    # Per-actuator triptychs.
    for actuator in actuators:
        state_col = f"{actuator}_state"
        if state_col not in emb_df.columns:
            continue
        ser = emb_df[state_col].astype("string").fillna("unknown").astype(str)
        order = [s for s in ("off", "transition", "on", "unknown") if s in set(ser.tolist())]
        if not order:
            continue
        fig = plt.figure(figsize=(12, 12), dpi=160)
        axes = [
            fig.add_subplot(3, 1, 1, projection=("3d" if projection == "3d" else None)),
            fig.add_subplot(3, 1, 2, projection=("3d" if projection == "3d" else None)),
            fig.add_subplot(3, 1, 3, projection=("3d" if projection == "3d" else None)),
        ]
        for (row_title, df_row, cols_row, _ax_dummy, limits), ax in zip(rows, axes):
            x = pd.to_numeric(df_row[cols_row[0]], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(df_row[cols_row[1]], errors="coerce").to_numpy(dtype=float)
            z = pd.to_numeric(df_row[cols_row[2]], errors="coerce").to_numpy(dtype=float) if projection == "3d" else None
            for state in order:
                mask = ser.to_numpy() == state
                _scatter(ax, x, y, z, mask, color=STATE_COLORS.get(state, "#444444"), point_size=float(args.point_size), alpha=float(args.alpha), projection=projection)
            ax.set_title(f"{row_title} | {actuator} state")
            ax.set_xlabel("PC1")
            ax.set_ylabel("PC2")
            if projection == "3d":
                ax.set_zlabel("PC3")
            _apply_limits(ax, limits, projection)
            ax.grid(alpha=0.2)
            handles = [Line2D([0], [0], marker="o", linestyle="", markersize=6, markerfacecolor=STATE_COLORS.get(s, "#444444"), markeredgewidth=0, label=str(s)) for s in order]
            ax.legend(handles=handles, loc="best", fontsize=8, framealpha=0.9)
        metrics_suffix = _metrics_suffix(metrics_lines, actuator)
        title = f"{args.title_prefix} | {actuator} state"
        if metrics_suffix:
            title = f"{title} | {metrics_suffix}"
        fig.suptitle(title)
        fig.tight_layout()
        fig.savefig(out_dir / f"{actuator}_triptych.png", bbox_inches="tight")
        plt.close(fig)

    print(f"[ok] wrote {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
