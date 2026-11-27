#!/usr/bin/env python3
"""Bootstrap generator for the PyVault CLI password vault project."""

from __future__ import annotations

import argparse
import os
import py_compile
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


ROOT_DIR_NAME = "pyvault_project"
PACKAGE_NAME = "pyvault"
REQUIRED_PACKAGES = ["argon2-cffi", "cryptography"]


FILE_INIT_PY = textwrap.dedent(
    '''\
    """PyVault — Local CLI password vault using Argon2id and AES-GCM."""

    __version__ = "0.1.0"
    '''
)


FILE_STORAGE_PY = textwrap.dedent(
    '''\
    from __future__ import annotations

    import json
    import os
    import tempfile
    from pathlib import Path
    from typing import Any


    class StorageError(Exception):
        """Raised when vault file I/O or JSON parsing fails."""


    def vault_exists(path: Path) -> bool:
        """Return True if the vault file exists and is a regular file."""
        return path.is_file()


    def read_vault_file(path: Path) -> dict[str, Any]:
        """Read and parse the JSON vault file."""
        if not path.is_file():
            raise StorageError(f"Vault file not found at: {path}")

        try:
            raw_text = path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StorageError(f"Failed to read or parse vault file: {exc}") from exc

        if not isinstance(data, dict):
            raise StorageError("Vault file root must be a JSON object.")

        return data


    def write_vault_atomic(path: Path, payload: dict[str, Any]) -> None:
        """Atomically write payload as JSON to path using a temporary file and fsync."""
        parent_dir = path.parent.resolve()
        parent_dir.mkdir(parents=True, exist_ok=True)

        serialized = json.dumps(payload, indent=2).encode("utf-8")
        tmp_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=parent_dir,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_file.write(serialized)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            os.replace(tmp_path, path)
        except OSError as exc:
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise StorageError(f"Failed to write vault file atomically: {exc}") from exc
    '''
)


FILE_CRYPTO_PY = textwrap.dedent(
    '''\
    from __future__ import annotations

    import base64
    import json
    import os
    from typing import Any

    from argon2 import PasswordHasher, Type
    from argon2.exceptions import Argon2Error, VerificationError, VerifyMismatchError
    from argon2.low_level import hash_secret_raw
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM


    class CryptoError(Exception):
        """Raised when hashing, key derivation, encryption, or decryption fails."""


    class InvalidMasterPasswordError(CryptoError):
        """Raised when the provided master password does not match."""


    DEFAULT_KDF_PARAMS: dict[str, int] = {
        "time_cost": 3,
        "memory_cost": 65536,  # 64 MiB
        "parallelism": 2,
        "hash_len": 32,  # 256-bit AES key
    }

    _MASTER_HASHER = PasswordHasher(
        time_cost=DEFAULT_KDF_PARAMS["time_cost"],
        memory_cost=DEFAULT_KDF_PARAMS["memory_cost"],
        parallelism=DEFAULT_KDF_PARAMS["parallelism"],
        hash_len=32,
        salt_len=16,
        type=Type.ID,
    )


    def _b64_encode(data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")


    def _b64_decode(value: str, field_name: str) -> bytes:
        try:
            return base64.b64decode(value.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError) as exc:
            raise CryptoError(f"Invalid base64 encoding in '{field_name}'.") from exc


    def hash_master_password(master_password: str) -> str:
        """Hash a master password using Argon2id."""
        if not master_password:
            raise CryptoError("Master password cannot be empty.")
        return _MASTER_HASHER.hash(master_password)


    def verify_master_password(master_password: str, stored_hash: str) -> bool:
        """Verify a master password against an Argon2id hash string."""
        try:
            return _MASTER_HASHER.verify(stored_hash, master_password)
        except VerifyMismatchError:
            return False
        except VerificationError as exc:
            raise CryptoError("Master password verification failed.") from exc
        except Argon2Error as exc:
            raise CryptoError(f"Argon2 error during verification: {exc}") from exc


    def generate_salt(length: int = 16) -> bytes:
        """Generate a cryptographically random salt."""
        return os.urandom(length)


    def derive_vault_key(
        master_password: str,
        salt: bytes,
        kdf_params: dict[str, Any] | None = None,
    ) -> bytes:
        """Derive a 256-bit encryption key from the master password and salt via Argon2id."""
        params = {**DEFAULT_KDF_PARAMS, **(kdf_params or {})}
        try:
            return hash_secret_raw(
                secret=master_password.encode("utf-8"),
                salt=salt,
                time_cost=int(params["time_cost"]),
                memory_cost=int(params["memory_cost"]),
                parallelism=int(params["parallelism"]),
                hash_len=int(params["hash_len"]),
                type=Type.ID,
            )
        except Argon2Error as exc:
            raise CryptoError(f"Failed to derive vault key: {exc}") from exc


    def encrypt_entries(entries: list[dict[str, Any]], key: bytes) -> dict[str, str]:
        """Encrypt the entries list using AES-256-GCM."""
        if len(key) != 32:
            raise CryptoError("AES-256-GCM key must be exactly 32 bytes.")

        nonce = os.urandom(12)  # Standard 96-bit GCM nonce
        aesgcm = AESGCM(key)
        plaintext = json.dumps(entries, separators=(",", ":")).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)

        return {
            "nonce": _b64_encode(nonce),
            "ciphertext": _b64_encode(ciphertext),
        }


    def decrypt_entries(encrypted_blob: dict[str, Any], key: bytes) -> list[dict[str, Any]]:
        """Decrypt and authenticate AES-256-GCM encrypted vault entries."""
        if len(key) != 32:
            raise CryptoError("AES-256-GCM key must be exactly 32 bytes.")

        nonce_b64 = encrypted_blob.get("nonce")
        ciphertext_b64 = encrypted_blob.get("ciphertext")
        if not isinstance(nonce_b64, str) or not isinstance(ciphertext_b64, str):
            raise CryptoError("Encrypted vault payload is missing 'nonce' or 'ciphertext'.")

        nonce = _b64_decode(nonce_b64, "nonce")
        ciphertext = _b64_decode(ciphertext_b64, "ciphertext")

        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
            entries = json.loads(plaintext.decode("utf-8"))
        except InvalidTag as exc:
            raise CryptoError(
                "Decryption failed: wrong key or vault data has been tampered with."
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CryptoError("Decrypted vault data is corrupted.") from exc

        if not isinstance(entries, list):
            raise CryptoError("Decrypted entries payload must be a list.")

        return entries
    '''
)


