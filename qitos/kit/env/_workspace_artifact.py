"""Bounded private workspace snapshots carried by the artifact resolver."""

import base64
import hashlib
import json
import subprocess
from typing import Any

from qitos.core.artifact import ArtifactRef
from qitos.core.env import EnvCapabilityError


_LIMIT = 8 * 1024 * 1024
_CAPTURE = r'''
import base64, json, os, pathlib, stat, sys
root = pathlib.Path(sys.argv[1])
limit = int(sys.argv[2]); total = 0; files = {}; directories = []
for parent, names, entries in os.walk(root, followlinks=False):
    for name in sorted(names + entries):
        path = pathlib.Path(parent) / name
        relative = path.relative_to(root).as_posix()
        facts = path.lstat()
        if stat.S_ISDIR(facts.st_mode):
            directories.append(relative)
            continue
        if not stat.S_ISREG(facts.st_mode) or facts.st_nlink != 1:
            raise ValueError('workspace_special_file')
        total += facts.st_size
        if total > limit // 2 or len(files) + len(directories) >= 4096:
            raise ValueError('workspace_snapshot_limit')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            current = os.fstat(stream.fileno())
            if not stat.S_ISREG(current.st_mode) or current.st_ino != facts.st_ino:
                raise ValueError('workspace_changed')
            body = stream.read(limit // 2 + 1)
            after = os.fstat(stream.fileno())
            if len(body) != facts.st_size or facts.st_mtime_ns != after.st_mtime_ns:
                raise ValueError('workspace_changed')
        files[relative] = {'body': base64.b64encode(body).decode(), 'mode': facts.st_mode & 0o777}
payload = json.dumps({'files': files, 'directories': directories}, sort_keys=True, separators=(',', ':'))
if len(payload.encode()) > limit:
    raise ValueError('workspace_snapshot_limit')
print(payload)
'''
_RESTORE = r'''
import base64, json, pathlib, shutil, sys
root = pathlib.Path(sys.argv[1]); payload = json.load(sys.stdin)
for name in list(payload['files']) + payload['directories']:
    path = pathlib.PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('workspace_path_invalid')
# This is an attested, task-owned container tmpfs, never a host bind.
for entry in root.iterdir():
    if entry.is_dir() and not entry.is_symlink():
        shutil.rmtree(entry)
    else:
        entry.unlink()
for name in sorted(payload['directories'], key=lambda value: len(pathlib.PurePosixPath(value).parts)):
    (root / name).mkdir(parents=True, exist_ok=True)
for name, value in payload['files'].items():
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(value['body'], validate=True))
    target.chmod(value['mode'] & 0o777)
'''


def retain_workspace(env: Any) -> ArtifactRef:
    resolver = env._artifact_resolver
    if resolver is None or not callable(getattr(resolver, "put", None)):
        raise EnvCapabilityError("sandbox_artifact_unavailable", "workspace retention requires an artifact store")
    try:
        result = subprocess.run(["docker", "exec", env.container, "python3", "-c", _CAPTURE,
                                 env.container_workspace, str(_LIMIT)], capture_output=True, timeout=30, check=True)
        if len(result.stdout) > _LIMIT:
            raise ValueError("snapshot bound exceeded")
        payload = json.loads(result.stdout)
        payload.update(input_files=env._input_files, input_digest=env.input_digest)
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        if len(body) > _LIMIT:
            raise ValueError("snapshot bound exceeded")
        digest = hashlib.sha256(body).hexdigest()
        reference = ArtifactRef(artifact_id=f"sha256:{digest}", resolver_key=resolver.resolver_key,
                                sha256=digest, byte_length=len(body), media_type="application/json",
                                sensitivity="restricted")
        resolver.put(reference, body)
        env.output_artifact = reference
        env.workspace_digest = digest
        return reference
    except Exception:
        raise EnvCapabilityError("sandbox_snapshot_failed", "workspace artifact could not be retained") from None


def workspace_payload(env: Any, reference: ArtifactRef) -> dict[str, Any]:
    try:
        resolved = env._artifact_resolver.resolve(reference)
        if len(resolved.body) > _LIMIT:
            raise ValueError("snapshot bound exceeded")
        return dict(json.loads(resolved.body))
    except Exception:
        raise EnvCapabilityError("sandbox_artifact_unavailable", "workspace artifact is unavailable or invalid") from None


def restore_workspace(env: Any, reference: ArtifactRef) -> None:
    payload = workspace_payload(env, reference)
    try:
        subprocess.run(["docker", "exec", "-i", env.container, "python3", "-c", _RESTORE, env.container_workspace],
                       input=json.dumps(payload).encode(), capture_output=True, timeout=30, check=True)
    except Exception:
        raise EnvCapabilityError("sandbox_restore_failed", "workspace restoration failed") from None
    env._input_files = payload["input_files"]
    env.input_digest = payload["input_digest"]
    env.output_artifact = reference
    env.workspace_digest = reference.sha256


def selected_output(env: Any, path: str) -> bytes:
    if env.output_artifact is None:
        raise EnvCapabilityError("sandbox_artifact_unavailable", "workspace output was not retained")
    payload = workspace_payload(env, env.output_artifact)
    try:
        return base64.b64decode(payload["files"][path]["body"], validate=True)
    except (KeyError, ValueError):
        raise EnvCapabilityError("publication_output_missing", "selected output is unavailable") from None
