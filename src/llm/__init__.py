"""LLM subsystem: types, providers, security, router, and discovery."""

from src.llm.base import (
    ChatMessage, ChatRequest, ChatResponse, FinishReason, Role, ToolCall, Usage,
)
from src.llm.discovery import list_models, pick_default_model
from src.llm.providers import (
    PROVIDER_CATALOG, ProviderInfo, get_provider_info, list_providers,
)
from src.llm.router import (
    LLMError, LLMRouter, get_default_router, reset_default_router,
)
from src.llm.security import (
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