FILE_GENERATOR_PY = textwrap.dedent(
    '''\
    from __future__ import annotations

    import secrets
    import string


    class GeneratorError(Exception):
        """Raised when password generation parameters are invalid."""


    SYMBOLS = "!@#$%^&*()-_=+[]{}:,.?"


    def generate_password(
        length: int = 16,
        use_upper: bool = True,
        use_lower: bool = True,
        use_digits: bool = True,
        use_symbols: bool = True,
    ) -> str:
        """Generate a strong random password with guaranteed character class coverage."""
        pools: list[str] = []
        if use_upper:
            pools.append(string.ascii_uppercase)
        if use_lower:
            pools.append(string.ascii_lowercase)
        if use_digits:
            pools.append(string.digits)
        if use_symbols:
            pools.append(SYMBOLS)

        if not pools:
            raise GeneratorError("At least one character set must be enabled.")
        if length < len(pools):
            raise GeneratorError(
                f"Password length ({length}) must be at least {len(pools)} for selected sets."
            )

        chars: list[str] = [secrets.choice(pool) for pool in pools]
        combined_pool = "".join(pools)

        while len(chars) < length:
            chars.append(secrets.choice(combined_pool))

        secrets.SystemRandom().shuffle(chars)
        return "".join(chars)


    def check_password_strength(password: str) -> tuple[str, list[str]]:
        """Return a strength label ('Weak', 'Medium', 'Strong') and improvement tips."""
        tips: list[str] = []
        score = 0

        if len(password) >= 12:
            score += 1
        else:
            tips.append("Use at least 12 characters (16+ recommended).")

        if len(password) >= 16:
            score += 1

        if any(ch.islower() for ch in password):
            score += 1
        else:
            tips.append("Add lowercase letters.")

        if any(ch.isupper() for ch in password):
            score += 1
        else:
            tips.append("Add uppercase letters.")

        if any(ch.isdigit() for ch in password):
            score += 1
        else:
            tips.append("Add numbers.")

        if any(not ch.isalnum() for ch in password):
            score += 1
        else:
            tips.append("Add symbols.")

        if score <= 2:
            rating = "Weak"
        elif score <= 4:
            rating = "Medium"
        else:
            rating = "Strong"

        return rating, tips
    '''
)


