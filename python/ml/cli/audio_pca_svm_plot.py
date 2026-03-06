from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..train.audio_pca_svm_plot import render_audio_pca_svm_overview


def main() -> int:
    p = argparse.ArgumentParser(description="Render 4-panel PCA overview from audio PCA+SVM train projection parquet")
    p.add_argument("--projection", default=None, help="Path to train_projection.parquet")
    p.add_argument("--checkpoint-dir", default=None, help="Checkpoint dir containing train_projection.parquet")
    p.add_argument("--out-png", default=None, help="Output PNG path (default next to projection)")
    p.add_argument("--out-meta", default=None, help="Output metadata JSON path (default next to projection)")
    p.add_argument("--title", default="Audio PCA+SVM Training Projection")
    p.add_argument("--positive-name", default="on")
    p.add_argument("--negative-name", default="not_on")
    p.add_argument("--score-label", default=None)
    p.add_argument("--class-names", nargs="*", default=None, help="Optional explicit multiclass names by class index")
    p.add_argument("--max-points", type=int, default=12000)
    p.add_argument(
        "--pc-pairs",
        default="1:2",
        help="Comma-separated PCA pairs, e.g. '1:2,1:3,2:3'",
    )
    p.add_argument("--metrics-path", default=None, help="Optional metrics JSON (used for tuned thresholds/class names)")
    p.add_argument("--use-tuned-thresholds", default="no", choices=["yes", "no"], help="For tiny-cnn multilabel, recompute y_pred_* from score_* using tuned thresholds")
    args = p.parse_args()

    if bool(args.projection) == bool(args.checkpoint_dir):
        raise SystemExit("Provide exactly one of --projection or --checkpoint-dir")
    ckpt_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else None
    proj = Path(args.projection) if args.projection else ckpt_dir / "train_projection.parquet"

    class_names = args.class_names
    metrics_path = Path(args.metrics_path) if args.metrics_path else None
    if metrics_path is None and ckpt_dir is not None:
        # Prefer tiny-cnn metrics when present, fallback to pca+svm.
        tiny_metrics = ckpt_dir / "audio_tiny_cnn_metrics.json"
        svm_metrics = ckpt_dir / "audio_pca_svm_metrics.json"
        if tiny_metrics.exists():
            metrics_path = tiny_metrics
        elif svm_metrics.exists():
            metrics_path = svm_metrics
    metrics: dict = {}
    if metrics_path is not None and metrics_path.exists():
        if metrics_path.exists():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                maybe = ((metrics.get("y_meta") or {}).get("classes"))
                if isinstance(maybe, list) and maybe:
                    class_names = [str(x) for x in maybe]
            except Exception:
                pass

    tuned_thresholds_by_class = None
    if str(args.use_tuned_thresholds) == "yes":
        classes = ((metrics.get("y_meta") or {}).get("classes")) if isinstance(metrics, dict) else None
        th = metrics.get("inference_thresholds") if isinstance(metrics, dict) else None
        if isinstance(classes, list) and isinstance(th, list) and len(classes) == len(th) and len(classes) > 0:
            tuned_thresholds_by_class = {str(c): float(v) for c, v in zip(classes, th)}

    pc_pairs = []
    for tok in str(args.pc_pairs).split(","):
        s = tok.strip()
        if not s:
            continue
        if ":" not in s:
            raise SystemExit(f"Invalid --pc-pairs token {s!r}; expected 'A:B'")
        a, b = s.split(":", 1)
        try:
            ia = int(a.strip())
            ib = int(b.strip())
        except Exception as exc:
            raise SystemExit(f"Invalid --pc-pairs token {s!r}; expected integer indices") from exc
        if ia < 1 or ib < 1:
            raise SystemExit(f"Invalid --pc-pairs token {s!r}; PCA indices must be >= 1")
        pc_pairs.append((ia, ib))
    if not pc_pairs:
        pc_pairs = [(1, 2)]

    res = render_audio_pca_svm_overview(
        projection_path=proj,
        out_png=Path(args.out_png) if args.out_png else None,
        out_meta=Path(args.out_meta) if args.out_meta else None,
        title=str(args.title),
        positive_name=str(args.positive_name),
        negative_name=str(args.negative_name),
        score_label=str(args.score_label) if args.score_label else None,
        max_points=int(args.max_points),
        class_names=class_names,
        tuned_thresholds_by_class=tuned_thresholds_by_class,
        pc_pairs=pc_pairs,
    )
    print(f"Plot -> {res['plot_path']}")
    print(f"Meta -> {res['meta_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
