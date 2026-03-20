from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _finite(v: Any) -> bool:
    try:
        x = float(v)
    except Exception:
        return False
    return math.isfinite(x)


def _series(hist: Sequence[Dict[str, Any]], key: str) -> List[float]:
    return [float(row[key]) if _finite(row.get(key)) else float("nan") for row in hist]


def _resolve_metrics_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_file():
        return path
    candidates = [
        path / "audio_pretrained_embedding_multitask_metrics.json",
        path / "audio_tiny_cnn_metrics.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(f"Could not find supported metrics JSON under: {path}")


def _best_finite(
    epochs: Sequence[int],
    values: Sequence[float],
    *,
    lower_is_better: bool,
) -> Tuple[Optional[int], Optional[float]]:
    finite = [(int(epoch), float(value)) for epoch, value in zip(epochs, values) if math.isfinite(value)]
    if not finite:
        return None, None
    key_fn = (lambda item: item[1]) if lower_is_better else (lambda item: -item[1])
    best_epoch, best_value = sorted(finite, key=key_fn)[0]
    return best_epoch, best_value


def _infer_task(metrics: Dict[str, Any]) -> str:
    task = str(metrics.get("task") or "")
    if not task:
        task = str(metrics.get("task_mode") or "")
    return task


def _metric_label(task: str) -> str:
    if task == "multiregression":
        return "mae"
    if task == "multiclass":
        return "acc"
    if task == "multilabel":
        return "exact_match"
    return "metric"


def _label_from_path(metrics_path: Path) -> str:
    name = metrics_path.parent.name or metrics_path.stem
    return name.replace("_", " ")


def main() -> int:
    p = argparse.ArgumentParser(description="Compare multiple training runs with stacked epoch curves")
    p.add_argument(
        "--run",
        action="append",
        required=True,
        help="Metrics JSON path or checkpoint dir. Pass once per run.",
    )
    p.add_argument(
        "--label",
        action="append",
        default=[],
        help="Optional label for each run, in the same order as --run.",
    )
    p.add_argument("--out-png", required=True, help="Output PNG path")
    p.add_argument("--out-meta", default=None, help="Output summary JSON path")
    p.add_argument("--title", default="Aux Sweep Comparison")
    args = p.parse_args()

    if args.label and len(args.label) != len(args.run):
        raise SystemExit("If provided, --label must be passed exactly once per --run")

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    runs: List[Dict[str, Any]] = []
    for idx, run_arg in enumerate(args.run):
        metrics_path = _resolve_metrics_path(run_arg)
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        hist: List[Dict[str, Any]] = list(metrics.get("epoch_history") or [])
        if not hist:
            raise SystemExit(f"No epoch_history found in: {metrics_path}")
        task = _infer_task(metrics)
        metric_label = _metric_label(task)
        metric_lower_is_better = task == "multiregression"
        epochs = [int(row.get("epoch", i + 1)) for i, row in enumerate(hist)]
        val_metric = _series(hist, "val_metric")
        test_metric = _series(hist, "test_metric")
        val_macro_f1 = _series(hist, "val_macro_f1")
        test_macro_f1 = _series(hist, "test_macro_f1")
        loss = _series(hist, "loss")
        best_val_epoch, best_val_metric = _best_finite(epochs, val_metric, lower_is_better=metric_lower_is_better)
        runs.append(
            {
                "label": args.label[idx] if idx < len(args.label) else _label_from_path(metrics_path),
                "metrics_path": str(metrics_path),
                "task": task,
                "metric_label": metric_label,
                "metric_lower_is_better": metric_lower_is_better,
                "epochs": epochs,
                "loss": loss,
                "val_metric": val_metric,
                "test_metric": test_metric,
                "val_macro_f1": val_macro_f1,
                "test_macro_f1": test_macro_f1,
                "best_val_epoch": best_val_epoch,
                "best_val_metric": best_val_metric,
            }
        )

    max_epochs = max(len(run["epochs"]) for run in runs)
    fig, axes = plt.subplots(len(runs), 2, figsize=(13.5, max(3.2 * len(runs), 4.8)), sharex=True, constrained_layout=True)
    if len(runs) == 1:
        axes = [axes]

    for row_idx, run in enumerate(runs):
        ax_left = axes[row_idx][0]
        ax_right = axes[row_idx][1]

        epochs = run["epochs"]
        label = run["label"]
        metric_label = run["metric_label"]
        val_metric = run["val_metric"]
        test_metric = run["test_metric"]
        val_macro_f1 = run["val_macro_f1"]
        test_macro_f1 = run["test_macro_f1"]
        loss = run["loss"]

        ax_left.plot(epochs, val_metric, color="#1f77b4", linewidth=1.8, label=f"val_{metric_label}")
        ax_left.plot(epochs, test_metric, color="#d62728", linewidth=1.4, alpha=0.85, label=f"test_{metric_label}")
        if any(math.isfinite(x) for x in val_macro_f1):
            ax_left.plot(epochs, val_macro_f1, color="#2ca02c", linewidth=1.4, alpha=0.9, label="val_macro_f1")
        if any(math.isfinite(x) for x in test_macro_f1):
            ax_left.plot(epochs, test_macro_f1, color="#9467bd", linewidth=1.2, alpha=0.85, label="test_macro_f1")
        if run["best_val_epoch"] is not None and run["best_val_metric"] is not None:
            ax_left.axvline(int(run["best_val_epoch"]), color="#7f7f7f", linestyle="--", linewidth=1.0, alpha=0.6)
            best_txt = f"best val {metric_label}={float(run['best_val_metric']):.4f} @ ep {int(run['best_val_epoch'])}"
        else:
            best_txt = "best val n/a"
        ax_left.set_title(f"{label} | {best_txt}", fontsize=10)
        ax_left.set_ylabel("metric")
        ax_left.grid(alpha=0.25)
        ax_left.legend(loc="best", fontsize=8)

        ax_right.plot(epochs, loss, color="#ff7f0e", linewidth=1.8, label="loss")
        ax_right.set_title(f"{label} | loss", fontsize=10)
        ax_right.set_ylabel("loss")
        ax_right.grid(alpha=0.25)
        ax_right.legend(loc="best", fontsize=8)

    axes[-1][0].set_xlabel("epoch")
    axes[-1][1].set_xlabel("epoch")
    fig.suptitle(args.title, fontsize=14)

    out_png = Path(args.out_png)
    out_meta = Path(args.out_meta) if args.out_meta else out_png.with_suffix(".json")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=170)
    plt.close(fig)

    summary = {
        "title": args.title,
        "plot_path": str(out_png),
        "runs": [
            {
                "label": run["label"],
                "metrics_path": run["metrics_path"],
                "task": run["task"],
                "metric_name": run["metric_label"],
                "best_val_epoch": run["best_val_epoch"],
                "best_val_metric": run["best_val_metric"],
                "last_val_metric": next((float(v) for v in reversed(run["val_metric"]) if math.isfinite(v)), None),
                "last_test_metric": next((float(v) for v in reversed(run["test_metric"]) if math.isfinite(v)), None),
            }
            for run in runs
        ],
    }
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Comparison plot -> {out_png}")
    print(f"Summary         -> {out_meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