FILE_VAULT_PY = textwrap.dedent(
    '''\
    from __future__ import annotations

    from datetime import datetime, timezone
    from pathlib import Path
    from typing import Any

    from pyvault.crypto import (
        DEFAULT_KDF_PARAMS,
        CryptoError,
        InvalidMasterPasswordError,
        _b64_decode,
        _b64_encode,
        decrypt_entries,
        derive_vault_key,
        encrypt_entries,
        generate_salt,
        hash_master_password,
        verify_master_password,
    )
    from pyvault.storage import StorageError, read_vault_file, vault_exists, write_vault_atomic


    class VaultError(Exception):
        """Base exception for vault operations."""


    class VaultAlreadyExistsError(VaultError):
        """Raised when initializing a vault where one already exists."""


    class VaultNotFoundError(VaultError):
        """Raised when the vault file does not exist."""


    class EntryNotFoundError(VaultError):
        """Raised when no entry matches the given ID or service."""


    class AmbiguousEntryError(VaultError):
        """Raised when multiple entries share a service name."""


    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


    def _next_entry_id(entries: list[dict[str, Any]]) -> int:
        max_id = 0
        for item in entries:
            try:
                item_id = int(item.get("id", 0))
                if item_id > max_id:
                    max_id = item_id
            except (TypeError, ValueError):
                continue
        return max_id + 1


    def _build_vault_payload(
        master_password: str,
        entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        master_hash = hash_master_password(master_password)
        salt = generate_salt(16)
        key = derive_vault_key(master_password, salt, DEFAULT_KDF_PARAMS)
        encrypted = encrypt_entries(entries, key)

        return {
            "version": 1,
            "kdf": {
                "algorithm": "argon2id",
                "salt": _b64_encode(salt),
                "params": dict(DEFAULT_KDF_PARAMS),
            },
            "master_verifier": master_hash,
            "vault": encrypted,
        }


    def init_vault(path: Path, master_password: str) -> None:
        """Create a new encrypted vault file."""
        if vault_exists(path):
            raise VaultAlreadyExistsError(f"Vault already exists at: {path}")

        payload = _build_vault_payload(master_password, entries=[])
        try:
            write_vault_atomic(path, payload)
        except StorageError as exc:
            raise VaultError(str(exc)) from exc


    def unlock_vault(
        path: Path,
        master_password: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bytes]:
        """Verify master password, derive vault key, and decrypt entries."""
        try:
            vault_doc = read_vault_file(path)
        except StorageError as exc:
            if not vault_exists(path):
                raise VaultNotFoundError(str(exc)) from exc
            raise VaultError(str(exc)) from exc

        verifier = vault_doc.get("master_verifier")
        if not isinstance(verifier, str):
            raise VaultError("Vault file is missing 'master_verifier'.")

        try:
            if not verify_master_password(master_password, verifier):
                raise InvalidMasterPasswordError("Incorrect master password.")

            kdf_section = vault_doc.get("kdf", {})
            salt_b64 = kdf_section.get("salt")
            params = kdf_section.get("params", DEFAULT_KDF_PARAMS)
            encrypted_blob = vault_doc.get("vault", {})

            if not isinstance(salt_b64, str):
                raise VaultError("Vault file is missing KDF salt.")

            salt = _b64_decode(salt_b64, "kdf.salt")
            key = derive_vault_key(master_password, salt, params)
            entries = decrypt_entries(encrypted_blob, key)
        except InvalidMasterPasswordError:
            raise
        except CryptoError as exc:
            raise VaultError(str(exc)) from exc

        return vault_doc, entries, key


    def save_entries(
        path: Path,
        vault_doc: dict[str, Any],
        entries: list[dict[str, Any]],
        key: bytes,
    ) -> None:
        """Re-encrypt entries with the active vault key and write atomically."""
        try:
            vault_doc["vault"] = encrypt_entries(entries, key)
            write_vault_atomic(path, vault_doc)
        except (CryptoError, StorageError) as exc:
            raise VaultError(str(exc)) from exc


    def add_entry(
        entries: list[dict[str, Any]],
        service: str,
        username: str,
        password: str,
        notes: str = "",
    ) -> dict[str, Any]:
        """Validate and append a new credential entry."""
        clean_service = service.strip()
        clean_username = username.strip()

        if not clean_service:
            raise VaultError("Service name cannot be empty.")
        if not clean_username:
            raise VaultError("Username cannot be empty.")
        if not password:
            raise VaultError("Entry password cannot be empty.")

        now = _utc_now_iso()
        entry: dict[str, Any] = {
            "id": _next_entry_id(entries),
            "service": clean_service,
            "username": clean_username,
            "password": password,
            "notes": notes.strip(),
            "created_at": now,
            "updated_at": now,
        }
        entries.append(entry)
        return entry


    def find_entry(entries: list[dict[str, Any]], identifier: str) -> dict[str, Any]:
        """Find an entry by numeric ID or service name."""
        query = identifier.strip()
        if not query:
            raise EntryNotFoundError("Entry identifier cannot be empty.")

        if query.isdigit():
            target_id = int(query)
            for entry in entries:
                if int(entry.get("id", -1)) == target_id:
                    return entry
            raise EntryNotFoundError(f"No entry found with ID {target_id}.")

        lowered = query.lower()
        exact_matches = [
            entry for entry in entries if str(entry.get("service", "")).lower() == lowered
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            ids = ", ".join(str(e.get("id")) for e in exact_matches)
            raise AmbiguousEntryError(
                f"Multiple entries match '{query}' (IDs: {ids}). Specify a numeric ID."
            )

        raise EntryNotFoundError(f"No entry found for service '{query}'.")


    def list_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return non-secret summary fields for all entries."""
        return [
            {
                "id": entry.get("id"),
                "service": entry.get("service", ""),
                "username": entry.get("username", ""),
                "updated_at": entry.get("updated_at", ""),
            }
            for entry in entries
        ]


    def search_entries(entries: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        """Search entries case-insensitively across service, username, and notes."""
        needle = query.strip().lower()
        if not needle:
            return list(entries)

        results: list[dict[str, Any]] = []
        for entry in entries:
            haystack = " ".join(
                [
                    str(entry.get("service", "")),
                    str(entry.get("username", "")),
                    str(entry.get("notes", "")),
                ]
            ).lower()
            if needle in haystack:
                results.append(entry)
        return results


    def update_entry(
        entries: list[dict[str, Any]],
        identifier: str,
        service: str | None = None,
        username: str | None = None,
        password: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Update one or more fields of an existing entry."""
        entry = find_entry(entries, identifier)

        if service is not None:
            cleaned = service.strip()
            if not cleaned:
                raise VaultError("Service name cannot be blank.")
            entry["service"] = cleaned

        if username is not None:
            cleaned = username.strip()
            if not cleaned:
                raise VaultError("Username cannot be blank.")
            entry["username"] = cleaned

        if password is not None:
            if not password:
                raise VaultError("Password cannot be blank.")
            entry["password"] = password

        if notes is not None:
            entry["notes"] = notes.strip()

        entry["updated_at"] = _utc_now_iso()
        return entry


    def delete_entry(entries: list[dict[str, Any]], identifier: str) -> dict[str, Any]:
        """Remove an entry by ID or service name and return the removed record."""
        target = find_entry(entries, identifier)
        entries.remove(target)
        return target


    def rotate_master_password(
        path: Path,
        current_password: str,
        new_password: str,
    ) -> None:
        """Verify current master password, re-encrypt entries under a new key, and save."""
        _, entries, _ = unlock_vault(path, current_password)
        new_payload = _build_vault_payload(new_password, entries=entries)
        try:
            write_vault_atomic(path, new_payload)
        except StorageError as exc:
            raise VaultError(str(exc)) from exc
    '''
)


