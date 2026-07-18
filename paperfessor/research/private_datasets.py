"""Private (user-supplied) datasets and gated public-dataset access.

Two concerns live here:

1. **Private datasets** — OFF by default. When the user enables them
   (``allow_private_datasets``) and points ``private_datasets_dir`` at
   a folder, each SUBFOLDER is treated as one dataset. The UG may
   search these and use the ones that fit the research direction; the
   PhD's ``must_use_datasets`` list is treated as high priority. Nothing
   here ever leaves the machine — private data is read locally and its
   name/paths never enter the paper (the appendix redactor and privacy
   scan still apply).

2. **Gated public datasets** — some public datasets need a license
   click or a login and cannot be fetched unattended. Rather than fail
   or fake data, we record a clear, actionable NEEDS_ACTION note so the
   user can satisfy the requirement and re-run.

A private dataset folder is recognized if it contains EITHER:
  - ``train_x.npy`` + ``test_x.npy`` (+ optional ``test_y.npy``), or
  - a single ``*.csv`` / ``*.npy`` table (auto-split, last 30% test).
The materialized split lands in the standard
``workspace/src/datasets/<name>@<hash>/`` layout so the experiment
runner consumes it exactly like a public dataset.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip("-_") or "private"


def list_private(private_dir: str | Path) -> list[str]:
    """Names of recognizable private datasets under ``private_dir``."""
    root = Path(private_dir) if private_dir else None
    if not root or not root.is_dir():
        return []
    out: list[str] = []
    for sub in sorted(root.iterdir()):
        if sub.is_dir() and _recognize(sub):
            out.append(sub.name)
    return out


def _recognize(folder: Path) -> str | None:
    """Return the load-kind for ``folder`` or None if unrecognized."""
    if (folder / "train_x.npy").is_file() and (folder / "test_x.npy").is_file():
        return "split-npy"
    csvs = list(folder.glob("*.csv"))
    npys = list(folder.glob("*.npy"))
    if len(csvs) == 1:
        return "single-csv"
    if len(npys) == 1:
        return "single-npy"
    return None


def prepare_private(name: str, workspace: Path, private_dir: str | Path) -> Path:
    """Materialize a private dataset into the standard split layout.

    Returns the dataset directory (``src/datasets/<name>@<hash>/``).
    Raises ``FileNotFoundError`` / ``ValueError`` on a missing or
    unrecognized folder — never fabricates data.
    """
    import numpy as np

    root = Path(private_dir)
    folder = root / name
    if not folder.is_dir():
        raise FileNotFoundError(f"private dataset folder not found: {folder}")
    kind = _recognize(folder)
    if kind is None:
        raise ValueError(
            f"private dataset {name!r}: no train_x.npy/test_x.npy pair and "
            f"no single .csv/.npy table found"
        )
    # Load into train/test/label arrays.
    if kind == "split-npy":
        train_x = np.load(folder / "train_x.npy")
        test_x = np.load(folder / "test_x.npy")
        test_y = (np.load(folder / "test_y.npy")
                  if (folder / "test_y.npy").is_file()
                  else np.zeros(len(test_x), dtype="int64"))
    else:
        if kind == "single-csv":
            src = next(folder.glob("*.csv"))
            arr = np.genfromtxt(src, delimiter=",", dtype="float32",
                                skip_header=1)
        else:
            src = next(folder.glob("*.npy"))
            arr = np.load(src).astype("float32")
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        arr = np.nan_to_num(arr)
        n_train = max(1, int(0.7 * len(arr)))
        train_x, test_x = arr[:n_train], arr[n_train:]
        test_y = np.zeros(len(test_x), dtype="int64")
    if train_x.ndim == 1:
        train_x = train_x.reshape(-1, 1)
    if test_x.ndim == 1:
        test_x = test_x.reshape(-1, 1)
    n_val = max(1, int(0.1 * len(train_x)))

    # Hash the raw content for a stable cache key.
    h = hashlib.sha256()
    h.update(train_x.tobytes()[:1 << 20])
    h.update(test_x.tobytes()[:1 << 20])
    digest = h.hexdigest()[:12]
    dest = workspace / "src" / "datasets" / f"{_safe_name(name)}@{digest}"
    dest.mkdir(parents=True, exist_ok=True)
    np.save(dest / "train_x.npy", train_x[:-n_val])
    np.save(dest / "val_x.npy", train_x[-n_val:])
    np.save(dest / "test_x.npy", test_x)
    np.save(dest / "test_y.npy", test_y)
    (dest / "manifest.json").write_text(json.dumps({
        "n_train": int(len(train_x) - n_val),
        "n_val": int(n_val),
        "n_test": int(len(test_x)),
        "n_features": int(train_x.shape[1]) if train_x.ndim > 1 else 1,
        "anomaly_ratio_test": float(test_y.mean()) if len(test_y) else 0.0,
        "private": True,
        "synthetic": False,
        "source": "user-private (path withheld from paper)",
    }, indent=2), encoding="utf-8")
    return dest


def record_needs_action(workspace: Path, dataset: str, reason: str,
                        instructions: str) -> Path:
    """Write a clear, actionable note when a gated public dataset needs
    the user (license acceptance, login, manual download)."""
    d = workspace / "src" / "datasets"
    d.mkdir(parents=True, exist_ok=True)
    note = d / "NEEDS_ACTION.md"
    from datetime import datetime
    entry = (
        f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — {dataset}\n"
        f"- **Why**: {reason}\n"
        f"- **What to do**: {instructions}\n"
        f"- After providing it, re-run; the run continues with the "
        f"datasets it can already access.\n"
    )
    with note.open("a", encoding="utf-8") as f:
        if note.stat().st_size == 0:
            f.write("# Datasets needing your action\n")
        f.write(entry)
    return note


__all__ = [
    "list_private",
    "prepare_private",
    "record_needs_action",
]
