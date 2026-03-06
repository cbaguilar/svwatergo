from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def render_audio_pca_svm_overview(
    *,
    projection_path: Path,
    out_png: Optional[Path] = None,
    out_meta: Optional[Path] = None,
    title: str = "Audio PCA+SVM Training Projection",
    positive_name: str = "on",
    negative_name: str = "not_on",
    score_label: Optional[str] = None,
    max_points: int = 12000,
    class_names: Optional[Sequence[str]] = None,
    tuned_thresholds_by_class: Optional[Dict[str, float]] = None,
    pc_pairs: Optional[Sequence[Tuple[int, int]]] = None,
) -> Dict[str, Any]:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    projection_path = Path(projection_path)
    if out_png is None:
        out_png = projection_path.with_name("pca_run_overview.png")
    if out_meta is None:
        out_meta = projection_path.with_name("pca_run_overview_metadata.json")

    df = pd.read_parquet(projection_path).copy()
    for c in ("y_true", "y_pred"):
        if c not in df.columns:
            raise ValueError(f"Projection file missing required column: {c}")
    if pc_pairs is None:
        pc_pairs = [(1, 2)]
    pairs = [(int(a), int(b)) for a, b in pc_pairs]
    for a, b in pairs:
        for c in (f"pca{a}", f"pca{b}"):
            if c not in df.columns:
                raise ValueError(f"Projection file missing required column for --pc-pairs: {c}")

    applied_thresholds: Dict[str, float] = {}
    if tuned_thresholds_by_class:
        for name, thr in tuned_thresholds_by_class.items():
            score_col = f"score_{name}"
            pred_col = f"y_pred_{name}"
            if score_col in df.columns:
                t = float(thr)
                df[pred_col] = (pd.to_numeric(df[score_col], errors="coerce").fillna(0.0) >= t).astype("int64")
                applied_thresholds[str(name)] = t
        if applied_thresholds:
            first = next(iter(applied_thresholds.keys()))
            true_base = f"y_true_{first}"
            pred_base = f"y_pred_{first}"
            if true_base in df.columns:
                df["y_true"] = pd.to_numeric(df[true_base], errors="coerce").fillna(0).astype(int)
            if pred_base in df.columns:
                df["y_pred"] = pd.to_numeric(df[pred_base], errors="coerce").fillna(0).astype(int)

    df["y_true"] = pd.to_numeric(df["y_true"], errors="coerce").fillna(0).astype(int)
    df["y_pred"] = pd.to_numeric(df["y_pred"], errors="coerce").fillna(0).astype(int)

    multilabel_true_cols = sorted([c for c in df.columns if c.startswith("y_true_")])
    multilabel_suffixes = [c[len("y_true_") :] for c in multilabel_true_cols if f"y_pred_{c[len('y_true_'):]}" in df.columns]
    is_multilabel = len(multilabel_suffixes) >= 2

    if is_multilabel:
        true_cols = [f"y_true_{s}" for s in multilabel_suffixes]
        pred_cols = [f"y_pred_{s}" for s in multilabel_suffixes]
        df["true_label"] = df[true_cols].astype(int).astype(str).agg("".join, axis=1)
        df["pred_label"] = df[pred_cols].astype(int).astype(str).agg("".join, axis=1)
        df["is_error"] = (df[true_cols].astype(int).to_numpy() != df[pred_cols].astype(int).to_numpy()).any(axis=1)
        score_cols_ml = [f"score_{s}" for s in multilabel_suffixes if f"score_{s}" in df.columns]
        if score_cols_ml:
            # Confidence that all bits are correct: high when scores are far from 0.5.
            df["pred_confidence"] = (
                np.abs(df[score_cols_ml].astype(float).to_numpy() - 0.5) * 2.0
            ).mean(axis=1)
        else:
            df["pred_confidence"] = np.nan
        task_mode = "multilabel"
    else:
        df["is_error"] = df["y_true"] != df["y_pred"]
        uniq_classes = sorted(set(df["y_true"].unique().tolist()) | set(df["y_pred"].unique().tolist()))
        is_multiclass = len(uniq_classes) > 2
        if is_multiclass:
            if class_names and len(class_names) > max(uniq_classes):
                idx_to_name = {i: str(class_names[i]) for i in uniq_classes}
            else:
                idx_to_name = {i: f"class_{i}" for i in uniq_classes}
            df["true_label"] = df["y_true"].map(idx_to_name).fillna("unknown")
            df["pred_label"] = df["y_pred"].map(idx_to_name).fillna("unknown")
            score_cols = sorted([c for c in df.columns if c.startswith("score_class_")], key=lambda x: int(x.split("_")[-1]))
            if score_cols:
                df["pred_confidence"] = df[score_cols].max(axis=1).astype(float)
            else:
                df["pred_confidence"] = np.nan
            task_mode = "multiclass"
        else:
            df["true_label"] = np.where(df["y_true"] == 1, positive_name, negative_name)
            df["pred_label"] = np.where(df["y_pred"] == 1, positive_name, negative_name)
            if "score_positive" in df.columns:
                df["pred_confidence"] = np.maximum(df["score_positive"].astype(float), 1.0 - df["score_positive"].astype(float))
            else:
                df["pred_confidence"] = np.nan
            task_mode = "binary"

    accuracy = float((~df["is_error"]).mean()) if len(df) else 0.0

    plot_df = df if len(df) <= int(max_points) else df.sample(int(max_points), random_state=42)
    source_col = next((c for c in ("audio_source", "source_name", "source") if c in plot_df.columns), None)
    if source_col is not None:
        plot_df["source_label"] = plot_df[source_col].astype(str).fillna("unknown")

    ncols = 5 if source_col is not None else 4
    nrows = int(len(pairs))
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 4.3 * nrows), constrained_layout=True)
    if nrows == 1:
        axes = np.asarray([axes], dtype=object)

    def _scatter_categorical(ax, col: str, panel_title: str, xcol: str, ycol: str, xname: str, yname: str) -> None:
        labels = sorted(plot_df[col].astype(str).unique().tolist())
        palette = plt.cm.tab20(np.linspace(0, 1, max(1, len(labels))))
        colors = {lab: palette[i] for i, lab in enumerate(labels)}
        for label in labels:
            m = plot_df[col] == label
            if m.any():
                ax.scatter(plot_df.loc[m, xcol], plot_df.loc[m, ycol], s=8, alpha=0.45, c=[colors[label]], label=label)
        ax.set_title(panel_title)
        ax.set_xlabel(xname)
        ax.set_ylabel(yname)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)

    conf_finite = np.isfinite(plot_df["pred_confidence"].to_numpy(dtype=float)).any()
    sc = None
    for row_i, (pcx, pcy) in enumerate(pairs):
        xcol = f"pca{pcx}"
        ycol = f"pca{pcy}"
        xname = f"PC{pcx}"
        yname = f"PC{pcy}"

        _scatter_categorical(
            axes[row_i, 0],
            "true_label",
            f"{xname} vs {yname} (True Label)",
            xcol,
            ycol,
            xname,
            yname,
        )
        _scatter_categorical(
            axes[row_i, 1],
            "pred_label",
            f"{xname} vs {yname} (Predicted Label)",
            xcol,
            ycol,
            xname,
            yname,
        )

        ax = axes[row_i, 2]
        if conf_finite:
            sc = ax.scatter(
                plot_df[xcol],
                plot_df[ycol],
                c=plot_df["pred_confidence"],
                s=8,
                alpha=0.55,
                cmap="viridis",
                vmin=0,
                vmax=1,
            )
            ax.set_title(f"{xname} vs {yname} (Confidence)")
        else:
            ax.scatter(plot_df[xcol], plot_df[ycol], s=8, alpha=0.35, c="#444")
            ax.set_title(f"{xname} vs {yname} (Confidence N/A)")
        ax.set_xlabel(xname)
        ax.set_ylabel(yname)
        ax.grid(alpha=0.2)

        ax = axes[row_i, 3]
        m_ok = ~plot_df["is_error"]
        m_err = plot_df["is_error"]
        ax.scatter(plot_df.loc[m_ok, xcol], plot_df.loc[m_ok, ycol], s=7, alpha=0.2, c="#7f7f7f", label="correct")
        if m_err.any():
            ax.scatter(plot_df.loc[m_err, xcol], plot_df.loc[m_err, ycol], s=14, alpha=0.85, c="#e41a1c", label="error")
        ax.set_title(f"{xname} vs {yname} (Errors Highlighted)")
        ax.set_xlabel(xname)
        ax.set_ylabel(yname)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)

        if source_col is not None:
            _scatter_categorical(
                axes[row_i, 4],
                "source_label",
                f"{xname} vs {yname} (Audio Source)",
                xcol,
                ycol,
                xname,
                yname,
            )

    if sc is not None:
        cbar = fig.colorbar(sc, ax=axes[:, 2].ravel().tolist() if nrows > 1 else axes[0, 2])
        cbar.set_label(score_label or "prediction confidence")

    fig.suptitle(title, fontsize=14)
    fig.text(
        0.99,
        0.985,
        f"Accuracy: {accuracy*100:.2f}%  (errors={int(df['is_error'].sum())}/{int(len(df))})",
        ha="right",
        va="top",
        fontsize=10,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160)
    plt.close(fig)

    meta = {
        "projection_path": str(projection_path),
        "plot_path": str(out_png),
        "rows_total": int(len(df)),
        "rows_plotted": int(len(plot_df)),
        "task_mode": str(task_mode),
        "class_names": list(class_names) if class_names is not None else None,
        "positive_name": str(positive_name),
        "negative_name": str(negative_name),
        "true_counts": {str(k): int(v) for k, v in df["true_label"].value_counts().to_dict().items()},
        "pred_counts": {str(k): int(v) for k, v in df["pred_label"].value_counts().to_dict().items()},
        "n_errors": int(df["is_error"].sum()),
        "error_rate": float(df["is_error"].mean()),
        "accuracy": accuracy,
        "split_counts": {str(k): int(v) for k, v in df["split"].astype(str).value_counts().to_dict().items()}
        if "split" in df.columns
        else {},
        "source_column": str(source_col) if source_col is not None else None,
        "source_counts": {str(k): int(v) for k, v in df[source_col].astype(str).value_counts().to_dict().items()}
        if source_col is not None
        else {},
        "applied_tuned_thresholds": applied_thresholds,
        "pc_pairs": [[int(a), int(b)] for a, b in pairs],
    }
    out_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"plot_path": out_png, "meta_path": out_meta, "meta": meta}
