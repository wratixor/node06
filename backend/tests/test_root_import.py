import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from node06_service.root_import import (
    MAX_FILE,
    GitBlob,
    RootImportError,
    RootManifest,
    prepare_candidate,
)
from node06_service.root_preflight import preflight

ROOT = Path(__file__).resolve().parents[2]
SITE = "s_" + "1" * 32
OTHER = "s_" + "2" * 32
COMMIT = "a" * 40
REVISION = "v_" + "3" * 32


def fixture_source():
    manifest = {
        "schema_version": 1,
        "site_id": SITE,
        "content_directory": "site-content",
        "welcome": {"file": "welcome.md", "mode": "git"},
        "points": [{"id": "thought", "file": "thought.md", "lang": "ja"}],
    }
    blobs = {
        "site-content/welcome.md": GitBlob(b"[thought](md://local/thought)"),
        "site-content/thought.md": GitBlob("言葉 [start](md://local/welcome)".encode()),
    }
    return manifest, blobs


def candidate(manifest=None, blobs=None, **kwargs):
    original, files = fixture_source()
    return prepare_candidate(
        json.dumps(original if manifest is None else manifest).encode(),
        files if blobs is None else blobs,
        site_id=kwargs.pop("site_id", SITE),
        commit_sha=kwargs.pop("commit_sha", COMMIT),
        **kwargs,
    )


def test_schema_is_published_without_drift():
    assert json.loads((ROOT / "docs/schemas/root-manifest-v1.schema.json").read_text()) == (
        RootManifest.model_json_schema()
    )


def test_namespace_welcome_and_content_identity_are_stable():
    first = candidate()
    assert {p.id for p in first.points} == {SITE, "r_" + "1" * 32 + "_thought"}
    assert first == candidate()
    manifest, blobs = fixture_source()
    manifest["points"][0]["file"] = "renamed.md"
    blobs["site-content/renamed.md"] = blobs.pop("site-content/thought.md")
    renamed = candidate(manifest, blobs, commit_sha="b" * 40)
    assert [p.content_digest for p in first.points] == [p.content_digest for p in renamed.points]
    assert first.digest != renamed.digest
    manifest["site_id"] = OTHER
    different = candidate(manifest, blobs, site_id=OTHER)
    assert {p.id for p in first.points}.isdisjoint({p.id for p in different.points})
    with pytest.raises(FrozenInstanceError):
        first.site_id = OTHER


def test_external_targets_pin_supplied_public_revision_only():
    manifest, blobs = fixture_source()
    body = blobs["site-content/thought.md"].data + b" [core](md://point/all-sites)"
    blobs["site-content/thought.md"] = GitBlob(body)
    with pytest.raises(RootImportError, match="PUBLIC_TARGET_MISSING"):
        candidate(manifest, blobs)
    result = candidate(manifest, blobs, public_revisions={"all-sites": REVISION})
    assert dict(result.points[0].external_revision_pins) == {"all-sites": REVISION}
    changed = candidate(manifest, blobs, public_revisions={"all-sites": "v_" + "4" * 32})
    assert result.digest != changed.digest


def test_unlisted_core_not_imported_and_proof_not_disclosed():
    manifest, blobs = fixture_source()
    manifest["source_proof"] = "e" * 64
    blobs["content/core.md"] = GitBlob(b"not imported", "120000")
    report = json.dumps(candidate(manifest, blobs).summary())
    assert "e" * 64 not in report and "言葉" not in report
    assert '"source_ownership_verified": false' in report
    assert len(candidate(manifest, blobs).points) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"site_id": OTHER},
        {"content_directory": "content"},
        {"extra": "value"},
    ],
)
def test_manifest_version_site_namespace_and_unknown_fields(mutation):
    manifest, blobs = fixture_source()
    manifest.update(mutation)
    with pytest.raises(RootImportError):
        candidate(manifest, blobs)


@pytest.mark.parametrize(
    "file",
    [
        "../outside.md",
        "/tmp/x.md",
        "a/../x.md",
        "a//x.md",
        ".git/x.md",
        "a\\x.md",
        "x%2emd",
        "a.txt",
        "x.md\n",
    ],
)
def test_paths_cannot_escape_manifest_subtree(file):
    manifest, blobs = fixture_source()
    manifest["points"][0]["file"] = file
    with pytest.raises(RootImportError, match="INVALID_MANIFEST"):
        candidate(manifest, blobs)