FILE_MAIN_PY = textwrap.dedent(
    r'''
    from __future__ import annotations

    import argparse
    import getpass
    import sys
    from pathlib import Path
    from typing import Any

    from pyvault.crypto import InvalidMasterPasswordError
    from pyvault.generator import (
        GeneratorError,
        check_password_strength,
        generate_password,
    )
    from pyvault.storage import vault_exists
    from pyvault.vault import (
        VaultError,
        VaultNotFoundError,
        add_entry,
        delete_entry,
        find_entry,
        init_vault,
        list_entries,
        rotate_master_password,
        save_entries,
        search_entries,
        unlock_vault,
        update_entry,
    )

    DEFAULT_VAULT_PATH = Path.home() / ".pyvault" / "vault.json"


    def _prompt_master_password(confirm: bool = False, prompt_text: str = "Master password: ") -> str:
        """Prompt for a master password without echoing characters."""
        password = getpass.getpass(prompt_text)
        if not password:
            raise VaultError("Master password cannot be empty.")

        if confirm:
            second = getpass.getpass("Confirm master password: ")
            if password != second:
                raise VaultError("Passwords do not match.")

            rating, tips = check_password_strength(password)
            print(f"Master password strength: {rating}")
            for tip in tips:
                print(f"  - Tip: {tip}")

        return password


    def _prompt_new_master_password_with_retry(max_attempts: int = 3) -> str:
        for attempt in range(1, max_attempts + 1):
            try:
                return _prompt_master_password(confirm=True, prompt_text="New master password: ")
            except VaultError as exc:
                print(f"Error: {exc}")
                if attempt < max_attempts:
                    print(f"Try again ({attempt}/{max_attempts}).")
        raise VaultError("Too many invalid master password attempts.")


    def _unlock_with_retry(
        vault_path: Path, max_attempts: int = 3
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bytes]:
        for attempt in range(1, max_attempts + 1):
            try:
                master_pw = getpass.getpass("Master password: ")
                return unlock_vault(vault_path, master_pw)
            except InvalidMasterPasswordError:
                remaining = max_attempts - attempt
                if remaining > 0:
                    print(f"Incorrect master password. {remaining} attempt(s) left.")
                else:
                    raise InvalidMasterPasswordError("Too many failed unlock attempts.")


    def _format_table(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "No entries found."

        headers = ("ID", "Service", "Username", "Updated (UTC)")
        formatted_rows = [
            (
                str(r.get("id", "")),
                str(r.get("service", "")),
                str(r.get("username", "")),
                str(r.get("updated_at", "")),
            )
            for r in rows
        ]

        widths = [len(h) for h in headers]
        for row in formatted_rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))

        sep = "  "
        header_line = sep.join(h.ljust(widths[i]) for i, h in enumerate(headers))
        divider = sep.join("-" * w for w in widths)
        body_lines = [
            sep.join(cell.ljust(widths[i]) for i, cell in enumerate(row))
            for row in formatted_rows
        ]
        return "\n".join([header_line, divider, *body_lines])


    def _print_entry_detail(entry: dict[str, Any]) -> None:
        print(f"\nID       : {entry.get('id')}")
        print(f"Service  : {entry.get('service')}")
        print(f"Username : {entry.get('username')}")
        print(f"Password : {entry.get('password')}")
        if entry.get("notes"):
            print(f"Notes    : {entry.get('notes')}")
        print(f"Updated  : {entry.get('updated_at')}\n")


    def _confirm(prompt: str = "Are you sure? [y/N]: ") -> bool:
        ans = input(prompt).strip().lower()
        return ans in {"y", "yes"}


    def _handle_init(vault_path: Path) -> None:
        master_pw = _prompt_master_password(confirm=True)
        init_vault(vault_path, master_pw)
        print(f"Vault initialized at: {vault_path}")


    def _handle_add(vault_path: Path, args: argparse.Namespace) -> None:
        vault_doc, entries, key = _unlock_with_retry(vault_path)

        service = args.service or input("Service name: ").strip()
        username = args.username or input("Username/email: ").strip()

        if args.generate:
            password = generate_password(length=args.length)
            print(f"Generated password: {password}")
        elif args.password is not None:
            password = args.password
        else:
            password = getpass.getpass("Entry password (leave blank to generate): ")
            if not password:
                password = generate_password(length=16)
                print(f"Generated password: {password}")

        notes = args.notes if args.notes is not None else input("Notes (optional): ").strip()

        created = add_entry(entries, service, username, password, notes)
        save_entries(vault_path, vault_doc, entries, key)
        print(f"Saved entry #{created['id']} for '{created['service']}'.")


    def _handle_get(vault_path: Path, args: argparse.Namespace) -> None:
        _, entries, _ = _unlock_with_retry(vault_path)
        identifier = args.identifier or input("Entry ID or service name: ").strip()
        entry = find_entry(entries, identifier)
        _print_entry_detail(entry)


    def _handle_list(vault_path: Path) -> None:
        _, entries, _ = _unlock_with_retry(vault_path)
        print(_format_table(list_entries(entries)))


    def _handle_search(vault_path: Path, args: argparse.Namespace) -> None:
        _, entries, _ = _unlock_with_retry(vault_path)
        query = args.query if args.query is not None else input("Search query: ").strip()
        matches = search_entries(entries, query)
        print(_format_table(list_entries(matches)))


    def _handle_update(vault_path: Path, args: argparse.Namespace) -> None:
        vault_doc, entries, key = _unlock_with_retry(vault_path)
        identifier = args.identifier or input("Entry ID or service name to update: ").strip()
        existing = find_entry(entries, identifier)

        if (
            args.service is not None
            or args.username is not None
            or args.password is not None
            or args.notes is not None
        ):
            updated = update_entry(
                entries,
                str(existing["id"]),
                service=args.service,
                username=args.username,
                password=args.password,
                notes=args.notes,
            )
        else:
            print(f"Updating '{existing['service']}' (press Enter to keep current value):")
            new_service = input(f"Service [{existing['service']}]: ").strip() or None
            new_username = input(f"Username [{existing['username']}]: ").strip() or None
            new_pw = getpass.getpass("New password (leave blank to keep current): ") or None
            new_notes = input(f"Notes [{existing.get('notes', '')}]: ").strip()
            notes_arg = new_notes if new_notes != existing.get("notes", "") else None

            updated = update_entry(
                entries,
                str(existing["id"]),
                service=new_service,
                username=new_username,
                password=new_pw,
                notes=notes_arg,
            )

        save_entries(vault_path, vault_doc, entries, key)
        print(f"Updated entry #{updated['id']} ('{updated['service']}').")


    def _handle_delete(vault_path: Path, args: argparse.Namespace) -> None:
        vault_doc, entries, key = _unlock_with_retry(vault_path)
        identifier = args.identifier or input("Entry ID or service name to delete: ").strip()
        entry = find_entry(entries, identifier)

        if not args.yes and not _confirm(
            f"Delete entry #{entry['id']} ('{entry['service']}' / '{entry['username']}')? [y/N]: "
        ):
            print("Deletion cancelled.")
            return

        removed = delete_entry(entries, str(entry["id"]))
        save_entries(vault_path, vault_doc, entries, key)
        print(f"Deleted entry #{removed['id']} ('{removed['service']}').")


    def _handle_generate(args: argparse.Namespace) -> None:
        pw = generate_password(
            length=args.length,
            use_upper=not args.no_upper,
            use_lower=not args.no_lower,
            use_digits=not args.no_digits,
            use_symbols=not args.no_symbols,
        )
        rating, _ = check_password_strength(pw)
        print(f"{pw}   [{rating}]")


    def _handle_rotate_master(vault_path: Path) -> None:
        current_pw = getpass.getpass("Current master password: ")
        new_pw = _prompt_new_master_password_with_retry()
        rotate_master_password(vault_path, current_pw, new_pw)
        print("Master password updated and vault re-encrypted.")


    def run_interactive_menu(vault_path: Path) -> None:
        """Interactive menu session after unlocking the vault."""
        print(f"\n=== PyVault ({vault_path}) ===")
        if not vault_exists(vault_path):
            print("No vault found yet.")
            if _confirm("Create a new vault now? [y/N]: "):
                _handle_init(vault_path)
            else:
                return

        vault_doc, entries, key = _unlock_with_retry(vault_path)
        print("Vault unlocked.")

        while True:
            print(
                "\n1. Add entry\n"
                "2. Get entry\n"
                "3. List entries\n"
                "4. Search entries\n"
                "5. Update entry\n"
                "6. Delete entry\n"
                "7. Generate password\n"
                "8. Change master password\n"
                "9. Lock & Exit"
            )
            choice = input("\nSelect option [1-9]: ").strip()

            try:
                if choice == "1":
                    service = input("Service name: ").strip()
                    username = input("Username/email: ").strip()
                    password = getpass.getpass("Entry password (leave blank to generate): ")
                    if not password:
                        password = generate_password(length=16)
                        print(f"Generated password: {password}")
                    notes = input("Notes (optional): ").strip()
                    created = add_entry(entries, service, username, password, notes)
                    save_entries(vault_path, vault_doc, entries, key)
                    print(f"Saved entry #{created['id']} for '{created['service']}'.")

                elif choice == "2":
                    identifier = input("Entry ID or service name: ").strip()
                    entry = find_entry(entries, identifier)
                    _print_entry_detail(entry)

                elif choice == "3":
                    print(_format_table(list_entries(entries)))

                elif choice == "4":
                    query = input("Search query: ").strip()
                    matches = search_entries(entries, query)
                    print(_format_table(list_entries(matches)))

                elif choice == "5":
                    identifier = input("Entry ID or service name to update: ").strip()
                    existing = find_entry(entries, identifier)
                    print(f"Updating '{existing['service']}' (leave blank to keep current):")
                    new_service = input(f"Service [{existing['service']}]: ").strip() or None
                    new_username = input(f"Username [{existing['username']}]: ").strip() or None
                    new_pw = getpass.getpass("New password: ") or None
                    new_notes_raw = input(f"Notes [{existing.get('notes', '')}]: ").strip()
                    new_notes = (
                        new_notes_raw if new_notes_raw != existing.get("notes", "") else None
                    )
                    updated = update_entry(
                        entries,
                        str(existing["id"]),
                        service=new_service,
                        username=new_username,
                        password=new_pw,
                        notes=new_notes,
                    )
                    save_entries(vault_path, vault_doc, entries, key)
                    print(f"Updated entry #{updated['id']}.")

                elif choice == "6":
                    identifier = input("Entry ID or service name to delete: ").strip()
                    entry = find_entry(entries, identifier)
                    if _confirm(f"Delete '{entry['service']}' ({entry['username']})? [y/N]: "):
                        removed = delete_entry(entries, str(entry["id"]))
                        save_entries(vault_path, vault_doc, entries, key)
                        print(f"Deleted entry #{removed['id']}.")
                    else:
                        print("Cancelled.")

                elif choice == "7":
                    raw_len = input("Length [16]: ").strip()
                    length = int(raw_len) if raw_len else 16
                    pw = generate_password(length=length)
                    rating, _ = check_password_strength(pw)
                    print(f"Generated: {pw}   [{rating}]")

                elif choice == "8":
                    current_pw = getpass.getpass("Current master password: ")
                    new_pw = _prompt_new_master_password_with_retry()
                    rotate_master_password(vault_path, current_pw, new_pw)
                    vault_doc, entries, key = unlock_vault(vault_path, new_pw)
                    print("Master password rotated successfully.")

                elif choice == "9":
                    entries.clear()
                    key = b"\x00" * len(key)
                    print("Vault locked. Goodbye!")
                    break

                else:
                    print("Invalid choice. Enter a number from 1 to 9.")

            except (VaultError, GeneratorError, ValueError) as exc:
                print(f"Error: {exc}")

            input("\nPress Enter to continue...")


    def build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="pyvault",
            description="Local encrypted CLI password vault.",
        )
        parser.add_argument(
            "--vault",
            type=Path,
            default=DEFAULT_VAULT_PATH,
            help=f"Path to vault JSON file (default: {DEFAULT_VAULT_PATH})",
        )

        subparsers = parser.add_subparsers(dest="command")

        subparsers.add_parser("init", help="Initialize a new vault")

        add_p = subparsers.add_parser("add", help="Add a credential entry")
        add_p.add_argument("--service", help="Service or website name")
        add_p.add_argument("--username", help="Account username or email")
        add_p.add_argument("--password", help="Account password")
        add_p.add_argument("--notes", help="Optional notes")
        add_p.add_argument("--generate", action="store_true", help="Generate a random password")
        add_p.add_argument("--length", type=int, default=16, help="Generated password length")

        get_p = subparsers.add_parser("get", help="Retrieve an entry by ID or service name")
        get_p.add_argument("identifier", nargs="?", help="Entry ID or exact service name")

        subparsers.add_parser("list", help="List saved entries without passwords")

        search_p = subparsers.add_parser("search", help="Search entries")
        search_p.add_argument("query", nargs="?", help="Search term")

        upd_p = subparsers.add_parser("update", help="Update an existing entry")
        upd_p.add_argument("identifier", nargs="?", help="Entry ID or exact service name")
        upd_p.add_argument("--service", help="New service name")
        upd_p.add_argument("--username", help="New username")
        upd_p.add_argument("--password", help="New password")
        upd_p.add_argument("--notes", help="New notes")

        del_p = subparsers.add_parser("delete", help="Delete an entry")
        del_p.add_argument("identifier", nargs="?", help="Entry ID or exact service name")
        del_p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

        gen_p = subparsers.add_parser("generate", help="Generate a strong password")
        gen_p.add_argument("-l", "--length", type=int, default=16, help="Password length")
        gen_p.add_argument("--no-upper", action="store_true", help="Exclude uppercase letters")
        gen_p.add_argument("--no-lower", action="store_true", help="Exclude lowercase letters")
        gen_p.add_argument("--no-digits", action="store_true", help="Exclude digits")
        gen_p.add_argument("--no-symbols", action="store_true", help="Exclude symbols")

        subparsers.add_parser("rotate-master", help="Change master password and re-encrypt vault")
        subparsers.add_parser("menu", help="Launch interactive menu")

        return parser


    def main(argv: list[str] | None = None) -> int:
        parser = build_parser()
        args = parser.parse_args(argv)
        vault_path: Path = args.vault

        try:
            if args.command is None or args.command == "menu":
                run_interactive_menu(vault_path)
            elif args.command == "init":
                _handle_init(vault_path)
            elif args.command == "add":
                _handle_add(vault_path, args)
            elif args.command == "get":
                _handle_get(vault_path, args)
            elif args.command == "list":
                _handle_list(vault_path)
            elif args.command == "search":
                _handle_search(vault_path, args)
            elif args.command == "update":
                _handle_update(vault_path, args)
            elif args.command == "delete":
                _handle_delete(vault_path, args)
            elif args.command == "generate":
                _handle_generate(args)
            elif args.command == "rotate-master":
                _handle_rotate_master(vault_path)
            return 0

        except (VaultNotFoundError, InvalidMasterPasswordError, VaultError, GeneratorError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except (KeyboardInterrupt, EOFError):
            print("\nInterrupted. Exiting safely.")
            return 130


    if __name__ == "__main__":
        sys.exit(main())
    '''
).lstrip("\n")


