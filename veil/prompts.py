from __future__ import annotations

"""Interactive prompt helpers (arrow-key select, fuzzy search) for `veil init`.

Wraps InquirerPy. Imported lazily so non-interactive commands stay fast.
"""


def text(message: str, default: str | None = None) -> str:
    """Free-text input. `default` is shown as a greyed placeholder: pressing Enter
    on an empty field uses it; typing replaces it."""
    from html import escape

    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.formatted_text import HTML

    placeholder = (
        HTML(f'<style fg="ansibrightblack">{escape(str(default))}</style>') if default else None
    )
    message_ft = HTML(f'<style fg="ansigreen">?</style> {escape(message)} ')
    result = pt_prompt(message_ft, placeholder=placeholder).strip()
    return result or (default or "")


def confirm(message: str, default: bool = False) -> bool:
    from InquirerPy import inquirer

    return inquirer.confirm(message=message, default=default).execute()


def select(message: str, choices, default=None):
    from InquirerPy import inquirer

    return inquirer.select(
        message=message,
        choices=choices,
        default=default,
        border=True,
    ).execute()


def fuzzy(message: str, choices, max_visible: int = 5):
    """A searchable list: type to narrow, arrow keys to move, Enter to pick.

    Shows at most `max_visible` rows at a time for long lists (e.g. many secrets).
    """
    from InquirerPy import inquirer

    return inquirer.fuzzy(
        message=message,
        choices=choices,
        max_height=max_visible + 2,
        border=True,
        info=True,
    ).execute()
