from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def plot_umap_2d_webgl(
    df: "pd.DataFrame",
    *,
    x_col: str = "umap1",
    y_col: str = "umap2",
    color_col: "Optional[str]" = None,
    max_points: int = 200_000,
    point_size: float = 3.0,
    title: "Optional[str]" = None,
) -> None:
    try:
        import plotly.graph_objects as go
        import plotly.colors as pc
    except Exception as e:
        raise SystemExit("Missing plotly. Install: pip install plotly") from e

    plot_df = df.copy()
    for c in (x_col, y_col):
        plot_df[c] = pd.to_numeric(plot_df.get(c), errors="coerce")

    plot_df = plot_df[np.isfinite(plot_df[x_col]) & np.isfinite(plot_df[y_col])].copy()
    if len(plot_df) == 0:
        print("[plot] no finite points to plot")
        return

    if len(plot_df) > max_points:
        plot_df = plot_df.sample(max_points, random_state=0)

    marker: dict = {"size": point_size}
    if color_col and (color_col in plot_df.columns):
        if pd.api.types.is_numeric_dtype(plot_df[color_col]):
            marker["color"] = pd.to_numeric(plot_df[color_col], errors="coerce").to_numpy(dtype="float64")
            marker["colorscale"] = "Viridis"
            marker["showscale"] = True
            marker["colorbar"] = {"title": color_col or ""}
        else:
            cats = plot_df[color_col].astype(str)
            palette = pc.qualitative.Plotly
            color_map = {c: palette[i % len(palette)] for i, c in enumerate(cats.unique())}
            marker["color"] = [color_map[c] for c in cats]

    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            x=plot_df[x_col],
            y=plot_df[y_col],
            mode="markers",
            marker=marker,
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        title=title or f"{x_col} vs {y_col}",
        xaxis_title=x_col,
        yaxis_title=y_col,
    )
    fig.show()
