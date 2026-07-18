from __future__ import annotations

from pathlib import Path

from paperfessor.runner.pipeline import _assess_run_readiness, _cleanup_python_caches
from paperfessor.workspace import bootstrap_workspace


def test_assess_run_readiness_flags_blocked_survey_and_fallback_code(tmp_path: Path) -> None:
    workspace = bootstrap_workspace(tmp_path / "workspace", force=True)
    (workspace / "shared" / "research_log.md").write_text(
        "## Log entries\n\n## Full-text read: 1 papers extracted, 7 inaccessible\n\n"
        "I can't write a meaningful gap statement from this. The corpus is too thin.",
        encoding="utf-8",
    )
    (workspace / "shared" / "code_log.md").write_text(
        "## Log entries\n\n# Fallback skeleton\nprint('metric=PLACEHOLDER')",
        encoding="utf-8",
    )

    readiness = _assess_run_readiness(workspace, None)
    issues = readiness.issues()

    assert readiness.force_provisional_write is True
    assert any("survey only extracted 1 readable papers" in item for item in issues)
    assert any("survey gap statement was blocked or deferred" in item for item in issues)
    assert any("fallback skeleton" in item for item in issues)
    assert any("placeholder metrics" in item for item in issues)


def test_cleanup_python_caches_removes_repo_caches_but_skips_workspace(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    workspace = root / "workspace"
    outside_cache = root / "src" / "__pycache__"
    inside_cache = workspace / "src" / "__pycache__"
    outside_cache.mkdir(parents=True, exist_ok=True)
    inside_cache.mkdir(parents=True, exist_ok=True)
    (outside_cache / "mod.pyc").write_text("x", encoding="utf-8")
    (inside_cache / "mod.pyc").write_text("x", encoding="utf-8")

    _cleanup_python_caches(root, workspace)

    assert not outside_cache.exists()
    assert inside_cache.exists()