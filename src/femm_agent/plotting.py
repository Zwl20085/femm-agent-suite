"""PNG figures for experiments and field maps (matplotlib is optional: every function returns
``None`` instead of raising when it is missing). Uses the Agg backend; never opens a window.

Style: one y-axis per chart, thin 2 px lines, recessive grid, a legend whenever there are two or
more series, fixed categorical colour order, and a single-hue sequential ramp for |B| maps.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

# fixed categorical order (validated colour-blind-safe reference palette, light surface)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"


def _plt():
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        return plt
    except Exception:
        return None


def available() -> bool:
    return _plt() is not None


def _style(ax, title, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.tick_params(colors=INK2, labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)


def plot_curves(path: str | Path, x: Sequence[float], series: Mapping[str, Sequence[float]], *, title: str = "",
                xlabel: str = "", ylabel: str = "", markers: bool = True, dashed: Sequence[str] = ()) -> str | None:
    """Line chart of one or more series sharing x and one y unit (never mix units on one chart)."""
    plt = _plt()
    if plt is None:
        return None
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    for k, (name, y) in enumerate(series.items()):
        ax.plot(list(x), list(y), color=SERIES[k % len(SERIES)], linewidth=2,
                linestyle="--" if name in dashed else "-", marker="o" if markers else None, markersize=3.5,
                label=name)
    _style(ax, title, xlabel, ylabel)
    if len(series) >= 2:
        ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return str(path)


def plot_harmonics(path: str | Path, orders: Sequence[int], amplitudes: Sequence[float], *, title: str = "",
                   xlabel: str = "harmonic order", ylabel: str = "amplitude", max_order: int = 30,
                   skip_dc: bool = True) -> str | None:
    """Bar chart of a single-sided amplitude spectrum."""
    plt = _plt()
    if plt is None:
        return None
    pairs = [(o, a) for o, a in zip(orders, amplitudes) if o <= max_order and (o > 0 or not skip_dc)]
    fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    ax.bar([p[0] for p in pairs], [p[1] for p in pairs], color=SERIES[0], width=0.7)
    _style(ax, title, xlabel, ylabel)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return str(path)


def plot_field(path: str | Path, nodes, elements, values, *, title: str = "|B| (T)", label: str = "|B| (T)",
               vmax: float | None = None, outline=None, xlim=None, ylim=None) -> str | None:
    """Element-constant colour map from bulk arrays: ``nodes`` (N,2), ``elements`` (M,>=3) with
    0-based node indices, ``values`` (M,) e.g. |B| from ``mo_getallb``. ``xlim``/``ylim`` zoom."""
    plt = _plt()
    if plt is None:
        return None
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.tri import Triangulation

    p = np.asarray(nodes, dtype=float)
    t = np.asarray(elements)[:, :3].astype(int)
    v = np.asarray(values, dtype=float)
    cmap = LinearSegmentedColormap.from_list("blues", ["#f4f8fd", "#9ec5f0", "#2a78d6", "#14407a", "#0a1f3d"])
    fig, ax = plt.subplots(figsize=(6.0, 5.2), dpi=130)
    fig.patch.set_facecolor(SURFACE)
    tri = Triangulation(p[:, 0], p[:, 1], t)
    pc = ax.tripcolor(tri, facecolors=v, cmap=cmap, vmin=0, vmax=vmax if vmax else float(np.percentile(v, 99.5)),
                      shading="flat")
    if outline is not None:
        for seg in outline:
            ax.plot([seg[0][0], seg[1][0]], [seg[0][1], seg[1][1]], color=INK2, linewidth=0.5)
    ax.set_aspect("equal")
    if xlim:
        ax.set_xlim(*xlim)
    if ylim:
        ax.set_ylim(*ylim)
    _style(ax, title, "", "")
    ax.grid(False)
    cb = fig.colorbar(pc, ax=ax, shrink=0.8)
    cb.set_label(label, color=INK2, fontsize=9)
    cb.ax.tick_params(labelsize=8, colors=INK2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return str(path)


def plot_mesh(path: str | Path, nodes, elements, *, title: str = "mesh", xlim=None, ylim=None) -> str | None:
    plt = _plt()
    if plt is None:
        return None
    import numpy as np
    from matplotlib.tri import Triangulation

    p = np.asarray(nodes, dtype=float)
    t = np.asarray(elements)[:, :3].astype(int)
    fig, ax = plt.subplots(figsize=(6.0, 5.2), dpi=130)
    fig.patch.set_facecolor(SURFACE)
    ax.triplot(Triangulation(p[:, 0], p[:, 1], t), color=SERIES[0], linewidth=0.2)
    ax.set_aspect("equal")
    if xlim:
        ax.set_xlim(*xlim)
    if ylim:
        ax.set_ylim(*ylim)
    _style(ax, title, "", "")
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return str(path)
