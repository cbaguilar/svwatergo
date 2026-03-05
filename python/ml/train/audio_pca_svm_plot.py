from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

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
    for c in ("pca1", "pca2", "pca3", "y_true", "y_pred"):
        if c not in df.columns:
            raise ValueError(f"Projection file missing required column: {c}")

    df["y_true"] = pd.to_numeric(df["y_true"], errors="coerce").fillna(0).astype(int)
    df["y_pred"] = pd.to_numeric(df["y_pred"], errors="coerce").fillna(0).astype(int)
    df["is_error"] = df["y_true"] != df["y_pred"]
    accuracy = float((~df["is_error"]).mean()) if len(df) else 0.0
    uniq_classes = sorted(set(df["y_true"].unique().tolist()) | set(df["y_pred"].unique().tolist()))
    is_multiclass = len(uniq_classes) > 2

    if is_multiclass:
        if class_names and len(class_names) > max(uniq_classes):
            idx_to_name = {i: str(class_names[i]) for i in uniq_classes}
        else:
            idx_to_name = {i: f"class_{i}" for i in uniq_classes}
        df["true_label"] = df["y_true"].map(idx_to_name).fillna("unknown")
        df["pred_label"] = df["y_pred"].map(idx_to_name).fillna("unknown")
    else:
        df["true_label"] = np.where(df["y_true"] == 1, positive_name, negative_name)
        df["pred_label"] = np.where(df["y_pred"] == 1, positive_name, negative_name)

    plot_df = df if len(df) <= int(max_points) else df.sample(int(max_points), random_state=42)
    source_col = next((c for c in ("audio_source", "source_name", "source") if c in plot_df.columns), None)
    if source_col is not None:
        plot_df["source_label"] = plot_df[source_col].astype(str).fillna("unknown")

    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True)

    ax = axes[0, 0]
    labels_true = sorted(plot_df["true_label"].astype(str).unique().tolist())
    if is_multiclass:
        palette = plt.cm.tab10(np.linspace(0, 1, max(1, len(labels_true))))
        colors_true = {lab: palette[i] for i, lab in enumerate(labels_true)}
    else:
        colors_true = {negative_name: "#1f77b4", positive_name: "#d62728"}
        labels_true = [negative_name, positive_name]
    for label in labels_true:
        m = plot_df["true_label"] == label
        if m.any():
            ax.scatter(plot_df.loc[m, "pca1"], plot_df.loc[m, "pca2"], s=8, alpha=0.45, c=colors_true[label], label=label)
    ax.set_title("PC1 vs PC2 (True Label)")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    labels_pred = sorted(plot_df["pred_label"].astype(str).unique().tolist())
    if is_multiclass:
        palette2 = plt.cm.tab20(np.linspace(0, 1, max(1, len(labels_pred))))
        colors_pred = {lab: palette2[i] for i, lab in enumerate(labels_pred)}
    else:
        colors_pred = {negative_name: "#2ca02c", positive_name: "#ff7f0e"}
        labels_pred = [negative_name, positive_name]
    for label in labels_pred:
        m = plot_df["pred_label"] == label
        if m.any():
            ax.scatter(plot_df.loc[m, "pca1"], plot_df.loc[m, "pca2"], s=8, alpha=0.45, c=colors_pred[label], label=label)
    ax.set_title("PC1 vs PC2 (Predicted Label)")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    m_ok = ~plot_df["is_error"]
    m_err = plot_df["is_error"]
    ax.scatter(plot_df.loc[m_ok, "pca1"], plot_df.loc[m_ok, "pca3"], s=7, alpha=0.2, c="#7f7f7f", label="correct")
    if m_err.any():
        ax.scatter(plot_df.loc[m_err, "pca1"], plot_df.loc[m_err, "pca3"], s=14, alpha=0.85, c="#e41a1c", label="error")
    ax.set_title("PC1 vs PC3 (Errors Highlighted)")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC3")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)

    ax = axes[1, 1]
    if source_col is not None:
        labels_src = sorted(plot_df["source_label"].unique().tolist())
        palette_src = plt.cm.tab20(np.linspace(0, 1, max(1, len(labels_src))))
        colors_src = {lab: palette_src[i] for i, lab in enumerate(labels_src)}
        for label in labels_src:
            m = plot_df["source_label"] == label
            if m.any():
                ax.scatter(plot_df.loc[m, "pca1"], plot_df.loc[m, "pca2"], s=8, alpha=0.45, c=[colors_src[label]], label=label)
        ax.set_title("PC1 vs PC2 (Audio Source)")
        ax.legend(fontsize=8)
    elif is_multiclass:
        score_cols = sorted([c for c in plot_df.columns if c.startswith("score_class_")], key=lambda x: int(x.split("_")[-1]))
        if score_cols:
            conf = plot_df[score_cols].max(axis=1)
            sc = ax.scatter(
                plot_df["pca1"],
                plot_df["pca2"],
                c=conf,
                s=8,
                alpha=0.55,
                cmap="viridis",
                vmin=0,
                vmax=1,
            )
            cbar = fig.colorbar(sc, ax=ax)
            cbar.set_label(score_label or "max class probability")
            ax.set_title("PC1 vs PC2 (Prediction Confidence)")
        else:
            ax.scatter(plot_df["pca1"], plot_df["pca2"], s=8, alpha=0.4, c="#444")
            ax.set_title("PC1 vs PC2")
    elif "score_positive" in plot_df.columns:
        sc = ax.scatter(
            plot_df["pca1"],
            plot_df["pca2"],
            c=plot_df["score_positive"],
            s=8,
            alpha=0.55,
            cmap="viridis",
            vmin=0,
            vmax=1,
        )
        cbar = fig.colorbar(sc, ax=ax)
        cbar.set_label(score_label or f"score_positive (P[{positive_name}])")
        ax.set_title("PC1 vs PC2 (Model Score)")
    else:
        ax.scatter(plot_df["pca1"], plot_df["pca2"], s=8, alpha=0.4, c="#444")
        ax.set_title("PC1 vs PC2")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.grid(alpha=0.2)

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
        "task_mode": "multiclass" if is_multiclass else "binary",
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
    }
    out_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"plot_path": out_png, "meta_path": out_meta, "meta": meta}
