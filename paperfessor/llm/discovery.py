"""Model auto-discovery for cloud and local providers.

Used by the GUI's Settings tab and the ``paperfessor models`` CLI
command to populate the model picker without forcing the user to
type a name from memory.

Two endpoints are exercised:

- **OpenAI-compatible** (MiniMax, OpenAI, Google, llamacpp, custom):
  ``GET {base_url}/models`` -> ``{"data": [{"id": "..."}, ...]}``
- **Ollama** (native): ``GET {base_url}/api/tags`` ->
  ``{"models": [{"name": "..."}, ...]}``
"""

from __future__ import annotations

import json
import logging
import random
import urllib.error
import urllib.request
from typing import Final

logger = logging.getLogger(__name__)

_OLLAMA_DEFAULT_URL: Final[str] = "http://localhost:11434"
_LLAMACPP_DEFAULT_URL: Final[str] = "http://localhost:8080"
_OPENAI_COMPATIBLE: Final[frozenset[str]] = frozenset(
    {"minimax", "openai", "google", "custom"}
)
_ANTHROPIC_CURATED: Final[tuple[str, ...]] = (
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
    "claude-3-opus-latest",
)


def list_models(
    provider: str,
    base_url: str | None,
    api_key: str | None,
    *,
    timeout: float = 8.0,
) -> list[str]:
    """Return a list of model IDs available for ``provider``."""
    slug = (provider or "").strip().lower()
    if not slug:
        return []
    if slug == "ollama":
        return _list_ollama(base_url or _OLLAMA_DEFAULT_URL, timeout=timeout)
    if slug == "llamacpp":
        return _list_openai_compatible(
            _ensure_v1(base_url or _LLAMACPP_DEFAULT_URL), api_key=None, timeout=timeout
        )
    if slug == "anthropic":
        return list(_ANTHROPIC_CURATED)
    if slug in _OPENAI_COMPATIBLE:
        url = _ensure_v1(base_url or "")
        if not url:
            return []
        return _list_openai_compatible(url, api_key=api_key, timeout=timeout)
    return []


def pick_default_model(provider: str, models: list[str]) -> str | None:
    """Pick a sensible default. Cloud = latest by score; local = random."""
    slug = (provider or "").strip().lower()
    if not models:
        return None
    if slug in ("ollama", "llamacpp"):
        return random.choice(models)
    scored = sorted(models, key=_cloud_model_score, reverse=True)
    return scored[0]


def _list_openai_compatible(base_url: str, *, api_key: str | None, timeout: float) -> list[str]:
    if not base_url:
        return []
    url = base_url.rstrip("/") + "/models"
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        logger.debug("models list failed for %s: %s", url, exc)
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    items = data.get("data") or data.get("models") if isinstance(data, dict) else data if isinstance(data, list) else []
    out: list[str] = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            mid = item.get("id") or item.get("name")
            if isinstance(mid, str) and mid:
                out.append(mid)
    seen: set[str] = set()
    deduped: list[str] = []
    for m in out:
        if m not in seen:
            seen.add(m)
            deduped.append(m)
    return deduped


def _list_ollama(base_url: str, *, timeout: float) -> list[str]:
    if not base_url:
        return []
    url = base_url.rstrip("/") + "/api/tags"
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        logger.debug("ollama tags failed: %s", exc)
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    items = data.get("models") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if isinstance(name, str) and name:
            out.append(name)
    seen: set[str] = set()
    deduped: list[str] = []
    for m in out:
        if m not in seen:
            seen.add(m)
            deduped.append(m)
    return deduped


def _cloud_model_score(name: str) -> tuple[int, int, int, str]:
    n = name.lower()
    version = 0
    digits = ""
    for ch in n:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    if digits:
        try:
            version = int(digits)
        except ValueError:
            version = 0
    recency = 0
    if "latest" in n:
        recency = 3
    elif "preview" in n or "exp" in n:
        recency = 2
    elif "stable" in n:
        recency = 1
    thinking = 0
    if any(t in n for t in ("m3", "o1", "o3", "r1", "thinking", "reasoning", "opus")):
        thinking = 1
    return (version, recency, thinking, n)


def _ensure_v1(url: str) -> str:
    if not url:
        return ""
    base = url.rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1"):
        if base.endswith(suffix):
            return base[: -len(suffix)] + "/v1"
    if base.endswith("/v1"):
        return base
    return base + "/v1"


__all__ = ["list_models", "pick_default_model"]