FILE_TEST_PY = textwrap.dedent(
    '''\
    from pathlib import Path
    import pytest

    from pyvault.crypto import InvalidMasterPasswordError
    from pyvault.generator import check_password_strength, generate_password
    from pyvault.vault import (
        VaultAlreadyExistsError,
        add_entry,
        delete_entry,
        find_entry,
        init_vault,
        list_entries,
        rotate_master_password,
        save_entries,
        search_entries,
        unlock_vault,
        update_entry,
    )


    def test_init_unlock_and_crud(tmp_path: Path) -> None:
        vault_file = tmp_path / "vault.json"
        init_vault(vault_file, "CorrectHorseBatteryStaple!")

        with pytest.raises(VaultAlreadyExistsError):
            init_vault(vault_file, "AnotherPass123!")

        with pytest.raises(InvalidMasterPasswordError):
            unlock_vault(vault_file, "WrongPassword!")

        doc, entries, key = unlock_vault(vault_file, "CorrectHorseBatteryStaple!")
        assert entries == []

        item = add_entry(entries, "GitHub", "student_dev", "SecretPass#123", "school account")
        save_entries(vault_file, doc, entries, key)

        _, entries_after, _ = unlock_vault(vault_file, "CorrectHorseBatteryStaple!")
        assert len(entries_after) == 1
        assert find_entry(entries_after, "github")["username"] == "student_dev"
        assert len(search_entries(entries_after, "school")) == 1
        assert "password" not in list_entries(entries_after)[0]

        update_entry(entries_after, str(item["id"]), username="new_student_dev")
        save_entries(vault_file, doc, entries_after, key)
        _, entries_updated, _ = unlock_vault(vault_file, "CorrectHorseBatteryStaple!")
        assert entries_updated[0]["username"] == "new_student_dev"

        rotate_master_password(vault_file, "CorrectHorseBatteryStaple!", "NewMasterPass$999")
        with pytest.raises(InvalidMasterPasswordError):
            unlock_vault(vault_file, "CorrectHorseBatteryStaple!")

        _, entries_rot, _ = unlock_vault(vault_file, "NewMasterPass$999")
        delete_entry(entries_rot, "GitHub")
        assert entries_rot == []


    def test_generator_and_strength() -> None:
        pw = generate_password(length=20)
        assert len(pw) == 20
        rating, _ = check_password_strength(pw)
        assert rating == "Strong"
    '''
)


