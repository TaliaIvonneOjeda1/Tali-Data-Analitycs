"""Gráficos en código (matplotlib). El LLM no dibuja: pide esta tool. (Caso1 S2)"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from src.config import OUTPUTS_DIR

# Paleta TaliAnalytics (UI)
_ACCENT = "#2457d6"
_NEG = "#b91c1c"
_AXIS = "#334155"
_TITLE = "#101a2f"


def _prepare_dest(dest: Path | None, default_name: str) -> Path:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    path = Path(dest) if dest else (OUTPUTS_DIR / default_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def bar_chart(
    labels: Sequence[str],
    values: Sequence[float],
    dest: Path | None = None,
    *,
    title: str = "",
    ylabel: str = "",
    sort_desc: bool = True,
) -> Path:
    """Barras con eje en 0, paleta TaliAnalytics y orden mayor→menor si aplica."""
    # Agg = thread-safe / headless (evita crash tkinter en run_all paralelo)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if len(labels) != len(values):
        raise ValueError("labels y values deben tener la misma longitud")
    dest = _prepare_dest(dest, "chart_barras.png")

    vals = [float(v) for v in values]
    labs = [str(l) for l in labels]
    has_neg = any(v < 0 for v in vals)
    has_pos = any(v > 0 for v in vals)

    # Orden categórico mayor→menor solo si no hay negativos (desvíos conservan orden dado)
    if sort_desc and not has_neg and len(vals) > 1:
        paired = sorted(zip(labs, vals, strict=True), key=lambda x: x[1], reverse=True)
        labs = [p[0] for p in paired]
        vals = [p[1] for p in paired]

    colors = [_NEG if v < 0 else _ACCENT for v in vals]
    long_labels = any(len(l) > 14 for l in labs)

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Con valores negativos (desvíos), barras horizontales leen mejor.
    if has_neg or long_labels:
        y = list(range(len(labs)))
        ax.barh(y, vals, color=colors, height=0.65)
        ax.set_yticks(y)
        ax.set_yticklabels(labs, color=_TITLE)
        ax.axvline(0, color=_AXIS, linewidth=1.2)
        xmin = min(0.0, min(vals) if vals else 0.0)
        xmax = max(0.0, max(vals) if vals else 0.0)
        pad = max(abs(xmin), abs(xmax), 1.0) * 0.12
        ax.set_xlim(xmin - pad, xmax + pad)
        if ylabel:
            ax.set_xlabel(ylabel, color=_AXIS)
        for i, v in enumerate(vals):
            offset = pad * 0.15 if v >= 0 else -pad * 0.15
            ax.text(
                v + offset,
                i,
                f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                va="center",
                ha="left" if v >= 0 else "right",
                fontsize=9,
                color=_TITLE,
            )
        ax.invert_yaxis()
        ax.grid(axis="x", linestyle=":", alpha=0.35)
    else:
        x = list(range(len(labs)))
        ax.bar(x, vals, color=colors)
        ax.set_xticks(x)
        ax.set_xticklabels(labs, rotation=30, ha="right", color=_TITLE)
        ax.axhline(0, color=_AXIS, linewidth=1.0)
        if ylabel:
            ax.set_ylabel(ylabel, color=_AXIS)
        # Eje Y desde 0 (regla BI)
        if has_pos:
            ymax = max(vals) if vals else 1.0
            ax.set_ylim(0, ymax * 1.15 if ymax else 1)
        else:
            ax.set_ylim(0, 1)
        ax.grid(axis="y", linestyle=":", alpha=0.35)

    if title:
        ax.set_title(title, color=_TITLE, fontsize=12, pad=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(dest, dpi=120, facecolor="white")
    plt.close(fig)
    return dest


def line_chart(
    labels: Sequence[str],
    values: Sequence[float],
    dest: Path | None = None,
    *,
    title: str = "",
    ylabel: str = "",
) -> Path:
    """Línea para series temporales (orden de etiquetas = orden cronológico)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if len(labels) != len(values):
        raise ValueError("labels y values deben tener la misma longitud")
    dest = _prepare_dest(dest, "chart_lineas.png")

    vals = [float(v) for v in values]
    labs = [str(l) for l in labels]
    x = list(range(len(labs)))

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.plot(x, vals, color=_ACCENT, marker="o", linewidth=2.0, markersize=5)
    ax.set_xticks(x)
    ax.set_xticklabels(labs, rotation=30, ha="right", color=_TITLE)
    if ylabel:
        ax.set_ylabel(ylabel, color=_AXIS)
    if title:
        ax.set_title(title, color=_TITLE, fontsize=12, pad=10)
    # No forzar ymin=0 en líneas de ratios; sí incluir 0 si todos son no negativos
    if vals and min(vals) >= 0:
        ax.set_ylim(bottom=0)
    ax.grid(axis="y", linestyle=":", alpha=0.35)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(dest, dpi=120, facecolor="white")
    plt.close(fig)
    return dest
