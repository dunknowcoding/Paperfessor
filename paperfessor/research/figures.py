"""Block-diagram generator for the paper.

Used by the PhD's write phase to produce a one-figure
``method architecture`` block diagram. Per the user spec
(req.txt 2): "在论文写作中多利用框图（较大的框图需要双栏宽度，
根据实际情况判断）".

Output: PNG file at ``workspace/src/figures/block_diagram.png``.
The paper's Method section references this file via the standard
Markdown image syntax; :func:`src.research.latex.md_to_tex_body`
emits the corresponding ``\\begin{figure}`` block.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402


def generate_block_diagram(
    method: str,
    direction: str,
    out_path: Path,
    *,
    datasets: list[str] | None = None,
) -> Path:
    """Draw a 4-stage pipeline block diagram for the proposed method.

    Stages: Raw Input -> Representation -> Anomaly Score -> Decision.
    The diagram is the canonical "method architecture" figure the
    paper's Method section references.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    datasets = datasets or ["PSM", "MSL", "SMAP"]

    # Aspect ratio >= 1.8 so the .tex writer places the diagram in a
    # two-column ``figure*`` slot (readable at ~6 in); in a single
    # column the 4-stage pipeline shrinks below legibility.
    fig, ax = plt.subplots(figsize=(9.0, 4.0), dpi=200)
    ax.set_xlim(0.0, 10.0)
    ax.set_ylim(0.0, 5.0)
    ax.axis("off")
    # Title at the top.
    ax.text(5.0, 4.5, f"Architecture of {method}",
            ha="center", va="center", fontsize=14, fontweight="bold")
    ax.text(5.0, 4.05, f"for {direction}", ha="center", va="center",
            fontsize=10, style="italic", color="#555")
    # Boxes for the 4 stages.
    boxes = [
        ("Raw Input",
         "Multivariate time series\n"
         f"({', '.join(d[:18] for d in datasets[:3])})",
         "#cfe2ff"),
        ("Representation", "Self-supervised\ncontrastive encoder", "#d1e7dd"),
        ("Anomaly Score", "Per-window\ndeviation score", "#fff3cd"),
        ("Decision", "Threshold +\nlabel per window", "#f8d7da"),
    ]
    # Geometry: 4 boxes with real gaps so titles can never collide
    # (the old 1.8-wide boxes at 2.2 pitch made 11pt titles overlap).
    box_w, box_h = 2.1, 1.6
    gap = 0.35
    total = 4 * box_w + 3 * gap
    x_start = (10.0 - total) / 2
    x_positions = [x_start + i * (box_w + gap) for i in range(4)]
    y = 1.7
    centers = []
    import textwrap
    for (title, body, color), x in zip(boxes, x_positions):
        rect = mpatches.FancyBboxPatch(
            (x, y), box_w, box_h,
            boxstyle="round,pad=0.05,rounding_size=0.15",
            linewidth=1.2, edgecolor="#333", facecolor=color,
        )
        ax.add_patch(rect)
        ax.text(x + box_w / 2, y + box_h - 0.3, title,
                ha="center", va="center", fontsize=9.5, fontweight="bold")
        wrapped = "\n".join(
            textwrap.fill(line, width=20) for line in body.splitlines()
        )
        ax.text(x + box_w / 2, y + 0.55, wrapped,
                ha="center", va="center", fontsize=7.5)
        centers.append(x + box_w)
    # Arrows between boxes.
    for i in range(3):
        x0 = centers[i] + 0.04
        x1 = x_positions[i + 1] - 0.04
        ax.annotate(
            "", xy=(x1, y + box_h / 2), xytext=(x0, y + box_h / 2),
            arrowprops=dict(arrowstyle="->", lw=1.5, color="#333"),
        )
    # Footnote.
    ax.text(5.0, 0.4, "Trained on raw windows; evaluated on labeled windows.",
            ha="center", va="center", fontsize=8, color="#666")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
