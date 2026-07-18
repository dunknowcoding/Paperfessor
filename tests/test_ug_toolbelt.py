"""Tests for the UG toolbelt: scope guard, organization, permissions."""

from __future__ import annotations

from pathlib import Path

import pytest

from paperfessor.agents.undergrad import Undergraduate
from paperfessor.config import load_settings


def _ug(tmp_path: Path, **overrides) -> Undergraduate:
    settings = load_settings()
    for k, v in overrides.items():
        setattr(settings, k, v)
    return Undergraduate(settings, object(), tmp_path)  # router unused here


def test_src_path_refuses_escape(tmp_path: Path):
    ug = _ug(tmp_path)
    with pytest.raises(PermissionError):
        ug._src_path("../../etc/passwd")
    with pytest.raises(PermissionError):
        ug._src_path("..\\..\\outside.txt")


def test_save_script_routes_by_lifetime(tmp_path: Path):
    ug = _ug(tmp_path)
    final = ug.save_script("train.py", "print('x')\n")
    scratch = ug.save_script("probe.py", "pass\n", temporary=True)
    assert final == tmp_path / "src" / "code" / "train.py"
    assert scratch == tmp_path / "src" / "tmp" / "probe.py"
    assert ug.read_own_code("code/train.py") == "print('x')\n"


def test_permission_gates(tmp_path: Path):
    ug = _ug(tmp_path, ug_allow_local_tools=False, ug_allow_installs=False)
    with pytest.raises(PermissionError):
        ug.run_tool(["python", "--version"])
    with pytest.raises(PermissionError):
        ug.pip_install(["numpy"])


def test_make_zip_bundles_results(tmp_path: Path):
    ug = _ug(tmp_path)
    ug.save_script("a.py", "1\n")
    out = ug.make_zip(["code/a.py"], "bundle.zip")
    assert out.is_file() and out.parent == tmp_path / "src" / "results"