@pytest.mark.parametrize(
    "blob,code",
    [
        (GitBlob(b"x", "120000"), "NON_REGULAR_GIT_BLOB"),
        (GitBlob(b"x", "160000"), "NON_REGULAR_GIT_BLOB"),
        (GitBlob(b"\xff"), "INVALID_UTF8"),
        (GitBlob(b"\x00"), "BINARY_OR_CONTROL_TEXT"),
        (GitBlob(b"version https://git-lfs.github.com/spec/v1\noid sha256:abc"), "LFS_POINTER"),
        (GitBlob(b"x" * (MAX_FILE + 1)), "FILE_TOO_LARGE"),
    ],
)
def test_blob_boundary(blob, code):
    manifest, blobs = fixture_source()
    blobs["site-content/thought.md"] = blob
    with pytest.raises(RootImportError, match=code):
        candidate(manifest, blobs)


@pytest.mark.parametrize(
    "body,code",
    [
        (b"[missing](md://local/missing)", "LOCAL_TARGET_MISSING"),
        (b"[self](md://local/thought)", "SELF_LINK"),
        (b"[x](javascript:alert)", "UNSUPPORTED_LINK"),
        (b"[x](https://user:password@example.com)", "UNSUPPORTED_LINK"),
        (b"[x](https://[invalid)", "UNSUPPORTED_LINK"),
        (b"<script>alert(1)</script>", "UNSUPPORTED_HTML_OR_IMAGE"),
        (b"![x](https://example.com/x.png)", "UNSUPPORTED_HTML_OR_IMAGE"),
        (b"plain md://local/welcome", "UNSUPPORTED_POINT_LINK_SYNTAX"),
        (b"[start](md://local/welcome) [again](md://local/welcome)", "DUPLICATE_POINT_LINK"),
        (b"no reciprocal link", "LOCAL_LINK_NOT_RECIPROCAL"),
    ],
)
def test_unsafe_or_unresolved_body_reports_file_and_line(body, code):
    manifest, blobs = fixture_source()
    blobs["site-content/thought.md"] = GitBlob(body)
    with pytest.raises(RootImportError) as error:
        candidate(manifest, blobs)
    assert error.value.code == code
    assert error.value.path.startswith("site-content/")


def test_code_literals_and_intentional_orphan_are_preserved():
    manifest, _ = fixture_source()
    manifest.pop("welcome")
    body = b"`[x](md://local/missing)`\n```html\n<script>not executed</script>\n```"
    result = candidate(manifest, {"site-content/thought.md": GitBlob(body)})
    assert result.points[0].body == body.decode()
    assert result.points[0].links == ()
    assert result.warnings == ("ORPHAN_LOCAL_POINT:r_" + "1" * 32 + "_thought",)


def test_duplicate_manifest_keys_and_quota_fail():
    with pytest.raises(RootImportError, match="DUPLICATE_JSON_KEY"):
        prepare_candidate(
            b'{"schema_version":1,"schema_version":1}', {}, site_id=SITE, commit_sha=COMMIT
        )
    manifest, blobs = fixture_source()
    manifest["points"] *= 2
    with pytest.raises(RootImportError, match="INVALID_MANIFEST"):
        candidate(manifest, blobs)
    manifest["points"] *= 51
    with pytest.raises(RootImportError, match="INVALID_MANIFEST"):
        candidate(manifest, blobs)
    with pytest.raises(RootImportError, match="IMMUTABLE_COMMIT_REQUIRED"):
        candidate(commit_sha="main")


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return result.stdout.decode().strip()


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    manifest, blobs = fixture_source()
    (repo / "node06-roots.json").write_text(json.dumps(manifest))
    (repo / "site-content").mkdir()
    for path, blob in blobs.items():
        (repo / path).write_bytes(blob.data)
    (repo / "build.py").write_text("raise RuntimeError('MUST NOT RUN')")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "fixture")
    return repo, git(repo, "rev-parse", "HEAD")


