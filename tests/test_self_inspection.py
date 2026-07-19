"""Tests for the PhD's whole-paper self-inspection (deterministic part)."""

from __future__ import annotations

import json
from pathlib import Path

from paperfessor.runner.pipeline import (
    _defect_targets_section,
    _reassemble_paper,
    _whole_paper_defects,
)


def _workspace_with_results(tmp_path: Path) -> Path:
    ws = tmp_path
    results_dir = ws / "src" / "results"
    results_dir.mkdir(parents=True)
    (results_dir / "results.json").write_text(json.dumps({
        "rows": [
            {"dataset": "smd-1-1", "method": "Ours (ours)", "n_seeds": 3,
             "f1_mean": 0.760, "f1_ci": 0.0, "precision_mean": 0.656,
             "recall_mean": 0.903, "auroc_mean": 0.965, "auroc_ci": 0.0,
             "auprc_mean": 0.618, "seconds": 1.0, "error": None},
        ],
        "manifests": {"smd-1-1": {"anomaly_ratio_test": 0.095}},
    }), encoding="utf-8")
    (ws / "paper" / "body" / "figures").mkdir(parents=True)
    return ws


GOOD_MD = """# Method

## Abstract

We reach F1 0.760 and AUROC 0.965 on smd-1-1 (Su et al., 2019).

## References

- Su et al. (2019). *Robust Anomaly Detection*. arXiv:1903.00001. https://arxiv.org/abs/1903.00001
- A et al. (2020). *B*. arXiv:2. x
- C et al. (2020). *D*. arXiv:3. x
- E et al. (2020). *F*. arXiv:4. x
- G et al. (2020). *H*. arXiv:5. x
- I et al. (2020). *J*. arXiv:6. x
- K et al. (2020). *L*. arXiv:7. x
- M et al. (2020). *N*. arXiv:8. x
- O et al. (2020). *P*. arXiv:9. x
- Q et al. (2020). *R*. arXiv:10. x
"""


def test_clean_paper_has_no_defects(tmp_path: Path):
    ws = _workspace_with_results(tmp_path)
    assert _whole_paper_defects(GOOD_MD, ws) == []


def test_hallucinated_metric_is_flagged(tmp_path: Path):
    ws = _workspace_with_results(tmp_path)
    bad = GOOD_MD.replace("F1 0.760", "F1 0.812")
    defects = _whole_paper_defects(bad, ws)
    assert any("0.812" in d for d in defects)


def test_internal_wording_is_flagged(tmp_path: Path):
    ws = _workspace_with_results(tmp_path)
    bad = GOOD_MD.replace("We reach", "The UG measured, and we reach")
    assert any("internal wording" in d for d in _whole_paper_defects(bad, ws))


def test_missing_reference_is_flagged(tmp_path: Path):
    ws = _workspace_with_results(tmp_path)
    bad = GOOD_MD.replace("(Su et al., 2019)", "(Nowhere et al., 2019)")
    assert any("Nowhere" in d for d in _whole_paper_defects(bad, ws))


def test_dangling_figure_is_flagged(tmp_path: Path):
    ws = _workspace_with_results(tmp_path)
    bad = GOOD_MD.replace(
        "## References", "![x](figures/ghost.png)\n\n## References"
    )
    assert any("ghost.png" in d for d in _whole_paper_defects(bad, ws))


def test_defect_routing_to_section():
    assert _defect_targets_section(
        "Abstract: claims an unevaluated dataset", "Abstract", "anything"
    )
    assert _defect_targets_section(
        "number 0.812 does not match any measured value",
        "4. Experimental Setup", "the best F1 is 0.812 here",
    )
    assert not _defect_targets_section(
        "number 0.812 does not match any measured value",
        "1. Introduction", "no numbers here",
    )


