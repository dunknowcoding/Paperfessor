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

    import textwrap
    # Aspect ratio >= 1.8 so the .tex writer places the diagram in a
    # two-column ``figure*`` slot (readable at ~6 in); in a single
    # column the 4-stage pipeline shrinks below legibility. Taller
    # canvas gives the (possibly 2-line) title real room.
    fig, ax = plt.subplots(figsize=(9.6, 4.4), dpi=200)
    ax.set_xlim(0.0, 10.0)
    ax.set_ylim(0.0, 5.4)
    ax.axis("off")
    # Title: the method name, WRAPPED so it never overflows the
    # canvas width (the old single-line "Architecture of <long
    # name>" was clipped at the right edge). Font auto-shrinks a
    # step for very long names.
    raw_title = f"Architecture of {method}"
    title_lines = textwrap.wrap(raw_title, width=46) or [raw_title]
    title_fs = 15 if len(title_lines) == 1 else 13
    ax.text(5.0, 5.2, "\n".join(title_lines[:2]),
            ha="center", va="top", fontsize=title_fs, fontweight="bold")
    sub_y = 5.2 - 0.42 * len(title_lines[:2]) - 0.08
    ax.text(5.0, sub_y, f"for {direction}", ha="center", va="top",
            fontsize=11, style="italic", color="#555")
    # Boxes for the 4 stages. Concise stage titles that FIT the box
    # width at a bold 11pt; the descriptive body carries the detail.
    boxes = [
        ("Input",
         "Multivariate\ntime series\n"
         f"({', '.join(d for d in datasets[:3])})",
         "#cfe2ff"),
        ("Encoder", "Self-supervised\ncontrastive\nencoder", "#d1e7dd"),
        ("Scoring", "Per-window\ndeviation\nscore", "#fff3cd"),
        ("Decision", "Threshold +\nlabel per\nwindow", "#f8d7da"),
    ]
    # Geometry: wider boxes with a real gap so neither the bold stage
    # titles nor the arrows are cramped.
    box_w, box_h = 2.15, 1.9
    gap = 0.3
    assert gap >= 0.25, "inter-box gap too small; arrows become stubs"
    total = 4 * box_w + 3 * gap
    x_start = (10.0 - total) / 2
    x_positions = [x_start + i * (box_w + gap) for i in range(4)]
    y = 1.35
    centers = []
    for (title, body, color), x in zip(boxes, x_positions):
        rect = mpatches.FancyBboxPatch(
            (x, y), box_w, box_h,
            boxstyle="round,pad=0.04,rounding_size=0.12",
            linewidth=1.2, edgecolor="#333", facecolor=color,
        )
        ax.add_patch(rect)
        ax.text(x + box_w / 2, y + box_h - 0.28, title,
                ha="center", va="center", fontsize=11.5, fontweight="bold")
        wrapped = "\n".join(
            textwrap.fill(line, width=13) for line in body.splitlines()
        )
        ax.text(x + box_w / 2, y + box_h / 2 - 0.32, wrapped,
                ha="center", va="center", fontsize=9.5, linespacing=1.25)
        centers.append(x + box_w)
    # Arrows between boxes (vertically centered on the boxes).
    arrow_y = y + box_h / 2
    for i in range(3):
        x0 = centers[i] + 0.03
        x1 = x_positions[i + 1] - 0.03
        ax.annotate(
            "", xy=(x1, arrow_y), xytext=(x0, arrow_y),
            arrowprops=dict(arrowstyle="-|>", lw=1.6, color="#333",
                            mutation_scale=18),
        )
    # Footnote.
    ax.text(5.0, 0.35, "Trained on raw windows; evaluated on labeled windows.",
            ha="center", va="center", fontsize=10, color="#666")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
