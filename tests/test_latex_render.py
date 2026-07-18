"""Regression tests for the LaTeX writer.

The preamble templates use %-formatting: any literal ``%`` inside
them must be escaped as ``%%`` or ``write_tex`` dies with "not
enough arguments for format string" (regression observed 2026-07-16).
"""

from __future__ import annotations

from pathlib import Path

from paperfessor.research.latex import NEURIPS_PREAMBLE_TEMPLATE, write_tex


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


def test_currency_dollar_not_treated_as_math():
    # Economics/finance prose is full of $ amounts; pairing them as
    # inline math garbled the passage and overflowed the margin
    # (observed on an economics review, 2026-07-18).
    from paperfessor.research.latex import _md_inline_to_tex
    d = chr(36)
    out = _md_inline_to_tex(
        f"wages rose from {d}1.60 in 1968 to {d}7.25 today")
    assert r"\$1.60" in out and r"\$7.25" in out
    # Real inline math is still preserved, even next to currency.
    out2 = _md_inline_to_tex(f"a {d}5 floor and a rate {d}x{d} variable")
    assert r"\$5" in out2 and f"{d}x{d}" in out2


def test_stats_notation_escaped():
    # p < 0.05 / age > 65 in prose render as wrong glyphs in text mode
    # unless escaped (medical / social / economics papers, 2026-07-18).
    from paperfessor.research.latex import _md_inline_to_tex
    out = _md_inline_to_tex("significant (p < 0.05) but weak for age > 65")
    assert r"\textless{}" in out and r"\textgreater{}" in out
    assert "<" not in out and ">" not in out
    # Inequalities inside real math are untouched.
    d = chr(36)
    out2 = _md_inline_to_tex(f"the bound {d}x < y{d} holds")
    assert f"{d}x < y{d}" in out2


def test_inequality_symbol_before_currency_no_collision():
    # "BMI >= 25 or >= 30 ... $25" — the unicode >= must NOT be wrapped
    # in $...$ (its closing $ collided with the currency guard and
    # opened an unterminated math span, garbling the paragraph on a
    # medical review, 2026-07-18). \ensuremath has no $.
    import re
    from paperfessor.research.latex import _md_inline_to_tex
    d = chr(36)
    out = _md_inline_to_tex(f"BMI ≥ 25 or ≥ 30 kg then {d}25 cost")
    assert r"\ensuremath{\geq}" in out and "$" not in out.replace(r"\$", "")
    # No long garbled math span.
    assert not re.search(r"\$[^$]{30,}\$", out)
