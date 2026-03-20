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


def _choose_metrics_path(args: argparse.Namespace) -> Path:
    if args.metrics_path:
        return Path(args.metrics_path)
    checkpoint_dir = Path(args.checkpoint_dir)
    candidates = [
        checkpoint_dir / "audio_tiny_cnn_metrics.json",
        checkpoint_dir / "audio_pretrained_embedding_multitask_metrics.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise SystemExit(
        "Missing metrics JSON in checkpoint dir. Expected one of: "
        "audio_tiny_cnn_metrics.json, audio_pretrained_embedding_multitask_metrics.json"
    )


def _series(hist: Sequence[Dict[str, Any]], key: str) -> List[float]:
    return [float(row[key]) if _finite(row.get(key)) else float("nan") for row in hist]


def _first_present(metrics: Dict[str, Any], keys: Sequence[str], default: str) -> str:
    for key in keys:
        val = metrics.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return default


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


def main() -> int:
    p = argparse.ArgumentParser(
        description="Render training curves from audio_tiny_cnn_metrics.json or audio_pretrained_embedding_multitask_metrics.json"
    )
    p.add_argument("--metrics-path", default=None, help="Path to a metrics JSON file")
    p.add_argument("--checkpoint-dir", default=None, help="Checkpoint dir containing a supported metrics JSON")
    p.add_argument("--out-png", default=None, help="Output PNG path (default next to metrics)")
    p.add_argument("--out-meta", default=None, help="Output metadata JSON path (default next to metrics)")
    p.add_argument("--title", default="Audio Training Curves")
    args = p.parse_args()

    if bool(args.metrics_path) == bool(args.checkpoint_dir):
        raise SystemExit("Provide exactly one of --metrics-path or --checkpoint-dir")

    metrics_path = _choose_metrics_path(args)
    if not metrics_path.exists():
        raise SystemExit(f"Missing metrics JSON: {metrics_path}")

    out_png = Path(args.out_png) if args.out_png else metrics_path.with_name("training_curves.png")
    out_meta = Path(args.out_meta) if args.out_meta else metrics_path.with_name("training_curves_metadata.json")

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    hist: List[Dict[str, Any]] = list(metrics.get("epoch_history") or [])
    if not hist:
        raise SystemExit("No epoch_history found in metrics JSON. Re-run training with updated trainer.")

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    epochs = [int(r.get("epoch", i + 1)) for i, r in enumerate(hist)]
    losses = _series(hist, "loss")
    aux_losses = _series(hist, "aux_loss")
    lrs = _series(hist, "lr")

    task = str(metrics.get("task") or "")
    if not task:
        task = str(metrics.get("task_mode") or "")
    best_model = metrics.get("best_model") if isinstance(metrics.get("best_model"), dict) else {}
    metric_mode = _first_present(metrics, ["epoch_history_metric_name"], "")
    if not metric_mode:
        metric_mode = _first_present(best_model, ["metric"], "")
    if not metric_mode:
        metric_mode = "mae" if task == "multiregression" else "metric"
    metric_label = "mae" if task == "multiregression" else metric_mode
    metric_is_lower_better = (metric_mode == "mae") or (task == "multiregression")

    train_metric = _series(hist, "train_metric")
    val_metric = _series(hist, "val_metric")
    test_metric = _series(hist, "test_metric")
    train_macro_f1 = _series(hist, "train_macro_f1")
    val_macro_f1 = _series(hist, "val_macro_f1")
    test_macro_f1 = _series(hist, "test_macro_f1")
    train_plc_r2 = _series(hist, "train_plc_r2")
    val_plc_r2 = _series(hist, "val_plc_r2")
    test_plc_r2 = _series(hist, "test_plc_r2")

    panel_count = 2
    if any(math.isfinite(x) for x in train_macro_f1 + val_macro_f1 + test_macro_f1):
        panel_count += 1
    if any(math.isfinite(x) for x in train_plc_r2 + val_plc_r2 + test_plc_r2):
        panel_count += 1

    fig, axes = plt.subplots(1, panel_count, figsize=(6.2 * panel_count, 4.4), constrained_layout=True)
    if not isinstance(axes, (list, tuple)):
        try:
            axes = list(axes)
        except TypeError:
            axes = [axes]

    ax = axes[0]
    ax.plot(epochs, losses, label="loss", color="#1f77b4", linewidth=1.8)
    if any(math.isfinite(x) and x > 0.0 for x in aux_losses):
        ax.plot(epochs, aux_losses, label="aux_loss", color="#ff7f0e", linewidth=1.4, alpha=0.9)
    ax.set_title("Loss")
    ax.set_xlabel("epoch")
    ax.set_ylabel("value")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")

    ax2 = ax.twinx()
    ax2.plot(epochs, lrs, label="lr", color="#2ca02c", linestyle="--", linewidth=1.2, alpha=0.8)
    ax2.set_ylabel("lr")

    ax = axes[1]
    has_train = any(math.isfinite(x) for x in train_metric)
    has_val = any(math.isfinite(x) for x in val_metric)
    has_test = any(math.isfinite(x) for x in test_metric)
    if has_train:
        ax.plot(epochs, train_metric, label=f"train_{metric_label}", color="#9467bd", linewidth=1.6)
    if has_val:
        ax.plot(epochs, val_metric, label=f"val_{metric_label}", color="#ff7f0e", linewidth=1.6)
    if has_test:
        ax.plot(epochs, test_metric, label=f"test_{metric_label}", color="#d62728", linewidth=1.8)
    ax.set_title(f"Main Metric ({metric_label})")
    ax.set_xlabel("epoch")
    ax.set_ylabel(metric_label)
    ax.grid(alpha=0.25)
    if has_train or has_val or has_test:
        ax.legend(loc="best")

    axis_idx = 2
    has_macro_panel = any(math.isfinite(x) for x in train_macro_f1 + val_macro_f1 + test_macro_f1)
    if has_macro_panel:
        ax = axes[axis_idx]
        axis_idx += 1
        if any(math.isfinite(x) for x in train_macro_f1):
            ax.plot(epochs, train_macro_f1, label="train_macro_f1", color="#9467bd", linewidth=1.6)
        if any(math.isfinite(x) for x in val_macro_f1):
            ax.plot(epochs, val_macro_f1, label="val_macro_f1", color="#ff7f0e", linewidth=1.6)
        if any(math.isfinite(x) for x in test_macro_f1):
            ax.plot(epochs, test_macro_f1, label="test_macro_f1", color="#d62728", linewidth=1.8)
        ax.set_title("Macro F1")
        ax.set_xlabel("epoch")
        ax.set_ylabel("macro_f1")
        ax.grid(alpha=0.25)
        ax.legend(loc="best")

    has_plc_panel = any(math.isfinite(x) for x in train_plc_r2 + val_plc_r2 + test_plc_r2)
    if has_plc_panel:
        ax = axes[axis_idx]
        if any(math.isfinite(x) for x in train_plc_r2):
            ax.plot(epochs, train_plc_r2, label="train_plc_r2", color="#9467bd", linewidth=1.6)
        if any(math.isfinite(x) for x in val_plc_r2):
            ax.plot(epochs, val_plc_r2, label="val_plc_r2", color="#ff7f0e", linewidth=1.6)
        if any(math.isfinite(x) for x in test_plc_r2):
            ax.plot(epochs, test_plc_r2, label="test_plc_r2", color="#d62728", linewidth=1.8)
        ax.set_title("PLC R2")
        ax.set_xlabel("epoch")
        ax.set_ylabel("r2")
        ax.grid(alpha=0.25)
        ax.legend(loc="best")

    best_test_epoch, best_test_value = _best_finite(epochs, test_metric, lower_is_better=metric_is_lower_better)
    best_val_epoch, best_val_value = _best_finite(epochs, val_metric, lower_is_better=metric_is_lower_better)

    fig.suptitle(str(args.title), fontsize=13)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160)
    plt.close(fig)

    out = {
        "metrics_path": str(metrics_path),
        "plot_path": str(out_png),
        "n_epochs": int(len(hist)),
        "metric_name": metric_label,
        "metric_higher_is_better": bool(not metric_is_lower_better),
        "best_epoch_by_test_metric": best_test_epoch,
        "best_test_metric": best_test_value,
        "best_epoch_by_val_metric": best_val_epoch,
        "best_val_metric": best_val_value,
        "last_epoch": int(epochs[-1]) if epochs else None,
        "last_loss": float(losses[-1]) if losses else None,
        "last_aux_loss": float(aux_losses[-1]) if aux_losses else None,
        "last_val_metric": (float(val_metric[-1]) if val_metric and math.isfinite(val_metric[-1]) else None),
        "last_test_metric": (float(test_metric[-1]) if test_metric and math.isfinite(test_metric[-1]) else None),
    }
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Curves -> {out_png}")
    print(f"Meta   -> {out_meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