FILE_README_MD = textwrap.dedent(
    """\
    # PyVault (Grade 12 CLI Project)

    Local-only command-line password vault in Python using:
    - **Argon2id** (`argon2-cffi`) for master password hashing/verification and key derivation
    - **AES-256-GCM** (`cryptography`) for authenticated encryption of stored credentials
    - **Atomic file writes** (`tempfile` + `os.fsync` + `os.replace`) to prevent vault corruption

    ## Usage

    ```bash
    pip install argon2-cffi cryptography pytest
    python -m pyvault init
    python -m pyvault add --service github --username student --generate
    python -m pyvault list
    python -m pyvault get github
    python -m pyvault
    ```

    ## Run Tests

    ```bash
    pytest
    ```
    """
)


FILE_REQUIREMENTS_TXT = textwrap.dedent(
    """\
    argon2-cffi>=23.1.0
    cryptography>=42.0.0
    pytest>=8.0.0
    """
)


PROJECT_FILES: dict[str, str] = {
    f"{PACKAGE_NAME}/__init__.py": FILE_INIT_PY,
    f"{PACKAGE_NAME}/storage.py": FILE_STORAGE_PY,
    f"{PACKAGE_NAME}/crypto.py": FILE_CRYPTO_PY,
    f"{PACKAGE_NAME}/generator.py": FILE_GENERATOR_PY,
    f"{PACKAGE_NAME}/vault.py": FILE_VAULT_PY,
    f"{PACKAGE_NAME}/main.py": FILE_MAIN_PY,
    "tests/test_pyvault.py": FILE_TEST_PY,
    "requirements.txt": FILE_REQUIREMENTS_TXT,
    "README.md": FILE_README_MD,
}


