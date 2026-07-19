"""Provider routing: each cloud provider reaches its own endpoint."""

from __future__ import annotations

from paperfessor.config import ProviderName, load_settings
from paperfessor.llm.base import ChatMessage, ChatRequest, Role
from paperfessor.llm.providers import get_provider_info, list_providers
from paperfessor.llm.router import LLMRouter


def _kwargs(prov: ProviderName, model: str):
    s = load_settings()
    r = LLMRouter(s)
    req = ChatRequest(
        model=model,
        messages=[ChatMessage(role=Role.USER, content="hi")],
        temperature=1.0, max_tokens=8,
    )
    return r._build_kwargs(prov, req, "key")


def test_new_providers_route_to_their_own_endpoint():
    cases = {
        ProviderName.DEEPSEEK: ("openai/deepseek-chat", "api.deepseek.com"),
        ProviderName.MOONSHOT: ("openai/kimi", "api.moonshot"),
        ProviderName.QWEN: ("openai/qwen-max", "dashscope"),
        ProviderName.ZHIPU: ("openai/glm-4.5", "bigmodel.cn"),
        ProviderName.DOUBAO: ("openai/doubao-x", "volces.com"),
        ProviderName.XAI: ("openai/grok-2-latest", "api.x.ai"),
    }
    for prov, (model_prefix, host) in cases.items():
        model = model_prefix.split("/", 1)[1]
        kw = _kwargs(prov, model)
        assert kw["model"] == f"openai/{model}"
        assert host in kw["api_base"]


def test_minimax_routing_unchanged():
    kw = _kwargs(ProviderName.MINIMAX, "MiniMax-M3")
    assert kw["model"] == "minimax/MiniMax-M3"
    assert "minimax.io" in kw["api_base"]
    assert "extra_body" in kw  # thinking wiring stays MiniMax-only


def test_all_providers_have_a_default_model():
    for info in list_providers():
        assert info.default_model
        assert get_provider_info(info.slug) is info
