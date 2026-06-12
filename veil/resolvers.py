from __future__ import annotations

import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)


class ResolverError(RuntimeError):
    pass


def _scheme(ref: str) -> str:
    return ref.split("://", 1)[0].lower() if "://" in ref else ""


class EnvResolver:
    """env://VAR_NAME — read the DSN from an environment variable."""

    scheme = "env"

    def resolve(self, ref: str) -> str:
        var = ref[len("env://") :]
        val = os.environ.get(var)
        if not val:
            raise ResolverError(f"environment variable {var!r} is not set")
        return val


class LiteralResolver:
    """A plain DSN (postgresql://…) — returned unchanged."""

    scheme = ""

    def resolve(self, ref: str) -> str:
        return ref


class OnePasswordResolver:
    """op://vault/item/field — resolve via the 1Password CLI.

    Uses the operator's existing 1Password auth (desktop-app/biometric unlock
    locally, or OP_SERVICE_ACCOUNT_TOKEN in CI). The secret should hold the full DSN.
    """

    scheme = "op"

    def resolve(self, ref: str) -> str:
        if shutil.which("op") is None:
            raise ResolverError(
                "1Password CLI `op` not found. Install it: "
                "https://developer.1password.com/docs/cli/get-started/"
            )
        log.debug("running: op read %s", ref)
        try:
            proc = subprocess.run(
                ["op", "read", ref],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            raise ResolverError(f"1Password timed out reading {ref}") from exc

        if proc.returncode != 0:
            msg = (proc.stderr or "").strip()
            log.debug("op read failed (%d): %s", proc.returncode, msg)
            low = msg.lower()
            hint = ""
            if any(k in low for k in ("sign in", "signed in", "authoriz", "session", "unlock")):
                hint = " — sign in with `op signin` (or unlock the 1Password app) and retry"
            raise ResolverError(f"1Password could not read {ref}: {msg}{hint}")
        log.debug("op read ok")
        return proc.stdout.strip()


_RESOLVERS = {r.scheme: r for r in (EnvResolver(), OnePasswordResolver())}
_KINDS = {"op": "1Password", "env": "env", "gcp": "GCP Secret Manager"}


def resolve_url(ref: str) -> str:
    """Resolve a database url reference into a concrete DSN, by scheme."""
    ref = (ref or "").strip()
    if not ref:
        raise ResolverError("empty database url")
    scheme = _scheme(ref)
    if scheme == "gcp":
        raise ResolverError(
            "gcp:// (GCP Secret Manager) resolver is not implemented yet"
        )
    resolver = _RESOLVERS.get(scheme, LiteralResolver())
    shown = ref if scheme in ("op", "env", "gcp") else "<literal dsn>"
    log.debug("resolving database url via %s: %s", describe_ref(ref), shown)
    dsn = resolver.resolve(ref)
    log.debug("resolved ok")
    return dsn


def describe_ref(ref: str) -> str:
    """Name the resolver a reference would use, without resolving it (no secret read)."""
    return _KINDS.get(_scheme(ref), "literal")
