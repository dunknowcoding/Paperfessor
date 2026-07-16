"""CLI display helpers - the only module that talks to Rich.

The rest of the CLI goes through these helpers so the display style
(minimal / default / vibrant) is a single config knob and every
screen looks consistent.
"""

from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass
from typing import Any, Final, Iterable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

from src._meta import __version__

VALID_STYLES: Final[tuple[str, ...]] = ("minimal", "default", "vibrant")
VALID_COLORS: Final[tuple[str, ...]] = ("auto", "dark", "light", "monochrome")


@dataclass(frozen=True)
class _Palette:
    accent: str
    success: str
    warning: str
    danger: str
    muted: str
    info: str
    highlight: str
    border: str
    use_borders: bool
    use_spinners: bool
    use_emoji: bool


def _build_palettes() -> dict[tuple[str, str], _Palette]:
    out: dict[tuple[str, str], _Palette] = {}

    out[("minimal", "monochrome")] = _Palette(
        accent="", success="", warning="", danger="", muted="dim",
        info="", highlight="bold", border="", use_borders=False,
        use_spinners=False, use_emoji=False,
    )
    out[("minimal", "auto")] = _Palette(
        accent="", success="green", warning="yellow", danger="red",
        muted="dim", info="cyan", highlight="bold", border="",
        use_borders=False, use_spinners=False, use_emoji=False,
    )
    minimal_dark = _Palette(
        accent="", success="green", warning="yellow", danger="red",
        muted="bright_black", info="cyan", highlight="bold", border="",
        use_borders=False, use_spinners=False, use_emoji=False,
    )
    out[("minimal", "dark")] = minimal_dark
    out[("minimal", "light")] = minimal_dark

    out[("default", "monochrome")] = _Palette(
        accent="", success="", warning="", danger="", muted="dim",
        info="", highlight="bold", border="", use_borders=True,
        use_spinners=False, use_emoji=False,
    )
    out[("default", "auto")] = _Palette(
        accent="cyan", success="green", warning="yellow", danger="red",
        muted="bright_black", info="cyan", highlight="bold magenta",
        border="blue", use_borders=True, use_spinners=False,
        use_emoji=False,
    )
    default_dark = _Palette(
        accent="deep_sky_blue1", success="green3", warning="yellow1",
        danger="red1", muted="grey50", info="cyan1", highlight="bold cyan",
        border="dodger_blue2", use_borders=True, use_spinners=False,
        use_emoji=False,
    )
    out[("default", "dark")] = default_dark
    out[("default", "light")] = _Palette(
        accent="blue", success="dark_green", warning="dark_orange3",
        danger="red3", muted="grey50", info="blue", highlight="bold blue",
        border="blue", use_borders=True, use_spinners=False,
        use_emoji=False,
    )

    out[("vibrant", "monochrome")] = _Palette(
        accent="bold", success="bold green", warning="bold yellow",
        danger="bold red", muted="dim", info="bold cyan", highlight="bold",
        border="", use_borders=True, use_spinners=True, use_emoji=True,
    )
    out[("vibrant", "auto")] = _Palette(
        accent="bold cyan", success="bold green", warning="bold yellow",
        danger="bold red", muted="grey58", info="bold cyan",
        highlight="bold magenta", border="blue", use_borders=True,
        use_spinners=True, use_emoji=True,
    )
    vibrant_dark = _Palette(
        accent="bold deep_sky_blue1", success="bold green3",
        warning="bold yellow1", danger="bold red1", muted="grey58",
        info="bold cyan1", highlight="bold magenta", border="dodger_blue2",
        use_borders=True, use_spinners=True, use_emoji=True,
    )
    out[("vibrant", "dark")] = vibrant_dark
    out[("vibrant", "light")] = _Palette(
        accent="bold blue", success="bold dark_green", warning="bold dark_orange3",
        danger="bold red3", muted="grey50", info="bold blue",
        highlight="bold magenta", border="blue", use_borders=True,
        use_spinners=True, use_emoji=True,
    )
    return out


_PALETTES: dict[tuple[str, str], _Palette] = _build_palettes()


def _coerce_style(value: str | None) -> str:
    s = (value or "default").strip().lower()
    return s if s in VALID_STYLES else "default"


def _coerce_color(value: str | None) -> str:
    c = (value or "auto").strip().lower()
    if c not in VALID_COLORS:
        return "auto"
    if c == "auto":
        if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
            return "monochrome"
        return "dark"
    return c


