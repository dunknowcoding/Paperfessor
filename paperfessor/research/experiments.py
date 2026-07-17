"""Real experiment runner for the UG agent.

Runs REAL anomaly-detection experiments on REAL downloaded datasets
and returns REAL metrics. Nothing here is allowed to fabricate a
number:

- Datasets come from :mod:`src.research.datasets` (which refuses to
  synthesize benchmark data). A manifest with ``synthetic: true`` is
  rejected outright as defense in depth.
- Baselines are deterministic, well-known detectors implemented with
  numpy / scikit-learn (PCA reconstruction error, IsolationForest,
  kNN distance).
- The proposed method is an LLM-written ``Model`` class that must
  satisfy a tiny contract (``fit(train_x)`` / ``score(test_x)``).
  It is executed in a subprocess with a hard timeout; if it fails,
  the caller decides what to do — this module never substitutes a
  fake number for it.
- Every method is run with ``k`` seeds; metrics are reported as
  mean ± half-width of a 95% confidence interval (Student-t).

Metrics: AUROC and AUPRC are threshold-free. F1 / precision / recall
use the best-F1 threshold sweep, which is the standard protocol in
the time-series anomaly detection literature (stated in the paper).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Student-t two-sided 97.5% quantile for df = k - 1 (k = seeds).
_T975 = {1: float("nan"), 2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}

# Hard cap for one (method, dataset, seed) run of the LLM model.
_MODEL_TIMEOUT_S = 240.0


@dataclasses.dataclass(frozen=True)
class MetricRow:
    """One (dataset, method) result aggregated over seeds."""

    dataset: str
    method: str
    n_seeds: int
    f1_mean: float
    f1_ci: float
    precision_mean: float
    recall_mean: float
    auroc_mean: float
    auroc_ci: float
    auprc_mean: float
    seconds: float
    error: str | None = None


# ---- Metrics (no sklearn needed for these, but sklearn is available) ----


def _best_f1(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float, float]:
    """Best-F1 threshold sweep. Returns (f1, precision, recall)."""
    order = np.argsort(-scores)
    y = labels[order].astype(np.float64)
    tp = np.cumsum(y)
    fp = np.cumsum(1.0 - y)
    pos = float(y.sum())
    if pos == 0:
        return 0.0, 0.0, 0.0
    precision = tp / np.maximum(tp + fp, 1e-12)
    recall = tp / pos
    f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-12)
    i = int(np.argmax(f1))
    return float(f1[i]), float(precision[i]), float(recall[i])


def _auroc_auprc(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    from sklearn.metrics import average_precision_score, roc_auc_score
    if labels.min() == labels.max():
        return float("nan"), float("nan")
    return (
        float(roc_auc_score(labels, scores)),
        float(average_precision_score(labels, scores)),
    )


def _mean_ci(values: list[float]) -> tuple[float, float]:
    arr = np.asarray(values, dtype=np.float64)
    mean = float(arr.mean())
    if len(arr) < 2:
        return mean, 0.0
    sem = float(arr.std(ddof=1) / np.sqrt(len(arr)))
    t = _T975.get(len(arr), 2.0)
    return mean, t * sem


# ---- Baselines (real, deterministic given the seed) ----------------------


def _standardize(train_x: np.ndarray, test_x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = train_x.mean(axis=0, keepdims=True)
    sd = train_x.std(axis=0, keepdims=True) + 1e-8
    return (train_x - mu) / sd, (test_x - mu) / sd


def _score_pca(train_x: np.ndarray, test_x: np.ndarray, seed: int) -> np.ndarray:
    """PCA reconstruction error (classic subspace baseline)."""
    from sklearn.decomposition import PCA
    tr, te = _standardize(train_x, test_x)
    n_comp = max(1, min(tr.shape[1] - 1, int(0.5 * tr.shape[1])) or 1)
    if tr.shape[1] == 1:
        # Univariate: use squared z-score as the "reconstruction error".
        return (te[:, 0] ** 2)
    pca = PCA(n_components=n_comp, random_state=seed)
    pca.fit(tr)
    rec = pca.inverse_transform(pca.transform(te))
    return ((te - rec) ** 2).mean(axis=1)


def _score_iforest(train_x: np.ndarray, test_x: np.ndarray, seed: int) -> np.ndarray:
    from sklearn.ensemble import IsolationForest
    tr, te = _standardize(train_x, test_x)
    clf = IsolationForest(n_estimators=100, random_state=seed, n_jobs=-1)
    clf.fit(tr)
    return -clf.score_samples(te)


def _score_knn(train_x: np.ndarray, test_x: np.ndarray, seed: int) -> np.ndarray:
    """Mean distance to the k nearest train points (k = 5)."""
    from sklearn.neighbors import NearestNeighbors
    tr, te = _standardize(train_x, test_x)
    # Subsample the train set for tractability on long series.
    rng = np.random.default_rng(seed)
    if len(tr) > 5000:
        tr = tr[rng.choice(len(tr), 5000, replace=False)]
    nn = NearestNeighbors(n_neighbors=min(5, len(tr)), n_jobs=-1)
    nn.fit(tr)
    dist, _ = nn.kneighbors(te)
    return dist.mean(axis=1)


BASELINES = {
    "PCA-recon": _score_pca,
    "IsolationForest": _score_iforest,
    "kNN-dist": _score_knn,
}


# ---- LLM model contract ---------------------------------------------------

# The harness executed in a subprocess. It loads the data, runs the
# LLM-written Model, and writes the scores to an .npy file. Any
# exception surfaces on stderr and via the exit code.
_HARNESS = r"""
import inspect
import sys
import numpy as np

