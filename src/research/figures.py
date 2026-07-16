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

    fig, ax = plt.subplots(figsize=(8.0, 4.5), dpi=150)
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
        ("Raw Input", f"Multivariate time series\n(datasets: {', '.join(datasets[:3])})", "#cfe2ff"),
        ("Representation", "Self-supervised\ncontrastive encoder", "#d1e7dd"),
        ("Anomaly Score", "Per-window\ndeviation score", "#fff3cd"),
        ("Decision", "Threshold +\nlabel per window", "#f8d7da"),
    ]
    box_w, box_h = 1.8, 1.5
    y = 1.7
    x_positions = [0.5, 2.7, 4.9, 7.1]
    centers = []
    for (title, body, color), x in zip(boxes, x_positions):
        rect = mpatches.FancyBboxPatch(
            (x, y), box_w, box_h,
            boxstyle="round,pad=0.05,rounding_size=0.15",
            linewidth=1.2, edgecolor="#333", facecolor=color,
        )
        ax.add_patch(rect)
        ax.text(x + box_w / 2, y + box_h - 0.25, title,
                ha="center", va="center", fontsize=11, fontweight="bold")
        ax.text(x + box_w / 2, y + 0.5, body,
                ha="center", va="center", fontsize=8.5)
        centers.append(x + box_w)
    # Arrows between boxes.
    for i in range(3):
        x0 = centers[i] + 0.05
        x1 = x_positions[i + 1] - 0.05
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
