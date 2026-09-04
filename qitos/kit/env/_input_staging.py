"""Descriptor-relative, bounded copy into task-owned staging storage."""
import hashlib
import os
from pathlib import Path
import stat

from qitos.core.env import EnvCapabilityError
from ._publication import _path, _root_descriptor


def _stage_input(source: Path, target: Path, *, byte_limit: int) -> dict[str, str]:
    def reject(code: str) -> EnvCapabilityError:
        return EnvCapabilityError(code, "sandbox input staging was rejected")

    total = 0
    entries = 0
    digests: dict[str, str] = {}

    def visit(directory: int, destination: Path, relative: Path, depth: int) -> None:
        nonlocal total, entries
        if depth > 64:
            raise reject("sandbox_input_depth_limit")
        destination.mkdir(mode=0o700)
        with os.scandir(directory) as listing:
            for item in listing:
                entries += 1
                if entries > 10000:
                    raise reject("sandbox_input_entry_limit")
                try:
                    _path(item.name)
                except EnvCapabilityError as error:
                    if error.code == "publication_protected_path":
                        continue
                    raise reject("sandbox_input_path_invalid") from None
                before = item.stat(follow_symlinks=False)
                if stat.S_ISLNK(before.st_mode):
                    continue
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if stat.S_ISDIR(before.st_mode):
                    flags |= os.O_DIRECTORY
                elif not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise reject("sandbox_input_special_file")
                descriptor = os.open(item.name, flags, dir_fd=directory)
                try:
                    opened = os.fstat(descriptor)
                    if (opened.st_dev, opened.st_ino, opened.st_mode) != (before.st_dev, before.st_ino, before.st_mode):
                        raise reject("sandbox_input_changed")
                    child = destination / item.name
                    if stat.S_ISDIR(opened.st_mode):
                        visit(descriptor, child, relative / item.name, depth + 1)
                    else:
                        if opened.st_nlink != 1 or opened.st_size + total > byte_limit:
                            raise reject("sandbox_input_size_or_link_limit")
                        digest = hashlib.sha256()
                        with child.open("xb") as output:
                            while chunk := os.read(descriptor, 1024 * 1024):
                                total += len(chunk)
                                if total > byte_limit:
                                    raise reject("sandbox_input_size_limit")
                                output.write(chunk)
                                digest.update(chunk)
                        os.chmod(child, opened.st_mode & 0o777)
                        digests[(relative / item.name).as_posix()] = digest.hexdigest()
                    after = os.fstat(descriptor)
                    if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise reject("sandbox_input_changed")
                finally:
                    os.close(descriptor)

    try:
        root = _root_descriptor(source)
        try:
            visit(root, target, Path(), 0)
        finally:
            os.close(root)
    except EnvCapabilityError as error:
        if error.code.startswith("publication_"):
            raise reject("sandbox_input_platform_or_containment") from None
        raise
    except OSError:
        raise reject("sandbox_input_containment") from None
    return digests
