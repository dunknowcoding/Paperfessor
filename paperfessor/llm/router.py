"""LLM router: dispatches completion requests to the right provider.

The router is the only object the rest of Paperfessor interacts with.
It hides the litellm / provider-specific details and applies:

- API key retrieval (from the OS keychain, never from config).
- Per-agent-group model override (phd/ms/ug) with fallback to the
  project-wide ``model`` field.
- Per-agent-group and per-role token accounting.
- Observer fan-out so the GUI token dashboard updates live.
- Input truncation to ``max_input_tokens`` (tiktoken when available).
- Thinking-mode wiring (``adaptive`` on MiniMax-M3).
- Process-wide rate limiter: small delays between calls so a single
  survey or paper-writing run does not get throttled.
- Retry with exponential backoff on transient errors.
- Output redaction (defense in depth — strips any keys that might
  have leaked into model output).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from paperfessor.config import ProviderName, Settings
from paperfessor.llm.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    FinishReason,
    Role,
    Usage,
)
from paperfessor.llm.security import get_api_key

logger = logging.getLogger(__name__)


class _TransientError(RuntimeError):
    pass


_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "<redacted:openai-style-key>"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"), "<redacted:anthropic-key>"),
    (re.compile(r"sk-or-[A-Za-z0-9_-]{16,}"), "<redacted:openrouter-key>"),
    (re.compile(r"AIza[A-Za-z0-9_-]{16,}"), "<redacted:google-key>"),
    (re.compile(r"ghp_[A-Za-z0-9]{16,}"), "<redacted:github-token>"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{16,}"), "<redacted:github-fine-token>"),
    (re.compile(r"xai-[A-Za-z0-9_-]{16,}"), "<redacted:xai-key>"),
    (re.compile(r"\bAKIA[0-9A-Z]{12,}\b"), "<redacted:aws-access-key>"),
)


# Per-agent-group model field map. The router reads the field that
# matches the role's group, falling back to the project-wide ``model``.
_GROUP_TO_FIELD: dict[str, str] = {
    "phd": "phd_model",
    "ms": "ms_model",
    "ug": "ug_model",
}


class LLMRouter:
    """Provider-agnostic LLM dispatcher."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.RLock()
        self._token_totals = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
        self._group_usage = {
            g: {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
            for g in ("phd", "ms", "ug")
        }
        self._role_usage: dict[str, dict[str, int]] = {}
        self._usage_observers: list[Any] = []
        self._last_call: dict[str, Any] | None = None
        # Process-wide throttle: a small sleep between calls so a
        # tight loop (e.g. writing 6 paper sections) does not exceed
        # the provider's per-second budget and start returning empty.
        # Override via PAPERFESSOR_LLM_MIN_GAP_MS env var if needed.
        import os
        gap_ms = int(os.environ.get("PAPERFESSOR_LLM_MIN_GAP_MS", "1500"))
        self._min_gap_s: float = max(0.0, gap_ms / 1000.0)
        self._last_dispatch: float = 0.0

    # ---- Public API -----------------------------------------------------

    def add_usage_observer(self, fn: Any) -> None:
        with self._lock:
            self._usage_observers.append(fn)

    def remove_usage_observer(self, fn: Any) -> None:
        with self._lock:
            try:
                self._usage_observers.remove(fn)
            except ValueError:
                pass

    def usage_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "totals": dict(self._token_totals),
                "groups": {k: dict(v) for k, v in self._group_usage.items()},
                "roles": {k: dict(v) for k, v in self._role_usage.items()},
                "last_call": dict(self._last_call) if self._last_call else None,
            }

    def reset_usage(self) -> None:
        with self._lock:
            for k in self._token_totals:
                self._token_totals[k] = 0
            for g in self._group_usage.values():
                for k in g:
                    g[k] = 0
            self._role_usage.clear()
            self._last_call = None

    def complete(
        self,
        *,
        role: str,
        group: str,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
        disable_thinking: bool = False,
    ) -> str:
        """Synchronous text completion."""
        effective_max = max_tokens or self._settings.default_max_tokens
        max_input = int(
            getattr(self._settings, "max_input_tokens", 1_000_000) or 1_000_000
        )
        # Good defaults per deployment: cloud APIs take the maximum
        # input we can give them; LOCAL models (Ollama / llama.cpp)
        # would swap or OOM at 1M-token contexts, so unless the user
        # explicitly set PAPERFESSOR_MAX_INPUT_TOKENS we cap local
        # providers at a safe 32K.
        import os as _os
        provider_value = getattr(self._settings.provider, "value",
                                 str(self._settings.provider))
        if (provider_value in ("ollama", "llamacpp")
                and "PAPERFESSOR_MAX_INPUT_TOKENS" not in _os.environ
                and max_input > 32_768):
            max_input = 32_768
        system_budget = self._estimate_tokens(system)
        user_budget = max(0, max_input - system_budget - 64)
        user = self._truncate_to_tokens(user, user_budget)
        # Per-group model override -> project default.
        group_field = _GROUP_TO_FIELD.get(group)
        group_model = (
            getattr(self._settings, group_field, None) if group_field else None
        )
        resolved_model = (
            model
            or (group_model if isinstance(group_model, str) and group_model.strip() else None)
            or self._settings.model
        )
        request = ChatRequest(
            model=resolved_model,
            messages=[
                ChatMessage(role=Role.SYSTEM, content=system),
                ChatMessage(role=Role.USER, content=user),
            ],
            temperature=temperature if temperature is not None else 1.0,
            max_tokens=effective_max,
            stop=stop,
            response_format=response_format,
            metadata={
                "agent_role": role,
                "agent_group": group,
                "disable_thinking": disable_thinking,
            },
        )
        response = self._dispatch(
            request, role=role, group=group, model=resolved_model,
            disable_thinking=disable_thinking,
        )
        return _redact(response.text)

    def token_usage(self) -> dict[str, int]:
        with self._lock:
            return dict(self._token_totals)

    # ---- Internals ------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(_TransientError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _dispatch(
        self,
        request: ChatRequest,
        *,
        role: str,
        group: str,
        model: str | None,
        disable_thinking: bool = False,
    ) -> ChatResponse:
        # Throttle: enforce a small gap between successive LLM calls.
        # If the previous call happened < ``_min_gap_s`` ago, sleep
        # until the gap is satisfied. Cheap and avoids the
        # "many empty responses" failure mode we hit in the wild.
        if self._min_gap_s > 0:
            with self._lock:
                now = time.monotonic()
                wait = self._min_gap_s - (now - self._last_dispatch)
                if wait > 0:
                    time.sleep(wait)
                self._last_dispatch = time.monotonic()
        try:
            import litellm  # local import so missing dep surfaces here
        except ImportError as exc:
            raise LLMError("litellm is not installed; run `pip install litellm`") from exc

        # Per-agent provider/base_url: each group (phd/ms/ug) may point
        # at a different cloud or local module; falls back to the global.
        provider = self._provider_for_group(group)
        api_key = get_api_key(provider.value)
        base_url = self._base_url_for_group(group)
        kwargs = self._build_kwargs(
            provider, request, api_key, disable_thinking=disable_thinking,
            base_url=base_url,
        )

        try:
            response = litellm.completion(**kwargs)
        except Exception as exc:  # noqa: BLE001
            if _is_transient(exc):
                raise _TransientError(str(exc)) from exc
            raise LLMError(f"LLM call failed: {exc}") from exc

        chat_response = _normalize_litellm_response(
            response, provider=provider.value, model=model or request.model
        )
        self._record_usage(role=role, group=group, model=model or request.model, usage=chat_response.usage)
        return chat_response

    def _record_usage(self, *, role: str, group: str, model: str, usage: Usage) -> None:
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        total = int(getattr(usage, "total_tokens", 0) or 0) or (prompt + completion)
        snapshot: dict[str, Any] = {}
        observers: list[Any] = []
        with self._lock:
            self._token_totals["prompt"] += prompt
            self._token_totals["completion"] += completion
            self._token_totals["total"] += total
            self._token_totals["calls"] += 1
            gbucket = self._group_usage.setdefault(
                group, {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
            )
            gbucket["prompt"] += prompt
            gbucket["completion"] += completion
            gbucket["total"] += total
            gbucket["calls"] += 1
            rbucket = self._role_usage.setdefault(
                role, {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
            )
            rbucket["prompt"] += prompt
            rbucket["completion"] += completion
            rbucket["total"] += total
            rbucket["calls"] += 1
            snapshot = {
                "role": role,
                "group": group,
                "model": model,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
                "cumulative": {
                    "prompt": gbucket["prompt"],
                    "completion": gbucket["completion"],
                    "total": gbucket["total"],
                    "calls": gbucket["calls"],
                },
            }
            self._last_call = snapshot
            observers = list(self._usage_observers)
        for fn in observers:
            try:
                fn(snapshot)
            except Exception:  # noqa: BLE001
                logger.exception("usage observer raised; continuing")

    def _provider_for_group(self, group: str) -> ProviderName:
        """The provider for an agent group, falling back to the global."""
        field = f"{group}_provider" if group in ("phd", "ms", "ug") else ""
        val = getattr(self._settings, field, None) if field else None
        return val if val is not None else self._settings.provider

    def _base_url_for_group(self, group: str) -> str | None:
        """The base_url override for an agent group.

        Returns the explicit per-agent ``{group}_base_url`` if set;
        otherwise the global ``base_url`` ONLY when the group's provider
        matches the global provider (they are configured together). When
        a group uses a DIFFERENT provider, this returns None so
        ``_build_kwargs`` falls back to that provider's catalog URL
        rather than the global (e.g. MiniMax) endpoint.
        """
        field = f"{group}_base_url" if group in ("phd", "ms", "ug") else ""
        val = getattr(self._settings, field, None) if field else None
        if val:
            return val
        group_prov = getattr(self._settings, f"{group}_provider", None) \
            if group in ("phd", "ms", "ug") else None
        if group_prov is None or group_prov == self._settings.provider:
            return self._settings.base_url
        return None

    def _build_kwargs(
        self,
        provider: ProviderName,
        request: ChatRequest,
        api_key: str | None,
        *,
        disable_thinking: bool = False,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        messages = [{"role": m.role.value, "content": m.content} for m in request.messages]
        kwargs: dict[str, Any] = {
            "model": self._model_string(provider, request.model),
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if api_key:
            kwargs["api_key"] = api_key
        # api_base precedence: the resolved override (``base_url`` already
        # encodes the per-agent / provider-matched global URL, or None
        # when the group's provider differs from the global one) -> the
        # provider's catalog default -> the global setting. This lets
        # selecting e.g. DeepSeek "just work" without the user pasting its
        # endpoint URL, while never leaking the global MiniMax URL to a
        # different provider.
        effective_base = (
            base_url or self._catalog_base_url(provider)
            or self._settings.base_url
        )
        if effective_base:
            kwargs["api_base"] = effective_base
        kwargs["timeout"] = self._settings.request_timeout_seconds
        # Thinking-mode wiring is MiniMax-specific (extra_body.thinking).
        # Only send it to MiniMax — other providers (OpenAI, Anthropic,
        # Ollama, ...) reject an unknown extra_body field.
        if provider == ProviderName.MINIMAX:
            thinking_on = bool(getattr(self._settings, "thinking_mode", True))
            if disable_thinking or not thinking_on or bool(getattr(self._settings, "disable_reasoning", False)):
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            else:
                kwargs["extra_body"] = {"thinking": {"type": "adaptive"}}
        return kwargs

    # Providers reached through litellm's OpenAI-compatible path
    # (``openai/<model>`` + api_base). Robust for any OpenAI-compatible
    # endpoint regardless of whether litellm ships a native prefix.
    # (MiniMax keeps its existing ``minimax/`` routing — the tested
    # default — and is intentionally not listed here.)
    _OPENAI_COMPATIBLE: frozenset = frozenset({
        ProviderName.DEEPSEEK, ProviderName.MOONSHOT,
        ProviderName.QWEN, ProviderName.DOUBAO, ProviderName.ZHIPU,
        ProviderName.XAI, ProviderName.LLAMACPP, ProviderName.CUSTOM,
    })

    def _model_string(self, provider: ProviderName, model: str) -> str:
        if "/" in model:
            return model
        if provider in self._OPENAI_COMPATIBLE:
            return f"openai/{model}"
        return f"{provider.value}/{model}"

    def _catalog_base_url(self, provider: ProviderName) -> str | None:
        try:
            from paperfessor.llm.providers import get_provider_info
            info = get_provider_info(provider.value)
            return info.base_url_hint if info else None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        try:
            import tiktoken  # type: ignore

            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:  # noqa: BLE001
            return max(1, len(text) // 4)

    @staticmethod
    def _truncate_to_tokens(text: str, budget: int) -> str:
        """Head+tail truncation that cuts at PARAGRAPH boundaries.

        A blind mid-token cut leaves half-sentences that derail the
        model's reading; snapping the cut points to the nearest
        newline keeps both retained parts coherent, and the marker
        states exactly how much was omitted so the model knows its
        context is incomplete rather than silently corrupted.
        """
        if budget <= 0 or not text:
            return ""
        try:
            import tiktoken  # type: ignore

            enc = tiktoken.get_encoding("cl100k_base")
            ids = enc.encode(text)
            if len(ids) <= budget:
                return text
            head_n = budget // 2
            tail_n = budget - head_n - 16
            head = enc.decode(ids[:head_n])
            tail = enc.decode(ids[-tail_n:])
        except Exception:  # noqa: BLE001
            char_budget = budget * 4
            if len(text) <= char_budget:
                return text
            half = char_budget // 2
            head, tail = text[:half], text[-half:]
        # Snap to paragraph/line boundaries (drop the ragged edge).
        nl = head.rfind("\n")
        if nl > len(head) * 0.6:
            head = head[:nl]
        nl = tail.find("\n")
        if 0 <= nl < len(tail) * 0.4:
            tail = tail[nl + 1:]
        omitted = len(text) - len(head) - len(tail)
        return (
            head
            + f"\n\n[... {omitted} characters omitted here; the text "
            f"resumes at a later section ...]\n\n"
            + tail
        )


# ---- Helpers ---------------------------------------------------------------


class LLMError(RuntimeError):
    pass


def _is_transient(exc: BaseException) -> bool:
    msg = str(exc).lower()
    needles = (
        "rate limit", "timeout", "temporarily", "service unavailable",
        "high load", "overloaded", "server is overloaded",
        " 5", " 408", " 409", " 425", " 429", " 500",
        " 502", " 503", " 504", " 529",
        # Network-level transients (observed: a single TLS
        # bad-record-mac hiccup killed an otherwise healthy run).
        "ssl", "bad record mac", "connection reset", "connection aborted",
        "connectionerror", "apiconnectionerror", "read timed out",
        "remote end closed",
    )
    return any(n in msg for n in needles)


def _normalize_litellm_response(response: Any, *, provider: str, model: str) -> ChatResponse:
    try:
        choice = response.choices[0]
        text = getattr(choice.message, "content", None) or ""
        finish = _coerce_finish_reason(getattr(choice, "finish_reason", None) or "stop")
        u = getattr(response, "usage", None)
        usage = Usage(
            prompt_tokens=int(getattr(u, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(u, "completion_tokens", 0) or 0),
            total_tokens=int(getattr(u, "total_tokens", 0) or 0),
        )
        return ChatResponse(text=text, finish_reason=finish, usage=usage, model=model,
                            provider=provider, raw=_safe_raw(response))
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"could not parse provider response: {exc}") from exc


def _coerce_finish_reason(value: Any) -> FinishReason:
    s = str(value).lower()
    if s in ("length", "max_tokens"):
        return FinishReason.LENGTH
    if s in ("tool_calls", "tool_call"):
        return FinishReason.TOOL_CALL
    if s in ("content_filter", "safety"):
        return FinishReason.CONTENT_FILTER
    if s in ("error", "stop_error"):
        return FinishReason.ERROR
    return FinishReason.STOP


def _safe_raw(response: Any) -> dict[str, Any]:
    try:
        import json
        return json.loads(response.json() if hasattr(response, "json") else str(response))
    except Exception:  # noqa: BLE001
        return {"_unparsed": True}


def _redact(text: str) -> str:
    out = text
    for pattern, replacement in _REDACT_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


# ---- Default factory ------------------------------------------------------


_default_router: LLMRouter | None = None
_default_lock = threading.Lock()


def get_default_router() -> LLMRouter:
    global _default_router
    with _default_lock:
        if _default_router is None:
            from paperfessor.config import load_settings
            _default_router = LLMRouter(load_settings())
        return _default_router


def reset_default_router() -> None:
    global _default_router
    with _default_lock:
        _default_router = None


__all__ = ["LLMError", "LLMRouter", "get_default_router", "reset_default_router"]
