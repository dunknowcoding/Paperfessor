"""Light/dark palettes and stylesheet for the PyQt6 GUI."""

from __future__ import annotations


def light_palette() -> dict[str, str]:
    return {
        "bg": "#f7f7fa", "bg_alt": "#ffffff", "bg_panel": "#ffffff",
        "border": "#dfe2ea", "text": "#1f2430", "text_muted": "#5a6373",
        "accent": "#2e6cf6", "accent_text": "#ffffff",
        "danger": "#d23a3a", "warning": "#d68a00", "success": "#1f9d55",
    }


def dark_palette() -> dict[str, str]:
    return {
        "bg": "#0f1115", "bg_alt": "#15181f", "bg_panel": "#1b1f27",
        "border": "#2a2f3a", "text": "#e6e8ee", "text_muted": "#9aa3b2",
        "accent": "#5b8cff", "accent_text": "#ffffff",
        "danger": "#ff5e5e", "warning": "#ffb648", "success": "#4fd58a",
    }


def stylesheet(palette: dict[str, str], font_size: int = 10) -> str:
    return f"""
        QMainWindow, QWidget {{
            background: {palette['bg']};
            color: {palette['text']};
            font-size: {font_size}pt;
        }}
        QGroupBox {{
            background: {palette['bg_panel']};
            border: 1px solid {palette['border']};
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 4px;
            color: {palette['text_muted']};
        }}
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
            background: {palette['bg_alt']};
            color: {palette['text']};
            border: 1px solid {palette['border']};
            border-radius: 4px;
            padding: 6px 8px;
        }}
        QPushButton {{
            background: {palette['accent']};
            color: {palette['accent_text']};
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: 600;
        }}
        QPushButton:hover {{ opacity: 0.85; }}
        QTabWidget::pane {{
            border: 1px solid {palette['border']};
            border-radius: 6px;
            background: {palette['bg_panel']};
        }}
        QTabBar::tab {{
            background: transparent;
            color: {palette['text_muted']};
            padding: 8px 16px;
            border: none;
        }}
        QTabBar::tab:selected {{
            color: {palette['accent']};
            border-bottom: 2px solid {palette['accent']};
            font-weight: 600;
        }}
        QProgressBar {{
            background: {palette['bg_alt']};
            color: {palette['text']};
            border: 1px solid {palette['border']};
            border-radius: 4px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background: {palette['accent']};
            border-radius: 3px;
        }}
        QStatusBar {{
            background: {palette['bg_alt']};
            color: {palette['text_muted']};
        }}
    """


def palette_for(theme: str) -> dict[str, str]:
    if theme == "dark":
        return dark_palette()
    return light_palette()


__all__ = ["dark_palette", "light_palette", "palette_for", "stylesheet"]
