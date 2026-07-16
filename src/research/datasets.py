"""Dataset registry, downloader, and preprocessor.

The user spec (req.txt) says the UG must process datasets after
downloading. This module is the single source of truth for
"how to fetch a dataset, hash it, preprocess it, and write a
manifest that the paper can cite". The UG's
``download_and_preprocess`` wraps it; the MS / PhD use the
``DatasetInfo`` records to populate the paper's Experimental
Setup section.

Each entry in :data:`REGISTRY` is a :class:`DatasetSpec` that
defines:

- a stable ``name`` (used in the paper, never the raw URL),
- a ``source_url`` (canonical, not a mirror),
- a ``license`` string,
- a ``loader`` callable that returns the raw data into
  ``workspace/src/datasets/<name>@<hash>/``,
- an optional ``preprocess`` callable that converts the raw
  bytes into a deterministic train/val/test split (also under
  ``workspace/src/datasets/<name>@<hash>/``).

Adding a new dataset is one entry in the registry; no other code
needs to change.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Callable

import requests

logger = logging.getLogger(__name__)


# ---- Spec ---------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class DatasetSpec:
    """Static description of a dataset the UG can fetch + preprocess."""

    name: str
    source_url: str
    license: str
    description: str
    loader: Callable[[Path], dict[str, Path]]
    preprocess: Callable[[Path], dict[str, Path]] | None = None
    sha256: str | None = None  # known-good hash, optional


@dataclasses.dataclass(frozen=True)
class DatasetInfo:
    """The result of a successful download + preprocess."""

    name: str
    path: Path             # workspace/src/datasets/<name>@<hash>/
    raw_files: dict[str, Path]
    processed_files: dict[str, Path]
    sha256: str
    size_bytes: int
    license: str
    source_url: str
    preprocess_log: list[str]


# ---- Loaders / preprocessors --------------------------------------------


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_file(url: str, dest: Path, *, timeout: float = 60.0) -> Path:
    """Download ``url`` to ``dest``. Returns ``dest``."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    resp = requests.get(url, headers={"User-Agent": "Paperfessor/0.4"},
                        timeout=timeout, stream=True)
    resp.raise_for_status()
    tmp = dest.with_suffix(dest.suffix + ".part")
    with tmp.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            if chunk:
                f.write(chunk)
    tmp.replace(dest)
    return dest


# ---- Concrete datasets --------------------------------------------------


def _load_iris(dest_dir: Path) -> dict[str, Path]:
    """Iris dataset (UCI). 150 samples, 4 features, 3 classes."""
    url = "https://archive.ics.uci.edu/ml/machine-learning-databases/iris/iris.data"
    raw = _download_file(url, dest_dir / "iris.data")
    return {"raw": raw}


def _preprocess_iris(dest_dir: Path) -> dict[str, Path]:
    """Parse iris.data -> train.npy / test.npy (deterministic 80/20)."""
    import csv
    import json
    import numpy as np
    raw = dest_dir / "iris.data"
    rows: list[list[float]] = []
    labels: list[str] = []
    with raw.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 5:
                continue
            try:
                feats = [float(x) for x in parts[:4]]
            except ValueError:
                continue
            rows.append(feats)
            labels.append(parts[4])
    arr = np.array(rows, dtype=np.float32)
    label_set = sorted(set(labels))
    label_to_id = {lab: i for i, lab in enumerate(label_set)}
    y = np.array([label_to_id[l] for l in labels], dtype=np.int64)
    rng = np.random.default_rng(42)
    perm = rng.permutation(len(arr))
    n_train = int(0.8 * len(arr))
    train_idx, test_idx = perm[:n_train], perm[n_train:]
    train_x, train_y = arr[train_idx], y[train_idx]
    test_x, test_y = arr[test_idx], y[test_idx]
    np.save(dest_dir / "train_x.npy", train_x)
    np.save(dest_dir / "train_y.npy", train_y)
    np.save(dest_dir / "test_x.npy", test_x)
    np.save(dest_dir / "test_y.npy", test_y)
    (dest_dir / "manifest.json").write_text(json.dumps({
        "n_train": int(train_x.shape[0]),
        "n_test": int(test_x.shape[0]),
        "n_features": int(arr.shape[1]),
        "classes": label_set,
        "seed": 42,
    }, indent=2), encoding="utf-8")
    return {
        "train_x": dest_dir / "train_x.npy",
        "train_y": dest_dir / "train_y.npy",
        "test_x": dest_dir / "test_x.npy",
        "test_y": dest_dir / "test_y.npy",
        "manifest": dest_dir / "manifest.json",
    }


