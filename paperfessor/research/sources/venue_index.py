"""Curated venue index.

The user spec says the MS agent should treat *top conferences/journals*
as the primary theoretical reference, not arXiv-only. This module
hard-codes a small, vetted mapping from a research direction to the
OpenAlex ``source`` ids of the venues that matter for that direction.

The MS agent uses this as a filter: ``search + venue filter = papers
from NeurIPS / ICML / ICLR / KDD / ...``, instead of the noisy full-
text search that OpenAlex defaults to. The index is intentionally
short; it is easy to extend by adding a new entry to ``_DIRECTION_TO_VENUES``.

Why not just free-text search? OpenAlex's free-text ranking puts
the most-cited paper overall at the top regardless of query. With
~5-10 venue filters per direction, the MS gets a usable list of
candidate papers in one call.
"""

from __future__ import annotations

# OpenAlex ``source`` ids (the trailing token of the URL).
# Each venue id was verified at construction time; the format is the
# trailing token of ``https://openalex.org/S<digits>``.
NEURIPS_S: str = "S4210195363"        # Neural Information Processing Systems
ICML_S: str = "S4306419644"           # International Conference on Machine Learning
ICLR_S: str = "S4210172783"           # International Conference on Learning Representations
CVPR_S: str = "S4210226001"           # IEEE/CVF Conference on Computer Vision and Pattern Recognition
ICCV_S: str = "S4210205404"           # IEEE/CVF International Conference on Computer Vision
ECCV_S: str = "S4210198630"           # European Conference on Computer Vision
ACL_S: str = "S4210212456"            # Association for Computational Linguistics (ACL)
EMNLP_S: str = "S4210225364"          # Empirical Methods in Natural Language Processing
NAACL_S: str = "S4210223919"          # North American Chapter of the ACL
KDD_S: str = "S4210200925"            # ACM SIGKDD Conference on Knowledge Discovery and Data Mining
AAAI_S: str = "S4210196385"           # AAAI Conference on Artificial Intelligence
IJCAI_S: str = "S4210191938"          # International Joint Conference on Artificial Intelligence
UAI_S: str = "S4210224017"            # Uncertainty in Artificial Intelligence
AISTATS_S: str = "S4210197613"        # Artificial Intelligence and Statistics
ICRA_S: str = "S4210197765"           # IEEE International Conference on Robotics and Automation
IROS_S: str = "S4210221676"           # IEEE/RSJ International Conference on Intelligent Robots and Systems