def test_git_reader_uses_immutable_objects_not_dirty_worktree(tmp_path):
    repo, sha = make_repo(tmp_path)
    first = preflight(repo, sha, SITE, "node06-roots.json")
    (repo / "site-content/thought.md").write_text("uncommitted replacement")
    (repo / "node06-roots.json").write_text("broken working tree")
    before = git(repo, "status", "--porcelain")
    second = preflight(repo, sha, SITE, "node06-roots.json")
    assert first == second
    assert git(repo, "status", "--porcelain") == before
    command = [
        sys.executable,
        "-m",
        "node06_service.root_preflight",
        "--repo",
        str(repo),
        "--site-id",
        SITE,
        "--commit",
        sha,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    assert json.loads(result.stdout)["source_ownership_verified"] is False
    assert "MUST NOT RUN" not in result.stdout


def test_git_reader_rejects_symlink_blob_and_branch_reference(tmp_path):
    repo, sha = make_repo(tmp_path)
    (repo / "site-content/thought.md").unlink()
    (repo / "site-content/thought.md").symlink_to("../build.py")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "symlink")
    with pytest.raises(RootImportError, match="NON_REGULAR_GIT_BLOB"):
        preflight(repo, git(repo, "rev-parse", "HEAD"), SITE, "node06-roots.json")
    with pytest.raises(RootImportError, match="IMMUTABLE_COMMIT_REQUIRED"):
        preflight(repo, "HEAD", SITE, "node06-roots.json")
    # Earlier immutable content remains valid after a bad later commit.
    assert len(preflight(repo, sha, SITE, "node06-roots.json").points) == 2


def test_total_source_bytes_and_link_count_are_bounded():
    manifest = {
        "schema_version": 1,
        "site_id": SITE,
        "content_directory": "site-content",
        "points": [{"id": f"p-{i}", "file": f"p-{i}.md", "lang": "und"} for i in range(33)],
    }
    blobs = {f"site-content/p-{i}.md": GitBlob(b"x" * MAX_FILE) for i in range(33)}
    with pytest.raises(RootImportError, match="SOURCE_TOO_LARGE"):
        candidate(manifest, blobs)
    manifest, blobs = fixture_source()
    refs = {f"external-{i}": REVISION for i in range(17)}
    blobs["site-content/thought.md"] = GitBlob(
        " ".join(f"[x](md://point/{target})" for target in refs).encode()
    )
    with pytest.raises(RootImportError, match="TOO_MANY_LINKS"):
        candidate(manifest, blobs, public_revisions=refs)


@pytest.mark.parametrize("index", [[], {"x": 123}, {"bad/id": REVISION}, {"x": "not-a-revision"}])
def test_public_revision_index_requires_canonical_ids(index):
    with pytest.raises(RootImportError, match="INVALID_PUBLIC_REVISION_INDEX"):
        candidate(public_revisions=index)


def test_optional_code_examples_and_execute_bit_are_data():
    manifest, blobs = fixture_source()
    blobs["site-content/thought.md"] = GitBlob(
        blobs["site-content/thought.md"].data + b"\n`<script>example</script>`", "100755"
    )
    assert len(candidate(manifest, blobs).points) == 2


def test_old_git_is_rejected_before_reading_objects(monkeypatch, tmp_path):
    from node06_service.root_preflight import GitSnapshot

    calls = []

    def version_only(self, *args):
        calls.append(args)
        return b"git version 2.39.0"

    monkeypatch.setattr(GitSnapshot, "git", version_only)
    with pytest.raises(RootImportError, match="GIT_2_46_REQUIRED"):
        GitSnapshot(tmp_path, COMMIT)
    assert calls == [("--version",)]


def test_fsmonitor_and_replace_refs_do_not_change_snapshot(tmp_path):
    repo, sha = make_repo(tmp_path)
    original = preflight(repo, sha, SITE, "node06-roots.json")
    marker = tmp_path / "hook-ran"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    hook.chmod(0o755)
    git(repo, "config", "core.fsmonitor", str(hook))
    (repo / "site-content/thought.md").write_text("replacement content")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "replacement")
    git(repo, "replace", sha, git(repo, "rev-parse", "HEAD"))
    # Ordinary git commands above can use the configured hook; only the reader is under test.
    marker.unlink(missing_ok=True)
    assert preflight(repo, sha, SITE, "node06-roots.json") == original
    assert not marker.exists()
