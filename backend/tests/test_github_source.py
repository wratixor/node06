"""No external network: GitHub object identity, immutable reads and unsafe modes."""

import base64
import hashlib
import json

import pytest
from node06_service.github_source import Snapshot, coordinates, load
from node06_service.root_import import RootImportError

SITE = "s_" + "1" * 32


def fixture_api(proof="f" * 64):
    manifest = {
        "schema_version": 1,
        "site_id": SITE,
        "source_proof": proof,
        "content_directory": "site-content",
        "welcome": {"file": "home.md", "mode": "git"},
        "points": [{"id": "idea", "file": "idea.md", "lang": "ru"}],
    }
    files = {
        "node06-roots.json": json.dumps(manifest).encode(),
        "site-content/home.md": b"[Idea](md://local/idea)",
        "site-content/idea.md": b"[Home](md://local/welcome)",
    }
    objects = {}

    def blob(path):
        data = files[path]
        sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        objects["/git/blobs/" + sha] = {
            "sha": sha,
            "size": len(data),
            "encoding": "base64",
            "content": base64.b64encode(data).decode(),
        }
        return {
            "path": path.split("/")[-1],
            "type": "blob",
            "mode": "100644",
            "sha": sha,
            "size": len(data),
        }

    objects.update(
        {
            "": {
                "id": 1,
                "owner": {"id": 2},
                "full_name": "Example/Wiki",
                "private": False,
                "visibility": "public",
            },
            "/git/ref/heads/main": {
                "ref": "refs/heads/main",
                "object": {"type": "commit", "sha": "a" * 40},
            },
            "/git/commits/" + "a" * 40: {"sha": "a" * 40, "tree": {"sha": "b" * 40}},
            "/git/trees/" + "b" * 40: {
                "sha": "b" * 40,
                "truncated": False,
                "tree": [
                    blob("node06-roots.json"),
                    {"path": "site-content", "type": "tree", "mode": "040000", "sha": "c" * 40},
                ],
            },
            "/git/trees/" + "c" * 40: {
                "sha": "c" * 40,
                "truncated": False,
                "tree": [blob("site-content/home.md"), blob("site-content/idea.md")],
            },
        }
    )
    calls = []

    def get(path, maximum, timeout):
        assert path.startswith("/repos/example/wiki") and 0 < timeout <= 5 and maximum <= 524288
        calls.append(path)
        return objects[path.removeprefix("/repos/example/wiki")]

    return objects, get, calls


def test_immutable_snapshot_manifest_and_hashes():
    _, get, calls = fixture_api()
    candidate, identity, proof = load("Example/Wiki", "main", SITE, get=get)
    assert candidate.commit_sha == "a" * 40 and identity == (1, 2)
    assert len(candidate.points) == 2 and proof == hashlib.sha256(("f" * 64).encode()).hexdigest()
    assert sum("/git/ref/" in p for p in calls) == 1
    assert all("/contents/" not in p for p in calls)


@pytest.mark.parametrize(
    "repository,branch",
    [
        ("https://localhost/x", "main"),
        ("a/b?url=x", "main"),
        ("a/..", "main"),
        ("a/b", "../x"),
        ("a/b", "main\r\nHost: evil"),
        ("a/b", "a//b"),
    ],
)
def test_source_coordinates_cannot_be_urls(repository, branch):
    with pytest.raises(RootImportError, match="INVALID_GITHUB_SOURCE"):
        coordinates(repository, branch)


@pytest.mark.parametrize(
    "case", ["symlink", "submodule", "truncated", "wrong-blob", "private", "wrong-ref"]
)
def test_reject_unsafe_or_changed_objects(case):
    objects, get, _ = fixture_api()
    if case in ("symlink", "submodule"):
        objects["/git/trees/" + "c" * 40]["tree"][0]["mode"] = (
            "120000" if case == "symlink" else "160000"
        )
    elif case == "truncated":
        objects["/git/trees/" + "b" * 40]["truncated"] = True
    elif case == "wrong-blob":
        next(value for key, value in objects.items() if key.startswith("/git/blobs/"))[
            "content"
        ] = "d3Jvbmc="
    elif case == "private":
        objects[""]["private"] = True
    else:
        objects["/git/ref/heads/main"]["ref"] = "refs/heads/other"
    with pytest.raises(RootImportError):
        load("example/wiki", "main", SITE, get=get)


def test_request_budget_and_deadline():
    _, get, _ = fixture_api()
    snapshot = Snapshot("example/wiki", "main", get=get)
    snapshot.requests = 128
    with pytest.raises(RootImportError, match="SOURCE_FETCH_LIMIT"):
        snapshot.blob("node06-roots.json", 16384)


def test_unchanged_commit_reads_only_public_identity_and_ref():
    _, get, calls = fixture_api()
    candidate, identity, proof = load("example/wiki", "main", SITE, "a" * 40, get=get)
    assert candidate is None and proof is None and identity == (1, 2)
    assert len(calls) == 2 and all("/git/blobs/" not in p for p in calls)