model_path, train_p, test_p, out_p, seed = sys.argv[1:6]
np.random.seed(int(seed))

ns = {"np": np, "numpy": np, "__name__": "ug_model"}
code = open(model_path, encoding="utf-8").read()
exec(compile(code, model_path, "exec"), ns)
Model = ns.get("Model")
if Model is None:
    raise SystemExit("contract violation: no `Model` class defined")


def _accepts_seed(cls):
    try:
        return "seed" in inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return False


train_x = np.load(train_p).astype("float64")
test_x = np.load(test_p).astype("float64")
if train_x.ndim == 1:
    train_x = train_x.reshape(-1, 1)
if test_x.ndim == 1:
    test_x = test_x.reshape(-1, 1)

m = Model(seed=int(seed)) if _accepts_seed(Model) else Model()
m.fit(train_x)
scores = np.asarray(m.score(test_x), dtype="float64").reshape(-1)
if scores.shape[0] != test_x.shape[0]:
    raise SystemExit(
        "contract violation: score() returned %d values for %d test rows"
        % (scores.shape[0], test_x.shape[0])
    )
if not np.isfinite(scores).all():
    raise SystemExit("contract violation: score() returned non-finite values")
np.save(out_p, scores)
"""


def gpu_available() -> bool:
    """True when PyTorch with a working CUDA device is importable.

    The UG uses this to decide whether the proposed model may use
    GPU acceleration. Baselines stay on CPU (scikit-learn); this is
    fair because the comparison is on detection QUALITY, not
    runtime — and the paper's Protocol section must state each
    method's hardware honestly.
    """
    try:
        import torch  # type: ignore
        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        return False


class ModelRunError(RuntimeError):
    """The LLM-written model failed to run; the message carries the
    subprocess stderr so the UG can feed it back for a fix."""


def run_llm_model(
    model_path: Path, train_x_path: Path, test_x_path: Path, seed: int,
    *, timeout: float = _MODEL_TIMEOUT_S,
) -> np.ndarray:
    """Execute the LLM-written model in a subprocess; return scores."""
    with tempfile.TemporaryDirectory() as td:
        harness = Path(td) / "harness.py"
        harness.write_text(_HARNESS, encoding="utf-8")
        out_p = Path(td) / "scores.npy"
        proc = subprocess.run(
            [sys.executable, str(harness), str(model_path),
             str(train_x_path), str(test_x_path), str(out_p), str(seed)],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0 or not out_p.is_file():
            tail = (proc.stderr or proc.stdout or "").strip()[-2000:]
            raise ModelRunError(tail or f"exit code {proc.returncode}")
        return np.load(out_p)


# ---- Experiment orchestration --------------------------------------------


def _load_split(dataset_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("synthetic"):
        raise ValueError(f"{dataset_dir.name}: synthetic data is banned from experiments")
    train_x = np.load(dataset_dir / "train_x.npy")
    test_x = np.load(dataset_dir / "test_x.npy")
    test_y = np.load(dataset_dir / "test_y.npy")
    if train_x.ndim == 1:
        train_x = train_x.reshape(-1, 1)
    if test_x.ndim == 1:
        test_x = test_x.reshape(-1, 1)
    return train_x.astype("float64"), test_x.astype("float64"), test_y.astype("int64"), manifest


def run_experiments(
    workspace: Path,
    dataset_names: list[str],
    *,
    proposed_model_path: Path | None = None,
    proposed_name: str = "Proposed",
    seeds: tuple[int, ...] = (0, 1, 2),
    max_train_rows: int = 20000,
) -> tuple[list[MetricRow], dict[str, dict]]:
    """Run all baselines (+ the proposed model if given) on each dataset.

    Returns (rows, manifests). Rows for the proposed model carry an
    ``error`` when the model failed; the numbers of failed runs are
    NaN and must not appear in the paper as results.
    """
    from paperfessor.research import datasets as ds

    rows: list[MetricRow] = []
    manifests: dict[str, dict] = {}
    for name in dataset_names:
        info = ds.fetch(name, workspace)
        dataset_dir = info.path
        train_x, test_x, test_y, manifest = _load_split(dataset_dir)
        manifests[name] = manifest
        # Cap the train size so a full sweep stays CPU-friendly.
        if len(train_x) > max_train_rows:
            step = len(train_x) // max_train_rows + 1
            train_x_cap = train_x[::step]
        else:
            train_x_cap = train_x

        methods: list[tuple[str, object]] = list(BASELINES.items())
        for method_name, fn in methods:
            f1s, precs, recs, rocs, prcs = [], [], [], [], []
            t0 = time.time()
            err = None
            for seed in seeds:
                try:
                    scores = fn(train_x_cap, test_x, seed)
                except Exception as exc:  # noqa: BLE001
                    err = f"{type(exc).__name__}: {exc}"
                    break
                f1, p, r = _best_f1(scores, test_y)
                roc, prc = _auroc_auprc(scores, test_y)
                f1s.append(f1); precs.append(p); recs.append(r)
                rocs.append(roc); prcs.append(prc)
            rows.append(_aggregate(name, method_name, f1s, precs, recs,
                                   rocs, prcs, time.time() - t0, err))

        if proposed_model_path is not None:
            f1s, precs, recs, rocs, prcs = [], [], [], [], []
            t0 = time.time()
            err = None
            # The subprocess loads from disk: write the capped train
            # once per dataset.
            capped_train = dataset_dir / "train_x_capped.npy"
            np.save(capped_train, train_x_cap)
            for seed in seeds:
                try:
                    scores = run_llm_model(
                        proposed_model_path, capped_train,
                        dataset_dir / "test_x.npy", seed,
                    )
                except (ModelRunError, subprocess.TimeoutExpired) as exc:
                    err = str(exc)[:2000]
                    break
                f1, p, r = _best_f1(scores, test_y)
                roc, prc = _auroc_auprc(scores, test_y)
                f1s.append(f1); precs.append(p); recs.append(r)
                rocs.append(roc); prcs.append(prc)
            rows.append(_aggregate(name, proposed_name, f1s, precs, recs,
                                   rocs, prcs, time.time() - t0, err))
    return rows, manifests


def _aggregate(
    dataset: str, method: str,
    f1s: list[float], precs: list[float], recs: list[float],
    rocs: list[float], prcs: list[float], seconds: float,
    err: str | None,
) -> MetricRow:
    if err or not f1s:
        return MetricRow(
            dataset=dataset, method=method, n_seeds=0,
            f1_mean=float("nan"), f1_ci=float("nan"),
            precision_mean=float("nan"), recall_mean=float("nan"),
            auroc_mean=float("nan"), auroc_ci=float("nan"),
            auprc_mean=float("nan"), seconds=seconds,
            error=err or "no seeds completed",
        )
    f1_m, f1_ci = _mean_ci(f1s)
    roc_m, roc_ci = _mean_ci([r for r in rocs if not np.isnan(r)] or [float("nan")])
    return MetricRow(
        dataset=dataset, method=method, n_seeds=len(f1s),
        f1_mean=f1_m, f1_ci=f1_ci,
        precision_mean=float(np.mean(precs)), recall_mean=float(np.mean(recs)),
        auroc_mean=roc_m, auroc_ci=roc_ci,
        auprc_mean=float(np.nanmean(prcs)), seconds=seconds,
        error=None,
    )


# ---- Rendering ------------------------------------------------------------


def rows_to_markdown(rows: list[MetricRow], *, include_time: bool = False) -> str:
    """Render the results as a Markdown table (real numbers only;
    failed runs show 'failed' so nothing fake enters the paper).

    ``include_time`` adds a wall-clock column for speed-optimization
    topics, where runtime is a first-class metric — every method is
    measured on the same machine, so the comparison is fair."""
    if include_time:
        lines = [
            "| Dataset | Method | F1 | Precision | Recall | AUROC | AUPRC | Time (s) |",
            "|---|---|---|---|---|---|---|---|",
        ]
    else:
        lines = [
            "| Dataset | Method | F1 | Precision | Recall | AUROC | AUPRC |",
            "|---|---|---|---|---|---|---|",
        ]
    # Best F1 per dataset gets bolded (published-paper convention).
    best_f1: dict[str, float] = {}
    for r in rows:
        if not r.error and not np.isnan(r.f1_mean):
            best_f1[r.dataset] = max(best_f1.get(r.dataset, 0.0), r.f1_mean)
    for r in rows:
        if r.error:
            tail = " - |" if include_time else ""
            lines.append(f"| {r.dataset} | {r.method} | failed | - | - | - | - |{tail}")
            continue
        # Consistency contract with the Protocol text: any method run
        # with multiple seeds prints its ± even when it is 0.000 —
        # otherwise the table looks single-seed against the k = 3
        # claim (flagged by the self-inspection reviewer in T14).
        multi = r.n_seeds > 1
        f1 = f"{r.f1_mean:.3f}" + (f" ± {r.f1_ci:.3f}" if multi else "")
        if best_f1.get(r.dataset) == r.f1_mean:
            f1 = f"**{f1}**"
        roc = f"{r.auroc_mean:.3f}" + (f" ± {r.auroc_ci:.3f}" if multi else "")
        time_cell = (
            f" {r.seconds / max(1, r.n_seeds):.2f} |" if include_time else ""
        )
        lines.append(
            f"| {r.dataset} | {r.method} | {f1} | {r.precision_mean:.3f} "
            f"| {r.recall_mean:.3f} | {roc} | {r.auprc_mean:.3f} |{time_cell}"
        )
    return "\n".join(lines)


def save_results(rows: list[MetricRow], manifests: dict[str, dict],
                 out_dir: Path, *, proposed_device: str = "cpu",
                 runtime_metric: bool = False) -> Path:
    """Persist results.json + results.md under ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "rows": [dataclasses.asdict(r) for r in rows],
        "manifests": manifests,
        "protocol": {
            "threshold": "best-F1 sweep (standard TS-AD protocol)",
            "seeds": "k = 3 seeds; mean ± 95% confidence interval (Student-t)",
            "split": "contiguous train/val/test split (no shuffling)",
            # Honest per-method hardware record: baselines always run
            # scikit-learn on CPU; the proposed model may use CUDA.
            "hardware": {
                "baselines": "cpu (numpy/scikit-learn)",
                "proposed": proposed_device,
            },
            # Speed topics: wall-clock is a first-class metric,
            # measured for every method on the same machine.
            "runtime_metric": runtime_metric,
        },
    }
    (out_dir / "results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    (out_dir / "results.md").write_text(
        rows_to_markdown(rows, include_time=runtime_metric) + "\n",
        encoding="utf-8")
    return out_dir / "results.json"


