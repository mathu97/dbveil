from __future__ import annotations

import json
import shutil
import subprocess

MIN_VERSION = (2, 0, 0)

INSTALL_HINT = (
    "1Password CLI `op` is required for the 1Password option.\n"
    "  Install:  brew install 1password-cli\n"
    "            (or https://developer.1password.com/docs/cli/get-started/)\n"
    "  Enable:   1Password app -> Settings -> Developer -> 'Integrate with 1Password CLI'"
)
SIGNIN_HINT = (
    "1Password CLI is installed but not signed in.\n"
    "  Easiest:  1Password app -> Settings -> Developer -> enable\n"
    "            'Integrate with 1Password CLI' (then `op` unlocks with Touch ID)\n"
    "  Or run:   op signin"
)


class OpError(RuntimeError):
    pass


def _op(args: list[str], account: str | None = None, timeout: int = 30) -> str:
    cmd = ["op", *args]
    if account:
        cmd += ["--account", account]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise OpError(INSTALL_HINT) from exc
    except subprocess.TimeoutExpired as exc:
        raise OpError("1Password CLI timed out") from exc
    if proc.returncode != 0:
        raise OpError((proc.stderr or proc.stdout or "op command failed").strip())
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
        raise OpError(SIGNIN_HINT) from exc


def ensure_ready(account: str | None = None) -> None:
    """Raise OpError with instructions unless op is installed, new enough, and signed in."""
    ensure_installed()
    ensure_signed_in(account)


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
