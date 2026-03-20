from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd


DEFAULT_LABEL_MAP = ",".join(
    [
        "bluerock=Site A",
        "pryorfarm=Site C",
        "santateresa=Site B",
        "all_sites=Pooled Train",
        "bluerock__rpi_audio=Site A RPi Audio",
        "bluerock__wyze_Bluerock_Cam_1=Site A Wyze Cam 1",
        "bluerock__wyze_Bluerock_Cam_2=Site A Wyze Cam 2",
        "bluerock__wyze_camera_5=Site A Wyze Cam 5",
        "pryorfarm__wyze_Pryor_Farms_1_inside_near_door=Site C Inside Near Door",
        "pryorfarm__wyze_Pryor_Farms_3_behind_ro=Site C Behind RO",
        "santateresa__wyze_Santa_Teresa_Cam_1=Site B Cam 1",
        "santateresa__wyze_Santa_Teresa_Outside=Site B Outside",
    ]
)

DEFAULT_METRICS = ",".join(
    [
        "mae_mean",
        "rmse_mean",
        "mse_mean",
        "r2_mean",
    ]
)


def _parse_label_map(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in str(text or "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _sanitize_label(text: str) -> str:
    s = str(text)
    replacements = [
        ("pryor_farms", "Site C"),
        ("pryorfarm", "Site C"),
        ("pryor farms", "Site C"),
        ("santa_teresa", "Site B"),
        ("santateresa", "Site B"),
        ("santa teresa", "Site B"),
        ("bluerock", "Site A"),
    ]
    lower = s.lower()
    for old, new in replacements:
        if old in lower:
            idx = lower.find(old)
            s = s[:idx] + new + s[idx + len(old) :]
            lower = s.lower()
    return s


def _apply_labels(df: pd.DataFrame, *, train_col: str, eval_col: str, label_map: Dict[str, str]) -> pd.DataFrame:
    out = df.copy()
    out[train_col] = out[train_col].astype(str).map(lambda x: _sanitize_label(label_map.get(x, x)))
    out[eval_col] = out[eval_col].astype(str).map(lambda x: _sanitize_label(label_map.get(x, x)))
    return out


def _ordered_domains(df: pd.DataFrame, *, train_col: str, eval_col: str) -> List[str]:
    raw = sorted(set(df[train_col].astype(str)).union(df[eval_col].astype(str)), key=lambda x: str(x).lower())
    if "Pooled Train" in raw:
        raw = [x for x in raw if x != "Pooled Train"] + ["Pooled Train"]
    return raw


def _pivot_metric(df: pd.DataFrame, *, train_col: str, eval_col: str, metric: str, order: Sequence[str]) -> pd.DataFrame:
    work = df.copy()
    work[metric] = pd.to_numeric(work[metric], errors="coerce")
    piv = work.pivot(index=train_col, columns=eval_col, values=metric)
    return piv.reindex(index=list(order), columns=list(order)).astype(float)


def _drop_all_na_axes(data: pd.DataFrame) -> pd.DataFrame:
    keep_rows = ~data.isna().all(axis=1)
    keep_cols = ~data.isna().all(axis=0)
    return data.loc[keep_rows, keep_cols]


def _metric_title(metric: str) -> str:
    title = str(metric)
    title = title.replace("macro_f1", "Macro F1")
    title = title.replace("exact_match", "Exact Match")
    title = title.replace("r2_mean", "Mean R2")
    title = title.replace("mae_mean", "Mean MAE")
    title = title.replace("rmse_mean", "Mean RMSE")
    title = title.replace("mse_mean", "Mean MSE")
    title = title.replace("r2__", "R2 ")
    title = title.replace("f1__", "F1 ")
    title = title.replace("__mean_tw", "")
    title = title.replace("_", " ")
    return title


def _metric_is_lower_better(metric: str) -> bool:
    m = str(metric).lower()
    return "mae" in m or "rmse" in m or "mse" in m or "loss" in m


def _latex_escape(text: object) -> str:
    s = str(text)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return s


def _format_value(metric: str, value: float, precision: int) -> str:
    m = str(metric).lower()
    if not np.isfinite(value):
        return "--"
    if "r2" in m or "f1" in m or "accuracy" in m or "precision" in m or "recall" in m:
        return f"{value:.{precision}f}"
    if abs(value) >= 1000:
        return f"{value:.1f}"
    return f"{value:.{precision}f}"


def _best_mask(table: pd.DataFrame, metric: str) -> pd.DataFrame:
    arr = table.to_numpy(dtype=float)
    mask = np.zeros_like(arr, dtype=bool)
    lower_better = _metric_is_lower_better(metric)
    for j in range(arr.shape[1]):
        col = arr[:, j]
        finite = np.isfinite(col)
        if not finite.any():
            continue
        target = np.nanmin(col) if lower_better else np.nanmax(col)
        mask[:, j] = finite & np.isclose(col, target, rtol=1e-9, atol=1e-12)
    return pd.DataFrame(mask, index=table.index, columns=table.columns)


def _table_label(prefix: str, metric: str) -> str:
    safe_metric = "".join(ch if ch.isalnum() else "_" for ch in str(metric)).strip("_")
    return f"{prefix}_{safe_metric}" if prefix else safe_metric


def _render_table(
    table: pd.DataFrame,
    *,
    metric: str,
    caption_prefix: str,
    label_prefix: str,
    precision: int,
    table_env: str,
    size_cmd: str,
) -> str:
    best = _best_mask(table, metric)
    cols = list(table.columns)
    lines: List[str] = []
    caption = _metric_title(metric) if not caption_prefix else f"{caption_prefix}: {_metric_title(metric)}"
    label = _table_label(label_prefix, metric)

    if table_env != "none":
        lines.append(f"\\begin{{{table_env}}}[htbp]")
        lines.append("\\centering")
    if size_cmd:
        lines.append(size_cmd)

    alignment = "l" + "r" * len(cols)
    lines.append(f"\\begin{{tabular}}{{{alignment}}}")
    lines.append("\\hline")
    lines.append(
        "Train $\\backslash$ Eval & "
        + " & ".join(_latex_escape(col) for col in cols)
        + r" \\"
    )
    lines.append("\\hline")
    for row_name in table.index:
        cells = [_latex_escape(row_name)]
        for col_name in cols:
            val = float(table.loc[row_name, col_name])
            text = _format_value(metric, val, precision)
            if np.isfinite(val) and bool(best.loc[row_name, col_name]):
                text = rf"\textbf{{{text}}}"
            cells.append(text)
        lines.append(" & ".join(cells) + r" \\")
    lines.append("\\hline")
    lines.append("\\end{tabular}")
    if table_env != "none":
        lines.append(rf"\caption{{{_latex_escape(caption)}}}")
        lines.append(rf"\label{{tab:{_latex_escape(label)}}}")
        lines.append(f"\\end{{{table_env}}}")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="Generate LaTeX domain-matrix tables from a summary CSV.")
    p.add_argument("--csv", required=True, help="Matrix summary CSV path")
    p.add_argument("--out-dir", required=True, help="Output directory for .tex files")
    p.add_argument("--metrics", default=DEFAULT_METRICS, help="Comma-separated metrics to render")
    p.add_argument("--train-col", default="train_domain")
    p.add_argument("--eval-col", default="eval_domain")
    p.add_argument("--label-map", default=DEFAULT_LABEL_MAP)
    p.add_argument("--caption-prefix", default="")
    p.add_argument("--label-prefix", default="domain_matrix")
    p.add_argument("--precision", type=int, default=3)
    p.add_argument("--table-env", default="table*", choices=["table", "table*", "none"])
    p.add_argument("--size-cmd", default="\\small")
    args = p.parse_args()

    csv_path = Path(args.csv)
    out_dir = Path(args.out_dir)
    metrics = [m.strip() for m in str(args.metrics).split(",") if m.strip()]
    label_map = _parse_label_map(args.label_map)

    df = pd.read_csv(csv_path)
    if "status" in df.columns:
        df = df[df["status"].fillna("ok").astype(str) == "ok"].copy()
    df = _apply_labels(df, train_col=str(args.train_col), eval_col=str(args.eval_col), label_map=label_map)
    order = _ordered_domains(df, train_col=str(args.train_col), eval_col=str(args.eval_col))

    out_dir.mkdir(parents=True, exist_ok=True)
    combined_parts: List[str] = []
    for metric in metrics:
        table = _drop_all_na_axes(
            _pivot_metric(
                df,
                train_col=str(args.train_col),
                eval_col=str(args.eval_col),
                metric=metric,
                order=order,
            )
        )
        rendered = _render_table(
            table,
            metric=metric,
            caption_prefix=str(args.caption_prefix).strip(),
            label_prefix=str(args.label_prefix).strip(),
            precision=int(args.precision),
            table_env=str(args.table_env),
            size_cmd=str(args.size_cmd).strip(),
        )
        metric_name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in metric)
        (out_dir / f"{metric_name}.tex").write_text(rendered, encoding="utf-8")
        combined_parts.append(rendered.rstrip())

    combined = "\n\n".join(combined_parts).rstrip() + "\n"
    (out_dir / "domain_matrix_tables.tex").write_text(combined, encoding="utf-8")
    print(f"[ok] wrote latex tables -> {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
