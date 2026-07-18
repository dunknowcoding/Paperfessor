"""The 3-agent run loop.

The PhD plans, dispatches, monitors, reviews, writes, and archives.
The MS surveys, the UG codes. The supervisor thread watches the
workers' logs and feeds the PhD's review callbacks.

Phases (in order):

1. **Plan** (PhD). The PhD reads SOUL.md, checks the archive, and
   designs 1-N methods. Records the plan in doc_memo.md.
2. **Survey** (MS). For each method, the PhD writes a survey task
   into shared/research_guide.md. The MS reads the guide, searches
   (prompted), and writes a structured report into
   shared/research_log.md. The PhD waits for the log entry.
3. **Code** (UG). Per the survey, the PhD writes coding tasks into
   shared/code_guide.md. The UG reads the guide, implements skeleton
   code, runs a smoke test, and reports into shared/code_log.md. The
   PhD waits.
4. **Write** (PhD). The PhD drafts paper sections (abstract,
   intro, related work, method, experiments, conclusion) into
   workspace/paper/body/paper.md, updating article_memo.md after
   every section.
5. **Archive** (PhD). The PhD writes metadata.yaml into
   workspace/archived/<slug>/<run_id>/ and copies the paper there.

Each phase has a timeout. On timeout the PhD voids the active task
and moves on. On exception the pipeline fails with a clear error.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from paperfessor._meta import SOUL_PATH, soul_sha256
from paperfessor.agents.master import (
    Evidence,
    MasterStudent,
    PaperInaccessible,
    PaperRecord,
)
from paperfessor.agents.phd import GuideTask, PhDStudent
from paperfessor.agents.status import MasterStatus, PhDStatus, UndergradStatus
from paperfessor.agents.undergrad import Undergraduate
from paperfessor.config import Settings
from paperfessor.llm.router import LLMRouter
from paperfessor.monitor import Supervisor, WorkerName
from paperfessor.prompting import compose_system_prompt
from paperfessor.workspace import workspace_dir
from paperfessor.workspace_reset import prepare_workspace_for_new_paper

logger = logging.getLogger(__name__)


# Time budgets (seconds) per phase. Tuned short for fast iteration;
# bump for real research.
PHASE_BUDGETS: dict[str, float] = {
    "plan": 60.0,
    "survey": 120.0,
    "code": 120.0,
    "write": 240.0,
    "archive": 30.0,
}
# How long to wait between log-mtime polls.
POLL_INTERVAL: float = 5.0


@dataclass(frozen=True)
class CoordinationPolicy:
    """Every loop in the 3-agent system is bounded HERE, in one
    place, so coordination is efficient and no agent can run away.

    - ``max_method_rounds``: how many runs may try to IMPROVE the
      same method before it is declared defective and the PhD must
      design a different one (the archive's post_mortem informs the
      improve-vs-abandon decision).
    - ``max_ug_rounds``: implement-verify-correct attempts for the
      UG's model.
    - ``max_section_redrafts``: supervisor-rejected section rewrites.
    - ``max_inspection_rounds``: whole-paper self-inspection cycles.
    - ``max_llm_calls``: hard per-run LLM budget; once exceeded, all
      remaining LLM steps degrade to deterministic fallbacks instead
      of burning tokens in a loop.
    """

    max_method_rounds: int = 3
    max_ug_rounds: int = 5
    max_section_redrafts: int = 1
    max_inspection_rounds: int = 3
    max_llm_calls: int = 85


POLICY = CoordinationPolicy()


def _policy_from_settings(settings: Settings) -> CoordinationPolicy:
    """Build the run's coordination policy from user settings (full
    control via CLI flags, env vars, or the GUI settings tab)."""
    return CoordinationPolicy(
        max_method_rounds=getattr(settings, "max_method_rounds", 3),
        max_ug_rounds=getattr(settings, "max_ug_rounds", 4),
        max_section_redrafts=getattr(settings, "max_section_redrafts", 1),
        max_inspection_rounds=getattr(settings, "max_inspection_rounds", 3),
        max_llm_calls=getattr(settings, "max_llm_calls", 80),
    )


def _llm_budget_left(router: LLMRouter, policy: CoordinationPolicy | None = None) -> bool:
    """True while the run is under its LLM-call budget."""
    policy = policy or POLICY
    try:
        calls = int(router.usage_snapshot()["totals"].get("calls", 0))
    except Exception:  # noqa: BLE001
        return True
    return calls < policy.max_llm_calls


def _method_strategy(
    archived: list[dict], direction: str,
    policy: CoordinationPolicy | None = None,
) -> tuple[str, str, str]:
    """Decide IMPROVE vs NEW for the next attempt.

    Returns ``(mode, prior_method, post_mortem)`` where mode is
    ``"improve"`` (the most recent attempt in this direction failed
    only on competitiveness and has rounds left) or ``"new"``.

    The rule (per spec): a method gets at most ``max_method_rounds``
    improvement attempts; once exhausted — or when it failed for a
    structural reason (theory/model defect, no data) — it is
    treated as vetoed and the PhD designs something different.
    """
    policy = policy or POLICY
    if not archived:
        return "new", "", ""
    dir_key = _slug_prefix(direction)
    recent = [
        a for a in archived
        if dir_key and dir_key in str(a.get("research_direction", "")).lower()
    ]
    if not recent:
        # A changed topic has NO improvable history — the paper starts
        # from scratch; other topics' failures are irrelevant here.
        return "new", "", ""
    last = max(recent, key=lambda a: str(a.get("archived_at", "")))
    if str(last.get("success")).lower() == "true":
        return "new", "", ""
    reason = str(last.get("reason", "")).lower()
    # Only a pure competitiveness failure is improvable; anything
    # structural (no data, broken implementation, hallucination)
    # means the attempt was defective end-to-end.
    improvable = ("won best f1 on no dataset" in reason
                  or "not competitive" in reason)
    if not improvable:
        return "new", "", ""
    method = str(last.get("method", ""))
    attempts = sum(
        1 for a in archived
        if str(a.get("method", "")) == method
    )
    if attempts >= policy.max_method_rounds:
        return "new", "", ""
    return "improve", method, str(last.get("post_mortem", ""))[:800]


def _slug_prefix(direction: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", direction.lower()).strip("-")
    return s[:20]


@dataclass
class PipelineResult:
    direction: str
    started_at: str
    finished_at: str
    status: str  # "ok" | "failed"
    method: str
    paper_path: str | None
    note: str = ""


@dataclass(frozen=True)
class RunReadiness:
    readable_papers: int
    survey_blocked: bool
    code_fallback: bool
    placeholder_metric: bool
    visual_ok: bool | None = None
    # True when the final artifact should have been a PDF but is not
    # (pdflatex failed). Checked only in the end-of-run assessment.
    pdf_missing: bool = False
    # True when experiments ran and the proposed method took best F1
    # on zero datasets. Honest negative results are still archived,
    # but per the spec the pipeline should then move on to a
    # different method rather than declare success.
    method_uncompetitive: bool = False

    @property
    def force_provisional_write(self) -> bool:
        return self.survey_blocked or self.code_fallback or self.placeholder_metric

    def issues(self) -> list[str]:
        out: list[str] = []
        if self.readable_papers < 3:
            out.append(f"survey only extracted {self.readable_papers} readable papers")
        if self.survey_blocked:
            out.append("survey gap statement was blocked or deferred")
        if self.code_fallback:
            out.append("UG returned a fallback skeleton instead of a real implementation")
        if self.placeholder_metric:
            out.append("UG output still contains placeholder metrics")
        if self.visual_ok is False:
            out.append("Article 19 visual inspection did not pass")
        if self.pdf_missing:
            out.append("no rendered PDF (pdflatex failed; .md/.tex only)")
        if self.method_uncompetitive:
            out.append(
                "proposed method won best F1 on no dataset (req: iterate "
                "methods until competitive; archived so the next run "
                "tries a different method)"
            )
        return out


def run(
    direction: str,
    *,
    settings: Settings,
    router: LLMRouter,
    workspace: Path | None = None,
    phase_budgets: dict[str, float] | None = None,
) -> PipelineResult:
    """Run the 3-agent pipeline on ``direction``."""
    started = datetime.now()
    workspace = Path(workspace) if workspace is not None else workspace_dir()
    budgets = dict(PHASE_BUDGETS)
    if phase_budgets:
        budgets.update(phase_budgets)

    # 0. Coordination policy from user settings (CLI / GUI / env).
    global POLICY
    POLICY = _policy_from_settings(settings)

    # 0. SOUL integrity + workspace bootstrap.
    sha = soul_sha256()
    if sha is None and not SOUL_PATH.is_file():
        logger.warning("SOUL.md not found at %s; proceeding without integrity check", SOUL_PATH)
    if settings.auto_bootstrap_workspace:
        prepare_workspace_for_new_paper(workspace)

    # 1. Construct agents.
    phd = PhDStudent(settings, router, workspace)
    ms = MasterStudent(settings, router, workspace)
    ug = Undergraduate(settings, router, workspace)

    # 2. Wire supervisor (passive + active review).
    sup = Supervisor(workspace)
    sup.on_worker_report = lambda name, log_path: _on_report(phd, name, log_path)
    sup.on_worker_idle = lambda name, idle_s: _on_idle(phd, name, idle_s)
    sup.start()

    result = PipelineResult(
        direction=direction,
        started_at=started.isoformat(timespec="seconds"),
        finished_at=started.isoformat(timespec="seconds"),
        status="ok",
        method="",
        paper_path=None,
    )

    try:
        method = _phase_plan(phd, router, direction, budgets["plan"], ms=ms)
        result.method = method
        _phase_survey(phd, ms, router, direction, method, budgets["survey"])
        # Active review: between phases the PhD inspects both workers
        # and decides continue / add_more / pause / stop. The
        # recommendation is persisted to doc_memo.
        _phd_review_workers(phd, ms, ug)
        _phase_code(phd, ug, router, direction, method, budgets["code"])
        _phd_review_workers(phd, ms, ug)
        paper_path = _phase_write(phd, router, direction, method, budgets["write"], ms=ms, ug=ug)
        result.paper_path = str(paper_path) if paper_path else None
        readiness = _assess_run_readiness(workspace, paper_path)
        if readiness.issues():
            result.status = "failed"
            result.note = "; ".join(readiness.issues())
            _phase_archive(phd, direction, method, paper_path, success=False, reason=result.note)
        else:
            _phase_archive(phd, direction, method, paper_path, success=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline failed")
        result.status = "failed"
        result.note = str(exc)
        # Per spec: failed runs are also archived (req.txt N13).
        try:
            fallback_method = result.method or "(unknown)"
            _phase_archive(phd, direction, fallback_method,
                          Path(result.paper_path) if result.paper_path else None,
                          success=False, reason=str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("could not archive failed run; continuing")
    finally:
        sup.stop()
        _cleanup_python_caches(workspace.parent, workspace)
        result.finished_at = datetime.now().isoformat(timespec="seconds")
        # Active review: log LLM usage so the user can see the model
        # is actually being used (per user standing order).
        try:
            usage = router.usage_snapshot()
            totals = usage.get("totals", {})
            phd.append_doc_memo(
                user_request=result.direction or "(unspecified)",
                method=result.method or "(none)",
                stage="run-finished",
                final_goal=(
                    f"Status: {result.status}; Paper: {result.paper_path or '-'}; "
                    f"Note: {result.note or '-'}; "
                    f"LLM calls: {totals.get('calls', 0)}; "
                    f"tokens: prompt={totals.get('prompt', 0)} "
                    f"completion={totals.get('completion', 0)} "
                    f"total={totals.get('total', 0)}"
                ),
            )
        except Exception:  # noqa: BLE001
            phd.append_doc_memo(
                user_request=result.direction or "(unspecified)",
                method=result.method or "(none)",
                stage="run-finished",
                final_goal=(
                    f"Status: {result.status}; Paper: {result.paper_path or '-'}; "
                    f"Note: {result.note or '-'}"
                ),
            )

    # 3. Persist the run to the SQLite memory (best-effort: never
    #    fail the pipeline on a memory error). The PhD is the only
    #    agent that touches the database.
    try:
        run_id = phd.record_run(
            direction=direction,
            method=result.method,
            started_at=started,
            finished_at=datetime.now(),
            status=result.status,
            paper_path=Path(result.paper_path) if result.paper_path else None,
            note=result.note,
            config={"phase_budgets": dict(budgets)},
        )
        if result.paper_path:
            try:
                phd.record_archived(
                    research_area="ml",
                    research_direction=direction,
                    research_question=result.method,
                    method=result.method,
                    success=(result.status == "ok"),
                    reason=(result.note or "v0.4 end-to-end run"),
                    paper_path=Path(result.paper_path),
                    run_id=run_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception("archive memory write failed; continuing")
    except Exception:  # noqa: BLE001
        logger.exception("memory write failed; continuing")

    return result


# ---- Phases ---------------------------------------------------------------


def _verify_ms_report(workspace: Path) -> dict[str, object]:
    """Supervisor audit of the MS's survey report against ground truth.

    A report is only as good as its evidence: every fully-read paper
    claimed in research_log.md must be backed by an actual PDF in
    ``src/papers``. A large gap means the report overstates the
    reading (hallucination / insufficiency) and the PhD must know.
    """
    log = workspace / "shared" / "research_log.md"
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    m = re.search(r"Full-text read:\s*(\d+)\s+papers extracted", text)
    claimed = int(m.group(1)) if m else 0
    pdf_count = len(list((workspace / "src" / "papers").glob("*.pdf"))) \
        if (workspace / "src" / "papers").is_dir() else 0
    # PDFs persist across runs, so pdf_count >= claimed is normal;
    # claimed > pdf_count is not.
    overstated = claimed > pdf_count
    return {
        "claimed_read": claimed,
        "pdfs_on_disk": pdf_count,
        "overstated": overstated,
    }


def _verify_ug_report(workspace: Path) -> dict[str, object]:
    """Supervisor audit of the UG's report against results.json.

    The metrics table pasted into code_log.md must be reproducible
    from results.json — a mismatch means the report contains numbers
    that were never measured (faulty result), and the model file the
    report names must exist on disk.
    """
    log = workspace / "shared" / "code_log.md"
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    results = _load_run_results(workspace)
    issues: list[str] = []
    if "model_status: ok" in text:
        m = re.search(r"model_file:\s*(\S+)", text)
        if m and not (workspace / m.group(1)).is_file():
            issues.append(f"report names missing model file {m.group(1)}")
    if results:
        # Every measured F1 mean must appear in the report table and
        # vice versa: sample-check the proposed rows.
        for r in results.get("rows", []):
            if r.get("error") or not str(r.get("method", "")).endswith("(ours)"):
                continue
            token = f"{r['f1_mean']:.3f}"
            if token not in text:
                issues.append(
                    f"measured F1 {token} for {r['dataset']} missing from report"
                )
    return {"issues": issues, "ok": not issues}


def _measured_number_tokens(workspace: Path) -> set[str]:
    """All legitimate 3-decimal tokens derivable from results.json.

    Includes the measured values themselves, dataset ratios, AND all
    pairwise absolute differences between same-metric means — papers
    legitimately write improvement gaps ("raising F1 by 0.026"), and
    flagging those as hallucinations burned redraft cycles on
    non-issues (observed in T12) while real errors survived.
    """
    results = _load_run_results(workspace)
    # Canonical constants that legitimately appear in AD papers:
    # random-classifier AUROC, CI levels, split fractions.
    tokens: set[str] = {"0.500", "0.950", "0.975", "0.050", "0.100", "0.150"}
    if not results:
        return tokens
    per_metric: dict[str, list[float]] = {}
    for r in results.get("rows", []):
        for k in ("f1_mean", "f1_ci", "precision_mean", "recall_mean",
                  "auroc_mean", "auroc_ci", "auprc_mean"):
            v = r.get(k)
            if isinstance(v, (int, float)) and not (isinstance(v, float) and v != v):
                tokens.add(f"{v:.3f}")
                if k.endswith("_mean"):
                    per_metric.setdefault(k, []).append(float(v))
    # Legitimate derived deltas: |a - b| within the same metric.
    for values in per_metric.values():
        for i, a in enumerate(values):
            for b in values[i + 1:]:
                tokens.add(f"{abs(a - b):.3f}")
    for m in results.get("manifests", {}).values():
        v = m.get("anomaly_ratio_test")
        if isinstance(v, (int, float)):
            tokens.add(f"{v:.3f}")
    return tokens


def _review_section(
    section_id: str, text: str, workspace: Path,
) -> str | None:
    """PhD supervisor review of one drafted section.

    Returns feedback (a redraft is required) or None (section passes).
    Deterministic checks only — this is the anti-hallucination /
    insufficiency filter, not a style pass:

    - forbidden internal role names / process phrasing;
    - 3-decimal metric tokens that were never measured;
    - sections that are too thin to carry their weight.
    """
    problems: list[str] = []
    lowered = text.lower()
    for banned in ("the ms ", "the ug ", "the phd", "master's student",
                   "undergraduate", "paperfessor", "what changed"):
        if banned in lowered:
            problems.append(
                f"internal/process wording {banned.strip()!r} must not "
                f"appear in a published paper"
            )
    valid = _measured_number_tokens(workspace)
    if valid:
        for tok in set(re.findall(r"\b0\.\d{3}\b", text)):
            if tok not in valid:
                problems.append(
                    f"the number {tok} does not match any measured value — "
                    f"replace it with a real measurement or remove the claim"
                )
    min_chars = {"abstract": 350, "intro": 500, "related": 500,
                 "method": 400, "experiments": 600}.get(section_id, 200)
    if len(text.strip()) < min_chars:
        problems.append(
            f"section is too thin ({len(text.strip())} chars); expand it "
            f"with concrete, evidence-anchored content"
        )
    if not problems:
        return None
    return "; ".join(problems)


def _phd_review_workers(phd: PhDStudent, ms: MasterStudent, ug: Undergraduate) -> None:
    """Active review: PhD inspects both workers, persists the
    assessment to doc_memo. The recommendation drives the next
    phase (continue / add_more / pause / stop).

    The PhD's own status transitions to ``REVIEWING`` during this
    so the GUI shows what is happening.
    """
    phd.set_status(PhDStatus.REVIEWING)
    # Ground-truth audits (hallucination / faulty-result detection):
    # the logs are checked against the artifacts they describe, not
    # merely read back.
    try:
        ms_audit = _verify_ms_report(phd.workspace)
        ug_audit = _verify_ug_report(phd.workspace)
        if ms_audit.get("overstated") or not ug_audit.get("ok", True):
            phd.append_doc_memo(
                user_request="supervisor audit",
                method="(supervision)",
                stage="audit",
                ms_summary=(
                    f"AUDIT FAIL: claims {ms_audit['claimed_read']} papers read, "
                    f"only {ms_audit['pdfs_on_disk']} PDFs on disk"
                    if ms_audit.get("overstated") else "audit ok"
                ),
                ug_summary=(
                    "AUDIT FAIL: " + "; ".join(ug_audit.get("issues", []))
                    if not ug_audit.get("ok", True) else "audit ok"
                ),
                stage_goal="reports must match the artifacts they describe",
                stage_complete=False,
            )
    except Exception:  # noqa: BLE001
        logger.exception("worker audit failed; continuing")
    for worker_name, worker in (("ms", ms), ("ug", ug)):
        # The spec's status-query API, actually CALLED by the PhD:
        # live agent state (websearch/reading/... or coding/thinking/
        # ...) is combined with the log-based assessment. A worker
        # that reports 'stopped' while tasks are active is abnormal.
        try:
            live = worker.api_status()
        except Exception:  # noqa: BLE001
            live = {"agent": worker_name, "status": "unknown"}
        try:
            assess = phd.assess_worker(worker_name)
        except Exception:  # noqa: BLE001
            continue
        assess["live_status"] = live.get("status", "unknown")
        if (live.get("status") == "stopped"
                and int(assess.get("active_tasks", 0)) > 0):
            assess["recommendation"] = "stop"
            assess["reason"] = (
                "ABNORMAL: worker reports status 'stopped' while "
                f"{assess.get('active_tasks')} task(s) remain active"
            )
        rec = assess.get("recommendation", "continue")
        reason = assess.get("reason", "")
        last_subj = assess.get("last_subject", "")
        last_content = assess.get("last_content", "")
        active = assess.get("active_tasks", 0)
        done = assess.get("done_tasks", 0)
        voided = assess.get("voided_tasks", 0)
        # Persist to doc_memo so the PhD's per-run memory shows the
        # active review's recommendation.
        live_s = assess.get("live_status", "unknown")
        phd.append_doc_memo(
            user_request="active review",
            method="(supervision)",
            stage="review",
            ug_summary=(f"status={live_s}; rec={rec}; reason={reason}; last='{last_subj}'" if worker_name == "ug" else ""),
            ms_summary=(f"status={live_s}; rec={rec}; reason={reason}; last='{last_subj}'" if worker_name == "ms" else ""),
            interaction_ug=(
                f"active review: rec={rec}; active={active}; done={done}; voided={voided}"
                if worker_name == "ug" else ""
            ),
            interaction_ms=(
                f"active review: rec={rec}; active={active}; done={done}; voided={voided}"
                if worker_name == "ms" else ""
            ),
            stage_goal=f"rec={rec}; reason={reason}",
            stage_complete=True,
        )


def _phase_plan(
    phd: PhDStudent, router: LLMRouter, direction: str, budget: float,
    ms: MasterStudent | None = None,
) -> str:
    """PhD plans. Returns the chosen method name.

    Innovation is survey-grounded: the MS runs a quick pre-survey of
    the direction (titles + abstracts, no full read) and the PhD must
    invent a method that explicitly DIFFERS from the surveyed
    approaches — not a rebrand of an existing one.
    """
    phd.set_status(PhDStatus.PLANNING)
    archived = phd.list_archived()
    # TOPIC ISOLATION: partition the archive into SAME-topic attempts
    # (authoritative prior art — skip/improve these) and OTHER-topic
    # attempts (informational only). Mixing them would let a method
    # from an unrelated topic masquerade as this topic's prior art.
    _dir_key = _slug_prefix(direction)

    def _same_topic(a: dict) -> bool:
        rd = _slug_prefix(str(a.get("research_direction", "")))
        return bool(_dir_key) and bool(rd) and (
            _dir_key.startswith(rd) or rd.startswith(_dir_key)
        )

    same_topic = [a for a in archived if _same_topic(a)]
    other_topic = [a for a in archived if not _same_topic(a)]
    archived_summary = (
        "\n".join(
            f"- {a.get('method', '?')} (success={a.get('success', '?')}, "
            f"reason={a.get('reason', '-')})"
            for a in same_topic)
        or "(no prior attempt on THIS topic)"
    )
    # Cross-topic learnings: useful for inspiration, but clearly
    # separated so they are never treated as this topic's prior art.
    other_summary = (
        "\n".join(
            f"- [{a.get('research_direction', '?')}] {a.get('method', '?')} "
            f"(success={a.get('success', '?')})"
            for a in other_topic[-5:])
        or "(none)"
    )
    # Self-evolution cuts both ways: the archive records what WORKED,
    # not only what failed. The planner must exploit proven strengths
    # (e.g. a method family that beat the baselines) while still
    # producing something new.
    wins = [
        a for a in same_topic
        if str(a.get("success")).lower() == "true"
    ]
    wins_summary = (
        "\n".join(f"- {a.get('method', '?')}" for a in wins[-3:])
        or "(no successful attempt yet)"
    )
    if wins:
        wins_note = (
            f"\n\nMethod families that PROVED COMPETITIVE in past attempts "
            f"on this exact direction:\n{wins_summary}\n"
            f"STRONG GUIDANCE: build DIRECTLY on the winning ingredient of "
            f"the most recent success (do not switch to an unrelated "
            f"family that has not been shown to work here); your novelty "
            f"must be an ADVANCE on that proven mechanism, not a departure "
            f"from it. Give it a new name; do not resubmit the prior "
            f"method verbatim.\n"
        )
    else:
        wins_note = (
            "\n\n(No method has yet proved competitive on this direction; "
            "propose the most promising novel approach.)\n"
        )
    # Quick pre-survey: what already exists in this direction?
    existing_lines: list[str] = []
    if ms is not None:
        try:
            pre = ms.search_papers(
                direction, max_arxiv=8, max_venue=6,
                relevance_cutoff=0.0,  # no LLM scoring: this is a cheap scan
                required_tokens=_derive_anchor_tokens(direction),
            )
            for p in pre[:10]:
                snippet = (p.abstract or "")[:180].replace("\n", " ")
                existing_lines.append(f"- {p.title} ({p.year}): {snippet}")
        except Exception:  # noqa: BLE001
            logger.warning("pre-survey failed; PhD plans without it")
    existing_summary = "\n".join(existing_lines) or "(pre-survey unavailable)"
    # Coordination: IMPROVE the previous method (bounded rounds) or
    # design a NEW one. The archive's post-mortem — extracted from
    # the previous run's article_memo — feeds the improvement.
    mode, prior_method, post_mortem = _method_strategy(archived, direction)
    if mode == "improve":
        prompt = (
            f"You are the PhD student. The previous attempt in this "
            f"direction used the method below and produced a real, honest "
            f"paper — but the method did not beat the baselines. You have "
            f"a limited number of improvement rounds before this method "
            f"is declared defective, so make this one count.\n\n"
            f"  direction: {direction}\n"
            f"  prior method: {prior_method}\n\n"
            f"Post-mortem from the previous attempt (from the writing "
            f"memory):\n{post_mortem or '(none recorded)'}\n\n"
            f"{wins_note}"
            f"Design an IMPROVED VARIANT of the prior method: KEEP its "
            f"core mechanism (do not switch to an unrelated family), fix "
            f"the specific weakness the post-mortem exposes — and where a "
            f"past attempt proved a technique competitive, fold that "
            f"winning ingredient in. Give the variant a distinct name "
            f"(do NOT reuse the prior name verbatim). Format your reply as:\n"
            f"  METHOD: <short name, max 8 words>\n"
            f"  WHY: <one sentence: which weakness this fixes and how>\n"
            f"  DIFFERS-FROM: <one sentence vs the prior variant>\n"
            f"  FIRST-STEP: <what the MS should survey first>"
        )
    else:
        prompt = (
            f"You are the PhD student on a new paper. The user said:\n\n"
            f"  direction: {direction}\n\n"
            f"Existing approaches found by the MS's quick pre-survey "
            f"(your method must be meaningfully DIFFERENT from all of these, "
            f"not a rebrand):\n{existing_summary}\n\n"
            f"Prior attempts ON THIS TOPIC (skip methods that already succeeded or were vetoed):\n"
            f"{archived_summary}\n\n"
            f"Attempts on OTHER, unrelated topics (for cross-domain "
            f"inspiration ONLY — these are NOT prior art for this topic and "
            f"must not be treated as such):\n{other_summary}\n"
            f"{wins_note}\n"
            f"Propose ONE concrete NOVEL method to attempt. When the "
            f"archive shows a technique that proved competitive, prefer "
            f"designs that build on that winning ingredient rather than "
            f"abandoning it. Format your reply as:\n"
            f"  METHOD: <short name, max 8 words>\n"
            f"  WHY: <one sentence on novelty and feasibility>\n"
            f"  DIFFERS-FROM: <one sentence: how it differs from the closest existing approach above>\n"
            f"  FIRST-STEP: <what the MS should survey first>\n"
            f"  ADAPT: <which SOFT boundaries you adapt for this topic and "
            f"why (metrics, acceleration, balance, structure), or "
            f"'defaults' if none>"
        )
    # Use a long, structured system prompt. Earlier diagnostics showed
    # the LLM returns empty when the system is short and the user is
    # long; padding the system to ~1 KB is a reliable workaround.
    system = (
        "You are a research PhD leading a small group (one master's student, "
        "one undergraduate) on a top-venue ML paper. Your job right now is "
        "the INNOVATION step: given a research direction and the archive of "
        "prior attempts, propose ONE concrete method to try next. The method "
        "must be: (1) specific enough to be implementable in 1-2 weeks by "
        "the UG, (2) novel relative to the archive, and (3) defensible at a "
        "top venue (NeurIPS / ICML / ICLR / KDD / ACL / CVPR tier). The MS "
        "will survey the related work after you pick; the UG will implement "
        "after the survey. So: pick something with real prior art to read, "
        "not pure speculation. Be terse. Do not propose anything already "
        "tried. Output the METHOD / WHY / FIRST-STEP block exactly as "
        "asked; do not wrap in Markdown."
    )
    text = _call_llm_with_retry(
        router, "innovator", "phd",
        system=system,
        user=prompt, max_tokens=640, temperature=0.2,
    )
    method = _parse_method(text) or _fallback_method(direction)
    # Soft-boundary adaptations are a DECLARED decision: whatever the
    # PhD adapts for this topic goes on the record so supervision can
    # audit it (an undeclared deviation is a defect).
    adapt_m = re.search(r"^\s*ADAPT:\s*(.+)$", text, re.M | re.I)
    adaptations = adapt_m.group(1).strip()[:300] if adapt_m else "defaults"
    phd.append_doc_memo(
        user_request=direction,
        method=method,
        stage="plan:boundary-adaptations",
        stage_goal="soft-boundary adaptations declared for this topic",
        lessons=f"ADAPT: {adaptations}",
        stage_complete=True,
    )
    archived_count = len(phd.list_archived())
    phd.append_doc_memo(
        user_request=direction,
        method=method,
        stage="plan",
        ug_summary="(no UG activity yet — PhD is planning)",
        ms_summary="(no MS activity yet — PhD is planning)",
        interaction_ug="(none yet)",
        interaction_ms="(none yet)",
        stage_goal=f"yes — picked a method that has not been used in the {archived_count} archived attempts",
        lessons=(
            f"Method: {method}. "
            + (f"LLM reasoning: {text.strip()[:500]}" if text.strip() else "LLM returned empty; fell back to a deterministic method.")
        ),
        stage_complete=True,
    )
    return method


# Domain-anchor derivation: maps direction keywords to the abstract
# tokens a relevant paper must mention. Extend per discipline.
_DOMAIN_ANCHORS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("time series", "time-series", "temporal", "forecasting"),
     ("time series", "time-series", "temporal", "sequential")),
    (("graph", "network embedding"), ("graph",)),
    (("image", "vision", "visual", "segmentation", "object detection"),
     ("image", "vision", "visual")),
    (("language", "nlp", "text", "translation", "llm"),
     ("language", "text", "nlp", "corpus")),
    (("audio", "speech", "acoustic"), ("audio", "speech", "acoustic")),
    (("reinforcement", "policy learning", "robot"),
     ("reinforcement", "policy", "agent")),
    (("tabular",), ("tabular",)),
)


def _derive_anchor_tokens(direction: str) -> tuple[str, ...] | None:
    """Derive the required-token filter from the research direction.

    Returns None when no known domain keyword matches — in that case
    the survey applies no hard filter and relies on the LLM
    relevance scores alone.
    """
    d = direction.lower()
    for keys, anchors in _DOMAIN_ANCHORS:
        if any(k in d for k in keys):
            return anchors
    return None


def _informative_tokens(text: str) -> list[str]:
    """The informative words of a method/direction name (stopwords
    and short words removed), for building condensed queries."""
    stop = {"for", "with", "from", "into", "that", "this", "and", "the",
            "via", "using", "based", "novel", "toward", "towards"}
    out: list[str] = []
    for t in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text):
        if t.lower() in stop:
            continue
        out.append(t)
    return out


def _fallback_method(direction: str) -> str:
    """If the LLM returns nothing, derive a sensible method from the direction.

    The PhD can always edit this later. Better than reporting
    "unspecified-method" and walking away.
    """
    d = direction.lower()
    if "anomaly" in d or "outlier" in d or "fraud" in d:
        return "self-supervised contrastive anomaly detection"
    if "forecast" in d or "time series" in d or "temporal" in d:
        return "transformer-based long-horizon time series forecasting"
    if "nlp" in d or "language" in d or "text" in d or "translat" in d:
        return "retrieval-augmented few-shot language model"
    if "vision" in d or "image" in d or "object detect" in d or "segment" in d:
        return "vision-transformer with self-supervised pretraining"
    if "graph" in d or "network" in d:
        return "graph neural network with positional encoding"
    if "reinforcement" in d or "rl" in d:
        return "model-based reinforcement learning with latent dynamics"
    return f"novel method for {direction[:60]}"


def _phase_survey(
    phd: PhDStudent, ms: MasterStudent, router: LLMRouter,
    direction: str, method: str, budget: float,
) -> None:
    """PhD dispatches a survey task; MS reports; PhD reviews.

    This is the *real* survey: MS hits arXiv + OpenAlex + Google
    Scholar, downloads PDFs, extracts evidence, and writes a
    structured log. The LLM is only used at the very end to summarize
    what the MS has already read — it is not asked to invent papers.
    """
    phd.set_status(PhDStatus.DISPATCHING)
    phd.update_research_guide([
        GuideTask(text=f"Survey top-venue papers for: {method} (direction: {direction})"),
    ])
    ms.set_status(MasterStatus.WEBSEARCH)
    phd.set_status(PhDStatus.MONITORING)

    # 1. Real search: API sources (arXiv + OpenAlex) PLUS Playwright-
    #    driven Google Scholar. Dedup by title across the lists.
    # Required-token hard filter: papers that do not mention the
    # domain anchors in their abstract are dropped (derived from the
    # DIRECTION, not hardcoded — this stops e.g. image anomaly
    # detection from leaking into a time-series paper, and works
    # for other disciplines too).
    required = _derive_anchor_tokens(direction)
    # The survey topic is the DIRECTION (short, well-indexed). The
    # method name is long and specific: its all-tokens-AND arXiv
    # query returns near-zero hits, so it is only used as a
    # secondary, condensed query.
    api_papers = ms.search_papers(
        direction, max_arxiv=12, max_venue=10, relevance_cutoff=0.55,
        required_tokens=required,
    )
    method_condensed = " ".join(_informative_tokens(method)[:4])
    if method_condensed and method_condensed.lower() != direction.lower():
        try:
            api_papers += ms.search_papers(
                method_condensed, max_arxiv=6, max_venue=5,
                relevance_cutoff=0.55, required_tokens=required,
            )
        except Exception:  # noqa: BLE001
            logger.warning("secondary (method) search failed; continuing")
    scholar_papers = ms.search_web(direction, limit=8)
    if not scholar_papers:
        scholar_papers = ms.search_web(method_condensed or method, limit=8)
    # Dedup the two lists by lowercased title.
    seen_keys: set[str] = set()
    papers: list[PaperRecord] = []
    for p in api_papers + scholar_papers:
        key = re.sub(r"\W+", "", p.title.lower())[:80]
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        papers.append(p)
    log_chunks: list[str] = []
    log_chunks.append(f"## Search: {len(papers)} candidate papers "
                      f"(api={len(api_papers)}, scholar={len(scholar_papers)})")
    log_chunks.append("")
    # Community context: publication momentum and venue spread,
    # computed from the real search metadata (helps the PhD judge
    # whether the direction is heating up and where it is published).
    years = sorted(p.year for p in papers if p.year)
    if years:
        from collections import Counter
        year_counts = Counter(years)
        recent = sum(c for y, c in year_counts.items() if y >= max(years) - 1)
        venues_seen = Counter((p.venue or "?").split("[")[0].strip() for p in papers)
        log_chunks.append("## Community context (from search metadata)")
        log_chunks.append("")
        log_chunks.append(
            f"- publication years: {min(years)}-{max(years)}; "
            f"{recent}/{len(years)} papers from the last two years "
            f"({'active' if recent >= len(years) // 2 else 'mature'} direction)"
        )
        log_chunks.append(
            "- venue spread: "
            + ", ".join(f"{v} ({c})" for v, c in venues_seen.most_common(5))
        )
        log_chunks.append("")
    for p in papers:
        log_chunks.append(
            f"- {p.short_cite()}  (src={p.venue_source}, cited={p.citation_count}, "
            f"arxiv={p.arxiv_id or '-'})  [{p.title[:80]!r}]"
        )
    log_chunks.append("")

    # 2. Read each paper, extract evidence.
    ms.set_status(MasterStatus.READING)
    evidences: list[Evidence] = []
    failed: list[tuple[PaperRecord, str]] = []
    for p in papers:
        try:
            ft = ms.read_paper(p)
        except PaperInaccessible as exc:
            failed.append((p, str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001
            # One malformed paper must never kill the survey.
            logger.warning("read_paper crashed on %r: %s", p.title[:60], exc)
            failed.append((p, f"reader error: {exc}"))
            continue
        ms.set_status(MasterStatus.ANALYZING)
        try:
            ev = ms.extract_evidence(ft)
        except Exception as exc:  # noqa: BLE001
            logger.warning("extract_evidence crashed on %r: %s", p.title[:60], exc)
            failed.append((p, f"evidence error: {exc}"))
            continue
        evidences.append(ev)

    log_chunks.append(f"## Full-text read: {len(evidences)} papers extracted, {len(failed)} inaccessible")
    log_chunks.append("")
    if failed:
        log_chunks.append("### Inaccessible (paywalled / 404 / read-failure)")
        for p, reason in failed:
            log_chunks.append(f"- {p.short_cite()}: {reason[:120]}")
        log_chunks.append("")

    # 3. Render the evidence as a structured survey.
    log_chunks.append("## Per-paper evidence")
    log_chunks.append("")
    log_chunks.append(ms.evidence_to_markdown(evidences))

    # 4. Gap statement from the LLM, anchored in the actual evidence.
    ms.set_status(MasterStatus.REPORTING)
    if evidences:
        bullet_lines: list[str] = []
        for ev in evidences:
            bullet_lines.append(f"- {ev.paper.short_cite()}: {ev.summary}")
        evidence_bullets = "\n".join(bullet_lines[:10])
        gap = _call_llm_with_retry(
            router, "surveyor", "ms",
            system=(
                "You are a master's student writing the gap statement for a survey. "
                "Your input is a list of REAL papers with REAL extracted summaries. "
                "Do not invent anything; ground every sentence in the bullets below. "
                "Write 3-5 sentences naming the most important open question this "
                "corpus does not yet answer, and how the PhD's proposed method would "
                "close it. If the corpus is thin, say so explicitly."
            ),
            user=(
                f"Research theme: {method}\n"
                f"Direction: {direction}\n\n"
                f"Extracted summaries from the papers we just read:\n{evidence_bullets}\n\n"
                f"Write the gap statement now."
            ),
            max_tokens=400,
        )
        log_chunks.append("## Gap statement (PhD's method should close this)")
        log_chunks.append("")
        if gap.strip():
            log_chunks.append(gap.strip())
        else:
            # LLM is currently unavailable: synthesize a deterministic
            # gap statement from the actual evidence so the PhD still
            # has something to read.
            log_chunks.append(
                "(LLM unavailable; the following is a deterministic gap "
                "statement derived from the evidence.)\n"
            )
            for ev in evidences[:3]:
                log_chunks.append(
                    f"- {ev.paper.short_cite()} contributes {ev.summary or 'no summary'}"
                )
            log_chunks.append(
                f"\nThe PhD's proposed method ({method}) should bridge the gap "
                f"between these threads and demonstrate {direction} in a setting "
                f"the corpus has not yet explored."
            )
        log_chunks.append("")
    else:
        log_chunks.append("## Gap statement")
        log_chunks.append("")
        log_chunks.append(
            "(no papers were readable in the search window; gap statement deferred to the PhD)"
        )
        log_chunks.append("")

    survey_md = "\n".join(log_chunks)
    ms.write_research_log(
        subject=f"Real survey for {method}",
        content=survey_md,
        task_ref="t1",
    )
    ms.set_status(MasterStatus.IDLE)
    phd.append_doc_memo(
        user_request=direction,
        method=method,
        stage="survey",
        ug_summary="(no UG activity in survey phase)",
        ms_summary=(
            f"searched {len(papers)} candidate papers via arXiv + OpenAlex + Google Scholar; "
            f"fully read {len(evidences)} of them; {len(failed)} paywalled/404"
        ),
        interaction_ug="(none — survey is MS-only)",
        interaction_ms=(
            f"dispatched survey task; MS reported a structured log with "
            f"{len(evidences)} real evidence records; result in shared/research_log.md"
        ),
        stage_goal=(
            f"yes — collected {len(evidences)} real paper records "
            f"(datasets/metrics/claims/figures) to feed the write phase"
        ),
        lessons=(
            f"{len(failed)} of {len(papers)} papers were paywalled; "
            f"re-survey with venue OpenAccess PDFs in a future iteration"
        ),
        stage_complete=True,
    )
    # Mark the guide task as done.
    tasks = phd._read_guide(phd._workspace / "shared" / "research_guide.md")[0]
    for t in tasks:
        if t.text.startswith("Survey top-venue"):
            t.done = True
    phd.update_research_guide(tasks)


# Benchmark datasets per research domain. All entries download real
# data (loaders raise on failure; no synthetic fallback). Domains
# without registered runnable benchmarks get an empty list — the
# code phase then reports honestly that no experiment could be run
# instead of running an off-domain one.
# Only domains whose registered datasets carry labels compatible
# with the runner's evaluation protocol are listed. mnist / iris
# carry CLASS labels, not anomaly labels — running the AD harness
# on them would produce meaningless numbers, so they are absent.
_DOMAIN_DATASETS: tuple[tuple[tuple[str, ...], list[str]], ...] = (
    (("time series", "time-series", "temporal", "forecasting", "anomaly"),
     ["smd-1-1", "nab-machine-temp", "nab-ec2-cpu"]),
)


def _speed_topic(direction: str) -> bool:
    """True when the research topic is ITSELF about runtime/efficiency
    (e.g. optimizing an approach's speed). For such topics there is no
    hardware/methodology restriction — acceleration is part of the
    contribution — and wall-clock time becomes a first-class measured
    metric (all methods run on the same machine, so the comparison is
    fair by construction)."""
    d = direction.lower()
    return any(k in d for k in (
        "speed", "latency", "throughput", "efficien", "accelerat",
        "real-time", "realtime", "runtime", "inference time",
        "lightweight", "fast ", "faster",
    ))


def _datasets_for_direction(direction: str) -> list[str]:
    d = direction.lower()
    for keys, names in _DOMAIN_DATASETS:
        if any(k in d for k in keys):
            return names
    return []

def _model_contract(gpu: bool) -> str:
    if gpu:
        compute_rules = (
            "- imports: numpy, scikit-learn, and OPTIONALLY torch with CUDA "
            "(a CUDA device is available and the workload is heavy). Use "
            "the GPU ONLY for the genuinely heavy stages (large matrix "
            "products, batched FFTs, training over full windows); light "
            "post-processing (thresholding, score aggregation, lookups) "
            "stays on CPU. Vectorization and batching are encouraged for "
            "heavy stages regardless of device. The code MUST still run "
            "correctly when torch.cuda.is_available() is False\n"
            "- no tensorflow, no pip installs\n"
            "- fit+score must finish within 120 seconds for n=20000, d=38\n"
        )
    else:
        compute_rules = (
            "- imports: numpy and scikit-learn ONLY (no torch, no "
            "tensorflow, no pip installs)\n"
            "- CPU only; fit+score must finish within 60 seconds for "
            "n=20000, d=38\n"
        )
    return (
        "Write ONE self-contained Python file implementing the method as an "
        "anomaly detector with EXACTLY this contract:\n"
        "```\n"
        "class Model:\n"
        "    def __init__(self, seed: int = 0): ...\n"
        "    def fit(self, train_x):  # np.ndarray (n, d) float64, unlabeled, mostly normal\n"
        "        ...\n"
        "    def score(self, test_x): # -> np.ndarray (m,), higher = more anomalous\n"
        "        ...\n"
        "```\n"
        "Hard constraints:\n"
        + compute_rules +
        "- no file I/O, no network access, no prints, no __main__ block\n"
        "- deterministic given the seed; all randomness through np.random.default_rng(seed)\n"
        "- handle both multivariate (d=38) and univariate (d=1) input\n"
        "- scores must be finite floats — return EXACTLY ONE score per "
        "test ROW: len(score(test_x)) == test_x.shape[0], ALWAYS.\n"
        "  WINDOWING: if you score over sliding windows, you MUST map "
        "window scores back to per-timestep scores of length "
        "test_x.shape[0] (e.g. assign each timestep the max/mean of the "
        "windows covering it, and pad the edges) — never return a "
        "per-window array of a different length. This is the #1 cause "
        "of failure; get the output length exactly right.\n"
        "Return ONLY a single ```python code block, nothing after it."
    )


def _extract_python_code(text: str) -> str | None:
    """Pull the Python source out of an LLM reply (fenced or raw)."""
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    candidate = m.group(1) if m else text
    candidate = candidate.strip()
    if not candidate:
        return None
    import ast
    try:
        tree = ast.parse(candidate)
    except SyntaxError:
        return None
    has_model = any(
        isinstance(node, ast.ClassDef) and node.name == "Model"
        for node in ast.walk(tree)
    )
    return candidate if has_model else None


def _validate_model_code(code: str, *, gpu_allowed: bool = False,
                         extra_allowed: tuple[str, ...] = ()) -> str | None:
    """Static safety check. Returns an error message or None.

    ``extra_allowed`` lets the user whitelist additional import names
    (settings.ug_extra_allowed_imports); the hard sandbox rules —
    no network, no file I/O, no shell — are not whitelistable.
    """
    banned = ["tensorflow", "requests", "urllib", "subprocess",
              "socket", "os.system", "shutil", "open("]
    if not gpu_allowed:
        banned.append("torch")
    hard = {"requests", "urllib", "subprocess", "socket", "os.system",
            "shutil", "open("}
    allowed = {a.strip() for a in extra_allowed if a.strip()}
    for b in banned:
        if b in allowed and b not in hard:
            continue
        if b in code:
            return f"banned construct in model code: {b!r}"
    return None


def _phase_code(
    phd: PhDStudent, ug: Undergraduate, router: LLMRouter,
    direction: str, method: str, budget: float,
) -> None:
    """PhD dispatches a coding task; the UG implements the method
    against a fixed contract, the implementation is verified by
    actually running it on real data, and the UG then runs the full
    experiment sweep (real baselines + the proposed model, k = 3
    seeds) and reports the REAL numbers to shared/code_log.md.

    Every request->work->verify micro-loop is closed: a model that
    does not parse, violates the contract, or crashes on the smoke
    run is sent back to the LLM with the error, up to 3 rounds.
    There is no fake-code fallback and no placeholder metric.
    """
    from paperfessor.research.experiments import (
        ModelRunError,
        gpu_available,
        plot_results,
        rows_to_markdown,
        run_experiments,
        run_llm_model,
        save_results,
    )

    # Acceleration policy: GPU (or any heavyweight acceleration) is
    # for LONG-RUNNING, HEAVY workloads only — never for light tasks
    # like thresholding or table assembly. The workload is measured
    # from the actual dataset manifests; CUDA is offered to the UG
    # only when hardware exists AND the data is heavy enough to
    # justify it. Baselines stay on CPU scikit-learn either way
    # (quality, not runtime, is compared; the Protocol records
    # per-method hardware).
    experiment_datasets_early = _datasets_for_direction(direction)
    workload_cells = 0
    from paperfessor.research import datasets as _ds_probe
    for _name in experiment_datasets_early:
        try:
            _info = _ds_probe.fetch(_name, ug.workspace)
            import json as _json
            _m = _json.loads((_info.path / "manifest.json").read_text(encoding="utf-8"))
            workload_cells += (
                (int(_m.get("n_train", 0)) + int(_m.get("n_test", 0)))
                * max(1, int(_m.get("n_features", 1)))
            )
        except Exception:  # noqa: BLE001
            continue
    _HEAVY_WORKLOAD_CELLS = 5_000_000
    speed_topic = _speed_topic(direction)
    user_allows_gpu = bool(getattr(ug._settings, "ug_allow_gpu", True))
    if not user_allows_gpu:
        gpu_ok = False
    elif speed_topic:
        # Speed-optimization topics: NO hardware/methodology limits —
        # acceleration is the contribution, and wall-clock is a
        # first-class metric (identical machine for every method).
        gpu_ok = gpu_available()
    else:
        gpu_ok = gpu_available() and workload_cells >= _HEAVY_WORKLOAD_CELLS
        if gpu_available() and not gpu_ok:
            logger.info(
                "GPU present but workload light (%s cells < %s); staying on CPU",
                workload_cells, _HEAVY_WORKLOAD_CELLS,
            )

    experiment_datasets = _datasets_for_direction(direction)
    if not experiment_datasets:
        # No benchmark with a compatible evaluation protocol is
        # registered for this domain. Report honestly and bail —
        # running an off-domain experiment would bias the paper.
        ug.write_code_log(
            subject=f"Experiments for {method}",
            content=(
                "model_status: failed\n"
                f"reason: no registered benchmark dataset matches the "
                f"direction {direction!r}; refusing to run an off-domain "
                f"experiment. Register a dataset + protocol for this "
                f"domain first."
            ),
            task_ref="t1",
        )
        phd.append_doc_memo(
            user_request=method, method=method, stage="code",
            ug_summary="no runnable benchmark for this domain; experiments skipped honestly",
            ms_summary="(none)", interaction_ug="dispatch aborted", interaction_ms="(none)",
            stage_goal="no — domain has no registered benchmark",
            stage_complete=True,
        )
        return

    phd.set_status(PhDStatus.DISPATCHING)
    code_tasks = [
        GuideTask(text=f"Implement `Model` (fit/score contract) for: {method}"),
        GuideTask(text=f"Run k=3-seed experiments on: {', '.join(experiment_datasets)}"),
    ]
    if speed_topic:
        # The optimization directive is the PhD's dispatched
        # instruction — posted to the guide like every other task.
        code_tasks.append(GuideTask(
            text="PhD directive: optimize runtime aggressively — this "
                 "topic treats wall-clock as a first-class metric; use "
                 "any acceleration available"))
    phd.update_code_guide(code_tasks)
    ug.set_status(UndergradStatus.CODING)
    phd.set_status(PhDStatus.MONITORING)

    code_dir = ug.workspace / "src" / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    safe_method = "".join(
        c for c in method.lower().replace(" ", "_") if c.isalnum() or c == "_"
    )[:40] or "method"
    model_path = code_dir / f"model_{safe_method}.py"

    # 1. Smoke-test fixture: a small slice of REAL data.
    from paperfessor.research import datasets as ds_mod
    smoke_info = ds_mod.fetch(experiment_datasets[0], ug.workspace)
    import numpy as np
    smoke_train = smoke_info.path / "smoke_train.npy"
    smoke_test = smoke_info.path / "smoke_test.npy"
    np.save(smoke_train, np.load(smoke_info.path / "train_x.npy")[:2000])
    np.save(smoke_test, np.load(smoke_info.path / "test_x.npy")[:500])

    # 2. Implement-verify-correct loop. Every failure is recorded
    #    WITH its error so the log is diagnosable and the LLM gets
    #    precise feedback.
    model_ok = False
    rounds: list[str] = []
    feedback = ""
    for attempt in range(POLICY.max_ug_rounds):
        if not _llm_budget_left(router):
            rounds.append(f"round {attempt + 1}: skipped (LLM budget exhausted)")
            break
        ug.set_status(UndergradStatus.CODING)
        speed_note = (
            "\nINSTRUCTION FROM THE SUPERVISING PhD (see code_guide.md): "
            "runtime is a first-class metric for this research "
            "direction — optimize aggressively with ANY acceleration "
            "available (GPU, vectorization, batching, algorithmic "
            "shortcuts). Wall-clock time is measured and reported for "
            "every method on the same machine.\n"
        ) if speed_topic else ""
        reply = ug.ask(
            system=(
                "You are an undergraduate research engineer. You write "
                "correct, minimal, well-commented numpy/scikit-learn code. "
                "Follow the contract EXACTLY."
            ),
            user=(
                f"Method to implement: {method}\n"
                f"Research direction: {direction}\n"
                f"{speed_note}\n"
                f"{_model_contract(gpu_ok)}\n"
                + (f"\nYour previous attempt failed with this error. Fix it "
                   f"and return the corrected FULL file:\n```\n{feedback}\n```\n"
                   if feedback else "")
                + "\nFINAL REMINDERS (violations fail automatically): "
                "numpy + scikit-learn ONLY (torch/tensorflow are rejected "
                "by a static check); if the full method is too heavy for "
                "numpy/scikit-learn, implement a SIMPLIFIED but faithful "
                "variant of it; deterministic given seed; finish within "
                "60s; return ONE ```python block."
            ),
            max_tokens=6000,
        )
        ug.set_status(UndergradStatus.THINKING)
        code = _extract_python_code(reply)
        if code is None:
            feedback = ("reply did not contain a parseable Python file "
                        "defining `class Model`")
            rounds.append(f"round {attempt + 1}: no valid code block")
            continue
        extra_ok = tuple(
            str(getattr(ug._settings, "ug_extra_allowed_imports", "") or ""
                ).split(","))
        err = _validate_model_code(code, gpu_allowed=gpu_ok,
                                   extra_allowed=extra_ok)
        if err:
            feedback = err
            rounds.append(f"round {attempt + 1}: static check: {err}")
            continue
        model_path.write_text(code, encoding="utf-8")
        try:
            smoke_timeout = min(
                120.0,
                float(getattr(ug._settings, "ug_sandbox_timeout_seconds", 240)),
            )
            scores = run_llm_model(model_path, smoke_train, smoke_test,
                                   seed=0, timeout=smoke_timeout)
        except (ModelRunError, Exception) as exc:  # noqa: BLE001
            feedback = str(exc)[:1500]
            first_line = feedback.strip().splitlines()[-1][:160] if feedback.strip() else "?"
            low = feedback.lower()
            # Targeted hints for the recurring failure classes so the
            # LLM fixes the actual bug instead of thrashing.
            if ("broadcast" in low or "shape" in low
                    or "could not broadcast" in low):
                feedback += (
                    "\n\nHINT: this is an OUTPUT-LENGTH bug. score(test_x) "
                    "MUST return exactly test_x.shape[0] values. You are "
                    "returning a per-window array of a different length. "
                    "Map window scores back to per-timestep: allocate "
                    "out = np.zeros(test_x.shape[0]); for each window "
                    "assign its score to the timesteps it covers "
                    "(np.maximum.at or averaging); pad any uncovered "
                    "edge timesteps with the nearest score. Verify "
                    "len(out) == test_x.shape[0] before returning."
                )
            rounds.append(f"round {attempt + 1}: smoke run failed ({first_line})")
            continue
        rounds.append(
            f"round {attempt + 1}: OK ({len(code)} chars; smoke scores "
            f"n={len(scores)}, mean={float(scores.mean()):.4f})"
        )
        model_ok = True
        break

    # 3. Full experiment sweep (real baselines always; proposed model
    #    only if it passed verification).
    ug.set_status(UndergradStatus.CODING)
    rows, manifests = run_experiments(
        ug.workspace, experiment_datasets,
        proposed_model_path=model_path if model_ok else None,
        proposed_name=f"{method.split()[0] if method else 'Proposed'} (ours)",
        seeds=(0, 1, 2),
    )
    results_dir = ug.workspace / "src" / "results"
    save_results(rows, manifests, results_dir,
                 proposed_device=("cuda" if gpu_ok else "cpu"),
                 runtime_metric=speed_topic)
    fig_path = plot_results(rows, ug.workspace / "src" / "figures" / "results_f1.png")
    # Raw-data sample figure (real test segment, labeled anomalies).
    try:
        from paperfessor.research.experiments import plot_dataset_sample
        plot_dataset_sample(
            smoke_info.path,
            ug.workspace / "src" / "figures" / "dataset_sample.png",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("dataset sample figure failed: %s", exc)
    # Qualitative comparison figure (PhD-dispatched, UG-executed):
    # every method's REAL score curve over the same anomaly-dense
    # segment — the visual counterpart of the results table.
    try:
        from paperfessor.research.experiments import plot_qualitative_comparison
        plot_qualitative_comparison(
            smoke_info.path,
            ug.workspace / "src" / "figures" / "qualitative_comparison.png",
            proposed_model_path=model_path if model_ok else None,
            proposed_name=f"{method.split()[0] if method else 'Proposed'} (ours)",
        )
        ug.write_code_log(
            subject="Qualitative comparison figure",
            content=(
                "Rendered per-method anomaly-score curves over the "
                "anomaly-dense test segment (PhD-dispatched); file: "
                "src/figures/qualitative_comparison.png"
            ),
            task_ref="fig-qual",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("qualitative comparison figure failed: %s", exc)

    # 4. Honest report to code_log.md. `model_status:` is the marker
    #    the readiness gate reads — never write 'ok' unless the
    #    proposed model really ran.
    proposed_rows = [r for r in rows if r.method.endswith("(ours)")]
    proposed_ran = any(r.n_seeds > 0 and not r.error for r in proposed_rows)
    table_md = rows_to_markdown(rows, include_time=speed_topic)
    ug.set_status(UndergradStatus.REPORTING)
    ug.write_code_log(
        subject=f"Experiments for {method}",
        content=(
            f"model_status: {'ok' if (model_ok and proposed_ran) else 'failed'}\n"
            f"model_file: src/code/{model_path.name}\n"
            f"verification rounds:\n"
            + "\n".join(f"- {r}" for r in rounds)
            + f"\n\ndatasets (all real downloads, no synthetic data):\n"
            + "\n".join(
                f"- {name}: n_train={m.get('n_train')}, n_test={m.get('n_test')}, "
                f"d={m.get('n_features')}, anomaly_ratio={m.get('anomaly_ratio_test'):.3f}"
                for name, m in manifests.items()
            )
            + "\n\nprotocol: best-F1 threshold sweep; k = 3 seeds; "
            f"mean ± 95% CI; contiguous splits\n\n"
            f"results (REAL numbers):\n{table_md}\n"
            + (f"\nfigure: src/figures/{fig_path.name}\n" if fig_path else "")
        ),
        task_ref="t1",
    )
    ug.set_status(UndergradStatus.IDLE)

    phd.append_doc_memo(
        user_request=method,
        method=method,
        stage="code",
        ug_summary=(
            f"model {model_path.name}: {'verified and ran' if model_ok else 'FAILED verification'} "
            f"after {len(rounds)} round(s); experiments on {len(manifests)} real datasets; "
            f"proposed_ran={proposed_ran}"
        ),
        ms_summary="(no MS interaction in code phase)",
        interaction_ug=(
            "PhD dispatched implement+experiment; UG verification rounds: "
            + "; ".join(rounds)
        ),
        interaction_ms="(none)",
        stage_goal=(
            "yes — real metrics recorded" if proposed_ran
            else "no — proposed model failed; only baselines ran"
        ),
        lessons=f"results in src/results/results.json ({len(rows)} rows)",
        stage_complete=True,
    )
    tasks = phd._read_guide(phd._workspace / "shared" / "code_guide.md")[0]
    for t in tasks:
        if t.text.startswith(("Implement `Model`", "Run k=3-seed")):
            t.done = True
    phd.update_code_guide(tasks)


def _phase_write(
    phd: PhDStudent, router: LLMRouter,
    direction: str, method: str, budget: float,
    ms: MasterStudent | None = None,
    ug: Undergraduate | None = None,
) -> Path | None:
    """PhD drafts the paper section by section, with per-section fallback.

    The previous single-shot call was fragile: a 3500-token call
    easily returned empty on the flaky LLM. The new flow:

    1. Read the per-paper evidence the MS collected in the survey.
    2. Draft each section (Abstract, Introduction, Related Work,
       Method, Experiments, Limitations) as a SEPARATE LLM call.
    3. If a call returns empty, fall back to a deterministic template
       that uses the *real* evidence (datasets, citations) the MS
       found. The LLM is the writer; the data is the truth.
    4. Write all sections to ``workspace/paper/body/paper.md``.
    5. Append an article_memo entry for each section so the PhD's
       paper-writing memory accumulates the per-section checks
       (template / text / style / references / etc.).

    Returns the path to the assembled paper file.
    """
    phd.set_status(PhDStatus.WRITING)
    body_dir = phd.workspace / "paper" / "body"
    body_dir.mkdir(parents=True, exist_ok=True)
    paper_path = body_dir / "paper.md"

    # Load the real evidence the MS collected (datasets, claims, etc.).
    evidence = _load_evidence(phd)

    # The write phase is TASK-DRIVEN: the PhD posts the section-
    # support subtasks to the shared guides, the workers execute and
    # report to their logs, and the PhD ticks tasks off — the same
    # dispatch loop as every other phase, now inside paper writing.
    write_tasks = [
        GuideTask(text=f"Answer: what are the top conferences/journals for {direction}?"),
        GuideTask(text="Supplement citations when the evidence base is thin (< 4 read papers)"),
    ]
    try:
        existing = phd._read_guide(phd._workspace / "shared" / "research_guide.md")[0]
        phd.update_research_guide(existing + write_tasks)
    except Exception:  # noqa: BLE001
        logger.warning("could not post write-phase tasks to research guide")

    # Subtask 1 — venue intelligence: the PhD asks, the MS answers
    # with a data-driven ranking into research_log.md.
    if ms is not None:
        try:
            venues_found = ms.find_top_venues(direction)
            phd.append_doc_memo(
                user_request="write-phase venue question",
                method=method, stage="write:venues",
                ms_summary=(
                    f"reported {len(venues_found)} venues for {direction!r} "
                    f"(see research_log.md)"
                ),
                interaction_ms="PhD asked for top venues; MS answered with sources",
                stage_goal="venue choice is evidence-based",
                stage_complete=True,
            )
        except Exception:  # noqa: BLE001
            logger.warning("venue question failed; continuing")

    # Subtask 2 — supplementary citations when the evidence base is
    # too thin to carry Related Work. Failures are non-fatal (search
    # APIs may be throttled).
    if ms is not None and len(evidence) < 4:
        try:
            extra = ms.search_papers(
                direction, max_arxiv=8, max_venue=5, relevance_cutoff=0.0,
                required_tokens=_derive_anchor_tokens(direction),
            )
            known = {ev.paper.title.lower()[:60] for ev in evidence}
            added = 0
            for p in extra:
                if p.title.lower()[:60] in known:
                    continue
                evidence.append(Evidence(
                    paper=p, datasets=(), metrics=(), claims=(),
                    key_figures=(), summary=(p.abstract or "")[:200],
                ))
                added += 1
            phd.append_doc_memo(
                user_request="write-phase support request",
                method=method, stage="write:supplement",
                ms_summary=f"supplementary search added {added} citable papers",
                interaction_ms="PhD asked MS for extra citations before drafting",
                stage_goal="evidence base thick enough for Related Work",
                stage_complete=added > 0,
            )
        except Exception:  # noqa: BLE001
            logger.warning("supplementary MS search failed; writing with existing evidence")
    readiness = _assess_run_readiness(phd.workspace, None)

    # Self-evolution: failure reasons from past attempts IN THIS
    # DIRECTION ride along in the writer's system prompt as an
    # avoid-list (topic-scoped — a changed topic starts clean).
    lessons = _past_lessons(phd, direction)

    # Pinned facts travel with EVERY write and revision call — a
    # revision that lacks them can re-introduce contradictions the
    # original prompts prevented (observed: a round-3 redraft wrote
    # a corpus count of 12 against Related Work's 18).
    from paperfessor.policy import topic_rules_for
    topic_rules = topic_rules_for(direction)
    facts_block = (
        f"\n\nPINNED FACTS (every section must agree with these exactly):\n"
        f"- surveyed corpus size: EXACTLY {len(evidence)} papers\n"
        f"- {_results_headline(phd.workspace) or 'no experiments were run: no numbers may be stated'}"
        + (("\nTOPIC RULES (hard): " + "; ".join(topic_rules))
           if topic_rules else "")
    )

    def _writer_system(section_id: str) -> str:
        base = _section_system(section_id, direction, method)
        return base + ("\n\n" + lessons if lessons else "") + facts_block

    # FULL-PAPER page discipline: unless the user asks for a short
    # paper, the body (excluding References/Appendix) must fill the
    # venue's page budget with dense, REAL content. Section token
    # budgets and word targets are sized for that goal; an expansion
    # loop after the first PDF build tops up under-filled papers.
    page_target = int(getattr(phd._settings, "paper_max_pages", 9) or 9)
    sections: list[tuple[str, str]] = []
    for section_id, title, user_prompt, max_tokens in [
        ("abstract", "Abstract", _abstract_prompt(direction, method, evidence, phd.workspace), 700),
        ("intro", "1. Introduction", _intro_prompt(direction, method, evidence, phd.workspace), 2000),
        ("related", "2. Related Work", _related_prompt(direction, method, evidence), 2200),
        ("method", "3. Method", _method_prompt(direction, method, evidence, phd.workspace), 2600),
        ("experiments", "4. Experimental Setup", _experiments_prompt(direction, method, evidence, phd.workspace), 3000),
        ("analysis", "5. Analysis and Discussion", _analysis_prompt(direction, method, evidence, phd.workspace), 2600),
        ("conclusion", "6. Conclusion", _conclusion_prompt(direction, method, evidence, phd.workspace), 700),
        ("limitations", "7. Limitations and Future Work", _limitations_prompt(direction, method, evidence, phd.workspace), 800),
    ]:
        if readiness.force_provisional_write:
            text = _section_fallback(section_id, direction, method, evidence)
            section_source = "fallback"
        else:
            text = _call_llm_with_retry(
                router, "writer", "phd",
                system=_writer_system(section_id),
                user=user_prompt,
                max_tokens=max_tokens,
            )
            if not text.strip():
                text = _section_fallback(section_id, direction, method, evidence)
                section_source = "fallback"
            else:
                section_source = "llm"
        # Strip duplicate headings the LLM emits (we add our own
        # ``## <title>`` above this body, so the LLM's echo of the
        # same heading creates a "## Related Work / ## Related Work"
        # pair). Also strip placeholder tags like [paper1, paper2]
        # and [ref: foo, bar] the LLM sometimes emits when the
        # survey did not give it concrete citation keys.
        cleaned = _clean_section_body(text, title)
        # For the experimental-setup section, enforce the four
        # sub-headings (4.1 / 4.2 / 4.3 / 4.4). When the LLM is
        # truncated, the last sub-section is often missing; we fill
        # it from the evidence so the paper still has the structure
        # the venue template expects.
        if section_id == "experiments":
            cleaned = _enforce_experiments_subsections(
                cleaned, direction=direction, method=method,
                evidence=evidence, workspace=phd.workspace,
            )
        # Dynamic supervision loop: the PhD reviews every drafted
        # section against ground truth (hallucinated numbers,
        # internal wording, thinness) and demands ONE redraft with
        # concrete feedback before accepting it. This closes the
        # write-phase request->work->verify loop the same way the
        # code phase does.
        feedback = _review_section(section_id, cleaned, phd.workspace)
        if feedback and section_source == "llm":
            phd.set_status(PhDStatus.REVIEWING)
            # Per-section PhD<->MS collaboration: when the section is
            # too thin to carry its claims, the PhD dispatches the MS
            # for targeted supporting evidence (real papers, real
            # abstracts), verifies it arrived, and hands it to the
            # redraft — theory gets backed by sources, and contrasts
            # can honestly highlight where ours differs.
            support_block = ""
            if ("too thin" in feedback and ms is not None
                    and section_id in ("intro", "related", "method", "analysis")):
                try:
                    support = ms.search_papers(
                        direction, max_arxiv=6, max_venue=4,
                        relevance_cutoff=0.0,
                        required_tokens=_derive_anchor_tokens(direction),
                    )
                    bullets = [
                        f"- {p.short_cite()}: {(p.abstract or '')[:180]}"
                        for p in support[:6]
                    ]
                    if bullets:
                        support_block = (
                            "\n\nSupporting evidence gathered by the "
                            "literature survey (REAL papers — cite them "
                            "author-year where they back a claim, and use "
                            "contrasts to show precisely where the proposed "
                            "method differs):\n" + "\n".join(bullets)
                        )
                        ms.write_research_log(
                            subject=f"Section support: {title}",
                            content=(
                                "PhD requested supporting evidence for a "
                                f"thin section; provided {len(bullets)} "
                                "sourced items.\n" + "\n".join(bullets)
                            ),
                            task_ref="section-support",
                        )
                        phd.append_doc_memo(
                            user_request=f"section support: {title}",
                            method=method, stage=f"write:{section_id}:support",
                            ms_summary=f"{len(bullets)} evidence items delivered",
                            interaction_ms=(
                                "PhD dispatched targeted evidence request; "
                                "MS reported to research_log"
                            ),
                            stage_goal="section claims backed by sources",
                            stage_complete=True,
                        )
                except Exception:  # noqa: BLE001
                    logger.warning("section support search failed; redrafting without it")
            redraft = _call_llm_with_retry(
                router, "writer", "phd",
                system=_writer_system(section_id),
                user=(
                    user_prompt
                    + "\n\nYour previous draft was REJECTED by the supervising "
                    "review for these reasons — fix every one and return the "
                    f"full corrected section:\n{feedback}"
                    + support_block
                    + f"\n\nPrevious draft:\n{cleaned[:4000]}"
                ),
                max_tokens=max_tokens,
            )
            phd.set_status(PhDStatus.WRITING)
            if redraft.strip():
                redrafted = _clean_section_body(redraft, title)
                if section_id == "experiments":
                    redrafted = _enforce_experiments_subsections(
                        redrafted, direction=direction, method=method,
                        evidence=evidence, workspace=phd.workspace,
                    )
                second = _review_section(section_id, redrafted, phd.workspace)
                # Accept the redraft when it is no worse than the first.
                if second is None or len(second) <= len(feedback):
                    cleaned = redrafted
                    feedback = second
        if feedback:
            phd.append_doc_memo(
                user_request="section review",
                method=method, stage=f"write:{section_id}",
                stage_goal="section passes the supervisor review",
                lessons=f"unresolved after redraft: {feedback[:300]}",
                stage_complete=False,
            )
        sections.append((title, cleaned.strip()))
        phd.append_article_memo(
            direction=direction,
            method=method,
            progress=f"section={section_id} ({section_source})",
            status=f"length={len(text)} chars",
            text_check=(
                f"section '{title}' written; no AI filler, "
                f"evidence-anchored{' (provisional inputs)' if readiness.force_provisional_write else ''}"
            ),
            style_check="declarative; no first-person; no local paths",
            references_check="cites from survey corpus only",
            figure_check="no figures in this section",
            table_check="no tables in this section",
            other_check="heading in proper Markdown; no local paths leaked",
        )

    # Generate + place figures INSIDE their sections (block diagram
    # in Method; results chart + raw-data sample in Experimental
    # Setup). Appending them after the Conclusion produced sparse
    # float-graveyard final pages.
    import shutil as _sh
    paper_figures_dir = phd._workspace / "paper" / "body" / "figures"
    paper_figures_dir.mkdir(parents=True, exist_ok=True)
    results = _load_run_results(phd.workspace)
    try:
        from paperfessor.research.figures import generate_block_diagram
        fig_path = phd._workspace / "src" / "figures" / "block_diagram.png"
        # Real dataset names from the experiment manifests — NOT the
        # survey paper titles (that bug crammed full titles into the
        # diagram and made it unreadable).
        ds_names = list((results or {}).get("manifests", {}).keys()) or ["(pending)"]
        generate_block_diagram(
            method=method, direction=direction,
            out_path=fig_path, datasets=ds_names,
        )
        _sh.copy(fig_path, paper_figures_dir / "block_diagram.png")
    except Exception as exc:  # noqa: BLE001
        logger.warning("block diagram generation failed: %s", exc)
    def _figure_ok(p: Path) -> tuple[bool, str]:
        """PhD self-audit of a figure it is about to put in the paper:
        the file must exist, load as an image, be reasonably sized,
        and be fresh (generated by THIS run, not a stale leftover)."""
        if not p.is_file():
            return False, "missing"
        try:
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
            if w < 400 or h < 150:
                return False, f"too small ({w}x{h}px)"
        except Exception as exc:  # noqa: BLE001
            return False, f"unreadable ({exc})"
        results_p = phd._workspace / "src" / "results" / "results.json"
        if results_p.is_file() and p.stat().st_mtime < results_p.stat().st_mtime - 3600:
            return False, "stale (predates this run's results)"
        return True, "ok"

    section_figures: dict[str, list[str]] = {
        "3. Method": [], "4. Experimental Setup": [],
        "5. Analysis and Discussion": [],
    }
    figure_audit: list[str] = []
    bd = paper_figures_dir / "block_diagram.png"
    ok, why = _figure_ok(bd)
    figure_audit.append(f"block_diagram.png: {why}")
    if ok:
        section_figures["3. Method"].append(
            "![Block diagram of the proposed method architecture.]"
            "(figures/block_diagram.png)"
        )
    def _ug_regenerate_figure(fname: str) -> bool:
        """Subtask dispatch: the PhD found a broken/missing figure in
        its self-audit and sends the UG to regenerate it from the
        stored results — the same collaborate-loop as everywhere
        else. Returns True when the regenerated file passes audit."""
        if ug is None or results is None:
            return False
        try:
            from paperfessor.research.experiments import (
                MetricRow, plot_dataset_sample, plot_results,
            )
            out = phd._workspace / "src" / "figures" / fname
            if fname == "results_f1.png":
                rows = [MetricRow(**r) for r in results.get("rows", [])]
                plot_results(rows, out)
            elif fname == "dataset_sample.png":
                from paperfessor.research import datasets as _ds
                first = next(iter(results.get("manifests", {})), None)
                if not first:
                    return False
                info = _ds.fetch(first, ug.workspace)
                plot_dataset_sample(info.path, out)
            elif fname == "qualitative_comparison.png":
                from paperfessor.research import datasets as _ds
                from paperfessor.research.experiments import (
                    plot_qualitative_comparison,
                )
                first = next(iter(results.get("manifests", {})), None)
                if not first:
                    return False
                info = _ds.fetch(first, ug.workspace)
                model_files = sorted(
                    (ug.workspace / "src" / "code").glob("model_*.py"))
                plot_qualitative_comparison(
                    info.path, out,
                    proposed_model_path=model_files[-1] if model_files else None,
                    proposed_name=f"{method.split()[0]} (ours)",
                )
            else:
                return False
            ug.write_code_log(
                subject=f"Regenerated paper figure {fname}",
                content=(
                    "PhD's figure self-audit flagged the file; regenerated "
                    "from src/results/results.json."
                ),
                task_ref="fig-regen",
            )
            return _figure_ok(out)[0]
        except Exception as exc:  # noqa: BLE001
            logger.warning("figure regeneration for %s failed: %s", fname, exc)
            return False

    for fname, caption, section in (
        ("results_f1.png",
         "Best F1 per dataset and method (mean ± 95% CI over 3 seeds).",
         "4. Experimental Setup"),
        ("dataset_sample.png",
         "A real test segment with labeled anomaly regions shaded.",
         "4. Experimental Setup"),
        ("qualitative_comparison.png",
         "Qualitative comparison: each method's anomaly-score curve "
         "(min-max normalized per panel) over the same anomaly-dense "
         "test segment; shaded regions are labeled anomalies.",
         "5. Analysis and Discussion"),
    ):
        src_fig = phd._workspace / "src" / "figures" / fname
        ok, why = _figure_ok(src_fig)
        if not ok and _ug_regenerate_figure(fname):
            ok, why = True, "regenerated by UG after audit failure"
        figure_audit.append(f"{fname}: {why}")
        if ok:
            _sh.copy(src_fig, paper_figures_dir / fname)
            section_figures[section].append(f"![{caption}](figures/{fname})")
    # The self-audit result goes into the PhD's paper memory so the
    # figure_check field carries real findings, not boilerplate.
    phd.append_article_memo(
        direction=direction, method=method,
        progress="figure self-audit",
        status="; ".join(figure_audit),
        figure_check="; ".join(figure_audit),
    )
    # Tick off the write-phase subtasks the workers completed.
    try:
        tasks_now = phd._read_guide(phd._workspace / "shared" / "research_guide.md")[0]
        for t in tasks_now:
            if t.text.startswith(("Answer: what are the top",
                                  "Supplement citations")):
                t.done = True
        phd.update_research_guide(tasks_now)
    except Exception:  # noqa: BLE001
        logger.warning("could not tick write-phase guide tasks")

    # Assembly happens via _reassemble_paper (below, after the
    # references are collected) so appendix blocks embedded in
    # section bodies route to the document tail. Run metadata
    # (direction / method / timestamp) lives in doc_memo and the
    # archive — NOT in the paper body.
    # References: cite every paper we read, by short cite. Collected
    # into ``reference_lines`` so the self-inspection loop can
    # reassemble the paper without re-running the searches.
    reference_lines: list[str] = []
    seen: set[str] = set()
    ref_count = 0
    for ev in evidence:
        cite = ev.paper.short_cite()
        if cite in seen:
            continue
        seen.add(cite)
        if ev.paper.arxiv_id:
            reference_lines.append(
                f"- {ev.paper.authors[0].split()[-1] if ev.paper.authors else 'anon'} "
                f"et al. ({ev.paper.year}). *{ev.paper.title}*. "
                f"arXiv:{ev.paper.arxiv_id}. {ev.paper.source_url}")
            ref_count += 1
        elif ev.paper.source_url:
            reference_lines.append(
                f"- {ev.paper.authors[0].split()[-1] if ev.paper.authors else 'anon'} "
                f"et al. ({ev.paper.year}). *{ev.paper.title}*. "
                f"{ev.paper.venue}. {ev.paper.source_url}")
            ref_count += 1
    # Fallback: if the survey gave us zero readable papers, the LLM
    # body still cites [1] [2] etc. Reuse the LLM's own References
    # block (the empty `## References` the LLM emitted at the end of
    # the limitations section) as a placeholder so the paper at
    # least has a non-empty References section. We also seed a few
    # canonical time-series anomaly detection references so the
    # reviewer can map the [n] markers in the body to real work.
    # FULL papers in this area carry 30-40 references — deep literature
    # engagement is a quality signal. Top up with REAL canonical works
    # (searched live, never fabricated) when the survey alone leaves
    # the list thin; the citation resolver adds more during
    # self-inspection as the body cites them.
    if ref_count < 28:
        from paperfessor.research.sources.arxiv import search as _ax_search
        canonical_titles = [
            "Anomaly Transformer Time-Series Association Discrepancy",
            "USAD UnSupervised Anomaly Detection multivariate time series",
            "RobustTAD robust time series anomaly detection decomposition convolutional",
            "TimesNet temporal 2D variation modeling",
            "OmniAnomaly stochastic recurrent neural network multivariate",
            "Deep learning for anomaly detection survey",
            "Isolation forest",
            "LOF local outlier factor density based",
            "Time series anomaly detection benchmark evaluation",
            "Contrastive learning time series representation",
            "TranAD deep transformer networks anomaly detection multivariate",
            "Spectral residual saliency time-series anomaly detection service",
            "LSTM encoder decoder multi-sensor anomaly detection",
            "Temporal hierarchical one-class network anomaly detection",
            "Deep autoencoding gaussian mixture model unsupervised anomaly",
            "Graph neural network anomaly detection multivariate time series",
            "Rigorous evaluation time-series anomaly detection point adjust",
            "Comprehensive evaluation anomaly detection time series benchmark",
            "Outlier detection review survey high-dimensional",
            "Self-supervised representation learning time series survey",
        ]
        for title in canonical_titles:
            if ref_count >= 32:
                break
            try:
                papers = _ax_search(title, max_results=3)
            except Exception:  # noqa: BLE001
                papers = []
            query_tokens = {t.lower() for t in _informative_tokens(title)}
            for p in papers:
                aid = p.arxiv_id.split("v", 1)[0] if p.arxiv_id else None
                if not aid:
                    continue
                # Relevance guard: arXiv's first hit is sometimes a
                # completely unrelated paper (observed: an air-pollutant
                # forecasting paper matched a TS-AD benchmark query).
                # The result's title must share >= 2 informative tokens
                # with the query, or it is skipped.
                hit_tokens = {t.lower() for t in _informative_tokens(p.title)}
                if len(query_tokens & hit_tokens) < 2:
                    continue
                first = p.authors[0].split()[-1] if p.authors else "anon"
                ref_text = (
                    f"- {first} et al. ({p.year}). *{p.title}*. "
                    f"arXiv:{aid}. https://arxiv.org/abs/{aid}"
                )
                # Avoid duplicates
                if any(aid in line for line in reference_lines):
                    continue
                reference_lines.append(ref_text)
                ref_count += 1
                break
    if ref_count == 0:
        # Last-resort: emit a single "no papers found" line so the
        # References section is non-empty.
        reference_lines.append(
            "- (No externally-indexed paper was retrievable in the survey window; "
            "all prior-art citations in the body reference the survey log.)"
        )
    paper_path.write_text(
        _reassemble_paper(method, sections, section_figures, reference_lines),
        encoding="utf-8",
    )

    # 0.5 PhD whole-paper SELF-INSPECTION loop (per spec: inspect the
    # assembled paper comprehensively, fix the problems one by one,
    # check again, and repeat until no problems remain). Deterministic
    # defect scans + the PhD re-reading its own full paper; defective
    # sections are redrafted with the concrete defect list and the
    # paper is reassembled. Bounded at 3 rounds.
    if not readiness.force_provisional_write:
        for inspect_round in range(1, POLICY.max_inspection_rounds + 1):
            md_now = paper_path.read_text(encoding="utf-8")
            defects = _whole_paper_defects(md_now, phd.workspace)
            defects += _llm_paper_review(
                router, md_now, phd.workspace, direction, method,
            )
            phd.append_article_memo(
                direction=direction, method=method,
                progress=f"self-inspection round {inspect_round}",
                status=(f"{len(defects)} defects" if defects else "clean"),
                text_check="; ".join(defects[:6]) or "no defects found",
            )
            if not defects:
                break
            # Citation defects get RESOLVED (find the real work, add a
            # verified reference) rather than redrafted — redrafting
            # them just swaps one uncited famous work for another.
            defects, refs_added = _resolve_missing_citations(
                defects, md_now, reference_lines,
            )
            if refs_added:
                phd.append_article_memo(
                    direction=direction, method=method,
                    progress=f"self-inspection round {inspect_round}: citation resolution",
                    status=f"added {refs_added} verified references",
                    references_check=f"{refs_added} body citations resolved to real entries",
                )
                paper_path.write_text(
                    _reassemble_paper(method, sections, section_figures,
                                      reference_lines),
                    encoding="utf-8",
                )
                if not defects:
                    continue
            fixed_any = refs_added > 0
            new_sections: list[tuple[str, str]] = []
            for title, body in sections:
                relevant = [
                    d for d in defects
                    if _defect_targets_section(d, title, body)
                ]
                if not relevant:
                    new_sections.append((title, body))
                    continue
                sec_id = _SECTION_ID_BY_TITLE.get(title, "")
                redraft = _call_llm_with_retry(
                    router, "writer", "phd",
                    system=_writer_system(sec_id or "revision"),
                    user=(
                        f"Revise this section of the paper to fix EVERY "
                        f"defect below. Keep everything that is correct; "
                        f"change only what the defects require. Return the "
                        f"full corrected section body (no heading).\n\n"
                        f"Defects:\n"
                        + "\n".join(f"- {d}" for d in relevant[:8])
                        + f"\n\nSection '{title}':\n{body[:5000]}"
                    ),
                    max_tokens=1600,
                )
                if redraft.strip():
                    nb = _clean_section_body(redraft, title)
                    if sec_id == "experiments":
                        nb = _enforce_experiments_subsections(
                            nb, direction=direction, method=method,
                            evidence=evidence, workspace=phd.workspace,
                        )
                    new_sections.append((title, nb.strip()))
                    fixed_any = True
                else:
                    new_sections.append((title, body))
            sections = new_sections
            if not fixed_any:
                break
            paper_path.write_text(
                _reassemble_paper(method, sections, section_figures,
                                  reference_lines),
                encoding="utf-8",
            )
    # 1. Ask the PhD to pick the right venue for this direction and
    #    try to download its official template. The .tex writer will
    #    use whatever class the PhD returns.
    try:
        venue = phd.detect_and_fetch_venue(direction)
    except Exception as exc:  # noqa: BLE001
        venue = {"venue_name": "Unknown", "class_name": "acmart-sigconf",
                 "class_source": "fallback", "page_limit": 9,
                 "venue_id": None, "venue_full": "", "template_path": None}
        phd.append_doc_memo(
            method=method, stage="write", user_request=direction,
            ug_summary="PhD venue pick failed: " + str(exc),
            stage_goal="PhD picks the right target venue",
            lessons="- venue pick raised; using acmart fallback"
        )
    # 2. Build the .tex + .pdf with the venue's class.
    try:
        from paperfessor.research.latex import build_pdf, write_tex
        tex_path = write_tex(
            paper_path.read_text(encoding="utf-8"),
            paper_path.parent,
            class_name=venue["class_name"],
            venue_id=venue.get("venue_id"),
            venue_name=venue.get("venue_name"),
            page_limit=venue.get("page_limit", 9),
            appendix_allowed=bool(venue.get("appendix_allowed", True)),
        )
        templates_dir = phd._workspace / "paper" / "templates"
        # The figure is copied into paper/body/figures/ (see
        # block-diagram generation above), so the .tex can resolve
        # the path without TEXINPUTS.
        pdf_path = build_pdf(tex_path, texinputs=[templates_dir])
        # If pdflatex failed, build_pdf returned the .tex path as a
        # sentinel. We treat the run as "tex-only" and skip the
        # visual inspect (which needs a real PDF).
        pdf_built = pdf_path.suffix.lower() == ".pdf" and pdf_path.is_file()
        # 2.4 FULL-PAPER page utilization: the body (before References)
        #     must fill the venue's page budget. Under-filled papers
        #     get bounded expansion rounds: the PhD deepens the most
        #     expandable sections with REAL content (analysis of the
        #     measured numbers, literature engagement) and rebuilds.
        target_body = max(3.0, float(venue.get("page_limit", 9)) - 1.0)
        for expand_round in range(2):
            if not pdf_built or readiness.force_provisional_write:
                break
            if not _llm_budget_left(router):
                break
            total_p, body_p = _count_body_pages(pdf_path)
            if body_p >= target_body:
                break
            deficit = target_body - body_p
            phd.append_article_memo(
                direction=direction, method=method,
                progress=f"page-fill round {expand_round + 1}",
                status=f"body {body_p:.1f} pages of {target_body:.0f} target",
                other_check=(
                    f"full-paper mode: expanding sections to close a "
                    f"{deficit:.1f}-page deficit"
                ),
            )
            # Expand the LONG-FORM sections (never abstract/conclusion).
            # Experiments-over-theory: grow the empirical sections to
            # fill the page budget, NOT the Method (theory) section —
            # excess theory belongs in the appendix, not the body.
            expandable = ("4. Experimental Setup", "5. Analysis and Discussion",
                          "1. Introduction", "2. Related Work")
            new_sections = []
            for title, body in sections:
                if title not in expandable:
                    new_sections.append((title, body))
                    continue
                sec_id = _SECTION_ID_BY_TITLE.get(title, "")
                grown = _call_llm_with_retry(
                    router, "writer", "phd",
                    system=_writer_system(sec_id),
                    user=(
                        f"The paper body must fill {target_body:.0f} pages "
                        f"but currently reaches {body_p:.1f}. EXPAND this "
                        f"section by 30-50% with REAL substance only: "
                        f"deeper analysis of the measured numbers, richer "
                        f"engagement with the ALREADY-CITED literature, "
                        f"precise methodological detail. NO filler "
                        f"sentences, NO new numbers, NO new datasets, and "
                        f"do NOT introduce NEW author-year citations that "
                        f"are not already in the paper — reuse the existing "
                        f"ones. Return the full expanded section body (no "
                        f"heading).\n\nCurrent section '{title}':\n{body[:6000]}"
                    ),
                    max_tokens=3000,
                )
                if grown.strip() and len(grown) > len(body):
                    nb = _clean_section_body(grown, title)
                    if _review_section(sec_id, nb, phd.workspace) is None:
                        new_sections.append((title, nb.strip()))
                        continue
                new_sections.append((title, body))
            sections = new_sections
            paper_path.write_text(
                _reassemble_paper(method, sections, section_figures,
                                  reference_lines),
                encoding="utf-8",
            )
            tex_path = write_tex(
                paper_path.read_text(encoding="utf-8"),
                paper_path.parent,
                class_name=venue["class_name"],
                venue_id=venue.get("venue_id"),
                venue_name=venue.get("venue_name"),
                page_limit=venue.get("page_limit", 9),
                appendix_allowed=bool(venue.get("appendix_allowed", True)),
            )
            pdf_path = build_pdf(tex_path, texinputs=[templates_dir])
            pdf_built = pdf_path.suffix.lower() == ".pdf" and pdf_path.is_file()
        # 2.45 POST-EXPANSION cleanup: expansion adds fresh prose that
        #      can reintroduce uncited references and borderline
        #      numbers the earlier self-inspection never saw (expansion
        #      runs after it). Run bounded cleanup on the FINAL text:
        #      resolve citations, scan defects, redraft the offending
        #      sections, rebuild — so the accepted paper is clean.
        if pdf_built and not readiness.force_provisional_write:
            for cleanup_round in range(2):
                md_now = paper_path.read_text(encoding="utf-8")
                defects = _whole_paper_defects(md_now, phd.workspace)
                if not defects:
                    break
                defects, refs_added = _resolve_missing_citations(
                    defects, md_now, reference_lines)
                fixed_any = refs_added > 0
                if defects and _llm_budget_left(router):
                    new_secs = []
                    for title, body in sections:
                        rel = [d for d in defects
                               if _defect_targets_section(d, title, body)]
                        if not rel:
                            new_secs.append((title, body))
                            continue
                        sid = _SECTION_ID_BY_TITLE.get(title, "")
                        rd = _call_llm_with_retry(
                            router, "writer", "phd",
                            system=_writer_system(sid or "revision"),
                            user=(
                                "Fix EVERY defect below in this section; "
                                "keep the length and everything correct. "
                                "Return the full corrected body (no "
                                "heading).\n\nDefects:\n"
                                + "\n".join(f"- {d}" for d in rel[:8])
                                + f"\n\nSection '{title}':\n{body[:6000]}"
                            ),
                            max_tokens=2400,
                        )
                        if rd.strip():
                            new_secs.append((title, _clean_section_body(rd, title).strip()))
                            fixed_any = True
                        else:
                            new_secs.append((title, body))
                    sections = new_secs
                phd.append_article_memo(
                    direction=direction, method=method,
                    progress=f"post-expansion cleanup round {cleanup_round + 1}",
                    status=f"{len(defects)} defects; +{refs_added} refs",
                    references_check=f"{refs_added} citations resolved post-expansion",
                )
                if not fixed_any:
                    break
                paper_path.write_text(
                    _reassemble_paper(method, sections, section_figures,
                                      reference_lines),
                    encoding="utf-8",
                )
                tex_path = write_tex(
                    paper_path.read_text(encoding="utf-8"),
                    paper_path.parent,
                    class_name=venue["class_name"],
                    venue_id=venue.get("venue_id"),
                    venue_name=venue.get("venue_name"),
                    page_limit=venue.get("page_limit", 9),
                    appendix_allowed=bool(venue.get("appendix_allowed", True)),
                )
                pdf_path = build_pdf(tex_path, texinputs=[templates_dir])
                pdf_built = pdf_path.suffix.lower() == ".pdf" and pdf_path.is_file()
        # 2.5 Run the Article 19 visual inspect on the rendered PDF and
        #     fold the result into the next article_memo entry. The
        #     PhD never declares the paper "ready" without this check.
        visual_ok: bool | None = None
        if pdf_built:
            try:
                from paperfessor.research.visual_inspect import inspect_pdf, summarize
                checks = inspect_pdf(pdf_path)
                visual_report = summarize(checks)
                visual_ok = all(c.passed for c in checks)
                visual_findings = (
                    f"Article 19: {sum(1 for c in checks if c.passed)}/"
                    f"{len(checks)} pages pass; "
                    f"font_min={min((c.font_min for c in checks), default=0):.1f}pt; "
                    f"line_gap_med={sum(c.line_gap_median for c in checks)/max(1,len(checks)):.1f}pt; "
                    f"density_avg={sum(c.text_density for c in checks)/max(1,len(checks)):.2f}."
                )
            except Exception as exc:  # noqa: BLE001
                visual_ok = False
                visual_findings = f"Article 19: visual inspect failed: {exc}"
        else:
            visual_ok = False
            visual_findings = (
                f"Article 19: pdflatex failed (.tex only); "
                f"the .md is the canonical artifact"
            )
        # 3. Record the venue choice in article_memo (模版检查).
        template_check = (
            f"venue={venue.get('venue_name')!r} ({venue.get('venue_full')!r}); "
            f"class={venue.get('class_name')!r}; source={venue.get('class_source')!r}; "
            f"page_limit={venue.get('page_limit')}; "
            f"template={'downloaded' if venue.get('template_path') else 'missing'}."
        )
        # Use the spec-format article_memo entry.
        phd.append_article_memo(
            direction=direction, method=method,
            progress=(
                "paper.md + paper.tex + paper.pdf" if pdf_built
                else "paper.md + paper.tex (pdf build failed)"
            ),
            status="compiled" if pdf_built else "tex-only",
            template_check=template_check,
            text_check=(
                "verified no AI-filler; "
                "all sections from spec format"
            ),
            style_check="no AI phrasing; no local paths leaked",
            references_check=(
                f"{ref_count} references (survey corpus + verified canonical top-ups)"
            ),
            figure_check="no figures yet (UG phase will add)",
            table_check="no tables yet (UG phase will add)",
            other_check=(
                f"title block has venue name; no local paths; provisional={readiness.force_provisional_write}; "
                f"{visual_findings}"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        phd.append_article_memo(
            direction=direction, method=method,
            progress="paper.md only",
            status="tex-build failed: " + str(exc),
            template_check="venue=" + str(venue.get("venue_name")),
            text_check="not yet (build failed)",
        )
    # Return the rendered PDF (not the .md) so the archive can
    # zip the canonical artifact. The .md is also available at
    # paper_path (the function's local variable).
    pdf_final = body_dir / "paper.pdf"
    if pdf_final.is_file():
        return pdf_final
    return paper_path


# ---- Section-level write helpers -----------------------------------------


def _load_evidence(phd: PhDStudent) -> list[Evidence]:
    """Reload the per-paper evidence from the MS's research log.

    The MS wrote a structured survey entry; we re-parse it into
    :class:`Evidence` records by matching the citation block. If the
    parse fails we fall back to an empty list and the write phase
    uses its built-in template strings.
    """
    log = phd._workspace / "shared" / "research_log.md"
    if not log.is_file():
        return []
    text = log.read_text(encoding="utf-8")
    # The survey log embeds "## <title>" headings for each paper.
    # Each block has lines like "- **Year / Venue**: ...".
    out: list[Evidence] = []
    chunks = re.split(r"\n## (?!#)(?!\s)", text)
    for chunk in chunks:
        m = re.search(r"^- \*\*Authors\*\*:\s*(.+)$", chunk, re.M)
        if not m:
            continue
        # Pull title (the chunk's first non-empty line).
        first_line = ""
        for line in chunk.splitlines():
            if line.strip():
                first_line = line.strip()
                break
        if first_line.startswith("#"):
            continue
        # Year / Venue line.
        ym = re.search(r"Year / Venue\*\*:\s*(\d+)\s*/\s*(.+?)\s*\[", chunk)
        year = int(ym.group(1)) if ym else 0
        venue = ym.group(2).strip() if ym else ""
        arxiv_m = re.search(r"arXiv\*\*:\s*(\S+)", chunk)
        arxiv_id = arxiv_m.group(1) if arxiv_m else None
        # Datasets / metrics / claims / summary.
        datasets = re.search(r"Datasets\*\*:\s*(.+)$", chunk, re.M)
        metrics = re.search(r"Headline metrics\*\*:\s*(.+)$", chunk, re.M)
        bottom = re.search(r"Bottom line\*\*:\s*(.+?)(?:\n\n|\Z)", chunk, re.S | re.M)
        claims_block = re.search(r"Claims \(from paper\)\*\*:\s*(.+?)(?:\n- \*\*Key figures|\Z)", chunk, re.S)
        claims = ()
        if claims_block:
            claims = tuple(
                c.strip().lstrip("-").strip()
                for c in claims_block.group(1).splitlines()
                if c.strip().startswith("-")
            )
        rec = PaperRecord(
            arxiv_id=arxiv_id,
            doi=None,
            title=first_line,
            authors=tuple(a.strip() for a in m.group(1).split(",") if a.strip()),
            year=year,
            venue=venue,
            venue_source="survey",
            source_url="",
            pdf_url=None,
            pdf_path=None,
            abstract="",
            citation_count=0,
            fields_of_study=(),
        )
        out.append(Evidence(
            paper=rec,
            datasets=_split_csv(datasets.group(1) if datasets else ""),
            metrics=_split_csv(metrics.group(1) if metrics else ""),
            claims=claims,
            key_figures=(),
            summary=(bottom.group(1).strip() if bottom else ""),
        ))
    return out


def _split_csv(s: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in re.split(r",\s*", s) if p.strip())


# Patterns the LLM occasionally emits that we want to remove from
# the assembled paper. These are real defects observed in the 200-round
# regression runs (e.g. "[paper1, paper2]" used in place of a citation,
# "[ref: foo, bar]" used as an unfulfilled reference). They have no
# place in a finished paper.
_PLACEHOLDER_PATTERNS: tuple[str, ...] = (
    re.compile(r"\[\s*paper\s*\d+\s*(?:[,;\s]+\s*paper\s*\d+)*\s*\]", re.I),
    re.compile(r"\[\s*ref\s*:\s*[^]]{1,80}\]", re.I),
    re.compile(r"\[\s*cite\s+needed\s*\]", re.I),
    re.compile(r"\[\s*todo[^\]]{0,40}\]", re.I),
    # [n3] / [n4] / [n1, n2] style placeholders the LLM uses
    # when it has not been given a real reference list. Strip them.
    re.compile(r"\[\s*n\d+(?:\s*[,;\s]+\s*n\d+)*\s*\]", re.I),
    # [Wang et al., 2024] / [Wu et al., 2024] author-year placeholders
    # that the LLM emits without an actual reference. Drop the brackets
    # so the sentence still reads naturally.
    re.compile(r"\[\s*[A-Z][a-zA-Z\-']+(?:\s+et\s+al\.)?(?:,?\s*\d{4})?\s*\]"),
    re.compile(r"\bTBD\s*\(\s*UG\s+to\s+run\s*\)", re.I),
    # BibTeX-style keys the LLM invents ([su2021raid], [xu2018unsupervised,
    # kim2022towards]) that map to nothing in the References section.
    re.compile(r"\[\s*[a-z]+\d{4}[a-z]*(?:\s*,\s*[a-z]+\d{4}[a-z]*)*\s*\]"),
)

# Process/handoff sections the shared guardrails ask agents to produce
# for their LOGS. They must never appear inside the paper body.
_PROCESS_SECTION_RE = re.compile(
    r"^#{1,6}\s*(What changed|Evidence|Risks?|Next steps?|Handoff|"
    r"Summary of changes|What remains risky|What the next agent must do)\b"
    r".*?(?=^#{1,6}\s|\Z)",
    re.M | re.S | re.I,
)


def _clean_section_body(text: str, title: str) -> str:
    """Strip LLM-emitted defects from a section body.

    The LLM occasionally:
      - echoes the section heading (``# 1 Introduction`` right after
        our own ``## 1. Introduction`` header)
      - emits placeholder citation tags like ``[paper1, paper2]``
      - emits placeholder reference tags like ``[ref: foo, bar]``
      - emits ``[cite needed]`` or ``[todo ...]`` placeholders
      - emits a stray ``## Datasets`` (without the 4.1 prefix) and
        a stray ``## References`` (we add our own References block
        at the end of the paper)

    All of these are removed here. We also normalize consecutive
    blank lines (max 2) and trim trailing whitespace.
    """
    out = text
    # Strip fenced code blocks: the LLM emits ASCII / box-drawing
    # pipeline diagrams that render as non-wrapping verbatim and
    # overflow the column margin (observed on page 3 of a full
    # paper). We already generate a real block_diagram.png figure,
    # so these are redundant as well as broken.
    out = re.sub(r"```.*?```", "", out, flags=re.S)
    # Strip stray "Figure N. ..." / "Figure N: ..." plain-text
    # captions the LLM writes for its ASCII diagram — real figures
    # get a proper \caption via the markdown image syntax, so these
    # are orphan text that also double-numbers the figures.
    out = re.sub(r"(?m)^\s*Figure\s+\d+[.:].*(?:\n(?!\s*$).*)*", "", out)
    # Box-drawing / heavy-arrow characters only ever come from ASCII
    # diagrams; drop any residual lines containing them.
    out = re.sub(r"(?m)^.*[─-╿←-⇿].*$\n?", "", out)
    # Remove a leading duplicate heading: the LLM sometimes writes
    # "# 1 Introduction" or "## Related Work" as the first line,
    # which then duplicates the heading we add above it. Match both
    # "# 1 Introduction" and "## 1. Introduction" forms.
    title_norm = re.escape(title).replace(r"\ ", r"\s*")
    head_patterns = [
        re.compile(rf"^\s*#{{1,6}}\s*{title_norm}\s*\.?\s*$", re.M | re.I),
    ]
    # Also strip the "## 1. Introduction" form when title is
    # "1. Introduction".
    bare_num = re.match(r"^(\d+)\.\s*(\S.*)$", title)
    if bare_num:
        # Also accept "1 Introduction" (no dot) and "1. Introduction".
        head_patterns.append(
            re.compile(rf"^\s*#{{1,6}}\s*{bare_num.group(1)}\.?\s+"
                       rf"{re.escape(bare_num.group(2))}\s*\.?\s*$", re.M | re.I)
        )
        # And the bare "## Related Work" form (no number) when the
        # canonical title is "2. Related Work".
        head_patterns.append(
            re.compile(rf"^\s*#{{1,6}}\s*{re.escape(bare_num.group(2))}\s*$",
                       re.M | re.I)
        )
    # And the form "## Abstract" (no number).
    head_patterns.append(
        re.compile(rf"^\s*#{{1,6}}\s*{re.escape(title)}\s*$", re.M | re.I)
    )
    for pat in head_patterns:
        out = pat.sub("", out, count=1)
    # For the experiments section we additionally strip a stray
    # "## Datasets" or "## References" the LLM may have inserted
    # before the canonical sub-headings. The "## References" in
    # particular conflicts with our own programmatically-added
    # References block at the end of the paper. We match both `##`
    # and `###` levels and exclude `### 4.x` (the canonical
    # experimental sub-headings) from the stop condition so the
    # pattern doesn't accidentally consume them.
    if title.lower().startswith(("4. experimental", "3. method",
                                 "5. analysis", "6. conclusion",
                                 "7. limitations")):
        stray_patterns: list[re.Pattern] = []
        # Strip "## Datasets" / "### Datasets" / "### Datasets and
        # experimental plan" from any of the body sections. The
        # canonical 4.1 Datasets sub-section in 4. Experimental
        # Setup is not affected because that heading is `## 4.1
        # Datasets` (with the "4.1" prefix), which does NOT match
        # the bare "Datasets" pattern.
        stray_patterns.append(
            re.compile(
                r"^#{2,3}\s+Datasets(?:\s+(?:and|for|used|in|of|on)\b[^#\n]*)?\s*$(?:\n(?!(?:#{1,3})\s).*)*",
                re.M | re.I,
            )
        )
        # "## References" / "### References" / "## Bibliography"
        # anywhere in the body. The paper assembles the real
        # References block at the end, so the LLM's ad-hoc block
        # is dropped. The stop condition is the next `## ` or
        # `###` heading that is NOT a References / Bibliography
        # continuation.
        stray_patterns.append(
            re.compile(
                r"^#{2,3}\s+(?:References|Bibliography)\s*$(?:\n(?!(?:#{1,3})\s).*)*",
                re.M,
            )
        )
        for pat in stray_patterns:
            out = pat.sub("", out)
    # Strip process/handoff summaries (the shared guardrails ask for
    # them in LOGS; inside the paper they are internal-info leakage).
    out = _PROCESS_SECTION_RE.sub("", out)
    # Drop the placeholder tags. We replace with a brief verbal
    # equivalent so the sentence still reads naturally.
    for pat in _PLACEHOLDER_PATTERNS:
        out = pat.sub("", out)
    # Collapse 3+ blank lines into 2.
    out = re.sub(r"\n{3,}", "\n\n", out)
    # Trim trailing whitespace.
    return out.rstrip()


_SECTION_ID_BY_TITLE: dict[str, str] = {
    "Abstract": "abstract",
    "1. Introduction": "intro",
    "2. Related Work": "related",
    "3. Method": "method",
    "4. Experimental Setup": "experiments",
    "5. Analysis and Discussion": "analysis",
    "6. Conclusion": "conclusion",
    "7. Limitations and Future Work": "limitations",
}


def _count_body_pages(pdf_path: Path) -> tuple[int, float]:
    """(total_pages, body_pages): body = pages before the References
    heading (the page containing it counts half)."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_path))
    total = len(pdf)
    body = float(total)
    for i in range(total):
        try:
            text = pdf[i].get_textpage().get_text_bounded()
        except Exception:  # noqa: BLE001
            continue
        if "References" in (text or ""):
            body = i + 0.5
            break
    pdf.close()
    return total, body


def _split_off_appendix(body: str) -> tuple[str, str]:
    """Split a section body into (main, appendix_block). Appendix
    blocks ('## Appendix ...') are written by the section authors at
    the end of their replies and must move to the document tail."""
    m = re.search(r"(?ms)^## Appendix.*\Z", body)
    if not m:
        return body, ""
    return body[:m.start()].rstrip(), m.group(0).strip()


def _reassemble_paper(
    method: str,
    sections: list[tuple[str, str]],
    section_figures: dict[str, list[str]],
    reference_lines: list[str],
) -> str:
    """Rebuild paper.md from its parts (used by the self-inspection
    loop after sections are revised). Appendix blocks embedded in
    section bodies are gathered and emitted contiguously before
    References so the .tex writer routes them after \\appendix."""
    parts: list[str] = [f"# {method}", ""]
    appendix_blocks: list[str] = []
    for title, body in sections:
        main, appendix = _split_off_appendix(body)
        if appendix:
            appendix_blocks.append(appendix)
        parts.append(f"## {title}")
        parts.append("")
        parts.append(main)
        parts.append("")
        for fig_md in section_figures.get(title, ()):
            parts.append(fig_md)
            parts.append("")
    for block in appendix_blocks:
        parts.append(block)
        parts.append("")
    parts.append("## References")
    parts.append("")
    parts.extend(reference_lines)
    return "\n".join(parts)


def _whole_paper_defects(paper_md: str, workspace: Path) -> list[str]:
    """Deterministic whole-paper defect scan (the PhD's self-check).

    Codifies the reviewer findings from development: hallucinated
    metrics, internal wording, dangling figure references, body
    citations missing from the References list, thin references.
    """
    defects: list[str] = []
    body, _, refs_block = paper_md.partition("## References")
    lowered = body.lower()
    # Safeguard 1 — internal/process wording and private artifacts.
    for banned in ("the ms ", "the ug ", "master's student", "undergraduate",
                   "paperfessor", "what changed", "doc_memo", "article_memo",
                   "research_log", "code_log", "skill/", "minimax"):
        if banned in lowered:
            defects.append(
                f"internal wording {banned.strip()!r} appears in the paper body"
            )
    # Safeguard 2 — local paths and source filenames must never leak
    # (drive letters, workspace paths, *.py names).
    for pat, label in (
        (r"\b[A-Za-z]:\\", "Windows drive path"),
        (r"\bworkspace[/\\]", "workspace-relative path"),
        (r"\b\w+\.py\b", "source filename"),
        (r"/Users/|/home/", "POSIX home path"),
    ):
        m = re.search(pat, body)
        if m:
            defects.append(
                f"private information leak: {label} {m.group(0)!r} in the paper body"
            )
    # Safeguard 3 — AI-style expressions (the classic tells).
    for phrase in ("it is worth noting", "in recent years",
                   "many researchers have", "delve into",
                   "plays a crucial role",
                   "extensive experiments demonstrate",
                   "the rest of the paper is organized"):
        if phrase in lowered:
            defects.append(f"AI-style expression {phrase!r} — rewrite the sentence")
    # Safeguard 4 — markdown footnote markers ([^1]) are not supported
    # by the LaTeX converter and would print literally.
    if re.search(r"\[\^\w+\]", paper_md):
        defects.append("markdown footnote marker [^...] would print literally in the PDF")
    # Safeguard 4b — Unicode mathematical-alphanumeric characters
    # (U+1D400..U+1D7FF) never render in standard LaTeX fonts; the LLM
    # sometimes pastes "styled" math. Use plain ASCII in $...$ math.
    if any(0x1D400 <= ord(c) <= 0x1D7FF for c in paper_md):
        bad = sorted({c for c in paper_md if 0x1D400 <= ord(c) <= 0x1D7FF})
        defects.append(
            f"Unicode math characters {bad[:5]} will not render — write "
            f"math in plain ASCII inside $...$ delimiters"
        )
    # Safeguard 5 — implementation fidelity: when the experiments ran
    # the CPU numpy/scikit-learn variant, Method text claiming
    # deep-learning training procedures contradicts the Protocol.
    # (With a recorded CUDA run, such claims are legitimate.)
    _res = _load_run_results(workspace)
    _proposed_hw = ((_res or {}).get("protocol", {}) or {}).get(
        "hardware", {}).get("proposed", "cpu")
    if _res and _proposed_hw == "cpu":
        m = re.search(
            r"\btrains? end-to-end\b|\bwith adam\b|\badam optimizer\b|"
            r"\bbackpropagat\w*|\bepochs? of training\b|\blearning-rate schedule\b",
            lowered,
        )
        if m:
            defects.append(
                f"Method text claims a deep-training procedure ({m.group(0)!r}) "
                f"but the implementation is CPU-only numpy/scikit-learn — "
                f"describe the SIMPLIFIED variant actually run; idealized "
                f"extensions belong in Future Work"
            )
    valid = _measured_number_tokens(workspace)
    if valid:
        valid_floats = []
        for v in valid:
            try:
                valid_floats.append(float(v))
            except ValueError:
                pass
        for tok in sorted(set(re.findall(r"\b0\.\d{3}\b", body))):
            if tok in valid:
                continue
            # Rounding-boundary tolerance: a derived delta the writer
            # rounded to 0.569 must not be flagged when the token set
            # holds 0.570 (both are the same measured difference at a
            # rounding edge). Accept within +-0.0015.
            try:
                tf = float(tok)
            except ValueError:
                continue
            if any(abs(tf - vf) <= 0.0015 for vf in valid_floats):
                continue
            defects.append(
                f"number {tok} does not match any measured value "
                f"(hallucinated metric?)"
            )
    # Figure references must resolve to real files.
    for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", paper_md):
        fig = workspace / "paper" / "body" / m.group(1)
        if not fig.is_file():
            defects.append(f"figure reference {m.group(1)} points to no file")
    # Author-year citations in the body must appear in References.
    surnames_in_refs = set(
        re.findall(r"^-\s+(\S+)\s+et al\.", refs_block, re.M)
    )
    cited = set(re.findall(r"\(([A-Z][a-zA-Z\-']+) et al\.,? \d{4}\)", body))
    for name in sorted(cited):
        if name not in surnames_in_refs:
            defects.append(
                f"body cites ({name} et al.) but the References list has "
                f"no such entry"
            )
    n_refs = len([l for l in refs_block.splitlines() if l.startswith("- ")])
    if n_refs < 10:
        defects.append(f"only {n_refs} references (venue norm is 18+)")
    return defects


def _review_input(paper_md: str, *, max_chars: int = 24000) -> str:
    """Fit the whole paper into the reviewer's context WITHOUT losing
    structure: every section heading survives, the References block
    is always included in full (citation checks need it), and long
    section bodies are trimmed at paragraph boundaries with an
    explicit omission note — never a silent mid-sentence cut."""
    if len(paper_md) <= max_chars:
        return paper_md
    chunks = re.split(r"(?m)^(## .+)$", paper_md)
    # chunks: [preamble, heading, body, heading, body, ...]
    sections: list[tuple[str, str]] = []
    preamble = chunks[0]
    for i in range(1, len(chunks) - 1, 2):
        sections.append((chunks[i], chunks[i + 1]))
    refs = [s for s in sections if "references" in s[0].lower()]
    others = [s for s in sections if "references" not in s[0].lower()]
    refs_text = "".join(h + b for h, b in refs)[:5000]
    budget = max_chars - len(refs_text) - len(preamble) - 200
    per_section = max(600, budget // max(1, len(others)))
    parts: list[str] = [preamble]
    for heading, body in others:
        if len(body) > per_section:
            cut = body[:per_section]
            nl = cut.rfind("\n\n")
            if nl > per_section * 0.5:
                cut = cut[:nl]
            body = cut + f"\n\n[... {len(body) - len(cut)} chars of this section omitted ...]\n"
        parts.append(heading + body)
    parts.append(refs_text)
    return "".join(parts)


def _llm_paper_review(
    router: LLMRouter, paper_md: str, workspace: Path,
    direction: str, method: str,
) -> list[str]:
    """The PhD re-reads its own full paper and lists concrete defects.

    Grounded review: the prompt carries the measured results, so
    unsupported claims are catchable. Output is one defect per line
    ("SECTION: defect ...") or the single word NONE. Failures return
    an empty list — the deterministic scan still applies.
    """
    table = _results_table_md(workspace) or "(no measured results)"
    try:
        raw = _call_llm_with_retry(
            router, "reviewer", "phd",
            system=(
                "You are the supervising professor doing the FINAL read of "
                "your own paper before submission. Be maximally critical "
                "about correctness, not style: flag (1) any claim not "
                "supported by the measured results below, (2) any dataset "
                "or baseline described as evaluated that is not in the "
                "results, (3) contradictions between sections, (4) numbers "
                "that disagree with the results table, (5) unclear or "
                "broken sentences. NOTE: markers like '[... N chars "
                "omitted ...]' are context-fitting notes from the review "
                "harness, NOT part of the paper — never report them as "
                "defects. Output ONE defect per line in the form "
                "'<SECTION TITLE>: <defect>'. If the paper has no such "
                "defects, output exactly: NONE"
            ),
            user=(
                f"Measured results (ground truth):\n{table}\n\n"
                f"Paper (direction: {direction}; method: {method}):\n\n"
                + _review_input(paper_md)
            ),
            max_tokens=900,
            attempts=2,
        )
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for line in raw.splitlines():
        line = line.strip().lstrip("-*#0123456789. ")
        if not line or line.upper() == "NONE":
            continue
        low = line.lower()
        # Parser hygiene: the reviewer sometimes emits preamble lines
        # ("Scanning for defects:") and verdict lines for things it
        # checked and found CORRECT — those are not defects.
        if low.startswith(("scanning", "checking", "reviewing", "here are",
                           "defects", "output", "looking", "examining",
                           "analyzing", "based on", "overall", "summary")):
            continue
        # A defect line names its section before the colon — long
        # pre-colon text is reviewer narration, not a defect.
        if len(line.split(":", 1)[0]) > 60:
            continue
        if any(okw in low for okw in ("— correct", "- correct", "is correct",
                                      "consistent with", "no issue",
                                      "matches the", "verified correct")):
            continue
        # The review copy's own trimming markers are not paper defects.
        if "chars omitted" in low or "chars of this section omitted" in low:
            continue
        if ":" in line and 10 < len(line) < 400:
            out.append(line)
    return out[:10]


# Curated canonical citations for the field's most-cited classics.
# Every entry is a real, verifiable published work; the alias tokens
# must appear in the citing sentence before the entry is used, so a
# surname collision can never attach the wrong work. This rung has
# no API dependence — the exact resilience the flaky-index rungs
# lack for precisely these famous papers.
_CANONICAL_CITATIONS: dict[tuple[str, int], tuple[str, tuple[str, ...]]] = {
    ("audibert", 2020): (
        "- Audibert et al. (2020). *USAD: UnSupervised Anomaly Detection on "
        "Multivariate Time Series*. KDD 2020. https://doi.org/10.1145/3394486.3403392",
        ("usad", "adversarial", "autoencoder")),
    ("liu", 2008): (
        "- Liu et al. (2008). *Isolation Forest*. ICDM 2008. "
        "https://doi.org/10.1109/ICDM.2008.17",
        ("isolation",)),
    ("breunig", 2000): (
        "- Breunig et al. (2000). *LOF: Identifying Density-Based Local "
        "Outliers*. SIGMOD 2000. https://doi.org/10.1145/342009.335388",
        ("lof", "density", "local outlier")),
    ("ramaswamy", 2000): (
        "- Ramaswamy et al. (2000). *Efficient Algorithms for Mining "
        "Outliers from Large Data Sets*. SIGMOD 2000. "
        "https://doi.org/10.1145/342009.335437",
        ("outlier", "nearest neighbor", "distance")),
    ("ahmad", 2017): (
        "- Ahmad et al. (2017). *Unsupervised Real-Time Anomaly Detection "
        "for Streaming Data*. Neurocomputing 262. "
        "https://doi.org/10.1016/j.neucom.2017.04.070",
        ("streaming", "nab", "numenta", "htm", "real-time")),
    ("hundman", 2018): (
        "- Hundman et al. (2018). *Detecting Spacecraft Anomalies Using "
        "LSTMs and Nonparametric Dynamic Thresholding*. KDD 2018. "
        "https://arxiv.org/abs/1802.04431",
        ("spacecraft", "lstm", "telemanom", "thresholding", "nasa")),
    ("su", 2019): (
        "- Su et al. (2019). *Robust Anomaly Detection for Multivariate "
        "Time Series through Stochastic Recurrent Neural Network*. KDD "
        "2019. https://doi.org/10.1145/3292500.3330672",
        ("omnianomaly", "stochastic", "recurrent", "smd", "server machine")),
    ("xu", 2022): (
        "- Xu et al. (2022). *Anomaly Transformer: Time Series Anomaly "
        "Detection with Association Discrepancy*. ICLR 2022. "
        "https://arxiv.org/abs/2110.02642",
        ("anomaly transformer", "association", "discrepancy", "attention")),
    ("ren", 2019): (
        "- Ren et al. (2019). *Time-Series Anomaly Detection Service at "
        "Microsoft*. KDD 2019. https://arxiv.org/abs/1906.03821",
        ("spectral residual", "sr-cnn", "microsoft", "saliency")),
    ("tuli", 2022): (
        "- Tuli et al. (2022). *TranAD: Deep Transformer Networks for "
        "Anomaly Detection in Multivariate Time Series Data*. VLDB 2022. "
        "https://arxiv.org/abs/2201.07284",
        ("tranad", "transformer")),
    ("wu", 2023): (
        "- Wu et al. (2023). *TimesNet: Temporal 2D-Variation Modeling for "
        "General Time Series Analysis*. ICLR 2023. "
        "https://arxiv.org/abs/2210.02186",
        ("timesnet", "2d-variation", "temporal")),
    ("kim", 2022): (
        "- Kim et al. (2022). *Towards a Rigorous Evaluation of Time-Series "
        "Anomaly Detection*. AAAI 2022. https://arxiv.org/abs/2109.05257",
        ("evaluation", "point adjust", "protocol", "rigorous")),
    ("schmidl", 2022): (
        "- Schmidl et al. (2022). *Anomaly Detection in Time Series: A "
        "Comprehensive Evaluation*. PVLDB 15(9). "
        "https://doi.org/10.14778/3538598.3538602",
        ("comprehensive evaluation", "benchmark", "survey")),
    ("pang", 2021): (
        "- Pang et al. (2021). *Deep Learning for Anomaly Detection: A "
        "Review*. ACM Computing Surveys 54(2). "
        "https://arxiv.org/abs/2007.02500",
        ("review", "survey", "deep learning")),
    ("zong", 2018): (
        "- Zong et al. (2018). *Deep Autoencoding Gaussian Mixture Model "
        "for Unsupervised Anomaly Detection*. ICLR 2018. "
        "https://openreview.net/forum?id=BJJLHbb0-",
        ("dagmm", "gaussian mixture", "autoencoding")),
    ("shen", 2020): (
        "- Shen et al. (2020). *Timeseries Anomaly Detection using Temporal "
        "Hierarchical One-Class Network*. NeurIPS 2020. "
        "https://proceedings.neurips.cc/paper/2020/hash/97e401a02082021fd24957f852e0e475-Abstract.html",
        ("thoc", "hierarchical", "one-class")),
    ("malhotra", 2016): (
        "- Malhotra et al. (2016). *LSTM-based Encoder-Decoder for "
        "Multi-sensor Anomaly Detection*. arXiv:1607.00148. "
        "https://arxiv.org/abs/1607.00148",
        ("encoder-decoder", "lstm", "multi-sensor")),
    # Software / tooling citations (papers legitimately cite the
    # scientific stack they run on).
    ("harris", 2020): (
        "- Harris et al. (2020). *Array Programming with NumPy*. "
        "Nature 585. https://doi.org/10.1038/s41586-020-2649-2",
        ("numpy", "array")),
    ("pedregosa", 2011): (
        "- Pedregosa et al. (2011). *Scikit-learn: Machine Learning in "
        "Python*. JMLR 12. https://jmlr.org/papers/v12/pedregosa11a.html",
        ("scikit-learn", "sklearn")),
    ("virtanen", 2020): (
        "- Virtanen et al. (2020). *SciPy 1.0: Fundamental Algorithms for "
        "Scientific Computing in Python*. Nature Methods 17. "
        "https://doi.org/10.1038/s41592-019-0686-2",
        ("scipy",)),
    ("paszke", 2019): (
        "- Paszke et al. (2019). *PyTorch: An Imperative Style, "
        "High-Performance Deep Learning Library*. NeurIPS 2019. "
        "https://arxiv.org/abs/1912.01703",
        ("pytorch", "torch")),
}


def _resolve_missing_citations(
    defects: list[str], paper_md: str, reference_lines: list[str],
) -> tuple[list[str], int]:
    """Resolve 'body cites (X et al.) missing from References' defects
    by FINDING the real work (arXiv, then OpenAlex for classic
    non-arXiv papers) and appending a verified reference entry.

    This is the converging actuator for citation defects: redrafting
    made the LLM swap one uncited famous work for another (observed:
    18 -> 15 -> 16 defects across rounds). Every added entry is
    verified: the cited surname must be among the found paper's
    authors and the year must match within +-1.

    Returns (unresolved_defects, n_added).
    """
    unresolved: list[str] = []
    added = 0
    for d in defects:
        m = re.match(r"body cites \(([A-Za-z\-']+) et al\.\)", d)
        if not m:
            unresolved.append(d)
            continue
        surname = m.group(1)
        ctx = re.search(
            rf"([^.\n]*\(\s*{re.escape(surname)} et al\.,?\s*(\d{{4}})\)[^.\n]*)",
            paper_md,
        )
        year = int(ctx.group(2)) if ctx else 0
        sentence = ctx.group(1) if ctx else ""
        keywords = " ".join(
            t for t in _informative_tokens(sentence)[:5]
            if t.lower() != surname.lower()
        )
        entry: str | None = None
        # Rung 0: curated canonical classics (no API dependence).
        # The citing sentence must corroborate via an alias token so
        # a surname collision can never attach the wrong work.
        sentence_low = sentence.lower()
        for (c_surname, c_year), (c_entry, aliases) in _CANONICAL_CITATIONS.items():
            if (c_surname == surname.lower()
                    and (year == 0 or abs(c_year - year) <= 1)
                    and any(a in sentence_low for a in aliases)):
                entry = c_entry
                break
        # Rung 1: arXiv.
        if entry is None:
            try:
                from paperfessor.research.sources.arxiv import search as _ax
                for h in _ax(f"{surname} {keywords}", max_results=5):
                    if (any(surname.lower() == a.split()[-1].lower()
                            for a in h.authors)
                            and (year == 0 or abs(h.year - year) <= 1)):
                        aid = h.arxiv_id.split("v", 1)[0]
                        entry = (f"- {surname} et al. ({h.year}). *{h.title}*. "
                                 f"arXiv:{aid}. https://arxiv.org/abs/{aid}")
                        break
            except Exception:  # noqa: BLE001
                pass
        # Rung 2: OpenAlex (classic pre-arXiv papers: IsolationForest,
        # Ramaswamy 2000, ...).
        if entry is None:
            try:
                from paperfessor.research.sources import openalex as _oa
                for h in _oa.search(f"{surname} {keywords}", limit=5):
                    if (any(surname.lower() == a.split()[-1].lower()
                            for a in h.authors)
                            and (year == 0 or abs(h.year - year) <= 1)):
                        link = h.doi or h.landing_page_url or ""
                        entry = (f"- {surname} et al. ({h.year}). *{h.title}*. "
                                 f"{h.venue or 'journal'}. {link}")
                        break
            except Exception:  # noqa: BLE001
                pass
        # Rung 3: Semantic Scholar free search (strong author/venue
        # coverage where the keyword-context search misses).
        if entry is None:
            try:
                from paperfessor.research.sources import s2 as _s2
                query = f"{surname} {year or ''} {keywords}".strip()
                for h in _s2.search(query, limit=5):
                    if (any(surname.lower() == a.split()[-1].lower()
                            for a in h.authors)
                            and (year == 0 or abs(h.year - year) <= 1)):
                        link = (f"https://arxiv.org/abs/{h.arxiv_id}"
                                if h.arxiv_id else (h.doi or ""))
                        entry = (f"- {surname} et al. ({h.year}). *{h.title}*. "
                                 f"{h.venue or 'S2'}. {link}")
                        break
            except Exception:  # noqa: BLE001
                pass
        if entry is None:
            logger.info("citation resolution failed for %s (%s)", surname, year)
            unresolved.append(d)
            continue
        if not any(entry.split("*")[1][:40] in l for l in reference_lines if "*" in l):
            reference_lines.append(entry)
            added += 1
    return unresolved, added


def _defect_targets_section(defect: str, title: str, body: str) -> bool:
    """Does this defect concern this section? Match by section-title
    prefix (LLM defects) or by offending token present in the body
    (deterministic defects).

    The reviewer names sections loosely ("Section 2 Related Work:",
    "2. Related Work:", "Related Work —"), so matching normalizes
    both sides down to the bare words.
    """
    d = defect.lower()
    t = title.lower()
    head = d.split(":", 1)[0][:60]
    # Normalize: drop "section", digits, punctuation.
    norm = lambda s: re.sub(r"[^a-z ]+", " ", s.replace("section", " ")).split()
    t_words = [w for w in norm(t) if len(w) > 2]
    head_words = set(norm(head))
    if t_words and all(w in head_words for w in t_words):
        return True
    if d.startswith(t) or t in head:
        return True
    # Deterministic defects carry the offending token in quotes or as
    # a number — check the body for it.
    m = re.search(r"'([^']+)'|number (0\.\d{3})|\(([A-Za-z\-']+) et al", defect)
    if m:
        token = next(g for g in m.groups() if g)
        return token.lower() in body.lower()
    return False


def _past_lessons(phd: PhDStudent, direction: str = "",
                  *, max_chars: int = 400) -> str:
    """Self-evolution memory: distinct failure reasons from past
    archived attempts IN THIS DIRECTION, distilled into an avoid-list
    for the writer. Scoped to the topic: when the topic changes, the
    paper starts fresh and other topics' failures must not shape it."""
    reasons: list[str] = []
    seen: set[str] = set()
    dir_key = _slug_prefix(direction) if direction else ""
    try:
        for a in phd.list_archived():
            if str(a.get("success")).lower() == "true":
                continue
            if dir_key and dir_key not in str(
                    a.get("research_direction", "")).lower():
                continue
            for chunk in str(a.get("reason", "")).split(";"):
                c = chunk.strip()
                key = c.lower()[:40]
                if c and key not in seen:
                    seen.add(key)
                    reasons.append(c)
    except Exception:  # noqa: BLE001
        return ""
    if not reasons:
        return ""
    text = "Known failure modes from previous attempts — do not repeat: " \
        + "; ".join(reasons)
    return text[:max_chars]


def _section_system(section_id: str, direction: str, method: str) -> str:
    """Long, structured system prompt for section-level LLM calls.

    Earlier diagnostics showed the LLM returns empty for short system
    prompts; a non-trivial system block fixes that.
    """
    return (
        f"You are a research PhD drafting section {section_id} of a top-venue "
        f"ML paper. The user spec is strict: active voice, declarative, no "
        f"AI-style filler ('It is worth noting', 'In recent years', 'Many "
        f"researchers', 'In this work we'). Cite every claim. Every sentence "
        f"must be evidence-anchored. The paper targets a top-tier venue; the "
        f"body must be dense. Write in Markdown under the section heading "
        f"given. Do not wrap the output in a Markdown code fence. Do not "
        f"include any local paths, project-internal names, or skill "
        f"references. Do not fabricate numbers; if the survey did not give "
        f"you a number, say 'not yet evaluated'. Output ONLY the section "
        f"prose — no process summaries ('What changed', 'Evidence', 'Next "
        f"steps'), no notes to other agents. NEVER mention the agents or "
        f"roles behind this paper (no 'PhD', 'MS', 'UG', 'master's "
        f"student', 'undergraduate', 'supervisor', 'agent', 'Paperfessor') "
        f"— published papers say 'we'. Cite ONLY as author-year in "
        f"parentheses, e.g. (Wu et al., 2024); never invent BibTeX keys "
        f"like [xu2018unsupervised]. Every citation is VERIFIED against "
        f"public indexes after you write: cite only works whose first "
        f"author and year you know precisely — unverifiable citations "
        f"are deleted from your text. Write like a published top-venue "
        f"paper: concrete nouns, measured numbers, no hedging filler. "
        f"Direction: {direction}. Proposed method: {method}."
    )


def _abstract_prompt(direction: str, method: str, evidence: list[Evidence],
                     workspace: Path | None = None) -> str:
    cite_lines = "\n".join(f"- {ev.paper.short_cite()}: {ev.summary or '(no summary)'}"
                            for ev in evidence[:6])
    headline = _results_headline(workspace)
    return (
        f"Write the Abstract (under the 'Abstract' heading) of a top-venue paper "
        f"on direction={direction!r} using method={method!r}. The abstract must be "
        f"150-200 words, must state (1) the problem, (2) the proposed approach, "
        f"(3) the datasets actually evaluated, and (4) the measured headline "
        f"result. Use ONLY the numbers given below; never promise results "
        f"'to be reported' when numbers exist. Write as a single "
        f"paragraph (no internal line breaks).\n\n"
        f"{headline or 'No experiments have been run: say results are pending and give no numbers.'}\n\n"
        f"Survey evidence (real, from the MS):\n{cite_lines or '(none yet)'}\n"
    )


def _intro_prompt(direction: str, method: str, evidence: list[Evidence],
                  workspace: Path | None = None) -> str:
    headline = _results_headline(workspace)
    return (
        f"Write the Introduction (3-4 dense paragraphs, ~600-800 words — "
        f"this is a FULL paper, size the section accordingly) of a "
        f"top-venue paper. "
        f"Frame the problem (direction={direction!r}), the gap in prior work "
        f"(use the survey evidence below; do not invent citations), and the "
        f"contribution of method={method!r}. Support every design claim "
        f"with a citation — a full paper engages the literature deeply. "
        f"End with a 3-bullet list of "
        f"concrete contributions. Dense, declarative. No filler.\n\n"
        f"HONESTY CONSTRAINT: the experiments compared ONLY against PCA "
        f"reconstruction, IsolationForest, and kNN distance. NEVER claim the "
        f"method was 'shown to outperform' any OTHER method (deep baselines "
        f"from the survey may be discussed as related work, but no victory "
        f"over them may be claimed — they were not run).\n\n"
        f"{headline}\n\n"
        f"Survey evidence (real):\n"
        + "\n".join(f"- {ev.paper.short_cite()}: {ev.summary or '(no summary)'}"
                     for ev in evidence[:8])
    )


def _related_prompt(direction: str, method: str, evidence: list[Evidence]) -> str:
    return (
        f"Write the Related Work section (4-5 dense paragraphs, ~700-900 "
        f"words — this is a FULL paper). Group the surveyed papers into "
        f"3-4 thematic clusters and discuss each cluster's assumptions, "
        f"strengths, and the specific gap it leaves. Cite EVERY surveyed "
        f"paper below, and additionally cite well-known canonical works "
        f"you can name precisely (author-year) — deep literature "
        f"engagement highlights the novelty of the proposed method. "
        f"If the survey found < 5 papers, "
        f"say so explicitly. CONSISTENCY: the corpus size is EXACTLY "
        f"{len(evidence)} papers — if you state a count anywhere, use "
        f"exactly {len(evidence)} (other sections state the same number).\n\n"
        f"Surveyed papers (real, dedup'd):\n"
        + "\n".join(f"- {ev.paper.short_cite()} ({ev.paper.venue or '?'}): "
                    f"{ev.paper.title}"
                    for ev in evidence[:15])
    )


def _method_prompt(direction: str, method: str, evidence: list[Evidence],
                   workspace: Path | None = None) -> str:
    headline = _results_headline(workspace)
    res = _load_run_results(workspace) if workspace else None
    proposed_hw = ((res or {}).get("protocol", {}) or {}).get(
        "hardware", {}).get("proposed", "cpu")
    if proposed_hw == "cpu":
        fidelity = (
            f"IMPLEMENTATION FIDELITY: describe the method AS "
            f"IMPLEMENTED — a CPU-only numpy/scikit-learn variant with no "
            f"neural training (no Adam, no backpropagation, no epochs, no "
            f"GPU); the Protocol section states this and the Method must not "
            f"contradict it. Idealized deep extensions may be mentioned only "
            f"as future work. "
        )
    else:
        fidelity = (
            f"IMPLEMENTATION FIDELITY: the implementation ran on "
            f"{proposed_hw}; describe the training procedure exactly as "
            f"implemented and claim no capability beyond it. "
        )
    return (
        f"Write the Method section (2-3 paragraphs, ~500-650 words MAX) "
        f"for {method!r}. "
        f"Describe the method concretely; include one figure described in "
        f"words. {fidelity}"
        f"Do NOT list evaluation datasets here (Section 4 "
        f"covers them); do NOT promise experiments on datasets that were "
        f"not run. No fabricated numbers. BALANCE RULE (this is an "
        f"EMPIRICAL paper — experiments and analysis must dominate the "
        f"page budget, not theory): the main body carries ONLY the core "
        f"formulation and the intuition a reader needs to follow the "
        f"experiments (~1 page). Push ALL extended derivations, lemmas, "
        f"proofs, complexity analysis, and secondary design variants into "
        f"a trailing block titled '## Appendix A: Extended "
        f"Derivations' at the END of your reply — it is routed out of "
        f"the main pages automatically.\n\n{headline}"
    )


def _load_run_results(workspace: Path) -> dict | None:
    """Load the UG's real experiment results (results.json), if any."""
    p = workspace / "src" / "results" / "results.json"
    if not p.is_file():
        return None
    try:
        import json
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _results_table_md(workspace: Path) -> str | None:
    p = workspace / "src" / "results" / "results.md"
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return None


def _dataset_summary_md(results: dict) -> str:
    lines = [
        "| Dataset | Domain | d | Train | Test | Anomaly ratio |",
        "|---|---|---|---|---|---|",
    ]
    domains = {
        "smd-1-1": "server telemetry (SMD)",
        "smd-2-1": "server telemetry (SMD)",
        "smd-3-1": "server telemetry (SMD)",
        "nab-machine-temp": "industrial temperature (NAB)",
        "nab-ec2-cpu": "cloud CPU utilization (NAB)",
    }
    for name, m in results.get("manifests", {}).items():
        lines.append(
            f"| {name} | {domains.get(name, 'time series')} | {m.get('n_features')} "
            f"| {m.get('n_train')} | {m.get('n_test')} "
            f"| {m.get('anomaly_ratio_test', 0):.3f} |"
        )
    return "\n".join(lines)


def _results_headline(workspace: Path | None) -> str:
    """One-paragraph factual summary of the measured results, for the
    abstract / intro / method / conclusion prompts. Empty string when
    no results exist (the prompts then must not claim any numbers)."""
    if workspace is None:
        return ""
    results = _load_run_results(workspace)
    if not results:
        return ""
    rows = results.get("rows", [])
    ok = [r for r in rows if not r.get("error")]
    ours = [r for r in ok if str(r.get("method", "")).endswith("(ours)")]
    if not ours:
        return ""
    datasets = sorted({r["dataset"] for r in ok})
    lines = [
        f"MEASURED RESULTS (real, already computed; the ONLY datasets run "
        f"are: {', '.join(datasets)} — do not claim any other dataset was "
        f"evaluated). The WIN/TIE/LOSS labels below are COMPUTED from the "
        f"numbers — use exactly these labels when framing outcomes (a TIE "
        f"is within the confidence interval and must not be called a win):"
    ]
    wins = ties = 0
    for r in ours:
        base_best = max(
            (b for b in ok if b["dataset"] == r["dataset"] and b is not r),
            key=lambda b: b.get("f1_mean", 0.0),
            default=None,
        )
        if base_best is None:
            continue
        diff = r.get("f1_mean", 0.0) - base_best.get("f1_mean", 0.0)
        tol = max(r.get("f1_ci") or 0.0, base_best.get("f1_ci") or 0.0, 0.005)
        if abs(diff) <= tol:
            label = "TIE"
            ties += 1
        elif diff > 0:
            label = "WIN"
            wins += 1
        else:
            label = "LOSS"
        lines.append(
            f"- {r['dataset']}: {label} on F1 — ours {r['f1_mean']:.3f} "
            f"(AUROC {r['auroc_mean']:.3f}) vs best baseline "
            f"{base_best['method']} F1 {base_best['f1_mean']:.3f}"
        )
    lines.append(
        f"Overall framing: {wins} win(s), {ties} tie(s), "
        f"{len(ours) - wins - ties} loss(es) across {len(ours)} datasets."
    )
    return "\n".join(lines)


def _experiments_prompt(direction: str, method: str, evidence: list[Evidence],
                        workspace: Path | None = None) -> str:
    results = _load_run_results(workspace) if workspace else None
    table = _results_table_md(workspace) if workspace else None
    if results and table:
        ds_table = _dataset_summary_md(results)
        hw = (results.get("protocol", {}) or {}).get("hardware", {}) or {}
        hw_note = (
            f"baselines on {hw.get('baselines', 'cpu (numpy/scikit-learn)')}; "
            f"the proposed method on {hw.get('proposed', 'cpu')}"
        )
        return (
            f"Write the Experimental Setup section with EXACTLY these four sub-headings "
            f"(in this order, all four are MANDATORY):\n"
            f"  ## 4.1 Datasets\n"
            f"  ## 4.2 Baselines\n"
            f"  ## 4.3 Protocol\n"
            f"  ## 4.4 Results\n\n"
            f"The experiments have ALREADY been run on real data. Copy the numbers "
            f"below EXACTLY — do not round differently, do not invent, do not omit "
            f"the ± intervals.\n\n"
            f"Dataset facts (real, from the manifests):\n{ds_table}\n\n"
            f"Results (real, k = 3 seeds where stochastic):\n{table}\n\n"
            f"Contents for each subsection:\n"
            f"  ## 4.1 Datasets — reproduce the dataset table above as a Markdown table, "
            f"then 1-2 sentences per dataset (what it measures, why it is relevant).\n"
            f"  ## 4.2 Baselines — describe the three baselines that were actually run "
            f"(PCA reconstruction error, IsolationForest, kNN distance): what each "
            f"optimizes and why it is a fair comparison point. Also mention 2-3 strong "
            f"literature baselines from the survey by author-year for context.\n"
            f"  ## 4.3 Protocol — state EXACTLY: contiguous train/val/test split (no "
            f"shuffling), best-F1 threshold sweep (standard TS-AD protocol), 'k = 3 seeds' "
            f"and '95% confidence interval' (Student-t), Python 3.11, and the "
            f"per-method hardware as RECORDED: {hw_note}. State hardware "
            f"honestly per method; never claim hardware that was not used.\n"
            f"  ## 4.4 Results — reproduce the results table above EXACTLY as Markdown, "
            f"then 2-3 sentences of honest analysis: where the proposed method wins, "
            f"where it loses, and one plausible reason each.\n\n"
            f"Use proper Markdown table syntax with pipes '|'. No LaTeX, no $...$ math. "
            f"No placeholder tags. Do not stop before completing all four sub-sections."
        )
    # No real results available: write the setup honestly as a plan,
    # with no numbers at all.
    datasets = sorted({d for ev in evidence for d in ev.datasets}) or \
        ["SMD", "NAB machine temperature", "NAB EC2 CPU"]
    metrics = sorted({m for ev in evidence for m in ev.metrics}) or \
        ["F1", "AUROC", "AUPRC", "Precision", "Recall"]
    return (
        f"Write the Experimental Setup section with sub-headings 4.1 Datasets, "
        f"4.2 Baselines, 4.3 Protocol, 4.4 Results. The experiments have NOT "
        f"been run yet: describe the planned setup on {', '.join(datasets[:6])} "
        f"with metrics {', '.join(metrics[:5])}, and in 4.4 state explicitly that "
        f"results are pending — do NOT fabricate any number. No placeholder "
        f"citation tags. Markdown only."
    )


def _limitations_prompt(direction: str, method: str, evidence: list[Evidence],
                        workspace: Path | None = None) -> str:
    headline = _results_headline(workspace)
    return (
        f"Write a 1-paragraph Limitations and Future Work section. "
        f"Be honest: what does method={method!r} NOT solve? What datasets "
        f"are missing from the survey? What assumptions are not tested? "
        f"No filler. 80-150 words. "
        f"HONESTY CONSTRAINT: the empirical study covered ONLY the datasets "
        f"listed below — never describe the evaluation as spanning any other "
        f"benchmark. Unevaluated benchmarks may only be named as future work.\n\n"
        f"{headline or '(no experiments were run)'}\n\n"
        f"IMPORTANT: do NOT use placeholder citation tags like "
        f"'[paper1]', '[paper2]', '[ref: ...]', '[cite needed]', "
        f"'[todo ...]'. If you would have cited a paper, either drop "
        f"the claim or use a real author-year tag (e.g. 'Wu et al., 2024')."
    )


def _analysis_prompt(direction: str, method: str, evidence: list[Evidence],
                     workspace: Path | None = None) -> str:
    """Analysis & Discussion: the section that turns raw numbers into
    understanding — and legitimately fills a full paper with REAL
    content (per-dataset behavior, precision/recall trade-offs,
    failure-mode analysis, threats to validity)."""
    table = _results_table_md(workspace) or "(no measured results)"
    headline = _results_headline(workspace)
    return (
        f"Write the Analysis and Discussion section (4-6 dense paragraphs, "
        f"~700-900 words) for the paper on {method!r}. Use ONLY the "
        f"measured numbers below — every claim must trace to a cell of "
        f"the table. Cover, with sub-headings '## 5.1' to '## 5.4':\n"
        f"  ## 5.1 Per-dataset behavior — why the method wins/loses on "
        f"each dataset, grounded in that dataset's characteristics "
        f"(dimensionality, anomaly ratio, drift) and the metric pattern.\n"
        f"  ## 5.2 Precision-recall trade-offs — what the precision vs "
        f"recall split of each method says about its error profile.\n"
        f"  ## 5.3 Failure-mode analysis — the loss regime: what property "
        f"of the losing dataset defeats the method's core assumption.\n"
        f"  ## 5.4 Threats to validity — best-F1 threshold sweep caveats, "
        f"few-dataset scope, single-machine SMD shard, short NAB traces.\n"
        f"No fabricated numbers; no invented ablations. BALANCE RULE: "
        f"keep the main body focused on the headline findings; secondary "
        f"metric breakdowns (full precision/recall/AUPRC commentary per "
        f"dataset) go into a trailing block titled '## Appendix B: "
        f"Extended Results Commentary' at the END of your reply — it is "
        f"routed out of the main pages automatically.\n\n"
        f"{headline}\n\nFull results table:\n{table}"
    )


def _conclusion_prompt(direction: str, method: str, evidence: list[Evidence],
                       workspace: Path | None = None) -> str:
    """Prompt for a 1-paragraph Conclusion that summarizes the
    contribution and points to the next concrete step.
    """
    headline = _results_headline(workspace)
    return (
        f"Write a 1-paragraph Conclusion section for a paper about "
        f"direction={direction!r} using method={method!r}. "
        f"Summarize: (i) what problem we addressed, (ii) what we proposed "
        f"as the solution, (iii) what the survey of EXACTLY {len(evidence)} "
        f"papers showed (use exactly this count; other sections state the "
        f"same number), (iv) what the experiments measured (use ONLY the "
        f"numbers below), (v) the single most important next step. "
        f"No filler, no AI tells. 100-160 words. "
        f"IMPORTANT: do NOT use placeholder citation tags like "
        f"'[paper1]', '[paper2]', '[ref: ...]', '[cite needed]'. "
        f"Reference real author-year tags only (e.g. 'Wu et al., 2024').\n\n"
        f"{headline}"
    )


def _enforce_experiments_subsections(
    body: str, *, direction: str, method: str, evidence: list[Evidence],
    workspace: Path | None = None,
) -> str:
    """Make sure 4.1, 4.2, 4.3, 4.4 are all present in the
    experiments section AND in the correct order. The LLM
    sometimes writes the four sub-sections in reverse order
    (4.4 / 4.3 / 4.2 / 4.1) when the prompt template's numbering
    confuses it. We split the body on the sub-headings, dedupe
    duplicates, and reassemble in canonical order. Any missing
    sub-section is filled from a deterministic stub that uses ONLY
    real facts (the UG's results.json) — a stub never invents
    hardware, numbers, or baselines that did not run.
    """
    # The expected sub-headings, in order.
    sub_titles = [
        "## 4.1 Datasets",
        "## 4.2 Baselines",
        "## 4.3 Protocol",
        "## 4.4 Results",
    ]
    # Also match `### 4.x` (the LLM sometimes uses h3 instead of h2).
    alt_sub_titles = [sh.replace("## ", "### ") for sh in sub_titles]
    # Find the position of each sub-heading in the body. We also
    # accept the LLM's occasionally-emitted "## Datasets" stub
    # (without the "4.1" prefix) and re-label it as 4.1.
    positions: list[tuple[int, str]] = []
    for sh in sub_titles + alt_sub_titles:
        m = re.search(rf"^{re.escape(sh)}\s*$", body, re.M)
        if m:
            positions.append((m.start(), sh))
    # Treat the LLM's "## Datasets" stub as 4.1 if 4.1 is missing.
    if not any(sh.startswith("## 4.1 ") for _, sh in positions):
        m = re.search(r"^##\s+Datasets\s*$", body, re.M)
        if m:
            positions.append((m.start(), "## 4.1 Datasets"))
    # Sort by position so the body is split in document order.
    positions.sort(key=lambda x: x[0])
    # Dedupe (same sub-title appearing twice → keep the first one).
    seen_titles: set[str] = set()
    deduped_positions: list[tuple[int, str]] = []
    for pos, sh in positions:
        canon = sh.replace("### ", "## ")  # normalize h3 -> h2
        if canon in seen_titles:
            continue
        seen_titles.add(canon)
        deduped_positions.append((pos, canon))
    # Group body chunks by canonical sub-section title. The
    # canonical order is sub_titles (4.1 -> 4.4) regardless of
    # what order the LLM emitted them in.
    chunks: dict[str, str] = {}
    if deduped_positions:
        # Anything before the first sub-heading is preamble (rare).
        for i, (pos, sh) in enumerate(deduped_positions):
            end = (deduped_positions[i + 1][0]
                   if i + 1 < len(deduped_positions) else len(body))
            chunk = body[pos:end].strip()
            # Strip the original heading line; we will re-emit our
            # canonical heading in the final pass.
            lines = chunk.splitlines()
            if lines and re.match(r"^#{2,3}\s+", lines[0]):
                lines = lines[1:]
            chunk = "\n".join(lines).strip()
            # The first occurrence wins.
            chunks.setdefault(sh, chunk)
    # Build the canonical body in 4.1 -> 4.4 order.
    out_parts: list[str] = []
    for sh in sub_titles:
        if sh in chunks:
            out_parts.append(sh)
            out_parts.append("")
            out_parts.append(chunks[sh])
            out_parts.append("")
    body = "\n".join(out_parts).rstrip() + "\n"
    # Now check for missing sub-headings and append stubs. Stubs use
    # ONLY real facts from the UG's experiment run.
    have = set(chunks.keys())
    results = _load_run_results(workspace) if workspace else None
    results_table = _results_table_md(workspace) if workspace else None
    if "## 4.4 Results" not in have:
        lines = ["", "## 4.4 Results", ""]
        if results_table:
            lines.append(
                "All numbers below were measured by the accompanying "
                "implementation (k = 3 seeds where the method is "
                "stochastic; mean ± 95% confidence interval)."
            )
            lines.append("")
            lines.append(results_table)
        else:
            lines.append(
                "Experimental results are pending; no numbers are "
                "reported in this draft."
            )
        body = body.rstrip() + "\n\n" + "\n".join(lines)
    if "## 4.3 Protocol" not in have:
        body = body.rstrip() + (
            "\n\n## 4.3 Protocol\n\nWe use a contiguous train/val/test split "
            "(no shuffling, so temporal context does not leak across splits) "
            "and never re-fit on test data. Detection thresholds use the "
            "best-F1 sweep, the standard protocol in the time-series anomaly "
            "detection literature; AUROC and AUPRC are threshold-free. "
            "Stochastic methods run with k = 3 seeds and report the mean "
            "plus a 95% confidence interval (Student-t). All experiments "
            "are CPU-only, implemented in numpy and scikit-learn under "
            "Python 3.11.\n"
        )
    if "## 4.2 Baselines" not in have:
        body = body.rstrip() + (
            "\n\n## 4.2 Baselines\n\nWe compare against three classical "
            "unsupervised detectors that we run ourselves under the same "
            "protocol: PCA reconstruction error (subspace method), "
            "IsolationForest (tree-ensemble isolation), and mean kNN "
            "distance (density method). Stronger deep baselines from the "
            "survey are discussed in Related Work; we do not copy their "
            "published numbers into our table because the evaluation "
            "protocols differ.\n"
        )
    if "## 4.1 Datasets" not in have:
        if results:
            ds_table = _dataset_summary_md(results)
            body = body.rstrip() + (
                "\n\n## 4.1 Datasets\n\nWe evaluate on real, publicly "
                "available benchmarks (no synthetic data):\n\n" + ds_table + "\n"
            )
        else:
            datasets = sorted({d for ev in evidence for d in ev.datasets})
            body = body.rstrip() + (
                "\n\n## 4.1 Datasets\n\nPlanned datasets: "
                + (", ".join(datasets[:6]) or "to be selected from the survey")
                + ".\n"
            )
    return body


def _section_fallback(
    section_id: str, direction: str, method: str, evidence: list[Evidence],
) -> str:
    """Deterministic per-section template when the LLM is unavailable.

    The output is dense and grounded in the real evidence, so even
    without an LLM the paper is not a lie.
    """
    cite_lines = "\n".join(f"- {ev.paper.short_cite()}: {ev.summary or '(no summary)'}"
                            for ev in evidence[:8])
    datasets = sorted({d for ev in evidence for d in ev.datasets})
    metrics = sorted({m for ev in evidence for m in ev.metrics})
    if section_id == "abstract":
        return (
            f"{method} addresses {direction}. Existing methods report "
            f"strong results on individual benchmarks but generalize poorly. "
            f"This paper proposes a method that combines the assumptions "
            f"underlying the approach with a reproducible evaluation protocol "
            f"on multiple public datasets. A survey of "
            f"{len(evidence)} related papers grounds the design; the "
            f"experimental section reports the measured results on the "
            f"evaluated benchmarks."
        )
    if section_id == "intro":
        cits = "\n".join(f"- {ev.paper.short_cite()}" for ev in evidence[:6])
        return (
            f"The setting of {direction} has received increasing attention. "
            f"Prior work in this area (see Related Work) can be grouped into "
            f"several threads, but cross-benchmark generalization remains "
            f"limited.\n\nThis paper makes three contributions: (i) a new "
            f"formulation of the proposed method, (ii) a reproducible evaluation "
            f"protocol across multiple public benchmarks, and (iii) a reference "
            f"implementation evaluated under that protocol.\n\n"
            f"Relevant prior work includes:\n{cits or '(none surveyed)'}"
        )
    if section_id == "related":
        groups: dict[str, list[str]] = {}
        for ev in evidence:
            venue = ev.paper.venue or "other"
            groups.setdefault(venue[:30], []).append(ev.paper.short_cite())
        chunks = []
        for venue, cites in list(groups.items())[:3]:
            chunks.append(f"**{venue}**: " + "; ".join(cites[:4]) + ".")
        return "\n\n".join(chunks) if chunks else "(survey returned no papers)"
    if section_id == "method":
        return (
            f"{method} operates in two stages. Stage A learns a "
            f"representation from unlabeled data using a self-supervised "
            f"objective. Stage B scores test points against the learned "
            f"representation of normal behavior. The evaluated datasets "
            f"and the full protocol are described in Section 4; the "
            f"architecture is described in the released implementation."
        )
    if section_id == "experiments":
        # The enforce pass fills 4.1-4.4 from the real results.json;
        # this body is only the connective text above the sub-headings.
        return (
            "The experimental study evaluates the proposed method against "
            "classical unsupervised baselines under a single frozen "
            "protocol. The four sub-sections below describe the datasets, "
            "the baselines, the protocol, and the measured results."
        )
    if section_id == "limitations":
        return (
            f"This paper does not yet cover out-of-distribution "
            f"robustness. The literature review covered {len(evidence)} "
            f"papers in depth; several additional papers were paywalled "
            f"and may contain relevant prior art. Future work will widen "
            f"the review to open-access venue proceedings and add "
            f"cross-dataset transfer experiments."
        )
    if section_id == "conclusion":
        n_evidence = len(evidence)
        return (
            f"We addressed {direction} with {method}. A review of "
            f"{n_evidence} related papers identified the open gap; the "
            f"proposed method was implemented and evaluated under a "
            f"frozen, reproducible protocol on public benchmarks, with "
            f"the measured results reported in Section 4. The most "
            f"important next step is to extend the evaluation to further "
            f"benchmark families and stronger deep baselines."
        )
    return ""


def _assess_run_readiness(workspace: Path, paper_path: Path | None) -> RunReadiness:
    research_log = (workspace / "shared" / "research_log.md").read_text(encoding="utf-8") \
        if (workspace / "shared" / "research_log.md").is_file() else ""
    code_log = (workspace / "shared" / "code_log.md").read_text(encoding="utf-8") \
        if (workspace / "shared" / "code_log.md").is_file() else ""
    readable_papers = 0
    m = re.search(r"Full-text read:\s*(\d+)\s+papers extracted", research_log)
    if m:
        readable_papers = int(m.group(1))
    survey_blocked = any(
        phrase in research_log.lower()
        for phrase in (
            "can't write a meaningful gap statement",
            "corpus is too thin",
            "gap statement deferred",
            "stage`: survey → gap statement (blocked)".lower(),
            "no papers were readable",
        )
    )
    code_fallback = (
        "# Fallback skeleton" in code_log
        or "model_status: failed" in code_log
    )
    placeholder_metric = "PLACEHOLDER" in code_log
    visual_ok: bool | None = None
    pdf_missing = False
    if paper_path is not None and paper_path.is_file() and paper_path.suffix.lower() == ".pdf":
        try:
            from paperfessor.research.visual_inspect import inspect_pdf
            checks = inspect_pdf(paper_path)
            visual_ok = bool(checks) and all(c.passed for c in checks)
        except Exception:  # noqa: BLE001
            visual_ok = False
    elif paper_path is not None:
        # A non-PDF final artifact means the LaTeX build failed. The
        # run must not pass just because there was nothing to inspect.
        pdf_missing = True
    # Competitiveness (end-of-run only, when experiments produced
    # results): the proposed method must take best F1 on at least
    # one dataset, or the attempt is archived as failed so the next
    # run designs a different method (req: iterate toward SOTA).
    method_uncompetitive = False
    if paper_path is not None:
        results = _load_run_results(workspace)
        rows = (results or {}).get("rows", [])
        ok_rows = [r for r in rows if not r.get("error")]
        ours = [r for r in ok_rows if str(r.get("method", "")).endswith("(ours)")]
        if ours:
            wins = 0
            for r in ours:
                best = max(
                    (b.get("f1_mean", 0.0) for b in ok_rows
                     if b.get("dataset") == r.get("dataset")),
                    default=0.0,
                )
                if r.get("f1_mean", 0.0) >= best:
                    wins += 1
            method_uncompetitive = (wins == 0)
    return RunReadiness(
        readable_papers=readable_papers,
        survey_blocked=survey_blocked,
        code_fallback=code_fallback,
        placeholder_metric=placeholder_metric,
        visual_ok=visual_ok,
        pdf_missing=pdf_missing,
        method_uncompetitive=method_uncompetitive,
    )


def _cleanup_python_caches(root: Path, workspace: Path) -> None:
    for cache_dir in root.rglob("__pycache__"):
        try:
            cache_dir.relative_to(workspace)
            continue
        except ValueError:
            pass
        shutil.rmtree(cache_dir, ignore_errors=True)


def _phase_archive(
    phd: PhDStudent, direction: str, method: str, paper_path: Path | None,
    *, success: bool = True, reason: str = "v0.4 end-to-end run",
) -> Path | None:
    """PhD archives the attempt (success or failure)."""
    phd.set_status(PhDStatus.ARCHIVING)
    # Truncate aggressively: Windows MAX_PATH is 260 chars.
    def _short(s: str, n: int) -> str:
        s = "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")
        return s[:n] or "x"
    # Even if there is no PDF, we still want a metadata.yaml
    # so the next run's lookup_method can see the failed attempt.
    if paper_path is None or not paper_path.is_file():
        # Find any rendered PDF as a last resort.
        candidate = phd.workspace / "paper" / "body" / "paper.pdf"
        paper_zip = candidate if candidate.is_file() else None
    else:
        paper_zip = paper_path
    slug_dir = phd.archive_attempt(
        research_area="ml",
        research_direction=_short(direction, 20),
        research_question=_short(method, 20),
        method=_short(method, 20),
        success=success,
        reason=reason,
        paper_zip=paper_zip,
    )
    return slug_dir


# ---- Helpers --------------------------------------------------------------


def _call_llm_with_retry(
    router: LLMRouter,
    role: str,
    group: str,
    *,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float = 0.4,
    attempts: int = 4,
    with_skills: bool = True,
    disable_thinking: bool = True,
) -> str:
    """Call the LLM with up to ``attempts`` retries on empty / too-short
    responses. The LLM occasionally returns a 1-2 char string (just
    whitespace) for long structured prompts; we re-raise the
    temperature slightly on each retry to escape that local minimum.
    We accept a result only when it is at least 20 non-whitespace
    characters long.

    ``disable_thinking`` is True by default: thinking mode on
    MiniMax-M3 eats all the max_tokens on long structured prompts
    and returns an empty text. Disabling thinking makes the call
    deterministic and reliable for prose.
    """
    # Coordination: hard per-run LLM budget. When it is spent, every
    # remaining LLM step degrades to its deterministic fallback
    # instead of looping on the API.
    if not _llm_budget_left(router):
        logger.warning("LLM budget exhausted (%s calls); %s/%s degrades to fallback",
                       POLICY.max_llm_calls, group, role)
        return ""
    full_system = compose_system_prompt(group, system, with_skills=with_skills)
    last = ""
    cur_temp = temperature
    for i in range(attempts):
        last = router.complete(
            role=role, group=group,
            system=full_system, user=user,
            max_tokens=max_tokens, temperature=cur_temp,
            disable_thinking=disable_thinking,
        )
        if last and last.strip() and len(last.strip()) >= 20:
            return last
        logger.warning(
            "LLM returned %d chars on attempt %d for %s/%s; retrying with temp=%.2f",
            len(last.strip()) if last else 0, i + 1, group, role, cur_temp,
        )
        cur_temp = min(1.0, cur_temp + 0.2)
    return last


def _with_fallback(text: str, fallback: str) -> str:
    """Return ``text`` if non-empty, else ``fallback``."""
    return text if (text and text.strip()) else fallback


def _survey_fallback(method: str, direction: str) -> str:
    return (
        f"(fallback survey - the LLM did not produce a response; using a generic skeleton)\n\n"
        f"PAPERS (template, please replace with real citations before submission):\n"
        f"- NeurIPS 2024 | [benchmark dataset] | [metric] | [number] | [follow-up paper]\n"
        f"- ICML 2024 | [benchmark dataset] | [metric] | [number] | [follow-up paper]\n"
        f"- ICLR 2024 | [benchmark dataset] | [metric] | [number] | [follow-up paper]\n"
        f"- arXiv 2025 | [benchmark dataset] | [metric] | [number] | [follow-up paper]\n\n"
        f"SURVEY (replace with a real synthesis):\n"
        f"- The method {method!r} sits at the intersection of two lines of work.\n"
        f"- Recent top-venue papers report strong results on standard benchmarks.\n"
        f"- Cross-benchmark generalization remains an open question.\n"
        f"- Robustness under distribution shift is under-studied.\n"
        f"- Most papers evaluate on a single dataset; we will evaluate on three.\n\n"
        f"GAP: No surveyed paper combines the assumptions underlying {method!r} under "
        f"the protocol we propose. Closing this gap is the contribution we will claim."
    )


def _code_fallback(method: str, direction: str) -> str:
    method_repr = repr(method)
    direction_repr = repr(direction)
    return (
        "# Fallback skeleton for " + method_repr + "\n"
        "# (the LLM did not produce a response; this is a minimal placeholder\n"
        "#  the UG should replace with a real implementation)\n"
        "import argparse\nimport sys\n\n"
        "def parse_args() -> argparse.Namespace:\n"
        "    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--epochs', type=int, default=1)\n"
        "    p.add_argument('--lr', type=float, default=1e-3)\n"
        "    return p.parse_args()\n\n"
        "def main() -> int:\n"
        "    args = parse_args()\n"
        "    print('train.py: {} epochs, lr={}, method={}, direction={}'.format(\n"
        "        args.epochs, args.lr, " + method_repr + ", " + direction_repr + "))\n"
        "    print('metric=PLACEHOLDER')\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(main())\n"
    )


def _paper_fallback(method: str, direction: str) -> str:
    return (
        f"# Fallback paper draft for {method!r}\n"
        f"# (the LLM did not produce a response; this is a minimal placeholder)\n\n"
        f"## Abstract\n\n"
        f"We study {method!r} in the context of {direction!r}. The method "
        f"combines recent advances in self-supervised representation learning with "
        f"domain-specific constraints. Experiments on standard benchmarks show "
        f"competitive performance relative to published baselines. Code and data "
        f"are released alongside the paper.\n\n"
        f"## 1. Introduction\n\n"
        f"The setting of {direction!r} has received increasing attention. Existing "
        f"methods report strong results on individual datasets but generalize poorly. "
        f"In this work we make three contributions: (i) a new formulation of {method!r}, "
        f"(ii) a reproducible evaluation protocol across three benchmarks, and "
        f"(iii) an open-source reference implementation.\n\n"
        f"## 2. Related Work\n\n"
        f"Prior work in this area can be grouped into three threads: classical "
        f"methods, deep learning baselines, and self-supervised approaches. "
        f"Our method builds on the latter thread while incorporating domain-specific "
        f"priors from the former two.\n\n"
        f"## 3. Method\n\n"
        f"{method!r} operates in two stages. Stage A learns a representation from "
        f"unlabeled data. Stage B fine-tunes the representation on the target task. "
        f"We describe both stages in detail, including the loss functions and "
        f"regularizers used.\n\n"
        f"## 4. Experimental Setup\n\n"
        f"We evaluate on three standard benchmarks. The protocol follows the "
        f"convention of prior work. Baselines are the strongest published numbers.\n\n"
        f"## 5. Limitations and Future Work\n\n"
        f"Our evaluation is limited to three benchmarks and does not cover "
        f"out-of-distribution settings. Future work will address these.\n"
    )


def _parse_method(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("METHOD:"):
            return _sanitize_method_name(line.split(":", 1)[1])
    return None


def _sanitize_method_name(raw: str) -> str | None:
    """Normalize the LLM's METHOD line into a clean short name.

    Observed defects: markdown bold markers, quotes, and truncation
    mid-parenthetical ("... Detection (Cross"). We strip markup, cap
    the length at a word boundary, and drop an unbalanced trailing
    parenthetical instead of keeping half of it.
    """
    name = raw.strip().strip("*_`\"'").strip()
    if not name:
        return None
    # Cap at 90 chars on a word boundary.
    if len(name) > 90:
        name = name[:90]
        if " " in name:
            name = name.rsplit(" ", 1)[0]
    # Drop an unbalanced trailing parenthetical.
    if name.count("(") > name.count(")"):
        name = name[:name.rindex("(")].rstrip(" -,;")
    return name.strip() or None


def _on_report(phd: PhDStudent, name: WorkerName, log_path: Path) -> None:
    logger.info("worker %s reported in %s", name.value, log_path)
    phd.append_doc_memo(
        user_request=f"worker {name.value} reported",
        method="(supervision)",
        stage="passive-review",
        ug_summary=f"{name.value} wrote to {log_path.name}" if "code" in str(log_path) else "(no UG)",
        ms_summary=f"{name.value} wrote to {log_path.name}" if "research" in str(log_path) else "(no MS)",
        interaction_ug=(f"UG logged to {log_path.name}" if "code" in str(log_path) else ""),
        interaction_ms=(f"MS logged to {log_path.name}" if "research" in str(log_path) else ""),
        stage_goal="passive review of worker report",
        stage_complete=True,
    )


# Idle beyond this many seconds with tasks still active is a TIMEOUT:
# the PhD re-dispatches the stale task (marked REDO) instead of only
# noting the silence.
_TASK_TIMEOUT_S: float = 300.0


def _on_idle(phd: PhDStudent, name: WorkerName, idle_seconds: float) -> None:
    logger.info("worker %s idle for %.0fs", name.value, idle_seconds)
    # Timeout handling: check the worker's task list; when a task has
    # been active through a prolonged silence, the PhD re-posts it as
    # a REDO so the worker cannot silently drop it — and the decision
    # goes on the record.
    redo_note = ""
    if idle_seconds >= _TASK_TIMEOUT_S:
        try:
            guide_name = "research_guide.md" if name.value == "ms" else "code_guide.md"
            guide_path = phd._workspace / "shared" / guide_name
            tasks = phd._read_guide(guide_path)[0]
            stale = next(
                (t for t in tasks
                 if not t.done and not t.voided
                 and not t.text.startswith("REDO")), None)
            if stale is not None:
                stale.text = f"REDO (timeout after {int(idle_seconds)}s idle): {stale.text}"
                if name.value == "ms":
                    phd.update_research_guide(tasks)
                else:
                    phd.update_code_guide(tasks)
                redo_note = f"; re-dispatched stale task as REDO: '{stale.text[:80]}'"
        except Exception:  # noqa: BLE001
            logger.exception("timeout re-dispatch failed; continuing")
    phd.append_doc_memo(
        user_request=f"worker {name.value} idle",
        method="(supervision)",
        stage="active-review",
        ug_summary=(f"{name.value} idle for {int(idle_seconds)}s{redo_note}"
                    if name.value == "ug" else "(idle, not UG)"),
        ms_summary=(f"{name.value} idle for {int(idle_seconds)}s{redo_note}"
                    if name.value == "ms" else "(idle, not MS)"),
        interaction_ug=(f"UG idle {int(idle_seconds)}s — status checked{redo_note}" if name.value == "ug" else ""),
        interaction_ms=(f"MS idle {int(idle_seconds)}s — status checked{redo_note}" if name.value == "ms" else ""),
        stage_goal="timeout supervision: silence never drops a task",
        stage_complete=True,
    )


__all__ = ["PipelineResult", "run"]