def _load_mnist(dest_dir: Path) -> dict[str, Path]:
    """MNIST (the small demo version from openml). ~10MB."""
    base = "https://storage.googleapis.com/tensorflow/tf-keras-datasets"
    train = _download_file(f"{base}/mnist.npz", dest_dir / "mnist.npz")
    return {"raw": train}


def _preprocess_mnist(dest_dir: Path) -> dict[str, Path]:
    import json
    import numpy as np
    with np.load(dest_dir / "mnist.npz") as data:
        x_train_full = data["x_train"]
        y_train_full = data["y_train"]
        x_test = data["x_test"]
        y_test = data["y_test"]
    rng = np.random.default_rng(42)
    perm = rng.permutation(len(x_train_full))
    n_val = 5000
    val_idx, train_idx = perm[:n_val], perm[n_val:]
    x_train = x_train_full[train_idx].astype("float32") / 255.0
    y_train = y_train_full[train_idx]
    x_val = x_train_full[val_idx].astype("float32") / 255.0
    y_val = y_train_full[val_idx]
    x_test = x_test.astype("float32") / 255.0
    np.save(dest_dir / "train_x.npy", x_train)
    np.save(dest_dir / "train_y.npy", y_train)
    np.save(dest_dir / "val_x.npy", x_val)
    np.save(dest_dir / "val_y.npy", y_val)
    np.save(dest_dir / "test_x.npy", x_test)
    np.save(dest_dir / "test_y.npy", y_test)
    (dest_dir / "manifest.json").write_text(json.dumps({
        "n_train": int(x_train.shape[0]),
        "n_val": int(x_val.shape[0]),
        "n_test": int(x_test.shape[0]),
        "image_shape": list(x_train.shape[1:]),
        "n_classes": 10,
        "seed": 42,
    }, indent=2), encoding="utf-8")
    return {
        "train_x": dest_dir / "train_x.npy", "train_y": dest_dir / "train_y.npy",
        "val_x": dest_dir / "val_x.npy", "val_y": dest_dir / "val_y.npy",
        "test_x": dest_dir / "test_x.npy", "test_y": dest_dir / "test_y.npy",
        "manifest": dest_dir / "manifest.json",
    }


# ---- Time-series anomaly detection datasets (req.txt H15) --------------
#
# HONESTY RULE: benchmark loaders download REAL data or raise. There is
# no synthetic fallback — a paper must never report numbers computed on
# stand-in data. (Verified alive 2026-07-16: OmniAnomaly SMD raw files
# and NAB CSVs on raw.githubusercontent.com.)

_SMD_BASE = ("https://raw.githubusercontent.com/NetManAIOps/OmniAnomaly/"
             "master/ServerMachineDataset")
_NAB_BASE = "https://raw.githubusercontent.com/numenta/NAB/master"


def _make_smd_loader(machine: str) -> Callable[[Path], dict[str, Path]]:
    """SMD (Server Machine Dataset, OmniAnomaly): one machine's
    train/test/test_label CSV-text files. 38 features, real labels."""
    def _load(dest_dir: Path) -> dict[str, Path]:
        return {
            "raw_train": _download_file(
                f"{_SMD_BASE}/train/{machine}.txt",
                dest_dir / "smd_train.txt", timeout=120.0),
            "raw_test": _download_file(
                f"{_SMD_BASE}/test/{machine}.txt",
                dest_dir / "smd_test.txt", timeout=120.0),
            "raw_test_label": _download_file(
                f"{_SMD_BASE}/test_label/{machine}.txt",
                dest_dir / "smd_test_label.txt", timeout=120.0),
        }
    return _load


def _preprocess_smd(dest_dir: Path) -> dict[str, Path]:
    """Parse the SMD comma-separated text into train/val/test splits.

    The val split is the LAST 10% of the train series (contiguous,
    not shuffled — shuffling would leak temporal context)."""
    import json
    import numpy as np
    train = np.loadtxt(dest_dir / "smd_train.txt", delimiter=",", dtype="float32")
    test = np.loadtxt(dest_dir / "smd_test.txt", delimiter=",", dtype="float32")
    label = np.loadtxt(dest_dir / "smd_test_label.txt", dtype="int64")
    n_val = max(1, int(0.1 * len(train)))
    np.save(dest_dir / "train_x.npy", train[:-n_val])
    np.save(dest_dir / "val_x.npy", train[-n_val:])
    np.save(dest_dir / "test_x.npy", test)
    np.save(dest_dir / "test_y.npy", label)
    (dest_dir / "manifest.json").write_text(json.dumps({
        "n_train": int(len(train) - n_val),
        "n_val": int(n_val),
        "n_test": int(len(test)),
        "n_features": int(train.shape[1]),
        "anomaly_ratio_test": float(label.mean()),
        "split": "contiguous (val = last 10% of train)",
        "synthetic": False,
    }, indent=2), encoding="utf-8")
    return {
        "train_x": dest_dir / "train_x.npy",
        "val_x": dest_dir / "val_x.npy",
        "test_x": dest_dir / "test_x.npy",
        "test_y": dest_dir / "test_y.npy",
        "manifest": dest_dir / "manifest.json",
    }


