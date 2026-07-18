from __future__ import annotations

from pathlib import Path

from paperfessor.workspace import bootstrap_workspace
from paperfessor.workspace_reset import hard_reset_workspace, prepare_workspace_for_new_paper


def test_prepare_workspace_for_new_paper_clears_active_state_but_keeps_assets(tmp_path: Path) -> None:
    workspace = bootstrap_workspace(tmp_path / "workspace", force=True)

    (workspace / "doc_memo.md").write_text("dirty doc memo", encoding="utf-8")
    (workspace / "article_memo.md").write_text("dirty article memo", encoding="utf-8")
    (workspace / "shared" / "research_log.md").write_text("old research log", encoding="utf-8")
    (workspace / "shared" / "code_log.md").write_text("old code log", encoding="utf-8")
    (workspace / "paper" / "body").mkdir(parents=True, exist_ok=True)
    (workspace / "paper" / "body" / "paper.md").write_text("draft", encoding="utf-8")
    (workspace / "paper" / "templates").mkdir(parents=True, exist_ok=True)
    (workspace / "paper" / "templates" / "keep.cls").write_text("template", encoding="utf-8")
    (workspace / "src" / "datasets").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "datasets" / "keep.csv").write_text("dataset", encoding="utf-8")
    (workspace / "src" / "tools").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "tools" / "keep.txt").write_text("tool", encoding="utf-8")
    (workspace / "src" / "code").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "code" / "temp.py").write_text("print('x')", encoding="utf-8")
    (workspace / "memory.sqlite3").write_text("keep-db", encoding="utf-8")

    prepare_workspace_for_new_paper(workspace)

    assert "Cleared when a new paper starts" in (workspace / "doc_memo.md").read_text(encoding="utf-8")
    assert "Cleared when a new paper starts" in (workspace / "article_memo.md").read_text(encoding="utf-8")
    assert "## Log entries" in (workspace / "shared" / "research_log.md").read_text(encoding="utf-8")
    assert "## Log entries" in (workspace / "shared" / "code_log.md").read_text(encoding="utf-8")
    assert not (workspace / "paper" / "body" / "paper.md").exists()
    assert (workspace / "paper" / "templates" / "keep.cls").exists()
    assert (workspace / "src" / "datasets" / "keep.csv").exists()
    assert (workspace / "src" / "tools" / "keep.txt").exists()
    assert not (workspace / "src" / "code" / "temp.py").exists()
    assert (workspace / "memory.sqlite3").read_text(encoding="utf-8") == "keep-db"


def test_hard_reset_workspace_rebuilds_clean_runtime_tree(tmp_path: Path) -> None:
    workspace = bootstrap_workspace(tmp_path / "workspace", force=True)
    (workspace / "archived" / "old-run").mkdir(parents=True, exist_ok=True)
    (workspace / "memory.sqlite3").write_text("old-db", encoding="utf-8")
    (workspace / "paper" / "body").mkdir(parents=True, exist_ok=True)
    (workspace / "paper" / "body" / "paper.md").write_text("draft", encoding="utf-8")

    hard_reset_workspace(workspace)

    assert (workspace / "doc_memo.md").exists()
    assert (workspace / "article_memo.md").exists()
    assert (workspace / "shared" / "research_guide.md").exists()
    assert (workspace / "shared" / "code_guide.md").exists()
    assert (workspace / "archived" / "README.md").exists()
    assert not (workspace / "archived" / "old-run").exists()
    assert not (workspace / "memory.sqlite3").exists()
    assert not (workspace / "paper" / "body" / "paper.md").exists()