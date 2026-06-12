from __future__ import annotations

"""Interactive prompt helpers (arrow-key select, fuzzy search) for `veil init`.

Wraps InquirerPy. Imported lazily so non-interactive commands stay fast.
"""


def text(message: str, default: str | None = None) -> str:
    from InquirerPy import inquirer

    return inquirer.text(message=message, default=default or "").execute().strip()


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