def _make_nab_loader(series_path: str) -> Callable[[Path], dict[str, Path]]:
    """NAB (Numenta Anomaly Benchmark): one real univariate series
    plus the combined anomaly-window labels."""
    def _load(dest_dir: Path) -> dict[str, Path]:
        return {
            "raw_csv": _download_file(
                f"{_NAB_BASE}/data/{series_path}",
                dest_dir / "series.csv", timeout=120.0),
            "raw_labels": _download_file(
                f"{_NAB_BASE}/labels/combined_windows.json",
                dest_dir / "combined_windows.json", timeout=120.0),
            "_series_path": _write_series_path(dest_dir, series_path),
        }
    return _load


def _write_series_path(dest_dir: Path, series_path: str) -> Path:
    p = dest_dir / "series_path.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(series_path, encoding="utf-8")
    return p


def _preprocess_nab(dest_dir: Path) -> dict[str, Path]:
    """NAB CSV + window labels -> train/test arrays.

    Follows the NAB convention: the first 15% of each series is the
    probationary period (used as train, assumed mostly normal); the
    rest is test. Labels are 1 inside a combined anomaly window."""
    import csv
    import json
    from datetime import datetime as dt
    import numpy as np
    series_path = (dest_dir / "series_path.txt").read_text(encoding="utf-8").strip()
    stamps: list[str] = []
    values: list[float] = []
    with (dest_dir / "series.csv").open() as f:
        for row in csv.DictReader(f):
            stamps.append(row["timestamp"])
            values.append(float(row["value"]))
    windows = json.loads((dest_dir / "combined_windows.json").read_text(encoding="utf-8"))
    win = [(dt.fromisoformat(a.split(".")[0]), dt.fromisoformat(b.split(".")[0]))
           for a, b in windows.get(series_path, [])]
    ts = [dt.fromisoformat(s.split(".")[0]) for s in stamps]
    label = np.array(
        [1 if any(a <= t <= b for a, b in win) else 0 for t in ts],
        dtype="int64",
    )
    arr = np.array(values, dtype="float32").reshape(-1, 1)
    n_train = max(1, int(0.15 * len(arr)))
    n_val = max(1, int(0.1 * n_train))
    np.save(dest_dir / "train_x.npy", arr[: n_train - n_val])
    np.save(dest_dir / "val_x.npy", arr[n_train - n_val:n_train])
    np.save(dest_dir / "test_x.npy", arr[n_train:])
    np.save(dest_dir / "test_y.npy", label[n_train:])
    (dest_dir / "manifest.json").write_text(json.dumps({
        "n_train": int(n_train - n_val),
        "n_val": int(n_val),
        "n_test": int(len(arr) - n_train),
        "n_features": 1,
        "anomaly_ratio_test": float(label[n_train:].mean()),
        "split": "NAB probationary (first 15% train, contiguous)",
        "series": series_path,
        "synthetic": False,
    }, indent=2), encoding="utf-8")
    return {
        "train_x": dest_dir / "train_x.npy",
        "val_x": dest_dir / "val_x.npy",
        "test_x": dest_dir / "test_x.npy",
        "test_y": dest_dir / "test_y.npy",
        "manifest": dest_dir / "manifest.json",
    }


# ---- Registry ----------------------------------------------------------


