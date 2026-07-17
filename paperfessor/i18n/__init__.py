"""Minimal i18n: loads one of the bundled JSON locales, exposes ``t()``.

The locale is chosen from the ``PAPERFESSOR_LANGUAGE`` env var
or the ``Settings.language`` field, falling back to ``en``.
The :func:`set_language` call forces a re-load (used by the GUI
when the user changes the language in the Settings tab).
"""

from __future__ import annotations

import json
import locale as _locale
import threading
from pathlib import Path
from typing import Any

_LOCALE_DIR: Path = Path(__file__).resolve().parent / "locales"
_FALLBACK_LANG: str = "en"
_lock = threading.RLock()
_current_lang: str = _FALLBACK_LANG
_strings: dict[str, Any] = {}


def _load(lang: str) -> dict[str, Any]:
    path = _LOCALE_DIR / f"{lang}.json"
    if not path.is_file():
        path = _LOCALE_DIR / f"{_FALLBACK_LANG}.json"
        lang = _FALLBACK_LANG
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {}
    return data


def detect_system_language() -> str:
    """Return the system's preferred language code if it matches a
    bundled locale, else ``en``.
    """
    candidates: list[str] = []
    try:
        loc = _locale.getlocale()[0] or ""
        if loc:
            candidates.append(loc.replace("_", "-"))
            candidates.append(loc.split("_")[0])
    except Exception:  # noqa: BLE001
        pass
    for c in candidates:
        if (_LOCALE_DIR / f"{c}.json").is_file():
            return c
    return _FALLBACK_LANG


def set_language(lang: str) -> None:
    """Force the active locale and refresh the in-memory strings."""
    global _current_lang, _strings
    with _lock:
        _current_lang = lang
        _strings = _load(lang)


def current_language() -> str:
    return _current_lang


def t(key: str, /, **kwargs: Any) -> str:
    """Look up ``key`` (dot-separated) and format it with ``kwargs``."""
    with _lock:
        s = _strings
    parts = key.split(".")
    for p in parts:
        if isinstance(s, dict) and p in s:
            s = s[p]
        else:
            return key  # missing key: return the key itself
    if isinstance(s, str) and kwargs:
        try:
            return s.format(**kwargs)
        except Exception:  # noqa: BLE001
            return s
    return s if isinstance(s, str) else key


# Bootstrap from settings (env or default).
try:
    from paperfessor.config import load_settings
    set_language(load_settings().language)
except Exception:  # noqa: BLE001
    set_language(_FALLBACK_LANG)


__all__ = ["current_language", "detect_system_language", "set_language", "t"]