def write_project_files(base_dir: Path, force: bool = False) -> list[Path]:
    """Create directories and write all PyVault project files."""
    created_files: list[Path] = []
    base_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, content in PROJECT_FILES.items():
        target = base_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and not force:
            print(f"[SKIP] {target} already exists (use --force to overwrite)")
            continue

        tmp_file: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                tmp_file = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_file, target)
            created_files.append(target)
            print(f"[OK]   Wrote {target}")
        except OSError as exc:
            if tmp_file is not None and tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass
            raise RuntimeError(f"Failed writing {target}: {exc}") from exc

    return created_files


def compile_check(base_dir: Path) -> None:
    """Syntax-check all generated .py files using py_compile."""
    print("\n--- Checking Python syntax ---")
    py_files = sorted(base_dir.rglob("*.py"))
    for py_file in py_files:
        py_compile.compile(str(py_file), doraise=True)
        print(f"[SYNTAX OK] {py_file}")


def install_dependencies(install_pytest: bool = False) -> None:
    """Install required packages via pip."""
    packages = list(REQUIRED_PACKAGES)
    if install_pytest:
        packages.append("pytest")

    print("\n--- Installing dependencies ---")
    cmd = [sys.executable, "-m", "pip", "install", *packages]
    subprocess.run(cmd, check=True)


