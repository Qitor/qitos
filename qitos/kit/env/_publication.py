"""Explicit descriptor-relative source publication with atomic file exchange.

The supported operation replaces selected top-level regular files. Nested path
publication is deliberately rejected until an equally strong containment
primitive is qualified. Cleanup never calls this module.
"""

import ctypes
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from uuid import uuid4

from qitos.core.env import EnvCapabilityError


def _reject(code: str) -> EnvCapabilityError:
    return EnvCapabilityError(code, "explicit workspace publication was rejected")


def _path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise _reject("publication_path_invalid")
    protected = {".git", ".ssh", ".gnupg", ".aws", ".azure", ".qitos", ".netrc", ".gitconfig"}
    if any(part.lower() in protected or part.lower().startswith(".env")
           or "secret" in part.lower() or "credential" in part.lower()
           or part.lower().endswith((".pem", ".key", ".p12")) for part in path.parts):
        raise _reject("publication_protected_path")
    if len(path.parts) != 1 or path.name in {"", "."}:
        raise _reject("nested_publication_unsupported")
    return path.name


def _root_descriptor(root: Path) -> int:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise _reject("publication_platform_unsupported")
    # Walk every ancestor without resolving a caller-supplied symlink.
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.absolute().parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError:
        os.close(descriptor)
        raise _reject("publication_target_containment") from None


def _digest_at(directory: int, name: str) -> str | None:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return None
    except OSError:
        raise _reject("publication_link_rejected") from None
    with os.fdopen(descriptor, "rb") as handle:
        facts = os.fstat(handle.fileno())
        if not stat.S_ISREG(facts.st_mode) or facts.st_nlink != 1:
            raise _reject("publication_special_file")
        # Keep the validated descriptor and bounded memory on Python 3.10 too.
        hasher = hashlib.sha256()
        for chunk in iter(lambda: handle.read(256 * 1024), b""):
            hasher.update(chunk)
        digest = hasher.hexdigest()
        after = os.fstat(handle.fileno())
        if (facts.st_size, facts.st_mtime_ns, facts.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise _reject("publication_source_conflict")
        return digest


def _exchange(directory: int, source: str, target: str) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    name = "renameatx_np" if sys.platform == "darwin" else "renameat2"
    operation = getattr(library, name, None)
    if operation is None:
        raise _reject("publication_platform_unsupported")
    operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    operation.restype = ctypes.c_int
    # Darwin RENAME_SWAP and Linux RENAME_EXCHANGE both use flag 2.
    if operation(directory, os.fsencode(source), directory, os.fsencode(target), 2) != 0:
        raise _reject("publication_exchange_failed")


def publish_files(root: Path, originals: dict[str, str], outputs: dict[str, bytes]) -> dict:
    names = [_path(name) for name in outputs]
    if len(names) != len(set(names)) or not names:
        raise _reject("publication_selection_invalid")
    directory = _root_descriptor(root)
    staged: dict[str, str] = {}
    committed: list[str] = []
    preserve = False
    try:
        import fcntl
        try:
            fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise _reject("publication_workspace_busy") from None
        for name in names:
            if _digest_at(directory, name) != originals.get(name):
                raise _reject("publication_source_conflict")
            temporary = f".qitos-publication-{uuid4().hex}"
            staged[name] = temporary
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            with os.fdopen(descriptor, "wb") as handle:
                if name in originals:
                    mode = os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode
                    os.fchmod(handle.fileno(), stat.S_IMODE(mode) & 0o777)
                handle.write(outputs[name])
                handle.flush()
                os.fsync(handle.fileno())
        for name in names:
            if name in originals:
                _exchange(directory, staged[name], name)
                committed.append(name)
                # Check the displaced inode, closing the check/replace race.
                if _digest_at(directory, staged[name]) != originals[name]:
                    raise _reject("publication_source_conflict")
            else:
                os.link(staged[name], name, src_dir_fd=directory, dst_dir_fd=directory,
                        follow_symlinks=False)
                committed.append(name)
                os.unlink(staged[name], dir_fd=directory)
        os.fsync(directory)
        return {"status": "published", "paths": names,
                "output_digests": {name: hashlib.sha256(outputs[name]).hexdigest() for name in names}}
    except (OSError, EnvCapabilityError):
        try:
            for name in reversed(committed):
                # Do not clobber a newer concurrent writer during rollback.
                current = _digest_at(directory, name)
                if current != hashlib.sha256(outputs[name]).hexdigest():
                    preserve = True
                    raise _reject("publication_rollback_unknown")
                if name in originals:
                    _exchange(directory, staged[name], name)
                else:
                    os.unlink(name, dir_fd=directory)
            os.fsync(directory)
        except (OSError, EnvCapabilityError):
            preserve = True
            raise _reject("publication_rollback_unknown") from None
        raise _reject("publication_rejected_rolled_back") from None
    finally:
        if not preserve:
            for temporary in staged.values():
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
        os.close(directory)
