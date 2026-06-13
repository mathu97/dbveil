from __future__ import annotations

import json
import logging
import shutil
import subprocess

log = logging.getLogger(__name__)

MIN_VERSION = (2, 0, 0)

_DEV_SETTINGS = (
    "  1. Open the 1Password app -> Settings (Cmd+,) -> Developer\n"
    "  2. Turn on 'Integrate with 1Password CLI'\n"
    "  3. Turn on 'Biometric unlock for 1Password CLI' (Touch ID)\n"
    "  Then verify with:  op whoami"
)

INSTALL_HINT = (
    "1Password CLI `op` isn't installed (veil needs it to read your database secret from 1Password).\n"
    "  Install:  brew install 1password-cli\n"
    "            (or https://developer.1password.com/docs/cli/get-started/)\n"
    "  Then connect it to the desktop app:\n" + _DEV_SETTINGS
)

SETUP_HINT = (
    "1Password CLI isn't connected to the desktop app yet. Enable it once:\n"
    + _DEV_SETTINGS
    + "\n  (CI / headless: set OP_SERVICE_ACCOUNT_TOKEN instead of using Touch ID.)"
)

LOCKED_HINT = (
    "1Password is set up but locked (the CLI session expired). Just unlock it:\n"
    "  Unlock:  op whoami     (approve the Touch ID prompt)\n"
    "  or:      op signin\n"
    "  Then retry — veil also prompts for Touch ID automatically on the next query."
)


def _auth_hint() -> str:
    """Pick the right message for an auth failure: locked (set up) vs not connected.

    `op account list` works while locked (no Touch ID), so accounts-present + auth-error
    means the session is locked, not that 1Password is unconfigured.
    """
    try:
        accounts = list_accounts()
    except OpError:
        accounts = []
    return LOCKED_HINT if accounts else SETUP_HINT


class OpError(RuntimeError):
    pass


def _op(args: list[str], account: str | None = None, timeout: int = 30) -> str:
    cmd = ["op", *args]
    if account:
        cmd += ["--account", account]
    log.debug("running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise OpError(INSTALL_HINT) from exc
    except subprocess.TimeoutExpired as exc:
        raise OpError("1Password CLI timed out") from exc
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "op command failed").strip()
        log.debug("op exited %d: %s", proc.returncode, msg)
        raise OpError(msg)
    log.debug("op ok (%d bytes)", len(proc.stdout))
    return proc.stdout


def installed_version() -> tuple[int, int, int] | None:
    if shutil.which("op") is None:
        return None
    try:
        out = subprocess.run(["op", "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return None
    nums: list[int] = []
    for part in out.split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        nums.append(int(digits) if digits else 0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def ensure_installed() -> None:
    version = installed_version()
    if version is None:
        raise OpError(INSTALL_HINT)
    if version < MIN_VERSION:
        cur = ".".join(map(str, version))
        need = ".".join(map(str, MIN_VERSION))
        raise OpError(f"op {cur} is too old (need >= {need}).\n{INSTALL_HINT}")


def ensure_signed_in(account: str | None = None) -> None:
    try:
        _op(["whoami"], account=account)
    except OpError as exc:
        raise OpError(_auth_hint()) from exc


def ensure_ready(account: str | None = None) -> None:
    """Raise OpError with instructions unless op is installed, new enough, and signed in."""
    ensure_installed()
    ensure_signed_in(account)


def readiness() -> tuple[str, str]:
    """Best-effort check WITHOUT triggering Touch ID.

    Returns (status, hint): status is 'ready' | 'install' | 'signin'. 'ready' means op is
    installed and at least one account is configured (the actual unlock happens at query time).
    """
    version = installed_version()
    if version is None:
        return ("install", INSTALL_HINT)
    if version < MIN_VERSION:
        cur = ".".join(map(str, version))
        need = ".".join(map(str, MIN_VERSION))
        return ("install", f"op {cur} is too old (need >= {need}).\n{INSTALL_HINT}")
    try:
        accounts = list_accounts()
    except OpError:
        accounts = []
    if not accounts:
        return ("setup", SETUP_HINT)
    return ("ready", "")


def read(ref: str) -> str:
    """Resolve an op:// reference to its value, with actionable errors when op isn't ready."""
    ensure_installed()
    try:
        out = _op(["read", ref], timeout=120)  # allow time for a Touch ID approval
    except OpError as exc:
        low = str(exc).lower()
        if any(
            k in low
            for k in ("sign in", "signed in", "not currently signed", "session", "authoriz", "unlock", "no account")
        ):
            raise OpError(_auth_hint()) from exc
        raise
    return out.strip()


def list_accounts() -> list[tuple[str, str]]:
    """Return [(label, account_ref)] for each configured account. account_ref is the sign-in URL."""
    try:
        data = json.loads(_op(["account", "list", "--format", "json"]))
    except OpError:
        return []
    accounts: list[tuple[str, str]] = []
    for a in data:
        url = a.get("url", "")
        email = a.get("email", "")
        label = f"{email} ({url})" if email else url
        if url:
            accounts.append((label, url))
    return accounts


def list_vaults(account: str | None = None) -> list[str]:
    data = json.loads(_op(["vault", "list", "--format", "json"], account=account))
    return [v["name"] for v in data if v.get("name")]


def list_items(vault: str, account: str | None = None) -> list[str]:
    data = json.loads(_op(["item", "list", "--vault", vault, "--format", "json"], account=account))
    return [i["title"] for i in data if i.get("title")]


def list_fields(vault: str, item: str, account: str | None = None) -> list[str]:
    data = json.loads(_op(["item", "get", item, "--vault", vault, "--format", "json"], account=account))
    labels: list[str] = []
    for f in data.get("fields", []):
        label = f.get("label") or f.get("id")
        if label and label not in labels:
            labels.append(label)
    return labels
