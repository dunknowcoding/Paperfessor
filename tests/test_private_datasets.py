"""Tests for private-dataset access and gating."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from paperfessor.research import private_datasets as pv


def test_list_private_recognizes_split_and_table(tmp_path: Path):
    root = tmp_path / "priv"
    (root / "ds_split").mkdir(parents=True)
    np.save(root / "ds_split" / "train_x.npy", np.zeros((10, 3), "float32"))
    np.save(root / "ds_split" / "test_x.npy", np.zeros((5, 3), "float32"))
    (root / "ds_csv").mkdir()
    (root / "ds_csv" / "data.csv").write_text(
        "a,b\n1,2\n3,4\n5,6\n7,8\n", encoding="utf-8")
    (root / "ignored").mkdir()  # empty → not recognized
    assert set(pv.list_private(root)) == {"ds_split", "ds_csv"}
    assert pv.list_private("") == []


def test_prepare_private_split_materializes_standard_layout(tmp_path: Path):
    root = tmp_path / "priv"
    (root / "mine").mkdir(parents=True)
    np.save(root / "mine" / "train_x.npy", np.random.rand(100, 4).astype("float32"))
    np.save(root / "mine" / "test_x.npy", np.random.rand(40, 4).astype("float32"))
    np.save(root / "mine" / "test_y.npy",
            (np.random.rand(40) > 0.8).astype("int64"))
    ws = tmp_path / "ws"
    dest = pv.prepare_private("mine", ws, root)
    import json
    m = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert m["private"] is True and m["synthetic"] is False
    assert m["n_features"] == 4 and m["n_test"] == 40
    for f in ("train_x.npy", "val_x.npy", "test_x.npy", "test_y.npy"):
        assert (dest / f).is_file()


def test_prepare_private_rejects_unrecognized(tmp_path: Path):
    root = tmp_path / "priv"
    (root / "bad").mkdir(parents=True)
    (root / "bad" / "readme.txt").write_text("nothing", encoding="utf-8")
    ws = tmp_path / "ws"
    import pytest
    with pytest.raises(ValueError):
        pv.prepare_private("bad", ws, root)


def test_needs_action_note(tmp_path: Path):
    note = pv.record_needs_action(
        tmp_path, "imagenet", "requires login", "sign in and download")
    txt = note.read_text(encoding="utf-8")
    assert "imagenet" in txt and "requires login" in txt


def test_selection_respects_gating():
    from paperfessor.config import load_settings
    from paperfessor.runner.pipeline import _select_experiment_datasets
    s = load_settings()
    s.allow_private_datasets = False
    names, private = _select_experiment_datasets(
        "anomaly detection in time series", s, Path("."))
    # Public benchmarks only; no private leakage when disabled.
    assert "smd-1-1" in names and private == set()
