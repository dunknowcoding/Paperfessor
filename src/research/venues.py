"""Venue template orchestration.

The PhD agent uses this module to:
1. Pick the right target venue for a research direction
   (:func:`pick_target_venue`).
2. Download the official .cls / .sty template for that venue from
   the venue's own download URL, falling back to acmart [sigconf]
   when the venue is ACM-aligned or when the download fails
   (:func:`download_venue_template`).
3. Verify the template is loadable and report the page-limit
   constraint (:func:`verify_venue_template`).

Templates are cached at ``workspace/paper/templates/`` so subsequent
runs do not re-download.
"""

from __future__ import annotations

import dataclasses
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from src.research.sources.venue_index import (
    page_limit_for_venue,
    primary_venue_for_direction,
    venue_label,
)

logger = logging.getLogger(__name__)


# Per-venue template metadata. The "url" is the official .sty/.cls
# download; "class" is the LaTeX class name to invoke. The page
# limit is read from :func:`page_limit_for_venue` so the article_memo
# can report it.
#
# A few of these URLs are best-effort; the host may move them. If
# the download fails we fall back to acmart [sigconf], which has
# the same 2-column look as most CS conferences.

@dataclasses.dataclass(frozen=True)
class VenueTemplate:
    venue_id: str          # OpenAlex source id
    venue_name: str        # short label, e.g. "NeurIPS 2026"
    venue_full: str        # long label, e.g. "Neural Information Processing Systems"
    class_name: str        # LaTeX class to invoke, e.g. "neurips_2026"
    page_limit: int        # main-text page limit
    template_url: str | None
    template_filename: str # local file name, e.g. "neurips_2026.sty"
    fallback_class: str    # class to use if download fails


# Curated mapping. Each entry pairs the OpenAlex id with the
# canonical home venue's template.
_VENUE_TEMPLATES: dict[str, VenueTemplate] = {
    # NeurIPS 2026
    "s4210195363": VenueTemplate(
        venue_id="s4210195363",
        venue_name="NeurIPS 2026",
        venue_full="Conference on Neural Information Processing Systems",
        class_name="neurips_2026",
        page_limit=9,
        template_url="https://media.neurips.cc/Conferences/NeurIPS2026/Styles/neurips_2026.sty",
        template_filename="neurips_2026.sty",
        fallback_class="acmart-sigconf",
    ),
    # ICML 2026
    "s4306419644": VenueTemplate(
        venue_id="s4306419644",
        venue_name="ICML 2026",
        venue_full="International Conference on Machine Learning",
        class_name="icml2026",
        page_limit=9,
        template_url="http://icml.cc/Conferences/2026/Styles/icml2026.sty",
        template_filename="icml2026.sty",
        fallback_class="acmart-sigconf",
    ),
    # ICLR 2026
    "s4210172783": VenueTemplate(
        venue_id="s4210172783",
        venue_name="ICLR 2026",
        venue_full="International Conference on Learning Representations",
        class_name="iclr2026_conference",
        page_limit=9,
        template_url="https://iclr.cc/Conferences/2026/ICLR2026_Style/conference.zip",
        template_filename="iclr2026_conference.sty",
        fallback_class="acmart-sigconf",
    ),
    # CVPR 2026
    "s4210226001": VenueTemplate(
        venue_id="s4210226001",
        venue_name="CVPR 2026",
        venue_full="IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        class_name="cvpr",
        page_limit=8,
        template_url="https://cvpr.thecvf.com/Conferences/2026/cvpr_2026_style_guide.zip",
        template_filename="cvpr.sty",
        fallback_class="acmart-sigconf",
    ),
    # ICCV 2026
    "s4210205404": VenueTemplate(
        venue_id="s4210205404",
        venue_name="ICCV 2026",
        venue_full="IEEE/CVF International Conference on Computer Vision",
        class_name="iccv",
        page_limit=8,
        template_url=None,
        template_filename="iccv.sty",
        fallback_class="acmart-sigconf",
    ),
    # ACL 2026
    "s4210212456": VenueTemplate(
        venue_id="s4210212456",
        venue_name="ACL 2026",
        venue_full="Annual Meeting of the Association for Computational Linguistics",
        class_name="acl",
        page_limit=8,
        template_url="https://acl-org.github.io/ACLPUB/formatting.html",
        template_filename="acl_latex.sty",
        fallback_class="acmart-sigconf",
    ),
    # EMNLP 2026
    "s4210225364": VenueTemplate(
        venue_id="s4210225364",
        venue_name="EMNLP 2026",
        venue_full="Conference on Empirical Methods in Natural Language Processing",
        class_name="emnlp",
        page_limit=8,
        template_url=None,
        template_filename="emnlp2026.sty",
        fallback_class="acmart-sigconf",
    ),
    # NAACL
    "s4210223919": VenueTemplate(
        venue_id="s4210223919",
        venue_name="NAACL 2026",
        venue_full="North American Chapter of the ACL",
        class_name="naacl",
        page_limit=8,
        template_url=None,
        template_filename="naacl2026.sty",
        fallback_class="acmart-sigconf",
    ),
    # KDD 2026 - ACM, use acmart sigconf
    "s4210200925": VenueTemplate(
        venue_id="s4210200925",
        venue_name="KDD 2026",
        venue_full="ACM SIGKDD Conference on Knowledge Discovery and Data Mining",
        class_name="acmart-sigconf",
        page_limit=9,
        template_url=None,
        template_filename="acmart.cls",
        fallback_class="acmart-sigconf",
    ),
    # AAAI 2026
    "s4210196385": VenueTemplate(
        venue_id="s4210196385",
        venue_name="AAAI 2026",
        venue_full="AAAI Conference on Artificial Intelligence",
        class_name="aaai26",
        page_limit=7,
        template_url="https://aaai.org/conference/aaai-26/aaai-26-style-files/",
        template_filename="aaai26.sty",
        fallback_class="acmart-sigconf",
    ),
    # IJCAI 2026
    "s4210191938": VenueTemplate(
        venue_id="s4210191938",
        venue_name="IJCAI 2026",
        venue_full="International Joint Conference on Artificial Intelligence",
        class_name="ijcai26",
        page_limit=7,
        template_url=None,
        template_filename="ijcai26.sty",
        fallback_class="acmart-sigconf",
    ),
    # UAI
    "s4210224017": VenueTemplate(
        venue_id="s4210224017",
        venue_name="UAI 2026",
        venue_full="Conference on Uncertainty in Artificial Intelligence",
        class_name="uai2026",
        page_limit=9,
        template_url=None,
        template_filename="uai2026.sty",
        fallback_class="acmart-sigconf",
    ),
    # AISTATS
    "s4210197613": VenueTemplate(
        venue_id="s4210197613",
        venue_name="AISTATS 2026",
        venue_full="International Conference on Artificial Intelligence and Statistics",
        class_name="aistats2026",
        page_limit=9,
        template_url=None,
        template_filename="aistats2026.sty",
        fallback_class="acmart-sigconf",
    ),
    # ICRA 2026
    "s4210197765": VenueTemplate(
        venue_id="s4210197765",
        venue_name="ICRA 2026",
        venue_full="IEEE International Conference on Robotics and Automation",
        class_name="icra2026",
        page_limit=8,
        template_url=None,
        template_filename="icra2026.sty",
        fallback_class="acmart-sigconf",
    ),
    # IROS
    "s4210221676": VenueTemplate(
        venue_id="s4210221676",
        venue_name="IROS 2026",
        venue_full="IEEE/RSJ International Conference on Intelligent Robots and Systems",
        class_name="iros2026",
        page_limit=8,
        template_url=None,
        template_filename="iros2026.sty",
        fallback_class="acmart-sigconf",
    ),
}


