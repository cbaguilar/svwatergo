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
    args = p.parse_args()

    if bool(args.projection) == bool(args.checkpoint_dir):
        raise SystemExit("Provide exactly one of --projection or --checkpoint-dir")
    ckpt_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else None
    proj = Path(args.projection) if args.projection else ckpt_dir / "train_projection.parquet"

    class_names = args.class_names
    if not class_names and ckpt_dir is not None:
        metrics_path = ckpt_dir / "audio_pca_svm_metrics.json"
        if metrics_path.exists():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                maybe = ((metrics.get("y_meta") or {}).get("classes"))
                if isinstance(maybe, list) and maybe:
                    class_names = [str(x) for x in maybe]
            except Exception:
                pass

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
    )
    print(f"Plot -> {res['plot_path']}")
    print(f"Meta -> {res['meta_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
