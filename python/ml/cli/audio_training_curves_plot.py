from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List


def _finite(v: Any) -> bool:
    try:
        x = float(v)
    except Exception:
        return False
    return math.isfinite(x)


def main() -> int:
    p = argparse.ArgumentParser(description="Render training loss/metric curves from audio_tiny_cnn_metrics.json")
    p.add_argument("--metrics-path", default=None, help="Path to audio_tiny_cnn_metrics.json")
    p.add_argument("--checkpoint-dir", default=None, help="Checkpoint dir containing audio_tiny_cnn_metrics.json")
    p.add_argument("--out-png", default=None, help="Output PNG path (default next to metrics)")
    p.add_argument("--out-meta", default=None, help="Output metadata JSON path (default next to metrics)")
    p.add_argument("--title", default="Audio Training Curves")
    args = p.parse_args()

    if bool(args.metrics_path) == bool(args.checkpoint_dir):
        raise SystemExit("Provide exactly one of --metrics-path or --checkpoint-dir")

    metrics_path = (
        Path(args.metrics_path)
        if args.metrics_path
        else (Path(args.checkpoint_dir) / "audio_tiny_cnn_metrics.json")
    )
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
    losses = [float(r.get("loss", float("nan"))) for r in hist]
    aux_losses = [float(r.get("aux_loss", float("nan"))) for r in hist]
    train_metric = [float(r["train_metric"]) if _finite(r.get("train_metric")) else float("nan") for r in hist]
    test_metric = [float(r["test_metric"]) if _finite(r.get("test_metric")) else float("nan") for r in hist]
    lrs = [float(r.get("lr", float("nan"))) for r in hist]

    metric_name = str(metrics.get("epoch_history_metric_name") or "acc")
    task = str(metrics.get("task") or "")
    metric_is_lower_better = (metric_name == "mae") or (task == "multiregression")

    fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.4), constrained_layout=True)

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
    has_test = any(math.isfinite(x) for x in test_metric)
    if has_train:
        ax.plot(epochs, train_metric, label=f"train_{metric_name}", color="#9467bd", linewidth=1.6)
    if has_test:
        ax.plot(epochs, test_metric, label=f"test_{metric_name}", color="#d62728", linewidth=1.8)
    ax.set_title(f"Metric ({metric_name})")
    ax.set_xlabel("epoch")
    ax.set_ylabel(metric_name)
    ax.grid(alpha=0.25)
    if has_train or has_test:
        ax.legend(loc="best")

    best_epoch = None
    best_test_metric = None
    finite_test = [(int(e), float(v)) for e, v in zip(epochs, test_metric) if math.isfinite(v)]
    if finite_test:
        key_fn = (lambda t: t[1]) if metric_is_lower_better else (lambda t: -t[1])
        best_epoch, best_test_metric = sorted(finite_test, key=key_fn)[0]

    fig.suptitle(str(args.title), fontsize=13)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160)
    plt.close(fig)

    out = {
        "metrics_path": str(metrics_path),
        "plot_path": str(out_png),
        "n_epochs": int(len(hist)),
        "metric_name": metric_name,
        "metric_higher_is_better": bool(not metric_is_lower_better),
        "best_epoch_by_test_metric": best_epoch,
        "best_test_metric": best_test_metric,
        "last_epoch": int(epochs[-1]) if epochs else None,
        "last_loss": float(losses[-1]) if losses else None,
        "last_aux_loss": float(aux_losses[-1]) if aux_losses else None,
        "last_test_metric": (float(test_metric[-1]) if test_metric and math.isfinite(test_metric[-1]) else None),
    }
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Curves -> {out_png}")
    print(f"Meta   -> {out_meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