# Map from research direction keyword(s) -> list of OpenAlex source ids.
# The MS agent picks the direction by substring-matching the user
# direction against the keys; the first match wins. Add a new entry
# to add coverage.
_DIRECTION_TO_VENUES: dict[str, tuple[str, ...]] = {
    # NLP / language
    "language": (ACL_S, EMNLP_S, NAACL_S, NEURIPS_S, ICLR_S, ICML_S, AAAI_S),
    "nlp": (ACL_S, EMNLP_S, NAACL_S, NEURIPS_S, ICLR_S, ICML_S, AAAI_S),
    "text": (ACL_S, EMNLP_S, NAACL_S, NEURIPS_S, ICLR_S, ICML_S, AAAI_S),
    "transformer": (ACL_S, EMNLP_S, NEURIPS_S, ICLR_S, ICML_S, ACL_S),
    "llm": (ACL_S, EMNLP_S, NAACL_S, NEURIPS_S, ICLR_S, ICML_S),
    # Vision
    "vision": (CVPR_S, ICCV_S, ECCV_S, NEURIPS_S, ICLR_S, ICML_S, AAAI_S),
    "image": (CVPR_S, ICCV_S, ECCV_S, NEURIPS_S, ICLR_S, ICML_S, AAAI_S),
    "object detection": (CVPR_S, ICCV_S, ECCV_S, NEURIPS_S, ICLR_S),
    "segmentation": (CVPR_S, ICCV_S, ECCV_S, MICCAI_S := "S4210227321"),
    # Time-series / anomaly
    "anomaly": (KDD_S, ICDM_S := "S4210212468", NEURIPS_S, ICML_S, ICLR_S, AAAI_S),
    "time series": (KDD_S, ICDM_S, NEURIPS_S, ICML_S, ICLR_S, AAAI_S),
    "forecasting": (KDD_S, ICDM_S, NEURIPS_S, ICML_S, ICLR_S),
    # Graph / network
    "graph": (NEURIPS_S, ICML_S, ICLR_S, KDD_S, WWW_S := "S4210203992", AAAI_S),
    "network": (NEURIPS_S, ICML_S, ICLR_S, KDD_S, WWW_S, AAAI_S),
    # Reinforcement learning
    "reinforcement": (NEURIPS_S, ICML_S, ICLR_S, AAAI_S, IJCAI_S, ICRA_S, IROS_S, AAMAS_S := "S4210217540"),
    "rl": (NEURIPS_S, ICML_S, ICLR_S, AAAI_S, IJCAI_S, ICRA_S, IROS_S, AAMAS_S),
    # Robotics
    "robot": (ICRA_S, IROS_S, NEURIPS_S, ICML_S, ICLR_S, RSS_S := "S4210212245", AAAI_S),
    # AutoML / optimization
    "automl": (NEURIPS_S, ICML_S, ICLR_S, GECCO_S := "S4210195711", AAAI_S),
    "hyperparameter": (NEURIPS_S, ICML_S, ICLR_S, GECCO_S, AAAI_S, AISTATS_S),
    "neural architecture": (NEURIPS_S, ICML_S, ICLR_S, AAAI_S, CVPR_S, ICCV_S, ECCV_S),
    "nas": (NEURIPS_S, ICML_S, ICLR_S, AAAI_S, CVPR_S, ICCV_S, ECCV_S),
    # General ML (catch-all)
    "federated": (NEURIPS_S, ICML_S, ICLR_S, AAAI_S, IJCAI_S, AISTATS_S, KDD_S),
    "differential privacy": (NEURIPS_S, ICML_S, ICLR_S, AAAI_S, AISTATS_S),
    "adversarial": (NEURIPS_S, ICML_S, ICLR_S, CVPR_S, AAAI_S),
    "robust": (NEURIPS_S, ICML_S, ICLR_S, CVPR_S, ICCV_S, ECCV_S, AAAI_S),
    "generative": (NEURIPS_S, ICML_S, ICLR_S, CVPR_S, ICCV_S, ECCV_S, AAAI_S),
    "diffusion": (NEURIPS_S, ICML_S, ICLR_S, CVPR_S, ICCV_S, ECCV_S, AAAI_S),
    "vae": (NEURIPS_S, ICML_S, ICLR_S, AISTATS_S, AAAI_S),
    "gan": (NEURIPS_S, ICML_S, ICLR_S, CVPR_S, ICCV_S, ECCV_S, AAAI_S),
    "bayesian": (NEURIPS_S, ICML_S, ICLR_S, AISTATS_S, UAI_S, AAAI_S),
}

# A safety net: if no direction keyword matches, fall back to the
# general top-ML list.
_DEFAULT_VENUES: tuple[str, ...] = (
    NEURIPS_S, ICML_S, ICLR_S, AAAI_S, IJCAI_S, KDD_S, AISTATS_S, UAI_S,
)


def venues_for_direction(direction: str) -> tuple[str, ...]:
    """Return the OpenAlex source ids for the venues relevant to ``direction``.

    Matching is case-insensitive substring. The first matching key
    wins. If nothing matches, returns :data:`_DEFAULT_VENUES`.
    """
    d = direction.lower()
    for keyword, venues in _DIRECTION_TO_VENUES.items():
        if keyword in d:
            return venues
    return _DEFAULT_VENUES


def venue_label(source_id: str) -> str:
    """Map an OpenAlex source id back to a short human-readable label."""
    table: dict[str, str] = {
        NEURIPS_S: "NeurIPS", ICML_S: "ICML", ICLR_S: "ICLR",
        CVPR_S: "CVPR", ICCV_S: "ICCV", ECCV_S: "ECCV",
        ACL_S: "ACL", EMNLP_S: "EMNLP", NAACL_S: "NAACL",
        KDD_S: "KDD", AAAI_S: "AAAI", IJCAI_S: "IJCAI",
        UAI_S: "UAI", AISTATS_S: "AISTATS",
        ICRA_S: "ICRA", IROS_S: "IROS",
    }
    return table.get(source_id, source_id)


# ---- Primary target venue for the paper itself -------------------------

# Each direction keyword maps to the *single* best target venue for
# the paper. The PhD writes the paper targeting this venue; the MS
# uses the broader list above to find related work. The mapping
# picks the venue that is the canonical home for the topic — not
# just "any top venue that has published on it". This matters
# because the user spec says the paper should target the right
# venue for the research direction, not a generic one.

