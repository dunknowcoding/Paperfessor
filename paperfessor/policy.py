"""Hard and soft boundaries for the Paperfessor agents.

The developer sets the BOUNDARIES; the agents adapt WITHIN them.

- HARD boundaries are enforced by code (gates, audits, sandboxes).
  No agent decision, prompt, or topic can cross them. They are also
  told to the agents so behavior aligns with enforcement.
- SOFT boundaries are defaults. The PhD may adapt them per research
  topic — different fields need different metrics, section
  conventions, acceleration policies, and theory/experiment balance —
  but every adaptation must be DECLARED (recorded in doc_memo) so
  supervision can audit it. An undeclared deviation is treated as a
  defect.
"""

from __future__ import annotations

HARD_BOUNDARIES: tuple[tuple[str, str], ...] = (
    ("no fabricated numbers, data, or citations",
     "measured-token scan, citation cross-check, competitiveness gate"),
    ("benchmark data must be real public downloads with recorded licenses",
     "dataset loaders raise on failure; synthetic manifests rejected"),
    ("no private information, local paths, or project-internal names in the paper",
     "whole-paper privacy scan + appendix redactor"),
    ("stay within the per-run budgets (LLM calls, retry rounds)",
     "CoordinationPolicy caps at every loop"),
    ("experiment code runs sandboxed: no network, no file I/O, no shell",
     "static check + subprocess harness with timeout"),
    ("reports must match the artifacts they describe",
     "PhD ground-truth audits of research_log / code_log"),
    ("results are reported honestly: losses stated plainly, ties never called wins",
     "computed WIN/TIE/LOSS labels pinned into every writer prompt"),
)

SOFT_BOUNDARIES: tuple[tuple[str, str], ...] = (
    ("evaluation metrics",
     "default: best-F1 / AUROC / AUPRC (anomaly detection); adapt to the "
     "topic's standard metrics as established by the survey (e.g. RMSE "
     "for forecasting, BLEU for translation, wall-clock for speed topics)"),
    ("acceleration policy",
     "default: CPU; GPU only for measured heavy workloads; adapt freely "
     "when the topic itself concerns runtime/efficiency — then hardware "
     "is unrestricted and wall-clock becomes a first-class metric"),
    ("theory/experiment balance",
     "default: core theory <= ~1.5 body pages, overflow to appendix; "
     "adapt for theory-centric venues where proofs ARE the contribution"),
    ("section structure",
     "default: Abstract/Intro/Related/Method/Experiments/Analysis/"
     "Conclusion/Limitations; adapt to the discipline's conventions "
     "(e.g. separate Theory section, Case Study section)"),
    ("figure and table conventions",
     "default: colorblind-safe palette, booktabs tables, figure* for "
     "wide figures; adapt to explicit venue style rules when they differ"),
)


# Topic behavior rules — HARD per topic class. The matcher keywords
# select the class from the research direction; each rule is stated
# with its enforcement so agents and code stay aligned. Topics that
# match no class get only the global hard boundaries.
TOPIC_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    # Speed / efficiency topics
    (("speed", "latency", "throughput", "efficien", "accelerat",
      "real-time", "realtime", "runtime", "lightweight"),
     ("wall-clock time MUST be measured and reported for every compared "
      "method on the same machine (enforced: runtime column in results)",
      "hardware is unrestricted BUT must be disclosed per method "
      "(enforced: hardware record in results.json protocol)")),
    # Anomaly detection topics
    (("anomaly", "outlier", "fault detection", "intrusion"),
     ("evaluation uses labeled test sets with threshold-free metrics "
      "plus best-F1 (enforced: experiment runner protocol)",
      "no training on test labels; thresholds selected without test "
      "fitting beyond the stated sweep protocol (enforced: runner)")),
    # Forecasting / temporal prediction topics
    (("forecast", "prediction horizon", "predictive"),
     ("no future leakage: training data strictly precedes evaluation "
      "data (enforced: contiguous-split loaders)",
      "error-based metrics (RMSE/MAE) are the primary evidence; "
      "without a registered protocol, experiments are honestly "
      "reported as pending (enforced: domain-dataset gate)")),
    # Theory-centric topics
    (("theorem", "proof", "complexity bound", "convergence analysis"),
     ("every formal claim is either proved or explicitly labeled a "
      "conjecture; no empirical claim without a run behind it "
      "(enforced: measured-number scan)",)),
    # Survey / review topics
    (("survey", "review of", "systematic literature"),
     ("no novel-method claims; the contribution is coverage and "
      "organization, and the corpus count is stated exactly "
      "(enforced: pinned corpus count)",)),
)


def topic_rules_for(direction: str) -> tuple[str, ...]:
    """The hard topic rules matching ``direction`` (may be empty)."""
    d = (direction or "").lower()
    out: list[str] = []
    for keywords, rules in TOPIC_RULES:
        if any(k in d for k in keywords):
            out.extend(rules)
    return tuple(out)


def render_boundaries_prompt(direction: str | None = None) -> str:
    """Compact boundary block injected into every agent system prompt.

    With a ``direction``, matched topic-class HARD rules are included;
    when NO class matches (a novel topic), the block says so
    explicitly and routes the agent to the soft-adaptation path: the
    survey establishes the field's norms, the PhD adapts the soft
    defaults to them, and every adaptation is declared.
    """
    hard = "; ".join(h for h, _ in HARD_BOUNDARIES)
    soft = " | ".join(f"{name}: {rule}" for name, rule in SOFT_BOUNDARIES)
    block = (
        "## Boundaries\n\n"
        f"HARD (code-enforced, never negotiable): {hard}.\n\n"
        "SOFT (defaults you may adapt to the research topic — but every "
        "adaptation must be declared and recorded in doc_memo; an "
        f"undeclared deviation is a defect): {soft}"
    )
    if direction is not None:
        rules = topic_rules_for(direction)
        if rules:
            block += (
                "\n\nTOPIC RULES (hard, for this research topic): "
                + "; ".join(rules)
            )
        else:
            block += (
                "\n\nTOPIC RULES: no predefined topic class matches this "
                "direction. Adapt the SOFT defaults to the field's norms "
                "as established by the literature survey (metrics, "
                "protocol, structure), declare each adaptation, and keep "
                "every HARD boundary intact."
            )
    return block


__all__ = ["HARD_BOUNDARIES", "SOFT_BOUNDARIES", "render_boundaries_prompt"]
