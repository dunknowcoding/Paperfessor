"""Draw the Paperfessor mascot: a meerkat professor with round
glasses, a suit, and a mortarboard. Flat-design icon, matplotlib
patches only, rendered at high resolution."""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import (Circle, Ellipse, FancyBboxPatch, Polygon,
                                Rectangle, Wedge, Arc)

OUT = sys.argv[1] if len(sys.argv) > 1 else "mascot.png"

# Palette
BG = "#2E5E4E"        # deep academic green badge
FUR = "#D9B380"       # meerkat tan
FUR_LIGHT = "#F0DCB8" # muzzle / belly
PATCH = "#5A4632"     # dark eye patches
DARK = "#2B2118"      # outlines / nose
SUIT = "#33475B"      # navy suit
SHIRT = "#FAF7EF"
TIE = "#B7412E"       # brick red tie
GOLD = "#E8B93E"      # tassel
PAPER = "#FFFFFF"

fig, ax = plt.subplots(figsize=(6, 6), dpi=300)
ax.set_xlim(0, 100); ax.set_ylim(0, 100)
ax.set_aspect("equal"); ax.axis("off")

# Badge background (rounded square)
ax.add_patch(FancyBboxPatch((4, 4), 92, 92,
             boxstyle="round,pad=0,rounding_size=18",
             fc=BG, ec="none"))

# ---- Body: suit ----------------------------------------------------------
# Shoulders / torso (trapezoid)
ax.add_patch(Polygon([[26, 4], [74, 4], [70, 34], [30, 34]], fc=SUIT, ec="none"))
# Shirt triangle
ax.add_patch(Polygon([[43, 34], [57, 34], [50, 16]], fc=SHIRT, ec="none"))
# Suit lapels
ax.add_patch(Polygon([[43, 34], [50, 24], [46, 15], [38, 30]], fc="#28394A", ec="none"))
ax.add_patch(Polygon([[57, 34], [50, 24], [54, 15], [62, 30]], fc="#28394A", ec="none"))
# Tie
ax.add_patch(Polygon([[48, 27], [52, 27], [53, 18], [50, 12], [47, 18]], fc=TIE, ec="none"))
ax.add_patch(Polygon([[48, 27], [52, 27], [50, 30]], fc=TIE, ec="none"))

# ---- Head ---------------------------------------------------------------
# Ears (small, set high and to the side — meerkat)
ax.add_patch(Circle((33.5, 68), 3.8, fc=FUR, ec=DARK, lw=1.2))
ax.add_patch(Circle((66.5, 68), 3.8, fc=FUR, ec=DARK, lw=1.2))
ax.add_patch(Circle((33.7, 68), 1.9, fc=PATCH, ec="none"))
ax.add_patch(Circle((66.3, 68), 1.9, fc=PATCH, ec="none"))
# Head (narrow tall ellipse — meerkats have slim faces)
ax.add_patch(Ellipse((50, 58), 34, 46, fc=FUR, ec=DARK, lw=1.4))
# Crown patch (darker fur on top of the head)
ax.add_patch(Ellipse((50, 72), 22, 14, fc="#C6A06B", ec="none"))
# Muzzle (small, pointy)
ax.add_patch(Ellipse((50, 46.5), 15, 13, fc=FUR_LIGHT, ec="none"))
# Meerkat eye patches (signature look) — behind glasses
ax.add_patch(Ellipse((43, 62.5), 8.5, 10.5, angle=10, fc=PATCH, ec="none"))
ax.add_patch(Ellipse((57, 62.5), 8.5, 10.5, angle=-10, fc=PATCH, ec="none"))
# Eyes
ax.add_patch(Circle((43, 62.5), 2.8, fc="white", ec="none"))
ax.add_patch(Circle((57, 62.5), 2.8, fc="white", ec="none"))
ax.add_patch(Circle((43.5, 62.2), 1.5, fc=DARK, ec="none"))
ax.add_patch(Circle((56.5, 62.2), 1.5, fc=DARK, ec="none"))
ax.add_patch(Circle((44.0, 62.9), 0.5, fc="white", ec="none"))
ax.add_patch(Circle((57.0, 62.9), 0.5, fc="white", ec="none"))
# Round professor glasses
for cx in (43, 57):
    ax.add_patch(Circle((cx, 62.5), 5.8, fc="none", ec=DARK, lw=1.8))
ax.plot([48.8, 51.2], [62.5, 62.5], color=DARK, lw=1.8, solid_capstyle="round")
ax.plot([37.2, 34.2], [62.5, 64.2], color=DARK, lw=1.6, solid_capstyle="round")
ax.plot([62.8, 65.8], [62.5, 64.2], color=DARK, lw=1.6, solid_capstyle="round")
# Nose + mouth (small, pointy)
ax.add_patch(Polygon([[48.6, 50.6], [51.4, 50.6], [50, 48.8]], fc=DARK, ec="none"))
ax.plot([50, 50], [48.8, 47.4], color=DARK, lw=1.2)
mouth = Arc((48.3, 47.3), 3.6, 2.6, angle=0, theta1=200, theta2=340, color=DARK, lw=1.2)
ax.add_patch(mouth)
mouth2 = Arc((51.7, 47.3), 3.6, 2.6, angle=0, theta1=200, theta2=340, color=DARK, lw=1.2)
ax.add_patch(mouth2)

# ---- Mortarboard ---------------------------------------------------------
# Cap base
ax.add_patch(Polygon([[38, 76], [62, 76], [62, 81], [38, 81]], fc=DARK, ec="none"))
# Board (diamond)
ax.add_patch(Polygon([[50, 92], [76, 82], [50, 74], [24, 82]], fc=DARK, ec="none"))
ax.add_patch(Polygon([[50, 90.2], [72.5, 81.7], [50, 75.4], [27.5, 81.7]], fc="#3A3028", ec="none"))
# Button + tassel
ax.add_patch(Circle((50, 82.5), 1.2, fc=GOLD, ec="none"))
ax.plot([50, 68, 69.5], [82.5, 79.5, 71], color=GOLD, lw=1.6, solid_capstyle="round")
ax.add_patch(Circle((69.7, 69.6), 1.7, fc=GOLD, ec="none"))

# ---- A paper in the pocket ----------------------------------------------
ax.add_patch(Rectangle((60.5, 22), 9, 11, angle=-8, fc=PAPER, ec=DARK, lw=1.0))
for i, y in enumerate((30.5, 28.3, 26.1)):
    ax.plot([61.6 + 0.3 * i, 67.2 + 0.3 * i], [y, y - 1.0], color="#8FA3B0", lw=0.9)

fig.savefig(OUT, transparent=True, bbox_inches="tight", pad_inches=0.02)
print("saved", OUT)