# Identity-keyed, colorblind-safe categorical palette (Okabe-Ito
# subset; adjacency order validated: worst CVD dE 11.4, all checks
# pass). "Ours" always wears the strong blue; baselines keep their
# fixed colors across every figure — color follows the entity.
_METHOD_ORDER_HINT = ("(ours)", "IsolationForest", "PCA-recon", "kNN-dist")
_METHOD_COLORS = {
    "ours": "#0072B2",
    "IsolationForest": "#009E73",
    "PCA-recon": "#E69F00",
    "kNN-dist": "#CC79A7",
}
_INK = "#333333"
_MUTED_INK = "#666666"


def _method_color(method: str) -> str:
    if method.endswith("(ours)"):
        return _METHOD_COLORS["ours"]
    return _METHOD_COLORS.get(method, "#7F7F7F")


def plot_results(rows: list[MetricRow], out_path: Path) -> Path | None:
    """Grouped bar chart of F1 by dataset/method (real numbers).

    Visual design: ours-first fixed method order, identity-keyed
    colorblind-safe colors, recessive dashed y-grid, subtle gray
    error bars, and selective direct labels (values on the "ours"
    bars only) — the full table in the paper is the numeric record.
    """
    ok = [r for r in rows if not r.error]
    if not ok:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    datasets = sorted({r.dataset for r in ok})
    methods_present = {r.method for r in ok}
    # Fixed order: ours first, then the canonical baseline order.
    methods: list[str] = []
    for hint in _METHOD_ORDER_HINT:
        for m in sorted(methods_present):
            if m in methods:
                continue
            if (hint == "(ours)" and m.endswith("(ours)")) or m == hint:
                methods.append(m)
    for m in sorted(methods_present):
        if m not in methods:
            methods.append(m)
    x = np.arange(len(datasets), dtype=float)
    width = 0.8 / max(1, len(methods))
    # FONT CONTRACT: this 7-in design renders at ~6 in (figure*), a
    # 0.86 factor — fonts must be >= 9 pt for >= 7.5 pt effective.
    fig, ax = plt.subplots(figsize=(7.0, 3.2), dpi=200)
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle=(0, (2, 4)), linewidth=0.6, color="#CCCCCC")
    for mi, method in enumerate(methods):
        vals, errs = [], []
        for d in datasets:
            row = next((r for r in ok if r.dataset == d and r.method == method), None)
            vals.append(row.f1_mean if row else 0.0)
            errs.append(row.f1_ci if row else 0.0)
        bars = ax.bar(
            x + mi * width, vals, width=width * 0.9, yerr=errs,
            capsize=2, label=method, color=_method_color(method),
            error_kw={"ecolor": _MUTED_INK, "elinewidth": 0.9},
        )
        # Selective direct labels: values on the "ours" bars only,
        # in ink (text never wears the series color).
        if method.endswith("(ours)"):
            for rect, v in zip(bars, vals):
                ax.annotate(
                    f"{v:.2f}",
                    xy=(rect.get_x() + rect.get_width() / 2, v),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.5, color=_INK,
                )
    ax.set_xticks(x + 0.4 - width / 2)
    ax.set_xticklabels(datasets, fontsize=10, color=_INK)
    ax.set_ylabel("Best F1", fontsize=10, color=_INK)
    ax.tick_params(axis="y", labelsize=9, colors=_MUTED_INK)
    ax.tick_params(axis="x", colors=_INK)
    ax.set_ylim(0, 1)
    # Legend ABOVE the axes so it can never collide with bars or
    # their direct labels (observed: a 0.81 label brushing the box).
    ax.legend(fontsize=9, ncol=min(4, len(methods)), frameon=False,
              loc="lower center", bbox_to_anchor=(0.5, 1.02))
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#AAAAAA")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def plot_qualitative_comparison(
    dataset_dir: Path, out_path: Path,
    *, proposed_model_path: Path | None = None,
    proposed_name: str = "Proposed (ours)",
    max_points: int = 2000, seed: int = 0,
) -> Path | None:
    """Qualitative comparison figure: the raw signal with labeled
    anomaly windows on top, then one panel per method showing its
    REAL anomaly-score curve over the same segment (min-max
    normalized per panel for shape comparison — stated in the
    caption). Every curve is computed by actually running the
    method; nothing is drawn by hand.
    """
    train_x, test_x, test_y, _ = _load_split(dataset_dir)
    if len(train_x) > 20000:
        train_x = train_x[::len(train_x) // 20000 + 1]
    # Anomaly-dense window (same logic as the sample figure).
    n = len(test_x)
    w = min(n, max_points)
    if n > w and test_y.sum() > 0:
        density = np.convolve(test_y.astype(float), np.ones(w), mode="valid")
        start = int(np.argmax(density))
    else:
        start = 0
    sl = slice(start, start + w)
    curves: list[tuple[str, np.ndarray]] = []
    for name, fn in BASELINES.items():
        try:
            curves.append((name, np.asarray(fn(train_x, test_x, seed))[sl]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("qualitative: baseline %s failed: %s", name, exc)
    if proposed_model_path is not None and proposed_model_path.is_file():
        try:
            capped = dataset_dir / "train_x_capped.npy"
            if not capped.is_file():
                np.save(capped, train_x)
            scores = run_llm_model(
                proposed_model_path, capped, dataset_dir / "test_x.npy", seed,
            )
            curves.append((proposed_name, np.asarray(scores)[sl]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("qualitative: proposed model failed: %s", exc)
    if not curves:
        return None
    # Ours on top of the method panels, then canonical baseline order.
    curves.sort(key=lambda c: (not c[0].endswith("(ours)"),
                               _METHOD_ORDER_HINT.index(c[0])
                               if c[0] in _METHOD_ORDER_HINT else 99))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n_panels = 1 + len(curves)
    # Wide aspect so the figure lands in a two-column slot.
    fig, axes = plt.subplots(
        n_panels, 1, figsize=(7.6, max(4.0, 0.85 * n_panels)),
        dpi=200, sharex=True, squeeze=False,
    )
    t = np.arange(start, start + w)
    seg_y = test_y[sl]

    def _shade(ax) -> None:
        in_a, a0 = False, 0
        for i, lab in enumerate(list(seg_y) + [0]):
            if lab and not in_a:
                in_a, a0 = True, i
            elif not lab and in_a:
                in_a = False
                ax.axvspan(t[a0], t[min(i, w - 1)],
                           color="#D55E00", alpha=0.12, lw=0)

    ax0 = axes[0][0]
    ax0.plot(t, test_x[sl, 0], lw=0.7, color=_INK)
    _shade(ax0)
    ax0.set_ylabel("signal\n(ch 0)", fontsize=9, color=_INK)
    ax0.set_title(
        f"{dataset_dir.name.split('@', 1)[0]}: raw signal and per-method "
        f"anomaly scores (shaded = labeled anomaly)",
        fontsize=10, color=_INK,
    )
    for (name, curve), axrow in zip(curves, axes[1:]):
        ax = axrow[0]
        lo, hi = float(np.min(curve)), float(np.max(curve))
        norm = (curve - lo) / (hi - lo) if hi > lo else curve * 0
        ax.plot(t, norm, lw=0.9, color=_method_color(name))
        _shade(ax)
        ax.set_ylabel(name.replace(" (ours)", "\n(ours)"),
                      fontsize=8.5, color=_INK)
        ax.set_ylim(-0.05, 1.1)
    for axrow in axes:
        ax = axrow[0]
        ax.tick_params(labelsize=8, colors=_MUTED_INK)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color("#AAAAAA")
    axes[-1][0].set_xlabel("time index", fontsize=9, color=_INK)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def plot_dataset_sample(dataset_dir: Path, out_path: Path,
                        *, max_points: int = 3000) -> Path | None:
    """Plot a real window of the test series with anomaly regions
    shaded — a genuine raw-data figure for the paper."""
    test_x = np.load(dataset_dir / "test_x.npy")
    test_y = np.load(dataset_dir / "test_y.npy")
    if test_x.ndim == 1:
        test_x = test_x.reshape(-1, 1)
    # Pick the window with the highest anomaly density so the figure
    # actually shows labeled anomalies.
    n = len(test_x)
    w = min(n, max_points)
    if n > w and test_y.sum() > 0:
        density = np.convolve(test_y.astype(float), np.ones(w), mode="valid")
        start = int(np.argmax(density))
    else:
        start = 0
    seg_x = test_x[start:start + w]
    seg_y = test_y[start:start + w]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n_ch = min(3, seg_x.shape[1])
    # 7 in wide with aspect >= 1.8 so the .tex writer promotes the
    # figure to a two-column ``figure*`` slot (readable label sizes).
    fig, axes = plt.subplots(n_ch, 1, figsize=(7.0, min(3.6, 1.0 * n_ch + 0.6)),
                             dpi=200, sharex=True, squeeze=False)
    t = np.arange(start, start + len(seg_x))
    shade_handle = None
    for ci in range(n_ch):
        ax = axes[ci][0]
        ax.plot(t, seg_x[:, ci], lw=0.7, color=_METHOD_COLORS["ours"])
        # Shade labeled anomaly regions (soft, recessive fill).
        in_anom = False
        a0 = 0
        for i, lab in enumerate(list(seg_y) + [0]):
            if lab and not in_anom:
                in_anom, a0 = True, i
            elif not lab and in_anom:
                in_anom = False
                shade_handle = ax.axvspan(
                    t[a0], t[min(i, len(t) - 1)],
                    color="#D55E00", alpha=0.15, lw=0,
                )
        ax.set_ylabel(f"ch {ci}", fontsize=9, color=_INK)
        ax.tick_params(labelsize=8, colors=_MUTED_INK)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color("#AAAAAA")
    if shade_handle is not None:
        axes[0][0].legend(
            [shade_handle], ["labeled anomaly window"],
            fontsize=8.5, frameon=False, loc="upper right",
        )
    axes[-1][0].set_xlabel("time index", fontsize=9, color=_INK)
    # Public dataset name only — the cache-dir name carries an
    # internal content hash that must not appear in the paper.
    public_name = dataset_dir.name.split("@", 1)[0]
    fig.suptitle(f"{public_name}: test segment with labeled anomalies (shaded)",
                 fontsize=10, color=_INK)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


__all__ = [
    "BASELINES",
    "plot_dataset_sample",
    "plot_qualitative_comparison",
    "MetricRow",
    "ModelRunError",
    "plot_results",
    "rows_to_markdown",
    "run_experiments",
    "run_llm_model",
    "save_results",
]