def make_console(style: str = "default", color: str = "auto") -> Console:
    """Build a Rich Console styled for the given combo."""
    pal = _PALETTES[(_coerce_style(style), _coerce_color(color))]
    theme = Theme({
        "accent": pal.accent,
        "success": pal.success,
        "warning": pal.warning,
        "danger": pal.danger,
        "muted": pal.muted,
        "info": pal.info,
        "highlight": pal.highlight,
        "border": pal.border,
    })
    return Console(theme=theme, highlight=False, soft_wrap=False)


def banner(console: Console, *, direction: str | None = None) -> None:
    style = getattr(console, "_pf_style", "default")
    color = getattr(console, "_pf_color", "auto")
    pal = _PALETTES[(_coerce_style(style), _coerce_color(color))]
    if pal.use_borders:
        body = [f"[accent]Paperfessor[/accent] [muted]v{__version__}[/muted]"]
        if direction:
            body.append(f"[muted]direction:[/muted] [info]{direction}[/info]")
        body.append("[muted]Use --help to see all options.[/muted]")
        console.print(Panel("\n".join(body), border_style=pal.border or "accent", padding=(0, 2)))
    else:
        if direction:
            console.print(f"Paperfessor v{__version__}  direction: {direction}")
        else:
            console.print(f"Paperfessor v{__version__}")


def success(console: Console, msg: str) -> None:
    console.print(f"[success]+[/success] {msg}")


def info(console: Console, msg: str) -> None:
    console.print(f"[info].[/info] {msg}")


def warning(console: Console, msg: str) -> None:
    console.print(f"[warning]![/warning] {msg}")


def error(console: Console, msg: str) -> None:
    console.print(f"[danger]x[/danger] {msg}")


def section(console: Console, title: str, items: Iterable[tuple[str, Any]]) -> None:
    style = getattr(console, "_pf_style", "default")
    color = getattr(console, "_pf_color", "auto")
    pal = _PALETTES[(_coerce_style(style), _coerce_color(color))]
    if pal.use_borders:
        lines = [f"  [muted]{k}:[/muted] [highlight]{v}[/highlight]" for k, v in items]
        console.print(Panel("\n".join(lines), title=f"[accent]{title}[/accent]",
                            border_style=pal.border or "accent", padding=(0, 2)))
    else:
        first = True
        for k, v in items:
            prefix = f"{title} " if first else "  "
            console.print(f"{prefix}[muted]{k}:[/muted] {v}")
            first = False


def kv_table(console: Console, rows: Iterable[tuple[str, Any]], *, title: str | None = None) -> None:
    style = getattr(console, "_pf_style", "default")
    color = getattr(console, "_pf_color", "auto")
    pal = _PALETTES[(_coerce_style(style), _coerce_color(color))]
    table = Table(
        title=f"[accent]{title}[/accent]" if title else None,
        show_header=False,
        border_style=pal.border if pal.use_borders else None,
        box=None if not pal.use_borders else None,
    )
    table.add_column("key", style="muted", no_wrap=True)
    table.add_column("value", style="highlight")
    for k, v in rows:
        table.add_row(str(k), str(v))
    console.print(table)


def metrics_table(
    console: Console,
    rows: Iterable[tuple[str, str, str, str]],
    *,
    title: str = "metrics",
) -> None:
    style = getattr(console, "_pf_style", "default")
    color = getattr(console, "_pf_color", "auto")
    pal = _PALETTES[(_coerce_style(style), _coerce_color(color))]
    table = Table(
        title=f"[accent]{title}[/accent]",
        show_header=True,
        header_style="bold",
        border_style=pal.border if pal.use_borders else None,
    )
    table.add_column("name", style="info")
    table.add_column("prompt", justify="right", style="muted")
    table.add_column("completion", justify="right", style="muted")
    table.add_column("total", justify="right", style="highlight")
    for r in rows:
        name, prompt, completion, total = r[0], r[1], r[2], r[3]
        table.add_row(name, prompt, completion, total)
    console.print(table)


def make_styled_console(style: str = "default", color: str = "auto") -> Console:
    """Build a Console and tag it with the style/color it was created for."""
    con = make_console(style=style, color=color)
    con._pf_style = _coerce_style(style)  # type: ignore[attr-defined]
    con._pf_color = _coerce_color(color)  # type: ignore[attr-defined]
    return con


__all__ = [
    "VALID_COLORS", "VALID_STYLES",
    "banner", "error", "info", "kv_table", "make_console",
    "make_styled_console", "metrics_table", "section", "success", "warning",
]