# ---- Public API --------------------------------------------------------


def pick_target_venue(direction: str) -> VenueTemplate:
    """Pick the right target venue for ``direction``.

    Returns the :class:`VenueTemplate` with the venue id, name,
    class file, page limit, and download URL. If the direction does
    not match any keyword, returns the generic NeurIPS template as
    a safe default.
    """
    venue_id = primary_venue_for_direction(direction)
    if venue_id in _VENUE_TEMPLATES:
        return _VENUE_TEMPLATES[venue_id]
    # Default to NeurIPS template
    return _VENUE_TEMPLATES["s4210195363"]


def all_known_venues() -> Iterable[VenueTemplate]:
    """All venues we know the template metadata for."""
    return list(_VENUE_TEMPLATES.values())


def download_venue_template(template: VenueTemplate, dest_dir: Path,
                            *, timeout: float = 30.0) -> Path | None:
    """Download ``template``'s official .cls/.sty to ``dest_dir``.

    Returns the local file path on success, ``None`` on failure.
    The caller is expected to fall back to ``template.fallback_class``
    when the download fails.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / template.template_filename
    if target.is_file() and target.stat().st_size > 100:
        return target
    if template.template_url is None:
        return None
    try:
        import requests
        resp = requests.get(
            template.template_url,
            headers={"User-Agent": "Paperfessor/0.4 (research)"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(
                "venue template download failed: %s -> HTTP %d",
                template.template_url, resp.status_code,
            )
            return None
        target.write_bytes(resp.content)
        if target.stat().st_size < 100:
            target.unlink()
            return None
        return target
    except Exception as exc:  # noqa: BLE001
        logger.warning("venue template download raised: %s", exc)
        return None


def verify_venue_template(template: VenueTemplate, dest_dir: Path,
                          *, pdflatex_bin: str | None = None) -> bool:
    """Smoke-test that the template compiles with a trivial doc.

    Returns True on success, False on any compile error.
    """
    target = dest_dir / template.template_filename
    if not target.is_file():
        return False
    test_tex = dest_dir / "_venue_check.tex"
    test_tex.write_text(
        f"\\documentclass{{{template.class_name}}}\n"
        f"\\begin{{document}}\\title{{T}}\\author{{A}}\\maketitle Test.\\end{{document}}\n",
        encoding="utf-8",
    )
    if pdflatex_bin is None:
        pdflatex_bin = shutil.which("pdflatex")
    if not pdflatex_bin:
        candidates = [
            r"H:\texlive\2026\bin\windows\pdflatex.exe",
        ]
        for c in candidates:
            if Path(c).is_file():
                pdflatex_bin = c
                break
    if not pdflatex_bin:
        return False
    try:
        subprocess.run(
            [pdflatex_bin, "-interaction=nonstopmode", "-halt-on-error",
             test_tex.name],
            cwd=str(dest_dir),
            capture_output=True, timeout=60,
        )
        ok = (dest_dir / "_venue_check.pdf").is_file()
        return ok
    except Exception:  # noqa: BLE001
        return False
    finally:
        for ext in (".aux", ".log", ".out", ".pdf"):
            p = dest_dir / f"_venue_check{ext}"
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass


def get_class_name(template: VenueTemplate, dest_dir: Path) -> tuple[str, str]:
    """Return (class_name, source) where source is 'downloaded' or 'fallback'."""
    target = dest_dir / template.template_filename
    if target.is_file() and target.stat().st_size > 100:
        return template.class_name, "downloaded"
    return template.fallback_class, "fallback"


__all__ = [
    "VenueTemplate",
    "all_known_venues",
    "download_venue_template",
    "get_class_name",
    "pick_target_venue",
    "verify_venue_template",
]