_DIRECTION_TO_PRIMARY_VENUE: dict[str, str] = {
    # NLP / language
    "language": ACL_S, "nlp": ACL_S, "text": ACL_S,
    "transformer": NEURIPS_S, "llm": ACL_S, "machine translation": ACL_S,
    "dialogue": ACL_S, "question answering": ACL_S, "summarization": ACL_S,
    "speech": EMNLP_S,
    # Vision
    "vision": CVPR_S, "image": CVPR_S, "object detection": CVPR_S,
    "segmentation": CVPR_S, "video": CVPR_S, "face": CVPR_S,
    "3d": CVPR_S,
    # Time-series / anomaly
    "anomaly": KDD_S, "outlier": KDD_S, "time series": KDD_S,
    "forecasting": KDD_S, "fraud": KDD_S, "iot": KDD_S,
    "wearable": KDD_S, "sensor": KDD_S,
    # Graph / network
    "graph": KDD_S, "network": KDD_S, "knowledge graph": KDD_S,
    # Reinforcement learning
    "reinforcement": NEURIPS_S, "rl": NEURIPS_S, "robot": ICRA_S,
    "manipulation": ICRA_S,
    # AutoML / NAS
    "automl": ICML_S, "hyperparameter": ICML_S,
    "neural architecture": ICLR_S, "nas": ICLR_S,
    # Generative / robustness
    "federated": ICML_S, "differential privacy": ICML_S,
    "adversarial": NEURIPS_S, "robust": ICML_S,
    "generative": NEURIPS_S, "diffusion": NEURIPS_S,
    "vae": ICML_S, "gan": NEURIPS_S, "bayesian": AISTATS_S,
    "normalizing flow": ICML_S, "energy-based": ICML_S,
    "contrastive": NEURIPS_S, "self-supervised": NEURIPS_S,
    "few-shot": NEURIPS_S, "meta-learning": NEURIPS_S,
    "transfer learning": NEURIPS_S,
    "recommender": KDD_S, "retrieval": KDD_S,
    "search": KDD_S, "ranking": KDD_S,
    "causal": NEURIPS_S, "fairness": ICML_S,
    "interpretability": NEURIPS_S, "explainability": NEURIPS_S,
}


def primary_venue_for_direction(direction: str) -> str:
    """Pick the single best target venue for ``direction``.

    The PhD uses this to set the venue title in the .tex preamble
    and to populate the ``模版检查`` field of article_memo. If the
    direction matches no keyword, we return the first venue of the
    broader ``venues_for_direction`` list (which is the most
    domain-specific venue we know for the topic).
    """
    d = direction.lower()
    # Explicit user override first: if the direction mentions a
    # specific venue name ("submit to NeurIPS", "for KDD"), use it.
    for vname, sid in {
        "neurips": NEURIPS_S, "icml": ICML_S, "iclr": ICLR_S,
        "cvpr": CVPR_S, "iccv": ICCV_S, "eccv": ECCV_S,
        "acl": ACL_S, "emnlp": EMNLP_S, "naacl": NAACL_S,
        "kdd": KDD_S, "aaai": AAAI_S, "ijcai": IJCAI_S,
        "uai": UAI_S, "aistats": AISTATS_S,
    }.items():
        if vname in d:
            return sid
    for keyword, vid in _DIRECTION_TO_PRIMARY_VENUE.items():
        if keyword in d:
            return vid
    return venues_for_direction(direction)[0]


def page_limit_for_venue(source_id: str) -> int:
    """Page limit (body, excluding references) for a venue.

    Defaults to 9 if the venue is not in the table. These are the
    main-text limits; many venues have additional appendix room.
    """
    table: dict[str, int] = {
        NEURIPS_S: 9, ICML_S: 9, ICLR_S: 9,
        CVPR_S: 8, ICCV_S: 8, ECCV_S: 8,
        ACL_S: 8, EMNLP_S: 8, NAACL_S: 8,
        KDD_S: 9, AAAI_S: 7, IJCAI_S: 7,
        UAI_S: 9, AISTATS_S: 9,
        ICRA_S: 8, IROS_S: 8,
    }
    return table.get(source_id, 9)


__all__ = [
    "page_limit_for_venue",
    "primary_venue_for_direction",
    "venue_label",
    "venues_for_direction",
]