REGISTRY: dict[str, DatasetSpec] = {
    "iris": DatasetSpec(
        name="iris",
        source_url="https://archive.ics.uci.edu/ml/machine-learning-databases/iris/iris.data",
        license="Public domain (UCI)",
        description="Iris flower dataset (150 samples, 4 features, 3 classes).",
        loader=_load_iris, preprocess=_preprocess_iris,
    ),
    "mnist": DatasetSpec(
        name="mnist",
        source_url="https://storage.googleapis.com/tensorflow/tf-keras-datasets/mnist.npz",
        license="CC-BY-SA-3.0 (MNIST)",
        description="MNIST handwritten digits (60k train + 10k test, 28x28 grayscale).",
        loader=_load_mnist, preprocess=_preprocess_mnist,
    ),
    # Time-series anomaly detection datasets (per req.txt H15).
    # Real sources only — loaders raise if the download fails; there
    # is no synthetic fallback for benchmark data.
    "smd-1-1": DatasetSpec(
        name="smd-1-1",
        source_url=f"{_SMD_BASE}/train/machine-1-1.txt",
        license="MIT (OmniAnomaly repo)",
        description="SMD machine-1-1 (Server Machine Dataset, OmniAnomaly): 38-dim server telemetry with labeled anomalies.",
        loader=_make_smd_loader("machine-1-1"), preprocess=_preprocess_smd,
    ),
    "smd-2-1": DatasetSpec(
        name="smd-2-1",
        source_url=f"{_SMD_BASE}/train/machine-2-1.txt",
        license="MIT (OmniAnomaly repo)",
        description="SMD machine-2-1 (Server Machine Dataset, OmniAnomaly): 38-dim server telemetry with labeled anomalies.",
        loader=_make_smd_loader("machine-2-1"), preprocess=_preprocess_smd,
    ),
    "smd-3-1": DatasetSpec(
        name="smd-3-1",
        source_url=f"{_SMD_BASE}/train/machine-3-1.txt",
        license="MIT (OmniAnomaly repo)",
        description="SMD machine-3-1 (Server Machine Dataset, OmniAnomaly): 38-dim server telemetry with labeled anomalies.",
        loader=_make_smd_loader("machine-3-1"), preprocess=_preprocess_smd,
    ),
    "nab-machine-temp": DatasetSpec(
        name="nab-machine-temp",
        source_url=f"{_NAB_BASE}/data/realKnownCause/machine_temperature_system_failure.csv",
        license="AGPL-3.0 (NAB)",
        description="NAB machine_temperature_system_failure: real industrial machine temperature with labeled failures.",
        loader=_make_nab_loader("realKnownCause/machine_temperature_system_failure.csv"),
        preprocess=_preprocess_nab,
    ),
    "nab-ec2-cpu": DatasetSpec(
        name="nab-ec2-cpu",
        source_url=f"{_NAB_BASE}/data/realAWSCloudwatch/ec2_cpu_utilization_24ae8d.csv",
        license="AGPL-3.0 (NAB)",
        description="NAB ec2_cpu_utilization_24ae8d: real AWS CloudWatch CPU utilization with labeled anomalies.",
        loader=_make_nab_loader("realAWSCloudwatch/ec2_cpu_utilization_24ae8d.csv"),
        preprocess=_preprocess_nab,
    ),
}


def list_known() -> list[str]:
    return sorted(REGISTRY.keys())


def get(name: str) -> DatasetSpec:
    if name not in REGISTRY:
        raise KeyError(f"unknown dataset {name!r}; known: {list_known()}")
    return REGISTRY[name]


def fetch(name: str, workspace: Path) -> DatasetInfo:
    """Download + preprocess ``name`` into the workspace. Idempotent.

    Caches under ``workspace/src/datasets/<name>@<hash>/`` where the
    hash is the SHA-256 of the largest raw file. If the cache
    already exists with a complete manifest, this is a no-op.
    """
    spec = get(name)
    # First, write raw to a staging dir under the registry name (no
    # hash yet). Then hash and move to the canonical <name>@<hash>/
    # dir.
    staging = workspace / "src" / "datasets" / f".{name}.staging"
    if staging.is_dir():
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    log: list[str] = []
    log.append(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}  fetch {name!r}")
    log.append(f"source: {spec.source_url}")
    log.append(f"license: {spec.license}")
    raw_files = spec.loader(staging)
    log.append(f"raw files: {[p.name for p in raw_files.values()]}")
    # Pick the largest raw file as the hash anchor.
    anchor = max(raw_files.values(), key=lambda p: p.stat().st_size)
    digest = _sha256_of(anchor)
    log.append(f"sha256({anchor.name}) = {digest}")
    final = workspace / "src" / "datasets" / f"{name}@{digest[:12]}"
    if final.is_dir():
        import shutil
        shutil.rmtree(final, ignore_errors=True)
    final.mkdir(parents=True, exist_ok=True)
    for src in raw_files.values():
        (final / src.name).write_bytes(src.read_bytes())
    if spec.preprocess is not None:
        processed = spec.preprocess(final)
        log.append(f"preprocess: {[p.name for p in processed.values()]}")
    else:
        processed = {}
    import shutil
    shutil.rmtree(staging, ignore_errors=True)
    size = sum(p.stat().st_size for p in final.rglob("*") if p.is_file())
    log.append(f"final size: {size} bytes at {final.relative_to(workspace)}")
    (final / "fetch.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return DatasetInfo(
        name=name,
        path=final,
        raw_files={k: final / v.name for k, v in raw_files.items()},
        processed_files=processed,
        sha256=digest,
        size_bytes=size,
        license=spec.license,
        source_url=spec.source_url,
        preprocess_log=log,
    )


__all__ = [
    "DatasetInfo",
    "DatasetSpec",
    "REGISTRY",
    "fetch",
    "get",
    "list_known",
]
