"""Bounded public reads over static core and accepted DB content, without social writes."""

import html
import re
from dataclasses import dataclass

from sqlalchemy import and_, case, exists, func, literal_column, or_, select

from .models import (
    authored_points,
    edge_claims,
    point_edges,
    point_revisions,
    points,
    root_entries,
    root_sources,
    sites,
    users,
)
from .root_import import digest
from .root_render import render_root
from .site_registry import ALL_SITES_ID
from .visibility import hidden_ids, visible

TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
SIMPLE = literal_column("'simple'::regconfig")


class PublicPointError(RuntimeError):
    def __init__(self, code, status=404):
        self.code, self.status = code, status


@dataclass(frozen=True)
class SearchQuery:
    value: str
    terms: tuple[str, ...]

    @classmethod
    def parse(cls, value):
        value = value.strip().casefold()
        terms = tuple(TOKEN.findall(value))
        if not value or len(value) > 128 or len(terms) > 8:
            raise PublicPointError("INVALID_SEARCH_QUERY", 422)
        return cls(value, terms)


def preview(body):
    return " ".join(body.split())[:220]


class PublicPoints:
    def __init__(self, database, *, roots=(), build_revision="dev", site_id=None, moderation=True):
        self.site_id, self.moderation = site_id, moderation
        self.database = database
        self.build_revision = build_revision
        self.core = {}
        for root in roots:
            value = dict(root)
            body = root.get("body")
            plain = (
                body if body is not None else html.unescape(re.sub(r"<[^>]*>", " ", root["html"]))
            )
            value.update(
                body=body,
                revision_id=None,
                content_digest=digest(
                    {
                        "id": root["id"],
                        "lang": root["lang"],
                        "body" if body is not None else "html": plain
                        if body is not None
                        else root["html"],
                        "links": sorted(root["links"]),
                    }
                ),
                source={"kind": "static-root", "build_revision": build_revision},
                declared_links=list(root["links"]),
            )
            value["_search"] = tuple(TOKEN.findall(plain.casefold()))
            self.core[root["id"]] = value
        self.author = users.alias("public_author")
        self.site = sites.alias("public_site")
        self.source_site = sites.alias("source_site")
        self.source_valid = and_(
            self.source_site.c.state == "active",
            self.source_site.c.primary_origin == root_sources.c.origin,
            self.source_site.c.owner_user_id == root_sources.c.owner_user_id,
            root_entries.c.revision_id == points.c.current_revision_id,
        )
        self.site_valid = and_(
            self.site.c.state == "active", self.site.c.primary_origin.is_not(None)
        )

    def _check(self):
        if not self.database.configured:
            raise PublicPointError("DATABASE_NOT_CONFIGURED", 503)

    def _query(self):
        return (
            select(
                points.c.id,
                points.c.origin,
                points.c.author_user_id,
                self.author.c.id.label("public_author_id"),
                self.author.c.handle.label("public_author_handle"),
                authored_points.c.lang.label("authored_lang"),
                points.c.created_at,
                points.c.last_interaction_at,
                points.c.current_revision_id,
                point_revisions.c.body,
                point_revisions.c.declared_links,
                root_entries.c.lang,
                root_entries.c.content_digest,
                root_entries.c.site_id,
                root_sources.c.repository_url,
                root_sources.c.commit_sha,
                self.source_valid.label("source_valid"),
            )
            .select_from(
                points.join(point_revisions, points.c.current_revision_id == point_revisions.c.id)
                .outerjoin(authored_points, authored_points.c.point_id == points.c.id)
                .outerjoin(root_entries, root_entries.c.point_id == points.c.id)
                .outerjoin(root_sources, root_sources.c.site_id == root_entries.c.site_id)
                .outerjoin(self.source_site, self.source_site.c.id == root_sources.c.site_id)
                .outerjoin(self.site, self.site.c.id == points.c.id)
                .outerjoin(
                    self.author,
                    self.author.c.id
                    == func.coalesce(
                        points.c.author_user_id,
                        self.site.c.owner_user_id,
                        root_sources.c.owner_user_id,
                    ),
                )
            )
            .where(
                points.c.lifecycle == "active",
                visible(points.c.id, self.site_id) if self.moderation else True,
                or_(
                    points.c.id == ALL_SITES_ID,
                    self.site_valid,
                    self.source_valid,
                    and_(points.c.origin == "user", authored_points.c.point_id.is_not(None)),
                ),
            )
        )

    def _convert(self, row, *, full=True):
        source = (
            {"kind": "system"}
            if row["id"] == ALL_SITES_ID
            else {"kind": "site", "site_id": row["id"]}
        )
        lang = "und"
        if row["source_valid"]:
            lang = row["lang"]
            source = {
                "kind": "operator-git",
                "site_id": row["site_id"],
                "repository_url": row["repository_url"],
                "commit_sha": row["commit_sha"],
            }
        if row["authored_lang"] is not None and not row["source_valid"]:
            lang = row["authored_lang"]
        if row["authored_lang"] is not None and row["origin"] == "user":
            source = {"kind": "user", "author_user_id": row["author_user_id"]}
        body = row["body"]
        refs = row["declared_links"]
        result = {
            "id": row["id"],
            "origin": row["origin"],
            "lang": lang,
            "preview": preview(body),
            "declared_links": refs,
            "revision_id": row["current_revision_id"],
            "content_digest": (
                row["content_digest"]
                if row["source_valid"]
                else digest({"id": row["id"], "lang": lang, "body": body, "links": sorted(refs)})
            ),
            "source": source,
            "author": (
                {"kind": "user", "id": row["public_author_id"], "name": row["public_author_handle"]}
                if row["public_author_id"]
                else {
                    "kind": "system" if source["kind"] == "system" else "source",
                    "name": "System" if source["kind"] == "system" else "Git source",
                }
            ),
            "created_at": row["created_at"].isoformat(),
            "last_interaction_at": row["last_interaction_at"].isoformat(),
        }

        if full:
            result["body"] = body
            result["html"] = (
                render_root(body, row["site_id"])
                if row["source_valid"] or row["authored_lang"] is not None
                else "<p>" + html.escape(body).replace("\n", "<br>") + "</p>"
            )
        return result

    def _raw(self, point_id):
        self._check()
        with self.database.connect() as connection:
            return self.raw_on(connection, point_id)

    def raw_on(self, connection, point_id):
        """Read current visibility on a caller's transaction, after its row locks."""
        if self.moderation and hidden_ids(connection, [point_id], self.site_id):
            raise PublicPointError("POINT_NOT_FOUND")
        if point_id in self.core:
            return {k: v for k, v in self.core[point_id].items() if not k.startswith("_")}
        row = (
            connection.execute(self._query().where(points.c.id == point_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise PublicPointError("POINT_NOT_FOUND")
        return self._convert(row)

    @staticmethod
    def _brief(point):
        return {
            k: point[k]
            for k in ("id", "origin", "lang", "preview", "revision_id", "content_digest", "source")
        }

    def get(self, point_id):
        point = self._raw(point_id)
        page = self.neighbors(point_id, check=False)
        return {
            **point,
            "links": [p["id"] for p in page["items"]],
            "links_truncated": page["next_cursor"] is not None,
            "neighbors_cursor": page["next_cursor"],
        }

    def search(self, value, *, after="", limit=20):
        self._check()
        query = SearchQuery.parse(value)
        core = []
        for pid, point in self.core.items():
            if pid > after and (
                query.value in pid.casefold()
                or (
                    query.terms
                    and all(
                        any(word.startswith(term) for word in point["_search"])
                        for term in query.terms
                    )
                )
            ):
                core.append(self._brief(point))
        match = points.c.id.contains(query.value, autoescape=True)
        if query.terms:
            tsquery = " & ".join("'" + term.replace("'", "''") + "':*" for term in query.terms)
            match = or_(
                match,
                func.to_tsvector(SIMPLE, point_revisions.c.search_text).op("@@")(
                    func.to_tsquery(SIMPLE, tsquery)
                ),
            )
        with self.database.connect() as connection:
            hidden = (
                hidden_ids(connection, [p["id"] for p in core], self.site_id)
                if self.moderation
                else set()
            )
            core = [p for p in core if p["id"] not in hidden]
            rows = (
                connection.execute(
                    self._query()
                    .where(points.c.id.collate("C") > after, match)
                    .order_by(points.c.id.collate("C"))
                    .limit(limit + 1)
                )
                .mappings()
                .all()
            )
        return self._page(core + [self._brief(self._convert(r, full=False)) for r in rows], limit)

    def neighbors(self, point_id, *, after="", limit=50, check=True):
        self._check()
        if check:
            self._raw(point_id)
        other = case(
            (point_edges.c.point_a == point_id, point_edges.c.point_b), else_=point_edges.c.point_a
        )
        ids = select(other).where(
            or_(point_edges.c.point_a == point_id, point_edges.c.point_b == point_id),
            exists(
                select(edge_claims.c.id).where(
                    edge_claims.c.point_a == point_edges.c.point_a,
                    edge_claims.c.point_b == point_edges.c.point_b,
                )
            ),
        )
        core_ids = set(self.core.get(point_id, {}).get("declared_links", []))
        with self.database.connect() as connection:
            core_ids.update(connection.execute(ids.where(other.in_(list(self.core)))).scalars())
            if self.moderation:
                core_ids -= hidden_ids(connection, core_ids, self.site_id)
            rows = (
                connection.execute(
                    self._query()
                    .where(points.c.id.in_(ids), points.c.id.collate("C") > after)
                    .order_by(points.c.id.collate("C"))
                    .limit(limit + 1)
                )
                .mappings()
                .all()
            )
        core = [self._brief(self.core[pid]) for pid in core_ids if pid in self.core and pid > after]
        return self._page(core + [self._brief(self._convert(r, full=False)) for r in rows], limit)

    @staticmethod
    def _page(items, limit):
        values = sorted({p["id"]: p for p in items}.values(), key=lambda p: p["id"])
        selected = values[:limit]
        return {
            "items": selected,
            "next_cursor": selected[-1]["id"] if len(values) > limit else None,
        }
