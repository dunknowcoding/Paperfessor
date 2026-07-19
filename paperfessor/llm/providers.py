"""Per-provider catalog (used by the router, the GUI, and the
``paperfessor models`` CLI command).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    slug: str
    base_url_hint: str | None
    default_model: str
    requires_api_key: bool
    supports_local: bool
    notes: str


PROVIDER_CATALOG: dict[str, ProviderInfo] = {
    "minimax": ProviderInfo(
        name="MiniMax",
        slug="minimax",
        base_url_hint="https://api.minimax.io/v1",
        default_model="MiniMax-M3",
        requires_api_key=True,
        supports_local=False,
        notes=(
            "MiniMax direct API (OpenAI-compatible). Default model "
            "MiniMax-M3 supports thinking-mode prefill. Users supply "
            "their own key in the OS keychain."
        ),
    ),
    "openai": ProviderInfo(
        name="OpenAI", slug="openai", base_url_hint=None,
        default_model="gpt-4o", requires_api_key=True, supports_local=False,
        notes="OpenAI public API.",
    ),
    "anthropic": ProviderInfo(
        name="Anthropic", slug="anthropic", base_url_hint=None,
        default_model="claude-3-5-sonnet-latest", requires_api_key=True,
        supports_local=False, notes="Anthropic Claude API.",
    ),
    "google": ProviderInfo(
        name="Google", slug="google", base_url_hint=None,
        default_model="gemini-1.5-pro", requires_api_key=True,
        supports_local=False, notes="Google AI Studio / Vertex AI.",
    ),
    "deepseek": ProviderInfo(
        name="DeepSeek", slug="deepseek",
        base_url_hint="https://api.deepseek.com/v1",
        default_model="deepseek-chat", requires_api_key=True,
        supports_local=False,
        notes="DeepSeek API (OpenAI-compatible). Models: deepseek-chat, "
              "deepseek-reasoner.",
    ),
    "moonshot": ProviderInfo(
        name="Moonshot (Kimi)", slug="moonshot",
        base_url_hint="https://api.moonshot.cn/v1",
        default_model="kimi-k2-0905-preview", requires_api_key=True,
        supports_local=False,
        notes="Moonshot / Kimi API (OpenAI-compatible). Use "
              "api.moonshot.ai/v1 for the international endpoint.",
    ),
    "qwen": ProviderInfo(
        name="Qwen (Alibaba DashScope)", slug="qwen",
        base_url_hint="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-max", requires_api_key=True,
        supports_local=False,
        notes="Alibaba Qwen via DashScope OpenAI-compatible endpoint. "
              "Use dashscope-intl.aliyuncs.com for the international region.",
    ),
    "doubao": ProviderInfo(
        name="Doubao (ByteDance Volcengine)", slug="doubao",
        base_url_hint="https://ark.cn-beijing.volces.com/api/v3",
        default_model="doubao-pro-32k", requires_api_key=True,
        supports_local=False,
        notes="ByteDance Doubao via Volcengine Ark (OpenAI-compatible). "
              "The model is usually a provisioned endpoint id.",
    ),
    "zhipu": ProviderInfo(
        name="Zhipu (GLM)", slug="zhipu",
        base_url_hint="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4.5", requires_api_key=True,
        supports_local=False,
        notes="Zhipu GLM (OpenAI-compatible). Models: glm-4.5, glm-4-plus.",
    ),
    "xai": ProviderInfo(
        name="xAI (Grok)", slug="xai",
        base_url_hint="https://api.x.ai/v1",
        default_model="grok-2-latest", requires_api_key=True,
        supports_local=False,
        notes="xAI Grok API (OpenAI-compatible).",
    ),
    "ollama": ProviderInfo(
        name="Ollama (local)", slug="ollama",
        base_url_hint="http://localhost:11434", default_model="llama3.1",
        requires_api_key=False, supports_local=True,
        notes="Local Ollama daemon.",
    ),
    "llamacpp": ProviderInfo(
        name="llama.cpp (local server)", slug="llamacpp",
        base_url_hint="http://localhost:8080", default_model="local",
        requires_api_key=False, supports_local=True,
        notes="llama.cpp server with OpenAI-compatible /v1 endpoint.",
    ),
    "custom": ProviderInfo(
        name="Custom OpenAI-compatible", slug="custom", base_url_hint=None,
        default_model="custom", requires_api_key=True, supports_local=False,
        notes="Any OpenAI-compatible endpoint. Set base_url and model.",
    ),
}


def get_provider_info(slug: str) -> ProviderInfo | None:
    return PROVIDER_CATALOG.get(slug.strip().lower())


def list_providers() -> list[ProviderInfo]:
    return list(PROVIDER_CATALOG.values())


__all__ = ["PROVIDER_CATALOG", "ProviderInfo", "get_provider_info", "list_providers"]
