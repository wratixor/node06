"""Public GitHub objects only: pinned TLS, immutable commit, no clone or execution."""

import base64
import hashlib
import http.client
import json
import multiprocessing
import os
import re
import signal
import socket
import ssl
import time
from urllib.parse import quote

from .root_import import (
    MAX_FILE,
    MAX_MANIFEST,
    MAX_TOTAL,
    SHA,
    GitBlob,
    RootImportError,
    parse_manifest,
    prepare_candidate,
    safe_path,
)
from .site_claims import SiteClaimError, resolve_public_target

REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}")
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,127}")


def coordinates(repository, branch):
    if (
        not REPOSITORY.fullmatch(repository)
        or repository.split("/")[1] in (".", "..")
        or repository.endswith(".git")
        or not BRANCH.fullmatch(branch)
        or any(part in ("", ".", "..") or part.endswith(".lock") for part in branch.split("/"))
        or ".." in branch
    ):
        raise RootImportError("INVALID_GITHUB_SOURCE")
    return repository.lower(), branch


def request_json(path, maximum, timeout):
    # Never use a response URL or redirect; every request is built under this one host.
    target = resolve_public_target("https://api.github.com")
    raw = socket.create_connection((target.addresses[0], 443), timeout=timeout)
    tls = None
    try:
        tls = ssl.create_default_context().wrap_socket(raw, server_hostname=target.hostname)
        tls.sendall(
            (
                f"GET {path} HTTP/1.1\r\nHost: api.github.com\r\n"
                "User-Agent: node06-public-source/1\r\nAccept: application/vnd.github+json\r\n"
                "X-GitHub-Api-Version: 2022-11-28\r\nConnection: close\r\n\r\n"
            ).encode("ascii")
        )
        with http.client.HTTPResponse(tls) as response:
            response.begin()
            if response.status != 200:
                raise RootImportError("GITHUB_UNAVAILABLE")
            data = response.read(maximum + 1)
            if len(data) > maximum:
                raise RootImportError("GITHUB_RESPONSE_TOO_LARGE")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise RootImportError("INVALID_GITHUB_RESPONSE")
            return result
    finally:
        if tls:
            tls.close()
        raw.close()


class Snapshot:
    def __init__(self, repository, branch, *, get=request_json, seconds=30):
        repository, branch = coordinates(repository, branch)
        self.prefix = "/repos/" + repository
        self.get, self.deadline, self.requests = get, time.monotonic() + seconds, 0
        meta = self.read("", 65536)
        if (
            meta.get("private") is not False
            or meta.get("visibility") != "public"
            or str(meta.get("full_name", "")).lower() != repository
            or type(meta.get("id")) is not int
            or type(meta.get("owner", {}).get("id")) is not int
        ):
            raise RootImportError("PUBLIC_REPOSITORY_REQUIRED")
        self.identity = (meta["id"], meta["owner"]["id"])
        ref = self.read("/git/ref/heads/" + quote(branch, safe=""), 8192)
        if (
            ref.get("ref") != "refs/heads/" + branch
            or ref.get("object", {}).get("type") != "commit"
        ):
            raise RootImportError("BRANCH_COMMIT_REQUIRED")
        self.commit = self.sha(ref["object"].get("sha"))
        self.tree_sha = None
        self.trees = {}

    @staticmethod
    def sha(value):
        if not isinstance(value, str) or not SHA.fullmatch(value):
            raise RootImportError("INVALID_GITHUB_OBJECT")
        return value

    def read(self, path, maximum):
        self.requests += 1
        remaining = self.deadline - time.monotonic()
        if self.requests > 128 or remaining <= 0:
            raise RootImportError("SOURCE_FETCH_LIMIT")
        return self.get(self.prefix + path, maximum, min(remaining, 5))

    def tree(self, sha):
        if sha not in self.trees:
            value = self.read("/git/trees/" + sha, 524288)
            if value.get("sha") != sha or value.get("truncated") is not False:
                raise RootImportError("INCOMPLETE_GITHUB_TREE")
            rows = value.get("tree")
            if not isinstance(rows, list) or len(rows) > 3000:
                raise RootImportError("GITHUB_TREE_TOO_LARGE")
            if any(not isinstance(r, dict) for r in rows):
                raise RootImportError("INVALID_GITHUB_TREE")
            names = [r.get("path") for r in rows]
            if any(not isinstance(n, str) for n in names) or len(set(names)) != len(names):
                raise RootImportError("INVALID_GITHUB_TREE")
            self.trees[sha] = {r["path"]: r for r in rows}
        return self.trees[sha]

    def blob(self, path, limit):
        safe_path(path)
        if self.tree_sha is None:
            commit = self.read("/git/commits/" + self.commit, 131072)
            if commit.get("sha") != self.commit:
                raise RootImportError("GITHUB_OBJECT_CHANGED")
            self.tree_sha = self.sha(commit.get("tree", {}).get("sha"))
        parts, sha = path.split("/"), self.tree_sha
        for i, part in enumerate(parts):
            row = self.tree(sha).get(part)
            if row is None:
                raise RootImportError("FILE_MISSING", path)
            sha = self.sha(row.get("sha"))
            if i < len(parts) - 1:
                if row.get("type") != "tree" or row.get("mode") != "040000":
                    raise RootImportError("NON_REGULAR_GIT_BLOB", path)
            elif row.get("type") != "blob" or row.get("mode") not in ("100644", "100755"):
                raise RootImportError("NON_REGULAR_GIT_BLOB", path)
        if type(row.get("size")) is not int or not 0 <= row["size"] <= limit:
            raise RootImportError("FILE_TOO_LARGE", path)
        value = self.read("/git/blobs/" + sha, limit * 2 + 8192)
        if value.get("sha") != sha or value.get("encoding") != "base64":
            raise RootImportError("INVALID_GITHUB_OBJECT")
        try:
            data = base64.b64decode("".join(value["content"].split()), validate=True)
        except (KeyError, ValueError, TypeError):
            raise RootImportError("INVALID_GITHUB_OBJECT") from None
        if (
            len(data) != row["size"]
            or value.get("size") != len(data)
            or hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != sha
        ):
            raise RootImportError("GITHUB_OBJECT_CHANGED")
        return GitBlob(data, row["mode"])