def test_method_strategy_improve_then_abandon():
    from paperfessor.runner.pipeline import CoordinationPolicy, _method_strategy
    policy = CoordinationPolicy(max_method_rounds=2)
    base = {
        "research_direction": "anomaly-detection-in-m",
        "success": "false",
        "reason": "proposed method won best F1 on no dataset (req: iterate ...)",
        "post_mortem": "band variance under-determined on short series",
        "archived_at": "2026-07-16T20:00:00",
        "method": "FBD",
    }
    # One failed competitiveness attempt -> improve.
    mode, method, pm = _method_strategy([base], "anomaly detection in multivariate time series", policy)
    assert mode == "improve" and method == "FBD" and "variance" in pm
    # Rounds exhausted -> new method.
    second = dict(base, archived_at="2026-07-16T21:00:00")
    mode, _, _ = _method_strategy([base, second], "anomaly detection in multivariate time series", policy)
    assert mode == "new"
    # Structural failure (not competitiveness) -> new method.
    broken = dict(base, reason="UG returned a fallback skeleton")
    mode, _, _ = _method_strategy([broken], "anomaly detection in multivariate time series", policy)
    assert mode == "new"
    # Success -> new method (never re-run a solved method).
    solved = dict(base, success="true")
    mode, _, _ = _method_strategy([solved], "anomaly detection in multivariate time series", policy)
    assert mode == "new"


def test_resolve_missing_citations_parses_and_skips_unmatchable(monkeypatch):
    from paperfessor.runner import pipeline as pl

    md = ("## 2. Related Work\n\nIsolation-based detection "
          "(Liu et al., 2008) is a strong baseline.\n\n## References\n\n- x\n")
    refs: list[str] = []

    class _Hit:
        authors = ("Fei Tony Liu", "Kai Ming Ting")
        year = 2008
        title = "Isolation Forest"
        arxiv_id = "0000.00000"
        doi = "https://doi.org/10.1109/ICDM.2008.17"
        landing_page_url = ""
        venue = "ICDM"

    monkeypatch.setattr(
        "paperfessor.research.sources.arxiv.search",
        lambda q, max_results=5: [_Hit()],
    )
    defects = ["body cites (Liu et al.) but the References list has no such entry",
               "number 0.999 does not match any measured value"]
    unresolved, added = pl._resolve_missing_citations(defects, md, refs)
    assert added == 1 and any("Isolation Forest" in r for r in refs)
    # The non-citation defect passes through untouched.
    assert unresolved == ["number 0.999 does not match any measured value"]


def test_canonical_citation_rung_needs_alias_corroboration(monkeypatch):
    from paperfessor.runner.pipeline import _resolve_missing_citations
    # Keep the test offline: live rungs return nothing.
    monkeypatch.setattr("paperfessor.research.sources.arxiv.search",
                        lambda *a, **k: [])
    monkeypatch.setattr("paperfessor.research.sources.openalex.search",
                        lambda *a, **k: [])
    monkeypatch.setattr("paperfessor.research.sources.s2.search",
                        lambda *a, **k: [])
    refs: list[str] = []
    md = ("## 2. Related Work\n\nUSAD frames detection as adversarial "
          "reconstruction (Audibert et al., 2020).\n\n## References\n\n- x\n")
    d = ["body cites (Audibert et al.) but the References list has no such entry"]
    unresolved, added = _resolve_missing_citations(d, md, refs)
    assert added == 1 and any("USAD" in r for r in refs)
    # Same surname WITHOUT corroborating context must not use the table
    # (falls through to the live rungs; with those failing it stays
    # unresolved rather than attaching the wrong work).
    refs2: list[str] = []
    md2 = ("## 2. Related Work\n\nA totally unrelated claim "
           "(Audibert et al., 1901).\n\n## References\n\n- x\n")
    unresolved2, added2 = _resolve_missing_citations(list(d), md2, refs2)
    assert not any("USAD" in r for r in refs2)


def test_clean_section_strips_ascii_diagrams():
    from paperfessor.runner.pipeline import _clean_section_body
    body = (
        "The method has three stages.\n\n"
        "```\n"
        "  x --> [FFT] --> [band] --> score\n"
        + "┌" + "─" * 40 + "┐\n"
        "```\n\n"
        "Figure 1. Pipeline of the method decomposed into bands and\n"
        "scored by kNN against references.\n\n"
        "The scorer is a kNN in latent space.\n"
    )
    out = _clean_section_body(body, "3. Method")
    assert "```" not in out
    assert "┌" not in out and "─" not in out
    assert "Figure 1." not in out
    # Real prose survives.
    assert "three stages" in out and "kNN in latent space" in out


