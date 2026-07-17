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


def test_reassemble_round_trip():
    md = _reassemble_paper(
        "M", [("Abstract", "body A"), ("3. Method", "body B")],
        {"3. Method": ["![f](figures/x.png)"]},
        ["- Su et al. (2019). *T*. arXiv:1. u"],
    )
    assert "## Abstract" in md and "body B" in md
    assert "![f](figures/x.png)" in md
    assert md.index("## References") > md.index("body B")
