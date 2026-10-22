"""Pure P04a candidate validation. No fetch, execution, rendering or database writes."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

SITE = re.compile(r"s_[0-9a-f]{32}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
REVISION = re.compile(r"v_[0-9a-f]{32}\Z")
POINT = re.compile(r"[a-z0-9][a-z0-9_-]{0,95}\Z")
MAX_MANIFEST = 16 * 1024
MAX_FILE = 32 * 1024
MAX_TOTAL = 1024 * 1024
LINK = re.compile(r"(?<![!\\])\[[^\]\n]*\]\(([^\s()]+)\)")
INLINE_CODE = re.compile(r"(`+).*?\1")
RAW_HTML = re.compile(r"<[!/A-Za-z]")


class RootImportError(ValueError):
    def __init__(self, code: str, path: str = "", line: int | None = None):
        self.code, self.path, self.line = code, path, line
        super().__init__(f"{code}: {path}" + (f":{line}" if line else ""))


def safe_path(value: str) -> str:
    parts = value.split("/")
    if (
        not value
        or len(value) > 256
        or len(parts) > 8
        or any(part in ("", ".", "..") or part.startswith(".") for part in parts)
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", value)
        or PurePosixPath(value).is_absolute()
    ):
        raise ValueError("Use a bounded relative ASCII path without dot/hidden components")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RootFile(StrictModel):
    file: Annotated[
        str,
        StringConstraints(
            min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_-][A-Za-z0-9_./-]*\.md$"
        ),
    ]

    @field_validator("file")
    @classmethod
    def markdown_path(cls, value: str) -> str:
        safe_path(value)
        if not value.endswith(".md"):
            raise ValueError("Markdown file required")
        return value


class RootSpec(RootFile):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,60}$")]
    lang: Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$")]

    @field_validator("id")
    @classmethod
    def reserved(cls, value: str) -> str:
        if value == "welcome" or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,60}", value):
            raise ValueError("welcome is reserved for the site point")
        return value


class WelcomeSpec(RootFile):
    mode: Literal["git"]
    lang: Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$")] = "und"


class RootManifest(StrictModel):
    schema_version: StrictInt = Field(ge=1, le=1)
    site_id: Annotated[str, StringConstraints(pattern=r"^s_[0-9a-f]{32}$")]
    content_directory: Literal["site-content"]
    source_proof: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    welcome: WelcomeSpec | None = None
    points: list[RootSpec] = Field(max_length=100)

    @model_validator(mode="after")
    def unique(self):
        ids = [p.id for p in self.points]
        paths = [p.file for p in self.points] + ([self.welcome.file] if self.welcome else [])
        if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
            raise ValueError("Duplicate point ID or file")
        specs = [*self.points, *([self.welcome] if self.welcome else [])]
        if any(not re.fullmatch(r"[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*", p.lang) for p in specs):
            raise ValueError("Invalid language label")
        return self


@dataclass(frozen=True)
class GitBlob:
    data: bytes
    mode: str = "100644"


@dataclass(frozen=True)
class CandidatePoint:
    id: str
    lang: str
    path: str
    body: str
    links: tuple[str, ...]
    external_revision_pins: tuple[tuple[str, str], ...]
    content_digest: str


@dataclass(frozen=True)
class RootCandidate:
    site_id: str
    commit_sha: str
    manifest_digest: str
    digest: str
    points: tuple[CandidatePoint, ...]
    warnings: tuple[str, ...]

    def summary(self) -> dict:
        """No proof, bodies, private host paths or credentials in the default report."""
        return {
            "site_id": self.site_id,
            "commit_sha": self.commit_sha,
            "manifest_digest": self.manifest_digest,
            "candidate_digest": self.digest,
            "points": [
                {
                    "id": p.id,
                    "lang": p.lang,
                    "file": p.path,
                    "links": p.links,
                    "external_revision_pins": dict(p.external_revision_pins),
                    "content_digest": p.content_digest,
                }
                for p in self.points
            ],
            "warnings": self.warnings,
            "writes_performed": False,
            "source_ownership_verified": False,
        }


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RootImportError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def parse_manifest(raw: bytes, site_id: str) -> RootManifest:
    if len(raw) > MAX_MANIFEST:
        raise RootImportError("MANIFEST_TOO_LARGE")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        manifest = RootManifest.model_validate(value)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, RootImportError):
            raise
        raise RootImportError("INVALID_MANIFEST") from None
    if not SITE.fullmatch(site_id) or manifest.site_id != site_id:
        raise RootImportError("SITE_MISMATCH")
    return manifest


def prose_lines(body: str):
    """Ignore fenced/inline code when resolving this initial inline-link subset."""
    fence = None
    for number, line in enumerate(body.splitlines(), 1):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            run = marker[1]
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not line[marker.end() :].strip():
                fence = None
            continue
        if fence is None:
            yield number, INLINE_CODE.sub("", line)


def _read_blob(blob: GitBlob | None, path: str) -> str:
    if blob is None:
        raise RootImportError("FILE_MISSING", path)
    if blob.mode not in ("100644", "100755"):
        raise RootImportError("NON_REGULAR_GIT_BLOB", path)
    if len(blob.data) > MAX_FILE:
        raise RootImportError("FILE_TOO_LARGE", path)
    try:
        body = blob.data.decode("utf-8")
    except UnicodeError:
        raise RootImportError("INVALID_UTF8", path) from None
    if body.startswith("version https://git-lfs.github.com/spec/v1"):
        raise RootImportError("LFS_POINTER", path)
    if any(ord(c) < 32 and c not in "\t\r\n" for c in body):
        raise RootImportError("BINARY_OR_CONTROL_TEXT", path)
    return body


def prepare_candidate(
    raw_manifest: bytes,
    blobs: dict[str, GitBlob],
    *,
    site_id: str,
    commit_sha: str,
    public_revisions: dict[str, str] | None = None,
) -> RootCandidate:
    if not SHA.fullmatch(commit_sha):
        raise RootImportError("IMMUTABLE_COMMIT_REQUIRED")
    manifest = parse_manifest(raw_manifest, site_id)
    public_revisions = {} if public_revisions is None else public_revisions
    if not isinstance(public_revisions, dict) or any(
        not isinstance(k, str)
        or not isinstance(v, str)
        or not POINT.fullmatch(k)
        or not REVISION.fullmatch(v)
        for k, v in public_revisions.items()
    ):
        raise RootImportError("INVALID_PUBLIC_REVISION_INDEX")
    entries = [(p.id, p) for p in manifest.points]
    if manifest.welcome:
        entries.append(("welcome", manifest.welcome))
    ids = {
        local: site_id if local == "welcome" else f"r_{site_id[2:]}_{local}" for local, _ in entries
    }
    total = len(raw_manifest)
    prepared = []
    for local, spec in entries:
        path = f"site-content/{spec.file}"
        blob = blobs.get(path)
        if blob:
            total += len(blob.data)
        if total > MAX_TOTAL:
            raise RootImportError("SOURCE_TOO_LARGE")
        body = _read_blob(blob, path)
        refs = []
        pins = {}
        for line, text in prose_lines(body):
            if RAW_HTML.search(text) or re.search(r"(?<!\\)!\[", text):
                raise RootImportError("UNSUPPORTED_HTML_OR_IMAGE", path, line)
            for match in LINK.finditer(text):
                target = match[1]
                if target.startswith("md://local/"):
                    linked = ids.get(target.removeprefix("md://local/"))
                    if linked is None:
                        raise RootImportError("LOCAL_TARGET_MISSING", path, line)
                elif target.startswith("md://point/"):
                    linked = target.removeprefix("md://point/")
                    if linked in ids.values():
                        raise RootImportError("USE_LOCAL_REFERENCE", path, line)
                    if linked not in public_revisions:
                        raise RootImportError("PUBLIC_TARGET_MISSING", path, line)
                    pins[linked] = public_revisions[linked]
                else:
                    try:
                        parsed = urlsplit(target)
                    except ValueError:
                        raise RootImportError("UNSUPPORTED_LINK", path, line) from None
                    if (
                        parsed.scheme not in ("http", "https")
                        or not parsed.hostname
                        or parsed.username
                        or parsed.password
                    ):
                        raise RootImportError("UNSUPPORTED_LINK", path, line)
                    continue
                if linked == ids[local]:
                    raise RootImportError("SELF_LINK", path, line)
                refs.append(linked)
            if "md://" in LINK.sub("", text):
                raise RootImportError("UNSUPPORTED_POINT_LINK_SYNTAX", path, line)
        if len(refs) != len(set(refs)):
            raise RootImportError("DUPLICATE_POINT_LINK", path)
        if len(refs) > 16:
            raise RootImportError("TOO_MANY_LINKS", path)
        links = tuple(sorted(refs))
        meaning = {
            "id": ids[local],
            "lang": spec.lang,
            "body": body,
            "links": links,
            "external_revision_pins": pins,
        }
        prepared.append(
            CandidatePoint(
                ids[local],
                spec.lang,
                path,
                body,
                links,
                tuple(sorted(pins.items())),
                digest(meaning),
            )
        )
    by_id = {p.id: p for p in prepared}
    warnings = []
    for point in prepared:
        if not point.links:
            warnings.append(f"ORPHAN_LOCAL_POINT:{point.id}")
        for target in point.links:
            if target in by_id and point.id not in by_id[target].links:
                raise RootImportError("LOCAL_LINK_NOT_RECIPROCAL", point.path)
    prepared.sort(key=lambda p: p.id)
    manifest_digest = digest(manifest.model_dump(mode="json"))
    payload = {
        "site_id": site_id,
        "commit_sha": commit_sha,
        "manifest_digest": manifest_digest,
        "points": [asdict(p) for p in prepared],
    }
    return RootCandidate(
        site_id,
        commit_sha,
        manifest_digest,
        digest(payload),
        tuple(prepared),
        tuple(sorted(warnings)),
    )