def run_smoke_test(base_dir: Path) -> None:
    """Run a quick non-interactive smoke test using an isolated temp vault."""
    print("\n--- Running smoke test ---")
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{base_dir}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(base_dir)
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        vault_file = Path(tmp_dir) / "smoke_vault.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                PACKAGE_NAME,
                "--vault",
                str(vault_file),
                "generate",
                "--length",
                "16",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        output = proc.stdout.strip()
        if not output or "[Strong]" not in output:
            raise RuntimeError(f"Unexpected generator output: {output!r}")
        print(f"[SMOKE OK] Generator output: {output}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the PyVault CLI password vault project files."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / ROOT_DIR_NAME,
        help=f"Target project directory (default: ./{ROOT_DIR_NAME})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files in the target directory",
    )
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Install argon2-cffi and cryptography using pip",
    )
    parser.add_argument(
        "--with-pytest",
        action="store_true",
        help="Also install pytest when used with --install-deps",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run a quick password generator smoke test after generating files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_dir: Path = args.output_dir.resolve()

    print(f"Setting up PyVault project in: {target_dir}\n")
    try:
        write_project_files(target_dir, force=args.force)
        compile_check(target_dir)

        if args.install_deps:
            install_dependencies(install_pytest=args.with_pytest)

        if args.smoke_test:
            run_smoke_test(target_dir)

    except (RuntimeError, py_compile.PyCompileError, subprocess.CalledProcessError) as exc:
        print(f"\nSetup failed: {exc}", file=sys.stderr)
        return 1

    print("\nSetup complete! Next steps:")
    print(f"  cd {target_dir}")
    print("  pip install -r requirements.txt")
    print("  python -m pyvault init")
    print("  python -m pyvault")
    return 0


if __name__ == "__main__":
    sys.exit(main())