def load(repository, branch, site_id, known_commit=None, *, get=request_json):
    snapshot = Snapshot(repository, branch, get=get)
    if known_commit == snapshot.commit:
        return None, snapshot.identity, None
    raw = snapshot.blob("node06-roots.json", MAX_MANIFEST).data
    manifest = parse_manifest(raw, site_id)
    if manifest.welcome is None:
        raise RootImportError("GIT_WELCOME_REQUIRED")
    files = [p.file for p in manifest.points] + [manifest.welcome.file]
    blobs, remaining = {}, MAX_TOTAL - len(raw)
    for file in files:
        path = "site-content/" + file
        blobs[path] = snapshot.blob(path, min(MAX_FILE, remaining))
        remaining -= len(blobs[path].data)
    candidate = prepare_candidate(raw, blobs, site_id=site_id, commit_sha=snapshot.commit)
    proof = hashlib.sha256((manifest.source_proof or "").encode()).hexdigest()
    return candidate, snapshot.identity, proof


def _worker(sender, args):
    if hasattr(signal, "setitimer"):
        signal.signal(signal.SIGALRM, lambda *_: os._exit(124))
        signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        sender.send((True, load(*args)))
    except RootImportError as exc:
        sender.send((False, exc.code))
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        SiteClaimError,
        http.client.HTTPException,
    ):
        sender.send((False, "GITHUB_UNAVAILABLE"))
    finally:
        sender.close()


def fetch(repository, branch, site_id, known_commit=None):
    """Hard deadline includes DNS, TLS, every object and the child lifetime."""
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker, args=(sender, (repository, branch, site_id, known_commit)), daemon=True
    )
    deadline = time.monotonic() + 30
    try:
        try:
            process.start()
        except (OSError, RuntimeError):
            raise RootImportError("SOURCE_FETCH_UNAVAILABLE") from None
        sender.close()
        if not receiver.poll(max(0, deadline - time.monotonic())):
            raise RootImportError("SOURCE_FETCH_TIMEOUT")
        try:
            ok, value = receiver.recv()
        except EOFError:
            raise RootImportError("SOURCE_FETCH_TIMEOUT") from None
        if not ok:
            raise RootImportError(value)
        if time.monotonic() > deadline:
            raise RootImportError("SOURCE_FETCH_TIMEOUT")
        return value
    finally:
        receiver.close()
        sender.close()
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=0.5)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
