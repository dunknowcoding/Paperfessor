"""LLM subsystem: types, providers, security, router, and discovery."""

from paperfessor.llm.base import (
    ChatMessage, ChatRequest, ChatResponse, FinishReason, Role, ToolCall, Usage,
)
from paperfessor.llm.discovery import list_models, pick_default_model
from paperfessor.llm.providers import (
    PROVIDER_CATALOG, ProviderInfo, get_provider_info, list_providers,
)
from paperfessor.llm.router import (
    LLMError, LLMRouter, get_default_router, reset_default_router,
)
from paperfessor.llm.security import (
    SecretStoreError, delete_api_key, get_api_key, has_api_key,
    list_configured_providers, set_api_key,
)

__all__ = [
    "ChatMessage", "ChatRequest", "ChatResponse",
    "FinishReason", "LLMError", "LLMRouter", "PROVIDER_CATALOG",
    "ProviderInfo", "Role", "SecretStoreError", "ToolCall", "Usage",
    "delete_api_key", "get_api_key", "get_default_router",
    "get_provider_info", "has_api_key", "list_configured_providers",
    "list_models", "list_providers", "pick_default_model",
    "reset_default_router", "set_api_key",
]
