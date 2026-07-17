"""Paperfessor CLI (built on Typer)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from paperfessor._meta import __version__
from paperfessor.cli.display import (
    VALID_COLORS,
    VALID_STYLES,
    banner,
    info as display_info,
    kv_table as display_kv_table,
    make_styled_console,
    metrics_table as display_metrics_table,
    section as display_section,
    success as display_success,
    warning as display_warning,
)
from paperfessor.config import ProviderName, load_settings
from paperfessor.i18n import t
from paperfessor.llm.discovery import list_models, pick_default_model
from paperfessor.llm.router import get_default_router
from paperfessor.paths import ensure_dirs, memory_db_path, workspace_dir

app = typer.Typer(
    name="paperfessor",
    help="Research direction to full project, end-to-end.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    invoke_without_command=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"paperfessor {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Print the version and exit.",
    ),
    display_style: Optional[str] = typer.Option(
        None, "--display-style",
        help=f"CLI display style: {' | '.join(VALID_STYLES)}",
    ),
    display_color: Optional[str] = typer.Option(
        None, "--display-color",
        help=f"CLI color scheme: {' | '.join(VALID_COLORS)}",
    ),
) -> None:
    if display_style:
        os.environ["PAPERFESSOR_DISPLAY_STYLE"] = display_style
    if display_color:
        os.environ["PAPERFESSOR_DISPLAY_COLOR"] = display_color


config_app = typer.Typer(help="Show and edit Paperfessor config.")
key_app = typer.Typer(help="Manage API keys in the OS keychain.")
display_app = typer.Typer(help="Configure the CLI display style.")
models_app = typer.Typer(help="Discover and pick LLM models.")
soul_app = typer.Typer(help="Show the SOUL.")
memory_app = typer.Typer(help="Inspect the long-term memory (SQLite).")
workspace_app = typer.Typer(help="Manage the runtime workspace.")
app.add_typer(config_app, name="config")
app.add_typer(key_app, name="key")
app.add_typer(display_app, name="display")
app.add_typer(models_app, name="models")
app.add_typer(soul_app, name="soul")
app.add_typer(memory_app, name="memory")
app.add_typer(workspace_app, name="workspace")


def _console() -> Console:
    style = os.environ.get("PAPERFESSOR_DISPLAY_STYLE")
    color = os.environ.get("PAPERFESSOR_DISPLAY_COLOR")
    if not style or not color:
        try:
            s = load_settings()
            style = style or s.display_style or "default"
            color = color or s.display_color or "auto"
        except Exception:  # noqa: BLE001
            style = style or "default"
            color = color or "auto"
    return make_styled_console(style=style, color=color)


def _err_console() -> Console:
    con = _console()
    con.file = sys.stderr  # type: ignore[attr-defined]
    return con


console = make_styled_console("default", "auto")
err_console = make_styled_console("default", "auto")


def _setup_logging(verbose: bool) -> None:
    import logging
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(message)s", datefmt="[%X]",
        handlers=[RichHandler(console=_err_console(), rich_tracebacks=True)],
    )


# ---- run ------------------------------------------------------------------


@app.command()
def run(
    direction: str = typer.Argument(..., help=t("direction.placeholder")),
    depth: Optional[str] = typer.Option(None, "--depth", "-d", help="shallow | normal | deep"),
    venue: Optional[str] = typer.Option(None, "--venue", "-v", help="Target venue"),
    language: Optional[str] = typer.Option(None, "--language", "-l", help="en | zh-CN | ja"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model ID"),
    phd_model: Optional[str] = typer.Option(None, "--phd-model"),
    ms_model: Optional[str] = typer.Option(None, "--ms-model"),
    ug_model: Optional[str] = typer.Option(None, "--ug-model"),
    thinking: Optional[bool] = typer.Option(None, "--thinking/--no-thinking"),
    max_input_tokens: Optional[int] = typer.Option(None, "--max-input-tokens"),
    max_output_tokens: Optional[int] = typer.Option(None, "--max-output-tokens"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
) -> None:
    """Start a new 3-agent run from a research direction."""
    _setup_logging(verbose)
    if language:
        from paperfessor.i18n import set_language
        set_language(language)
    settings = load_settings()
    if depth and depth in ("shallow", "normal", "deep"):
        from paperfessor.config import Depth
        settings.depth = Depth(depth)
    if venue:
        settings.target_venue = venue
    if language:
        settings.output_language = language
        settings.language = language
    if provider:
        try:
            settings.provider = ProviderName(provider.lower())
        except ValueError:
            err_console.print(f"[danger]x[/danger] unknown provider '{provider}'")
            raise typer.Exit(code=1) from None
    if model:
        settings.model = model
    if phd_model:
        settings.phd_model = phd_model
    if ms_model:
        settings.ms_model = ms_model
    if ug_model:
        settings.ug_model = ug_model
    if thinking is not None:
        settings.thinking_mode = thinking
        settings.disable_reasoning = not thinking
    if max_input_tokens is not None:
        settings.max_input_tokens = max_input_tokens
    if max_output_tokens is not None:
        settings.default_max_tokens = max_output_tokens
    ensure_dirs()

    con = _console()
    banner(con, direction=direction)
    display_info(con, f"starting run for: {direction}")

    router = get_default_router()
    # Hot-swap the router's settings to the overrides the user just set.
    router._settings = settings  # type: ignore[attr-defined]

    from paperfessor.runner.pipeline import run as pipeline_run
    result = pipeline_run(direction, settings=settings, router=router)
    display_section(
        con, "run finished",
        [
            ("direction", result.direction),
            ("started", result.started_at),
            ("finished", result.finished_at),
            ("status", result.status),
            ("note", result.note or "-"),
        ],
    )


# ---- display --------------------------------------------------------------


@display_app.command("show")
def display_show() -> None:
    settings = load_settings()
    con = _console()
    display_kv_table(con, [
        ("style", settings.display_style),
        ("color", settings.display_color),
        ("available styles", ", ".join(VALID_STYLES)),
        ("available colors", ", ".join(VALID_COLORS)),
    ], title="CLI display settings")


@display_app.command("set")
def display_set(
    style: Optional[str] = typer.Option(None, "--style"),
    color: Optional[str] = typer.Option(None, "--color"),
) -> None:
    if not style and not color:
        ec = _err_console()
        ec.print("[danger]x[/danger] pass --style and/or --color")
        raise typer.Exit(code=1) from None
    if style and style not in VALID_STYLES:
        ec = _err_console()
        ec.print(f"[danger]x[/danger] invalid style '{style}'; choose from {VALID_STYLES}")
        raise typer.Exit(code=1) from None
    if color and color not in VALID_COLORS:
        ec = _err_console()
        ec.print(f"[danger]x[/danger] invalid color '{color}'; choose from {VALID_COLORS}")
        raise typer.Exit(code=1) from None
    if style:
        os.environ["PAPERFESSOR_DISPLAY_STYLE"] = style
    if color:
        os.environ["PAPERFESSOR_DISPLAY_COLOR"] = color
    settings = load_settings()
    if style:
        settings.display_style = style
    if color:
        settings.display_color = color
    con = _console()
    display_success(con, f"display set: style={settings.display_style} color={settings.display_color}")


# ---- models ---------------------------------------------------------------


@models_app.command("list")
def models_list(
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
) -> None:
    settings = load_settings()
    slug = (provider or settings.provider.value).lower()
    api_key = None
    if slug not in ("ollama", "llamacpp", "anthropic"):
        from paperfessor.llm.security import get_api_key
        api_key = get_api_key(slug)
    models = list_models(slug, settings.base_url, api_key)
    con = _console()
    if not models:
        con.print(f"[warning]![/warning] no live models discovered for '{slug}'")
        return
    table_args: list[tuple[str, str, str, str]] = [
        (str(i), m, "", "") for i, m in enumerate(models, 1)
    ]
    display_metrics_table(con, table_args, title=f"Models for {slug}")


@models_app.command("pick")
def models_pick(
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="phd | ms | ug"),
) -> None:
    settings = load_settings()
    slug = (provider or settings.provider.value).lower()
    api_key = None
    if slug not in ("ollama", "llamacpp", "anthropic"):
        from paperfessor.llm.security import get_api_key
        api_key = get_api_key(slug)
    models = list_models(slug, settings.base_url, api_key)
    pick = pick_default_model(slug, models)
    if not pick:
        ec = _err_console()
        ec.print(f"[danger]x[/danger] no model could be picked for '{slug}'")
        raise typer.Exit(code=1) from None
    if group:
        g = group.lower()
        field = {"phd": "phd_model", "ms": "ms_model", "ug": "ug_model"}.get(g)
        if not field:
            ec = _err_console()
            ec.print(f"[danger]x[/danger] unknown group '{group}'; use phd|ms|ug")
            raise typer.Exit(code=1) from None
        setattr(settings, field, pick)
        con = _console()
        display_success(con, f"set {field} = {pick}")
    else:
        settings.model = pick
        con = _console()
        display_success(con, f"set model = {pick}")


# ---- key ------------------------------------------------------------------


@key_app.command("set")
def key_set(
    provider: str = typer.Argument(...),
    api_key: str = typer.Option(..., "--key", "-k", prompt=True, hide_input=True),
) -> None:
    from paperfessor.llm.security import set_api_key
    set_api_key(provider, api_key)
    con = _console()
    display_success(con, f"stored key for provider '{provider}' in OS keychain")


@key_app.command("list")
def key_list() -> None:
    from paperfessor.llm.security import list_configured_providers
    providers = list_configured_providers()
    con = _console()
    if not providers:
        con.print("[warning]![/warning] no API keys configured")
        return
    for p in providers:
        con.print(f"  - {p}")


@key_app.command("test")
def key_test(provider: str = typer.Argument(...)) -> None:
    from paperfessor.llm.security import has_api_key
    if not has_api_key(provider):
        ec = _err_console()
        ec.print(f"[danger]x[/danger] no key for provider '{provider}'")
        raise typer.Exit(code=1) from None
    settings = load_settings()
    try:
        settings.provider = ProviderName(provider.lower())
    except ValueError:
        ec = _err_console()
        ec.print(f"[danger]x[/danger] unknown provider '{provider}'")
        raise typer.Exit(code=1) from None
    router = get_default_router()
    router._settings = settings  # type: ignore[attr-defined]
    reply = router.complete(
        role="director", group="phd",
        system="Connectivity test. Reply with the single word: OK",
        user="ping", max_tokens=8,
    )
    con = _console()
    display_success(con, f"OK: {reply.strip()[:80]}")


# ---- config ---------------------------------------------------------------


@config_app.command("show")
def config_show() -> None:
    settings = load_settings()
    rows = []
    for fname, v in settings.model_dump().items():
        if isinstance(v, list):
            v = ", ".join(map(str, v))
        rows.append((fname, str(v)))
    con = _console()
    display_kv_table(con, rows, title="Paperfessor config")


# ---- memory ---------------------------------------------------------------


@memory_app.command("stats")
def memory_stats() -> None:
    """Show aggregate counts in the long-term memory DB."""
    from paperfessor.agents import PhDStudent
    from paperfessor.llm.router import get_default_router
    from paperfessor.paths import workspace_dir
    settings = load_settings()
    router = get_default_router()
    phd = PhDStudent(settings, router, workspace_dir())
    con = _console()
    display_kv_table(con, [(k, str(v)) for k, v in phd.memory_stats().items()], title="memory stats")


@memory_app.command("runs")
def memory_runs(limit: int = typer.Option(20, "--limit", "-n")) -> None:
    """List recent runs (most-recent first)."""
    from paperfessor.agents import PhDStudent
    from paperfessor.llm.router import get_default_router
    from paperfessor.paths import workspace_dir
    settings = load_settings()
    router = get_default_router()
    phd = PhDStudent(settings, router, workspace_dir())
    rows = [
        (str(r["id"]), r["started_at"], r["status"], r["method"], r["direction"][:60])
        for r in phd.list_runs(limit=limit)
    ]
    if not rows:
        con = _console()
        con.print("[muted](no runs yet)[/muted]")
        return
    con = _console()
    display_metrics_table(con, rows, title=f"recent runs (last {len(rows)})")


@memory_app.command("archived")
def memory_archived(limit: int = typer.Option(20, "--limit", "-n")) -> None:
    """List archived attempts from the long-term memory DB."""
    from paperfessor.agents import PhDStudent
    from paperfessor.llm.router import get_default_router
    from paperfessor.paths import workspace_dir
    settings = load_settings()
    router = get_default_router()
    phd = PhDStudent(settings, router, workspace_dir())
    rows = [
        (
            str(a["id"]),
            a["archived_at"],
            "ok" if a["success"] else "fail",
            a["method"],
            a["research_direction"][:60],
        )
        for a in phd.list_archived_db(limit=limit)
    ]
    if not rows:
        con = _console()
        con.print("[muted](no archived attempts yet)[/muted]")
        return
    con = _console()
    display_metrics_table(con, rows, title=f"archived attempts (last {len(rows)})")


# ---- workspace ------------------------------------------------------------


@workspace_app.command("reset")
def workspace_reset(
    fresh_owner: bool = typer.Option(
        False,
        "--fresh-owner",
        help="Clear archived attempts and the SQLite memory DB too.",
    ),
) -> None:
    """Reset the active workspace for a new paper or a fresh takeover."""
    from paperfessor.workspace_reset import hard_reset_workspace, prepare_workspace_for_new_paper

    if fresh_owner:
        path = hard_reset_workspace()
        message = "workspace hard-reset; memos, logs, archived attempts, and memory DB were cleared"
    else:
        path = prepare_workspace_for_new_paper()
        message = "workspace prepared for a new paper; archive, datasets, tools, and memory DB were preserved"
    con = _console()
    display_success(con, message)
    display_info(con, f"workspace: {path}")


# ---- soul -----------------------------------------------------------------


@soul_app.command("show")
def soul_show() -> None:
    from paperfessor._meta import SOUL_PATH, soul_sha256
    if not SOUL_PATH.is_file():
        ec = _err_console()
        ec.print(f"[danger]x[/danger] SOUL.md not found at {SOUL_PATH}")
        raise typer.Exit(code=1) from None
    con = _console()
    con.print(SOUL_PATH.read_text(encoding="utf-8"))
    sha = soul_sha256()
    if sha:
        con.print(f"\n[muted]sha256:[/muted] [highlight]{sha}[/highlight]")


# ---- doctor ---------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Print environment + dependency diagnostics."""
    from paperfessor.llm.security import list_configured_providers
    info = {
        "version": __version__,
        "python": sys.version.split()[0],
        "workspace_dir": str(workspace_dir()),
        "memory_db": str(memory_db_path()),
        "providers_with_keys": list_configured_providers(),
    }
    for k, v in _try_imports().items():
        info[k] = v
    con = _console()
    con.print_json(data=json.dumps(info, ensure_ascii=False, default=str))


def _try_imports() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in ("typer", "rich", "pydantic", "httpx", "litellm", "keyring", "PyQt6"):
        try:
            mod = __import__(name)
            out[name] = getattr(mod, "__version__", "installed")
        except Exception as exc:  # noqa: BLE001
            out[name] = f"missing: {exc}"
    return out


def main() -> int:
    """Entry point for the ``paperfessor`` console script."""
    return app()


if __name__ == "__main__":
    main()
