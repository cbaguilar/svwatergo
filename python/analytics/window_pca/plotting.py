from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from python.analytics.site_alias import alias_site_names
from python.units import label_with_unit
from .model import decode_alarmword_bits, parse_int_maybe


def plot_pca_3d(
    df: "pd.DataFrame",
    *,
    x_col: str = "pca1",
    y_col: str = "pca2",
    z_col: str = "pca3",
    color_col: "Optional[str]" = None,
    max_points: int = 200_000,
    point_size: float = 3.0,
    title: "Optional[str]" = None,
    hover_col: "Optional[str]" = "window_start_ts",
    color_discrete: bool = False,
    path: bool = False,
    path_time_col: "Optional[str]" = "window_start_ts",
    path_opacity: float = 0.25,
    path_width: float = 2.0,
) -> None:
    try:
        import plotly.express as px
    except Exception as e:
        raise SystemExit("Missing plotly. Install: pip install plotly") from e

    plot_df = df.copy()
    for c in (x_col, y_col, z_col):
        plot_df[c] = pd.to_numeric(plot_df.get(c), errors="coerce")

    plot_df = plot_df[np.isfinite(plot_df[x_col]) & np.isfinite(plot_df[y_col]) & np.isfinite(plot_df[z_col])].copy()
    if len(plot_df) == 0:
        print("[plot] no finite points to plot")
        return

    if path and path_time_col and (path_time_col in plot_df.columns):
        plot_df = plot_df.sort_values(path_time_col, kind="mergesort")

    if len(plot_df) > max_points:
        plot_df = plot_df.sample(max_points, random_state=0)

    hover_data = None
    if hover_col and (hover_col in plot_df.columns):
        hover_data = [hover_col]

    plot_color = None
    color_map = None
    if color_col and (color_col in plot_df.columns):
        plot_color = color_col
        if color_discrete:
            plot_df[color_col] = plot_df[color_col].astype(str)
            try:
                import plotly.express as px  # type: ignore
            except Exception:
                px = None
            if px is not None:
                palette = px.colors.qualitative.Plotly
                cats = list(plot_df[color_col].unique())
                color_map = {c: palette[i % len(palette)] for i, c in enumerate(cats)}

    fig = px.scatter_3d(
        plot_df,
        x=x_col,
        y=y_col,
        z=z_col,
        color=plot_color,
        color_discrete_map=color_map,
        opacity=0.7,
        title=title or f"{x_col} vs {y_col} vs {z_col}",
        hover_data=hover_data,
    )
    fig.update_traces(marker=dict(size=point_size))

    if path:
        if color_discrete and plot_color:
            for key, sub in plot_df.groupby(plot_color, sort=False):
                line_color = None
                if color_map and key in color_map:
                    line_color = color_map[key]
                fig.add_scatter3d(
                    x=sub[x_col],
                    y=sub[y_col],
                    z=sub[z_col],
                    mode="lines",
                    line=dict(width=path_width, color=line_color) if line_color else dict(width=path_width),
                    opacity=path_opacity,
                    name=f"path:{key}",
                    showlegend=False,
                )
        else:
            fig.add_scatter3d(
                x=plot_df[x_col],
                y=plot_df[y_col],
                z=plot_df[z_col],
                mode="lines",
                line=dict(width=path_width, color="rgba(0,0,0,0.25)"),
                opacity=path_opacity,
                name="path",
                showlegend=False,
            )

    fig.show()


