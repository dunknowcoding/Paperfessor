"""Paperfessor settings.

Configuration is loaded from environment variables (prefix
``PAPERFESSOR_``) and a YAML file at ``<user_data_dir>/config.yaml``.
API keys are NEVER read from these sources — they live in the OS
keychain via :mod:`src.llm.security`.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderName(str, Enum):
    MINIMAX = "minimax"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    LLAMACPP = "llamacpp"
    CUSTOM = "custom"


class Depth(str, Enum):
    SHALLOW = "shallow"
    NORMAL = "normal"
    DEEP = "deep"


class Theme(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PAPERFESSOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General -----------------------------------------------------------
    language: str = "en"
    theme: Theme = Theme.AUTO
    font_size: int = Field(default=10, ge=8, le=24)
    telemetry_enabled: bool = False
    display_style: str = Field(default="default")
    display_color: str = Field(default="auto")

    # --- LLM ---------------------------------------------------------------
    provider: ProviderName = ProviderName.MINIMAX
    model: str = "MiniMax-M3"
    base_url: str | None = "https://api.minimax.io/v1"
    request_timeout_seconds: int = Field(default=120, ge=5, le=600)
    max_retries: int = Field(default=3, ge=0, le=10)
    default_max_tokens: int = Field(default=32768, ge=256, le=128000)
    max_input_tokens: int = Field(default=1_000_000, ge=1024, le=1_000_000)
    thinking_mode: bool = True
    disable_reasoning: bool = False
    fast_model: str | None = None
    # Per-agent overrides (v0.4)
    phd_model: str = "MiniMax-M3"
    ms_model: str = "MiniMax-M3"
    ug_model: str = "MiniMax-M3"

    # --- Research ----------------------------------------------------------
    depth: Depth = Depth.NORMAL
    target_venue: str | None = None
    output_language: str = "en"
    max_papers_in_review: int = Field(default=30, ge=5, le=200)
    innovation_target_venue_tier: Literal["A*", "A", "B", "C"] = "A"

    # --- Paper / experiment loop ------------------------------------------
    paper_format: str = "latex"
    paper_template: str = "neurips"
    paper_authors: list[str] = Field(default_factory=list)
    paper_max_pages: int = Field(default=9, ge=4, le=40)
    use_gpu: bool = True
    gpu_device: str = "auto"
    max_iterations: int = Field(default=8, ge=1, le=64)
    compute_budget_minutes: int = Field(default=120, ge=1, le=10080)
    hpo_trials: int = Field(default=20, ge=0, le=500)
    reproduce_baselines: bool = True

    venue_requirements: dict[str, object] = Field(
        default_factory=lambda: {
            "name": "neurips_2026",
            "page_limit_main": 9,
            "page_limit_appendix": "unlimited",
            "anonymized": True,
            "requires_ethics_section": True,
            "requires_paper_checklist": True,
            "keywords_required": True,
            "min_keywords": 5,
            "max_keywords": 7,
            "abstract_max_words": 200,
        }
    )

    # --- Memory ------------------------------------------------------------
    long_term_memory_enabled: bool = True
    auto_compress_conversations: bool = True
    short_term_window_tokens: int = Field(default=8000, ge=1000)

    # --- Output ------------------------------------------------------------
    output_root: Path = Field(default=Path("./output"))

    # --- UG permissions (user-controlled; defaults ALL enabled) -----------
    # Two layers: (1) the strict sandbox for GENERATED experiment
    # code (network/file/shell never whitelistable there); (2) the
    # UG agent's own TOOLBELT — local tool execution (matlab -batch,
    # Rscript, office/plotting CLIs, zip, tests), package installs,
    # editing/inspecting its own code — every use logged to
    # code_log.md and confined to the workspace.
    ug_allow_gpu: bool = True            # permit torch+CUDA when justified
    ug_allow_local_tools: bool = True    # run_tool(): local CLIs (no shell=True)
    ug_allow_installs: bool = True       # pip_install(): recorded in src/tools
    ug_sandbox_timeout_seconds: int = Field(default=240, ge=30, le=3600)
    ug_tool_timeout_seconds: int = Field(default=300, ge=10, le=3600)
    ug_extra_allowed_imports: str = ""   # comma-separated, e.g. "numba,jax"

    # --- Coordination (full user control via CLI --flags / GUI) -----------
    # Bounds for every agent loop. Defaults favor quality on cloud
    # APIs; lower them for cheaper/faster runs.
    max_method_rounds: int = Field(default=3, ge=1, le=10)
    max_ug_rounds: int = Field(default=5, ge=1, le=10)
    max_section_redrafts: int = Field(default=1, ge=0, le=5)
    max_inspection_rounds: int = Field(default=3, ge=1, le=10)
    max_llm_calls: int = Field(default=85, ge=5, le=1000)

    # --- v0.4: workspace ----------------------------------------------------
    auto_bootstrap_workspace: bool = True

    @field_validator("language", "output_language")
    @classmethod
    def _normalize_language(cls, value: str) -> str:
        return value.strip().replace("_", "-")


def load_settings() -> Settings:
    """Build a Settings instance from env + YAML."""
    return Settings()
