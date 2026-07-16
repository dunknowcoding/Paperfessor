"""Regression tests for the LaTeX writer.

The preamble templates use %-formatting: any literal ``%`` inside
them must be escaped as ``%%`` or ``write_tex`` dies with "not
enough arguments for format string" (regression observed 2026-07-16).
"""

from __future__ import annotations

from pathlib import Path

from src.research.latex import NEURIPS_PREAMBLE_TEMPLATE, write_tex


SAMPLE_MD = """# Sample Paper Title

## Abstract

This is the abstract with a measured number: F1 0.622 ± 0.005.

## 1. Introduction

Body text with k ≥ 3 seeds and a citation (Wu et al., 2024).

## 4. Experimental Setup

| Dataset | Method | F1 | Precision | Recall | AUROC | AUPRC |
|---|---|---|---|---|---|---|
| smd-1-1 | ours | **0.622** | 0.647 | 0.599 | 0.910 | 0.636 |

## References

- Wu et al. (2024). *A Real Paper*. arXiv:2401.00001. https://arxiv.org/abs/2401.00001
"""


def test_preamble_template_formats_cleanly():
    # Two %s slots (title, abstract); no stray % may remain.
    rendered = NEURIPS_PREAMBLE_TEMPLATE % ("T", "A")
    assert "T" in rendered and "A" in rendered


def test_write_tex_smoke(tmp_path: Path):
    tex_path = write_tex(SAMPLE_MD, tmp_path, class_name="acmart-sigconf")
    assert tex_path.is_file()
    tex = tex_path.read_text(encoding="utf-8")
    # Title block present and well-formed.
    assert r"\title{" in tex and r"\maketitle" in tex
    assert r"\ccsdesc[500]" in tex
    # Math-only symbols are wrapped in $...$ (text-mode \pm broke pages).
    assert r"\pm{}" not in tex and r"\geq{}" not in tex
    # The 7-column table spans both columns and cannot overflow.
    assert r"\begin{table*}" in tex and r"\resizebox" in tex
    # No process/handoff headings.
    assert "What changed" not in tex and "Evidence" not in tex


def test_write_tex_no_percent_crash(tmp_path: Path):
    # A body containing literal % must not break the format either.
    md = SAMPLE_MD.replace("measured number", "measured 95% number")
    tex_path = write_tex(md, tmp_path, class_name="acmart-sigconf")
    assert tex_path.is_file()


def test_underscores_escaped_in_text_mode(tmp_path: Path):
    # `x_i` in prose or inline code must never reach LaTeX raw —
    # a bare _ in text mode kills the build (observed 2026-07-16).
    md = SAMPLE_MD.replace(
        "Body text with", "Per variable `x_i` and series x_t, body text with"
    )
    tex = write_tex(md, tmp_path, class_name="acmart-sigconf").read_text(encoding="utf-8")
    assert "x_i" not in tex.replace("x\\_i", "")
    assert "x\\_i" in tex and "x\\_t" in tex
