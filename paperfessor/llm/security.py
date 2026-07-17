"""API key storage in the OS keychain, with an encrypted-file
fallback for environments without a keyring.

API keys for any provider MUST NEVER be hardcoded, logged, echoed in
error messages, written to generated artifacts, or sent to telemetry.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import platform
import uuid
from pathlib import Path
from typing import Final

import keyring
from cryptography.fernet import Fernet, InvalidToken

from paperfessor.paths import ensure_dirs, workspace_dir

# Re-export ``data_dir`` as an alias of the workspace's ``.secrets``
# parent so the encrypted-fallback keyring backend keeps working
# without code changes there.
def data_dir() -> Path:
    return workspace_dir().parent / "data"


# Make ``data_dir`` importable from this module's namespace too,
# so callers that did ``from paperfessor.llm.security import data_dir``
# keep working.
__all__ = [
    "SecretStoreError", "data_dir", "delete_api_key", "get_api_key",
    "has_api_key", "list_configured_providers", "set_api_key",
]

logger = logging.getLogger(__name__)

_KEYRING_SERVICE: Final[str] = "Paperfessor"
_USER_SLUG: Final[str] = "api-key"
_FALLBACK_SALT: Final[bytes] = b"paperfessor.v1.fallback-salt"
_KNOWN_PROVIDER_SLUGS: Final[tuple[str, ...]] = (
    "minimax", "openai", "anthropic", "google", "ollama", "llamacpp", "custom",
)


class SecretStoreError(RuntimeError):
    pass


def _username_for(provider: str) -> str:
    slug = provider.strip().lower()
    if not slug:
        raise SecretStoreError("provider slug is empty")
    return f"{_USER_SLUG}:{slug}"


def set_api_key(provider: str, api_key: str) -> None:
    if not api_key or not api_key.strip():
        raise SecretStoreError("API key is empty")
    api_key = api_key.strip()
    username = _username_for(provider)
    try:
        keyring.set_password(_KEYRING_SERVICE, username, api_key)
        _fallback_delete(provider)
        return
    except keyring.errors.KeyringError as exc:
        logger.warning("keychain unavailable (%s); falling back to encrypted file", exc)
    _fallback_write(provider, api_key)


def get_api_key(provider: str) -> str | None:
    username = _username_for(provider)
    try:
        v = keyring.get_password(_KEYRING_SERVICE, username)
        if v is not None:
            return v
    except keyring.errors.KeyringError as exc:
        logger.warning("keychain read failed (%s)", exc)
    return _fallback_read(provider)


def has_api_key(provider: str) -> bool:
    return get_api_key(provider) is not None


def delete_api_key(provider: str) -> bool:
    removed = False
    username = _username_for(provider)
    try:
        existing = keyring.get_password(_KEYRING_SERVICE, username)
        if existing is not None:
            keyring.delete_password(_KEYRING_SERVICE, username)
            removed = True
    except keyring.errors.KeyringError as exc:
        logger.warning("keychain delete failed (%s)", exc)
    if _fallback_delete(provider):
        removed = True
    return removed


def list_configured_providers() -> list[str]:
    return sorted({s for s in _KNOWN_PROVIDER_SLUGS if has_api_key(s)})


# ---- Encrypted-fallback backend -------------------------------------------


def _fallback_path() -> Path:
    ensure_dirs()
    p = data_dir() / ".secrets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _fernet() -> Fernet:
    digest = hashlib.sha256(_machine_id() + _FALLBACK_SALT).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _machine_id() -> bytes:
    try:
        node = platform.node()
        if node:
            return node.encode("utf-8")
    except Exception:  # noqa: BLE001
        pass
    for c in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            if c.is_file():
                return c.read_text(encoding="utf-8").strip().encode("utf-8")
        except OSError:
            continue
    if os.name == "nt":
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            ) as k:
                v, _ = winreg.QueryValueEx(k, "MachineGuid")
                return str(v).encode("utf-8")
        except Exception:  # noqa: BLE001
            pass
    f = _fallback_path() / "machine-id"
    if f.is_file():
        try:
            return f.read_bytes()
        except OSError:
            pass
    new_id = uuid.uuid4().bytes
    try:
        f.write_bytes(new_id)
    except OSError:
        pass
    return new_id


def _fallback_file(provider: str) -> Path:
    safe = "".join(c for c in provider.lower() if c.isalnum() or c in ("-", "_")) or "unknown"
    return _fallback_path() / f"{safe}.key"


def _fallback_write(provider: str, api_key: str) -> None:
    token = _fernet().encrypt(api_key.encode("utf-8"))
    _fallback_file(provider).write_bytes(token)


def _fallback_read(provider: str) -> str | None:
    path = _fallback_file(provider)
    if not path.is_file():
        return None
    try:
        return _fernet().decrypt(path.read_bytes()).decode("utf-8")
    except (OSError, InvalidToken):
        return None


def _fallback_delete(provider: str) -> bool:
    path = _fallback_file(provider)
    if path.is_file():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False


__all__ = [
    "SecretStoreError",
    "delete_api_key",
    "get_api_key",
    "has_api_key",
    "list_configured_providers",
    "set_api_key",
]