def plot_pca_2d_live(
    df: "pd.DataFrame",
    *,
    x_col: str = "pca1",
    y_col: str = "pca2",
    color_col: "Optional[str]" = None,
    max_points: int = 200_000,
    alpha: float = 0.25,
    point_size: float = 4.0,
    title: "Optional[str]" = None,
    animate: bool = False,
    time_col: "Optional[str]" = None,
    trail_len: int = 60,
    interval_ms: int = 60,
    sample_every: int = 1,
    show_background: bool = True,
    path: bool = False,
    path_alpha: float = 0.12,
    path_width: float = 1.0,
    symlog_y: bool = True,
    symlog_linthresh: float = 1.0,
) -> None:
    from typing import Dict, List
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    plot_df = df.copy()

    x_all = pd.to_numeric(plot_df.get(x_col), errors="coerce").to_numpy(dtype="float64")
    y_all = pd.to_numeric(plot_df.get(y_col), errors="coerce").to_numpy(dtype="float64")
    good = np.isfinite(x_all) & np.isfinite(y_all)
    plot_df = plot_df.loc[good].copy()
    x_all = x_all[good]
    y_all = y_all[good]

    if len(plot_df) == 0:
        print("[plot] no finite points to plot")
        return

    if len(plot_df) > max_points:
        bg_df = plot_df.sample(max_points, random_state=0)
    else:
        bg_df = plot_df

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.set_title(alias_site_names(title or f"{label_with_unit(x_col)} vs {label_with_unit(y_col)}"))
    ax.set_xlabel(label_with_unit(x_col))
    ax.set_ylabel(label_with_unit(y_col))
    if symlog_y:
        # PCA scores can be negative, so use symmetric log scale for visibility.
        ax.set_yscale("symlog", linthresh=float(symlog_linthresh))

    x_min, x_max = float(np.nanmin(x_all)), float(np.nanmax(x_all))
    y_min, y_max = float(np.nanmin(y_all)), float(np.nanmax(y_all))
    pad_x = 0.03 * (x_max - x_min) if x_max > x_min else 1.0
    pad_y = 0.03 * (y_max - y_min) if y_max > y_min else 1.0

    ax.set_xlim(x_min - pad_x, x_max + pad_x)
    ax.set_ylim(y_min - pad_y, y_max + pad_y)

    if show_background:
        bx = pd.to_numeric(bg_df.get(x_col), errors="coerce").to_numpy(dtype="float64")
        by = pd.to_numeric(bg_df.get(y_col), errors="coerce").to_numpy(dtype="float64")

        if color_col and (color_col in bg_df.columns):
            c = bg_df[color_col]
            if pd.api.types.is_numeric_dtype(c):
                bc = pd.to_numeric(c, errors="coerce").to_numpy(dtype="float64")
                sc = ax.scatter(bx, by, c=bc, s=point_size, alpha=alpha, linewidths=0)
                fig.colorbar(sc, ax=ax, label=label_with_unit(color_col))
            else:
                codes, _uniques = pd.factorize(c.astype(str), sort=True)
                ax.scatter(bx, by, c=codes, s=point_size, alpha=alpha, linewidths=0)
        else:
            ax.scatter(bx, by, s=point_size, alpha=alpha, linewidths=0)

    if path:
        path_df = plot_df
        if time_col and time_col in path_df.columns:
            path_df = path_df.sort_values(time_col, kind="mergesort")
        px = pd.to_numeric(path_df.get(x_col), errors="coerce").to_numpy(dtype="float64")
        py = pd.to_numeric(path_df.get(y_col), errors="coerce").to_numpy(dtype="float64")
        good_path = np.isfinite(px) & np.isfinite(py)
        if np.any(good_path):
            px = px[good_path]
            py = py[good_path]
            if color_col and (color_col in path_df.columns):
                from matplotlib.collections import LineCollection

                cvals = path_df.loc[good_path, color_col]
                segments = np.stack(
                    [np.column_stack([px[:-1], py[:-1]]), np.column_stack([px[1:], py[1:]])],
                    axis=1,
                )
                if pd.api.types.is_numeric_dtype(cvals):
                    cnum = pd.to_numeric(cvals, errors="coerce").to_numpy(dtype="float64")
                    lc = LineCollection(
                        segments,
                        cmap="viridis",
                        linewidths=float(path_width),
                        alpha=float(path_alpha),
                    )
                    lc.set_array(cnum[:-1])
                    ax.add_collection(lc)
                else:
                    cats, _ = pd.factorize(cvals.astype(str), sort=True)
                    lc = LineCollection(
                        segments,
                        cmap="tab20",
                        linewidths=float(path_width),
                        alpha=float(path_alpha),
                    )
                    lc.set_array(cats[:-1].astype("float64"))
                    ax.add_collection(lc)
            else:
                ax.plot(
                    px,
                    py,
                    "-",
                    color="black",
                    alpha=float(path_alpha),
                    linewidth=float(path_width),
                )

    if not animate:
        plt.tight_layout()
        plt.show()
        return

    if time_col and time_col in plot_df.columns:
        plot_df = plot_df.sort_values(time_col, kind="mergesort")
    else:
        time_col = None

    alarm = None
    if "alarm__last" in plot_df.columns:
        alarm = pd.to_numeric(plot_df["alarm__last"], errors="coerce").fillna(0).to_numpy(dtype=np.int8)

    has_alarm = (alarm is not None) and bool(alarm.any())

    alarmword_labels_full: Optional[List[Optional[List[str]]]] = None
    if has_alarm and ("alarmword__last" in plot_df.columns):
        alarmword_labels_full = [None] * len(plot_df)
        alarm_idx = np.nonzero(alarm == 1)[0]
        for ii in alarm_idx:
            w = parse_int_maybe(plot_df.iloc[ii]["alarmword__last"])
            alarmword_labels_full[ii] = decode_alarmword_bits(w)

    per_point_color_full = None
    if color_col and (color_col in plot_df.columns) and pd.api.types.is_numeric_dtype(plot_df[color_col]):
        per_point_color_full = pd.to_numeric(plot_df[color_col], errors="coerce").to_numpy(dtype="float64")

    step = int(sample_every) if sample_every and sample_every > 1 else 1
    src_idx = np.arange(len(plot_df), dtype=np.int64)[::step]

    x = pd.to_numeric(plot_df.get(x_col), errors="coerce").to_numpy(dtype="float64")[::step]
    y = pd.to_numeric(plot_df.get(y_col), errors="coerce").to_numpy(dtype="float64")[::step]

    if per_point_color_full is not None:
        per_point_color = per_point_color_full[::step]
    else:
        per_point_color = None

    if alarm is not None:
        alarm_ds = alarm[::step]
    else:
        alarm_ds = None


    if alarmword_labels_full is not None:
        alarmword_labels_ds: Optional[List[Optional[List[str]]]] = [alarmword_labels_full[i] for i in src_idx]
    else:
        alarmword_labels_ds = None

    point, = ax.plot([], [], marker="o", linestyle="", markersize=7)
    trail, = ax.plot([], [], "-", alpha=0.7, linewidth=2)

    time_text = ax.text(
        0.01,
        0.99,
        "",
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10,
        bbox=dict(boxstyle="round", alpha=0.15),
    )

    def fmt_time_from_src(src_i: int) -> str:
        if time_col is None:
            return f"i={src_i}"
        v = plot_df.iloc[src_i][time_col]
        return f"{time_col}={v}"

    state = {
        "frozen": False,
        "freeze_i": 0,
        "freeze_alarm_text": "",
    }

    def init():
        point.set_data([], [])
        trail.set_data([], [])
        time_text.set_text("")
        return (point, trail, time_text)

    ani = None

    def update(i: int):
        nonlocal ani

        if state["frozen"]:
            i = state["freeze_i"]

        if (
            (not state["frozen"])
            and (alarm_ds is not None)
            and (i < len(alarm_ds))
            and (alarm_ds[i] == 1)
        ):
            state["frozen"] = True
            state["freeze_i"] = i

            alarm_text = "ALARM"
            if alarmword_labels_ds is not None:
                labels = alarmword_labels_ds[i]
                if labels:
                    alarm_text = labels[0]
            state["freeze_alarm_text"] = alarm_text

            if ani is not None:
                ani.event_source.stop()

        point.set_data([x[i]], [y[i]])
        j0 = max(0, i - int(trail_len))
        trail.set_data(x[j0 : i + 1], y[j0 : i + 1])

        src_i = int(src_idx[i])
        if state["frozen"]:
            point.set_color("orange")
            time_text.set_text(
                fmt_time_from_src(src_i) + "  |  ALARM (frozen): " + state["freeze_alarm_text"]
            )
        else:
            if per_point_color is not None and np.isfinite(per_point_color[i]):
                lo = float(np.nanmin(per_point_color))
                hi = float(np.nanmax(per_point_color))
                point.set_color(plt.cm.viridis((per_point_color[i] - lo) / max(1e-9, (hi - lo))))
            else:
                point.set_color("red")
            time_text.set_text(fmt_time_from_src(src_i))

        return (point, trail, time_text)

    ani = FuncAnimation(
        fig,
        update,
        frames=len(x),
        init_func=init,
        interval=int(interval_ms),
        blit=True,
        repeat=True,
    )

    plt.tight_layout()
    plt.show()


def plot_pca_2d_webgl(
    df: "pd.DataFrame",
    *,
    x_col: str = "pca1",
    y_col: str = "pca2",
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
