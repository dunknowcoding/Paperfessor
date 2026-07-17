"""Visual inspect — Article 19 layout checks.

Per the user's spec (req.txt, plus the spec's Article 19):
- no font too small or too large
- no line spacing wrong
- no paragraph spacing wrong
- no line overlap
- text density in range (not blank, not overcrowded)
- no content crosses the page margin

This module renders the PDF page with pypdfium2, runs a fast
heuristic pass over the rendered bitmap, and returns a per-page
report. The pipeline appends the report to ``article_memo.md``'s
``visual_inspect`` row so the PhD can act on it.

Heuristic note: the checks are *intentionally simple* — they
catch the obvious failure modes (overflow, blank page, extreme
density). They are not a substitute for human eyes; the PhD
must still read every page before sign-off.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Iterable

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

logger = logging.getLogger(__name__)


# Thresholds (per Article 19.1..19.6), calibrated 2026-07-16 against
# a real acmart[sigconf] PDF with the rect-based extractor. Note the
# "font" here is the text-rect HEIGHT, which runs ~1.1-1.4x the
# nominal font size (ascender + descender).
_FONT_MIN_PT = 4.3       # 5th-percentile INK height (acmart 7pt bibliography ~4.6)
_FONT_MAX_PT = 30.0      # anything taller than a title line is broken
_FONT_MEDIAN_MIN_PT = 5.8
_FONT_MEDIAN_MAX_PT = 15.0
_LINE_GAP_MIN_PT = 7.0
_LINE_GAP_MAX_PT = 26.0
_PARA_GAP_MIN_PT = 14.0
_PARA_GAP_MAX_PT = 60.0
# M9/M10: how many of the para gaps are too close / too far.
_PARA_CLOSE_TOO_MANY = 0.10  # <= 10% of paragraph breaks may be too close
_PARA_FAR_TOO_MANY = 0.20    # <= 20% may be too far
# Density = sum(line-rect area) / page area. A well-filled body page
# measures ~0.25-0.5; the title and final pages are legitimately
# sparser.
_DENSITY_MIN = 0.12
_DENSITY_MIN_EDGE_PAGE = 0.02  # first / last page
_DENSITY_MAX = 0.85
_MARGIN_MIN_PT = 4.0
# Artifact rects (rules, superscripts, stray marks) that must not
# skew the font statistics.
_ARTIFACT_MIN_H_PT = 3.0
_ARTIFACT_MIN_W_PT = 2.0
# Title / section-heading bboxes have larger fonts that the
# Article 19.1 font-size check should NOT flag. We mark a line
# "excluded" if it is in the top 1/8 of the page (title) or if
# its rect height is > 15pt (section heading or title text).
_TITLE_FRAC = 0.125
_HEADING_FONT_PT = 15.0


@dataclasses.dataclass(frozen=True)
class PageCheck:
    page_num: int
    width_pt: float
    height_pt: float
    font_min: float
    font_max: float
    font_median: float
    line_gap_median: float
    para_gap_median: float
    para_gap_too_close: int
    para_gap_too_far: int
    para_gap_total: int
    text_density: float
    margin_violation_count: int
    overlap_count: int
    passed: bool
    findings: tuple[str, ...]
    is_title_page: bool = False
    has_section_heading: bool = False


def _extract_words(pdfium_page) -> list[dict[str, float]]:
    """Extract per-line text rectangles from a pypdfium2 page.

    Uses the documented textpage rect API: ``count_rects()`` +
    ``get_rect(i)`` gives one rectangle per contiguous text segment
    (roughly one per rendered line), in PDF coordinates (origin
    bottom-left). ``get_text_bounded`` recovers the segment's text.
    We convert to top-left-origin coordinates; the rect height is a
    good proxy for the font size of the segment.

    (The previous implementation used ``get_textobj``, which does not
    return per-segment geometry — every metric downstream was junk:
    zero line gaps, uniform font sizes. Verified against a real
    acmart PDF on 2026-07-16.)
    """
    text_page = pdfium_page.get_textpage()
    page_h = pdfium_page.get_size()[1]
    n_rects = text_page.count_rects()
    lines: list[dict[str, float]] = []
    for i in range(n_rects):
        try:
            left, bottom, right, top = text_page.get_rect(i)
        except Exception:  # noqa: BLE001
            continue
        try:
            text = text_page.get_text_bounded(left, bottom, right, top) or ""
        except Exception:  # noqa: BLE001
            text = ""
        if not text.strip():
            continue
        w = max(0.0, right - left)
        h = max(0.0, top - bottom)
        # Drop artifact rects (rules, stray marks): they are not text
        # lines and would corrupt the font statistics.
        if w < _ARTIFACT_MIN_W_PT or h < _ARTIFACT_MIN_H_PT:
            continue
        lines.append({
            "x": float(left),
            "y": float(page_h - top),  # top-left origin
            "width": float(w),
            "height": float(h),
            "text": text.strip(),
        })
    return lines


def inspect_pdf(pdf_path: Path, *, scale: float = 2.0,
                max_pages: int | None = None) -> list[PageCheck]:
    """Run the 6 layout checks on every page of ``pdf_path``."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    n = len(pdf)
    limit = min(n, max_pages) if max_pages else n
    out: list[PageCheck] = []
    for i in range(limit):
        page = pdf[i]
        page_w_pt, page_h_pt = page.get_size()
        words = _extract_words(page)
        is_title_page = (i == 0)
        has_section_heading = any(
            w["height"] > _HEADING_FONT_PT for w in words
        )
        # M15/M16: title page and section heading bboxes are
        # excluded from the font-size check.
        # Page numbers / footnote markers (1-2 chars) are excluded
        # from font statistics on every page.
        def _is_marker(w: dict) -> bool:
            return len(str(w.get("text", ""))) <= 2

        if is_title_page:
            words_for_font = [
                w for w in words
                if w["y"] > page_h_pt * _TITLE_FRAC and not _is_marker(w)
            ]
        else:
            words_for_font = [
                w for w in words
                if w["height"] <= _HEADING_FONT_PT and not _is_marker(w)
            ]
        if not words:
            out.append(PageCheck(
                page_num=i + 1, width_pt=page_w_pt, height_pt=page_h_pt,
                font_min=0.0, font_max=0.0, font_median=0.0,
                line_gap_median=0.0, para_gap_median=0.0,
                para_gap_too_close=0, para_gap_too_far=0, para_gap_total=0,
                text_density=0.0, margin_violation_count=0,
                overlap_count=0, passed=False,
                findings=("page has no extractable text",),
                is_title_page=is_title_page,
                has_section_heading=has_section_heading,
            ))
            continue
        heights = sorted(w["height"] for w in words_for_font if w["height"] > 0)
        if not heights:
            heights = [0.0]
        # 5th percentile instead of the absolute min: one stray small
        # rect (footnote marker, subscript) must not fail the page.
        font_min = heights[max(0, int(0.05 * (len(heights) - 1)))]
        font_max = max(heights)
        font_median = heights[len(heights) // 2]
        # Vertical positions of line tops, per column (a two-column
        # layout has interleaved ys when pooled, which corrupts the
        # gap statistics). A line belongs to the left column when its
        # center is left of the page midline.
        # Only body-sized text lines participate in the gap stats:
        # shrunken table rows (resizebox) and headings would skew
        # the median and produce false line-spacing findings.
        body_words = [
            w for w in words
            if font_median > 0
            and 0.75 * font_median <= w["height"] <= _HEADING_FONT_PT
        ] or words
        line_gaps: list[float] = []
        for col in (0, 1):
            col_words = [
                w for w in body_words
                if (0 if (w["x"] + w["width"] / 2) < page_w_pt / 2 else 1) == col
            ]
            ys = sorted({round(w["y"], 1) for w in col_words})
            for j in range(1, len(ys)):
                gap = ys[j] - ys[j - 1]
                if 0 < gap < 100:
                    line_gaps.append(gap)
        line_gap_median = (
            sorted(line_gaps)[len(line_gaps) // 2] if line_gaps else 0.0
        )
        if line_gaps:
            median = line_gap_median
            para_gaps = [g for g in line_gaps if g > 1.6 * median + 4.0]
        else:
            para_gaps = []
        para_gap_median = (
            sorted(para_gaps)[len(para_gaps) // 2] if para_gaps else 0.0
        )
        # M9 / M10: per-paragraph-break classification.
        para_too_close = sum(1 for g in para_gaps if g < _PARA_GAP_MIN_PT)
        para_too_far = sum(1 for g in para_gaps if g > _PARA_GAP_MAX_PT)
        para_total = len(para_gaps)
        word_area = sum(w["width"] * w["height"] for w in words)
        page_area = page_w_pt * page_h_pt
        # Figures count toward density too: a page dominated by two
        # charts is full, not "mostly empty". Image object areas come
        # from the page's object list (best-effort; failures ignore
        # images rather than failing the page).
        image_area = 0.0
        image_findings: list[str] = []
        try:
            for obj in page.get_objects(max_depth=4):
                if getattr(obj, "type", None) == pdfium_c.FPDF_PAGEOBJ_IMAGE:
                    left, bottom, right, top = obj.get_bounds()
                    iw = max(0.0, right - left)
                    ih = max(0.0, top - bottom)
                    image_area += iw * ih
                    # Proportion checks (hard for a text-only reviewer
                    # to see): a figure narrower than ~1/5 of the page
                    # is unreadable; one covering > 60% of the page
                    # crowds out the text.
                    if 0 < iw < 0.20 * page_w_pt and ih > 20:
                        image_findings.append(
                            f"figure only {iw:.0f}pt wide "
                            f"({iw / page_w_pt:.0%} of page) — too small to read"
                        )
                    if iw * ih > 0.60 * page_w_pt * page_h_pt:
                        image_findings.append(
                            f"figure covers {iw * ih / (page_w_pt * page_h_pt):.0%} "
                            f"of the page — dominates the layout"
                        )
                    # Native raster resolution vs placed size: an image
                    # stretched beyond ~2x its pixel density prints
                    # blurry.
                    try:
                        px_w, px_h = obj.get_px_size()
                        if px_w and iw > 0 and (iw / 72.0) * 96 > px_w * 2:
                            image_findings.append(
                                f"figure upscaled ~{((iw / 72.0) * 96) / px_w:.1f}x "
                                f"beyond its pixel resolution (blurry)"
                            )
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass
        density = (word_area + min(image_area, page_area)) / max(1.0, page_area)
        margin_violations = 0
        for w in words:
            x, y, wd, ht = w["x"], w["y"], w["width"], w["height"]
            if (x < _MARGIN_MIN_PT or y < _MARGIN_MIN_PT
                    or (x + wd) > page_w_pt - _MARGIN_MIN_PT
                    or (y + ht) > page_h_pt - _MARGIN_MIN_PT):
                margin_violations += 1
        # Overlap check between line rects. Adjacent lines share
        # ascender/descender space, so only SUBSTANTIAL overlap
        # counts: > 40% of the smaller rect's height AND > 4pt of
        # horizontal intersection.
        overlaps = 0
        for j in range(len(words)):
            for k in range(j + 1, min(j + 30, len(words))):
                if _substantial_overlap(words[j], words[k]):
                    overlaps += 1
                    if overlaps > 50:
                        break
            if overlaps > 50:
                break
        findings: list[str] = []
        if font_min < _FONT_MIN_PT:
            findings.append(
                f"font_min={font_min:.1f}pt < {_FONT_MIN_PT}pt (text too small)"
            )
        if font_max > _FONT_MAX_PT:
            findings.append(
                f"font_max={font_max:.1f}pt > {_FONT_MAX_PT}pt (text too large)"
            )
        if not (_FONT_MEDIAN_MIN_PT <= font_median <= _FONT_MEDIAN_MAX_PT):
            findings.append(
                f"font_median={font_median:.1f}pt not in "
                f"[{_FONT_MEDIAN_MIN_PT},{_FONT_MEDIAN_MAX_PT}]"
            )
        if line_gap_median and (
            line_gap_median < _LINE_GAP_MIN_PT
            or line_gap_median > _LINE_GAP_MAX_PT
        ):
            findings.append(
                f"line_gap_median={line_gap_median:.1f}pt not in "
                f"[{_LINE_GAP_MIN_PT},{_LINE_GAP_MAX_PT}]"
            )
        # Paragraph-gap checks are skipped on the final page: a
        # trailing references/figures page has few, large, legitimate
        # gaps that say nothing about body typesetting.
        is_last_page = (i == limit - 1)
        if not is_last_page and para_gap_median and (
            para_gap_median < _PARA_GAP_MIN_PT
            or para_gap_median > _PARA_GAP_MAX_PT
        ):
            findings.append(
                f"para_gap_median={para_gap_median:.1f}pt not in "
                f"[{_PARA_GAP_MIN_PT},{_PARA_GAP_MAX_PT}]"
            )
        # M9 / M10: too-close / too-far para gap counts.
        if not is_last_page and para_total > 0:
            close_frac = para_too_close / para_total
            far_frac = para_too_far / para_total
            if close_frac > _PARA_CLOSE_TOO_MANY:
                findings.append(
                    f"para_gap_too_close={para_too_close}/{para_total} "
                    f"({close_frac:.0%}) > {_PARA_CLOSE_TOO_MANY:.0%}"
                )
            if far_frac > _PARA_FAR_TOO_MANY:
                findings.append(
                    f"para_gap_too_far={para_too_far}/{para_total} "
                    f"({far_frac:.0%}) > {_PARA_FAR_TOO_MANY:.0%}"
                )
        # First and last pages are legitimately sparser (title block,
        # trailing references).
        density_min = (
            _DENSITY_MIN_EDGE_PAGE if (i == 0 or i == limit - 1) else _DENSITY_MIN
        )
        if density < density_min:
            findings.append(
                f"density={density:.2f} < {density_min} (page is mostly empty)"
            )
        if density > _DENSITY_MAX:
            findings.append(
                f"density={density:.2f} > {_DENSITY_MAX} (page is overcrowded)"
            )
        if margin_violations > 0:
            findings.append(
                f"{margin_violations} words cross the page margin"
            )
        findings.extend(image_findings)
        if overlaps > 5:
            findings.append(f"{overlaps} word-bbox overlaps detected")
        # Title page flag: it's "passed" iff there are no findings
        # AND the page is not empty.
        passed = not findings
        out.append(PageCheck(
            page_num=i + 1, width_pt=page_w_pt, height_pt=page_h_pt,
            font_min=font_min, font_max=font_max, font_median=font_median,
            line_gap_median=line_gap_median, para_gap_median=para_gap_median,
            para_gap_too_close=para_too_close,
            para_gap_too_far=para_too_far, para_gap_total=para_total,
            text_density=density, margin_violation_count=margin_violations,
            overlap_count=overlaps, passed=passed,
            findings=tuple(findings),
            is_title_page=is_title_page,
            has_section_heading=has_section_heading,
        ))
    return out


def overall_exit_code(checks: Iterable[PageCheck]) -> int:
    """Article 19.7: 0 on full pass, 1 on any FAIL.

    Used by the CI / loop harness to gate the run.
    """
    checks = list(checks)
    if not checks:
        return 1
    return 0 if all(c.passed for c in checks) else 1


def render_report(checks: Iterable[PageCheck], pdf_path: Path) -> dict[str, object]:
    """Build the structured report the Integrator / GUI consumes."""
    checks = list(checks)
    return {
        "pdf": str(pdf_path),
        "exit_code": overall_exit_code(checks),
        "n_pages": len(checks),
        "passed": sum(1 for c in checks if c.passed),
        "failed": sum(1 for c in checks if not c.passed),
        "pages": [
            {
                "page_num": c.page_num,
                "passed": c.passed,
                "is_title_page": c.is_title_page,
                "has_section_heading": c.has_section_heading,
                "font_min": round(c.font_min, 2),
                "font_max": round(c.font_max, 2),
                "font_median": round(c.font_median, 2),
                "line_gap_median": round(c.line_gap_median, 2),
                "para_gap_median": round(c.para_gap_median, 2),
                "para_gap_too_close": c.para_gap_too_close,
                "para_gap_too_far": c.para_gap_too_far,
                "para_gap_total": c.para_gap_total,
                "text_density": round(c.text_density, 3),
                "margin_violations": c.margin_violation_count,
                "overlaps": c.overlap_count,
                "findings": list(c.findings),
            }
            for c in checks
        ],
    }


def _substantial_overlap(a: dict, b: dict) -> bool:
    """True when two line rects overlap enough to be a layout defect
    (adjacent lines legitimately share ascender/descender space)."""
    ax1, ay1 = float(a.get("x", 0.0)), float(a.get("y", 0.0))
    ax2 = ax1 + float(a.get("width", 0.0))
    ay2 = ay1 + float(a.get("height", 0.0))
    bx1, by1 = float(b.get("x", 0.0)), float(b.get("y", 0.0))
    bx2 = bx1 + float(b.get("width", 0.0))
    by2 = by1 + float(b.get("height", 0.0))
    x_olap = min(ax2, bx2) - max(ax1, bx1)
    y_olap = min(ay2, by2) - max(ay1, by1)
    if x_olap <= 4.0 or y_olap <= 0.0:
        return False
    min_h = min(ay2 - ay1, by2 - by1)
    return min_h > 0 and (y_olap / min_h) > 0.4


def summarize(checks: Iterable[PageCheck]) -> str:
    """Render a one-line-per-page Markdown summary for article_memo."""
    lines: list[str] = []
    for c in checks:
        flag = "OK" if c.passed else "FAIL"
        lines.append(
            f"- page {c.page_num}: {flag}  "
            f"font=({c.font_min:.1f},{c.font_median:.1f},{c.font_max:.1f})pt  "
            f"line_gap={c.line_gap_median:.1f}pt  "
            f"density={c.text_density:.2f}  "
            f"margin_violations={c.margin_violation_count}  "
            f"overlaps={c.overlap_count}"
        )
        for f in c.findings:
            lines.append(f"  - {f}")
    overall_pass = all(c.passed for c in checks)
    head = f"overall: {'PASS' if overall_pass else 'FAIL'}  pages: {len(checks)}"
    return head + "\n" + "\n".join(lines)


__all__ = [
    "PageCheck",
    "inspect_pdf",
    "overall_exit_code",
    "render_report",
    "summarize",
]