def test_review_input_keeps_structure_and_references():
    from paperfessor.runner.pipeline import _review_input
    long_body = ("Lorem ipsum dolor sit amet. " * 40 + "\n\n") * 30
    md = (
        "# T\n\n"
        + "".join(f"## {i}. Section {i}\n\n{long_body}" for i in range(1, 6))
        + "## References\n\n"
        + "\n".join(f"- Ref{i} et al. (2020). *X*. arXiv:{i}." for i in range(20))
    )
    out = _review_input(md, max_chars=8000)
    assert len(out) <= 11000
    # Every heading survives, references included in full, cuts marked.
    for i in range(1, 6):
        assert f"## {i}. Section {i}" in out
    assert "Ref19 et al." in out
    assert "omitted" in out


def test_competitiveness_gated_by_sota_mode():
    from paperfessor.runner.pipeline import RunReadiness
    # Uncompetitive method: fails in SOTA mode, passes otherwise.
    sota = RunReadiness(readable_papers=5, survey_blocked=False,
                        code_fallback=False, placeholder_metric=False,
                        visual_ok=True, method_uncompetitive=True, sota_mode=True)
    assert any("won best F1 on no dataset" in i for i in sota.issues())
    non_sota = RunReadiness(readable_papers=5, survey_blocked=False,
                            code_fallback=False, placeholder_metric=False,
                            visual_ok=True, method_uncompetitive=True, sota_mode=False)
    assert not any("won best F1" in i for i in non_sota.issues())
    # A hard defect still fails regardless of goal.
    broken = RunReadiness(readable_papers=5, survey_blocked=False,
                          code_fallback=True, placeholder_metric=False,
                          visual_ok=True, method_uncompetitive=True, sota_mode=False)
    assert broken.issues()


def test_reset_for_replan_keeps_memory_clears_artifacts(tmp_path):
    from paperfessor.workspace_reset import reset_for_replan
    ws = tmp_path / "workspace"
    # Seed memory + artifacts + datasets.
    (ws).mkdir()
    (ws / "doc_memo.md").write_text("MEMORY KEEP", encoding="utf-8")
    (ws / "article_memo.md").write_text("MEMORY KEEP", encoding="utf-8")
    (ws / "archived").mkdir(); (ws / "archived" / "a").mkdir()
    (ws / "archived" / "a" / "metadata.yaml").write_text("x", encoding="utf-8")
    (ws / "paper" / "body").mkdir(parents=True)
    (ws / "paper" / "body" / "paper.pdf").write_text("ARTIFACT", encoding="utf-8")
    (ws / "src" / "datasets" / "d").mkdir(parents=True)
    (ws / "src" / "datasets" / "d" / "train_x.npy").write_text("DATA", encoding="utf-8")
    (ws / "src" / "papers").mkdir(parents=True)
    (ws / "src" / "papers" / "p.pdf").write_text("PAPER", encoding="utf-8")
    reset_for_replan(ws)
    # Memory kept.
    assert (ws / "doc_memo.md").read_text(encoding="utf-8") == "MEMORY KEEP"
    assert (ws / "article_memo.md").read_text(encoding="utf-8") == "MEMORY KEEP"
    assert (ws / "archived" / "a" / "metadata.yaml").is_file()
    # Downloaded papers kept (literature, not experiment output).
    assert (ws / "src" / "papers" / "p.pdf").is_file()
    # Artifacts + datasets cleared.
    assert not (ws / "paper" / "body" / "paper.pdf").is_file()
    assert not (ws / "src" / "datasets" / "d").exists()


def test_reassemble_round_trip():
    md = _reassemble_paper(
        "M", [("Abstract", "body A"), ("3. Method", "body B")],
        {"3. Method": ["![f](figures/x.png)"]},
        ["- Su et al. (2019). *T*. arXiv:1. u"],
    )
    assert "## Abstract" in md and "body B" in md
    assert "![f](figures/x.png)" in md
    assert md.index("## References") > md.index("body B")


def test_bounded_memory_caps_prompt_cost():
    from paperfessor.runner.pipeline import _bounded_memory
    small = "line one\nline two"
    assert _bounded_memory(small) == small  # under budget: unchanged
    big = "\n".join(f"lesson {i}: " + "x" * 60 for i in range(200))
    out = _bounded_memory(big, max_chars=500)
    assert len(out) <= 600  # bounded (+ marker)
    assert "older memory omitted" in out
    # keeps whole leading lines
    assert out.startswith("lesson 0:")
