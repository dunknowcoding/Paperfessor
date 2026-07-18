"""Tests for the PhD's durable learning memory (doc_learn.md)."""

from __future__ import annotations

from pathlib import Path

from paperfessor.agents.phd import PhDStudent
from paperfessor.config import load_settings


def _phd(tmp_path: Path) -> PhDStudent:
    return PhDStudent(load_settings(), object(), tmp_path)


def test_learn_and_recall(tmp_path: Path):
    phd = _phd(tmp_path)
    phd.learn("venue-requirements", "NeurIPS 2026: 9-page main, appendix allowed")
    phd.learn("coordination-ug", "UG windowing bugs are the #1 failure")
    assert (tmp_path / "doc_learn.md").is_file()
    hits = phd.recall_learnings(query="neurips appendix")
    assert any("NeurIPS 2026" in h for h in hits)
    cat = phd.recall_learnings(category="coordination-ug")
    assert any("windowing" in h for h in cat)


def test_learn_replaces_near_duplicate(tmp_path: Path):
    phd = _phd(tmp_path)
    # Same opening (first ~40 chars) => treated as a restatement.
    phd.learn("method-design", "Frequency band contrastive scoring wins reliably on servers")
    phd.learn("method-design", "Frequency band contrastive scoring wins reliably overall")
    lines = phd.recall_learnings(category="method-design")
    assert len(lines) == 1 and "overall" in lines[0]


def test_per_category_cap(tmp_path: Path):
    phd = _phd(tmp_path)
    for i in range(20):
        phd.learn("process", f"distinct lesson number {i} about workflow step {i}")
    lines = phd.recall_learnings(category="process", limit=100)
    assert len(lines) <= phd._LEARN_MAX_PER_CATEGORY


def test_forget_learning(tmp_path: Path):
    phd = _phd(tmp_path)
    phd.learn("experiments", "SMD has 38 channels and low anomaly ratio")
    phd.learn("experiments", "NAB traces are short and univariate")
    removed = phd.forget_learning("experiments", contains="SMD")
    assert removed == 1
    remaining = phd.recall_learnings(category="experiments")
    assert not any("SMD" in r for r in remaining) and any("NAB" in r for r in remaining)


def test_learn_survives_reset(tmp_path: Path):
    # doc_learn is durable: a new-paper reset must NOT clear it.
    from paperfessor.workspace_reset import prepare_workspace_for_new_paper
    phd = _phd(tmp_path)
    phd.learn("process", "durable lesson that must survive a reset")
    prepare_workspace_for_new_paper(tmp_path)
    assert (tmp_path / "doc_learn.md").is_file()
    assert any("durable lesson" in h for h in phd.recall_learnings(category="process"))
