"""Read-only local Git adapter for P04a. Reads object data; never checks out or runs a fork."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from .root_import import (
    MAX_FILE,
    MAX_MANIFEST,
    MAX_TOTAL,
    SHA,
    GitBlob,
    RootImportError,
    RootManifest,
    parse_manifest,
    prepare_candidate,
    safe_path,
)


class GitSnapshot:
    def __init__(self, repo: Path, commit: str):
        if not SHA.fullmatch(commit):
            raise RootImportError("IMMUTABLE_COMMIT_REQUIRED")
        self.repo, self.commit = repo, commit
        version = re.match(rb"git version (\d+)\.(\d+)", self.git("--version"))
        if not version or tuple(map(int, version.groups())) < (2, 46):
            raise RootImportError("GIT_2_46_REQUIRED")
        if self.git("cat-file", "-t", commit).strip() != b"commit":
            raise RootImportError("COMMIT_NOT_FOUND")

    def git(self, *args) -> bytes:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_LITERAL_PATHSPECS="1")
        try:
            result = subprocess.run(
                [
                    "git",
                    "--no-pager",
                    "--no-optional-locks",
                    "-c",
                    "core.fsmonitor=false",
                    "-C",
                    str(self.repo),
                    *args,
                ],
                env=env,
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RootImportError("GIT_READ_FAILED") from None
        if result.returncode:
            raise RootImportError("GIT_READ_FAILED")
        return result.stdout

    def blob(self, path: str, limit: int) -> GitBlob:
        try:
            safe_path(path)
        except ValueError:
            raise RootImportError("INVALID_GIT_PATH") from None
        row = self.git("ls-tree", "-z", self.commit, "--", path).rstrip(b"\0")
        if not row:
            raise RootImportError("FILE_MISSING", path)
        try:
            metadata, filename = row.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split()
        except (ValueError, UnicodeError):
            raise RootImportError("INVALID_GIT_ENTRY", path) from None
        if (
            filename != path.encode()
            or kind != "blob"
            or mode not in ("100644", "100755")
            or not SHA.fullmatch(oid)
        ):
            raise RootImportError("NON_REGULAR_GIT_BLOB", path)
        size = int(self.git("cat-file", "-s", oid).strip())
        if size > limit:
            raise RootImportError("FILE_TOO_LARGE", path)
        data = self.git("cat-file", "blob", oid)
        if len(data) != size:
            raise RootImportError("GIT_OBJECT_CHANGED", path)
        return GitBlob(data, mode)


def preflight(
    repo: Path,
    commit: str,
    site_id: str,
    manifest_path: str,
    public_revisions: dict[str, str] | None = None,
):
    snapshot = GitSnapshot(repo, commit)
    raw = snapshot.blob(manifest_path, MAX_MANIFEST).data
    manifest = parse_manifest(raw, site_id)
    files = [p.file for p in manifest.points]
    if manifest.welcome:
        files.append(manifest.welcome.file)
    blobs = {}
    remaining = MAX_TOTAL - len(raw)
    for file in files:
        path = f"site-content/{file}"
        blobs[path] = snapshot.blob(path, min(MAX_FILE, remaining))
        remaining -= len(blobs[path].data)
    return prepare_candidate(
        raw, blobs, site_id=site_id, commit_sha=commit, public_revisions=public_revisions
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", action="store_true", help="Print the manifest JSON Schema")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--commit", help="Full immutable 40-character commit SHA, not a branch")
    parser.add_argument("--site-id", help="Expected public site ID; not proof of ownership")
    parser.add_argument("--manifest", default="node06-roots.json")
    parser.add_argument(
        "--public-revisions", type=Path, help="Trusted JSON map of public ID to revision"
    )
    args = parser.parse_args()
    if args.schema:
        print(json.dumps(RootManifest.model_json_schema(), ensure_ascii=False, indent=2))
        return 0
    if not all((args.repo, args.commit, args.site_id)):
        parser.error("--repo, --commit and --site-id are required")
    try:
        revisions = None
        if args.public_revisions:
            if args.public_revisions.stat().st_size > 1024 * 1024:
                raise RootImportError("PUBLIC_INDEX_TOO_LARGE")
            revisions = json.loads(args.public_revisions.read_text(encoding="utf-8"))
        candidate = preflight(args.repo, args.commit, args.site_id, args.manifest, revisions)
    except RootImportError as exc:
        print(
            json.dumps(
                {"code": exc.code, "file": exc.path, "line": exc.line, "writes_performed": False}
            )
        )
        return 1
    except (OSError, UnicodeError, ValueError, RecursionError):
        print(json.dumps({"code": "INVALID_LOCAL_INPUT", "writes_performed": False}))
        return 1
    print(json.dumps(candidate.summary(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
