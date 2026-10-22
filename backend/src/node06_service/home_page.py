"""Owner-controlled entrance navigation. Blocks are not graph edges or votes."""

import json
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=160)]
PointID = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z0-9][a-z0-9_-]{0,95}$")]


class HomeLink(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: Text
    point_id: PointID | None = None
    url: Annotated[str, StringConstraints(max_length=2048)] | None = None

    @model_validator(mode="after")
    def destination(self):
        if (self.point_id is None) == (self.url is None):
            raise ValueError("Choose one destination")
        if self.url is not None:
            try:
                parsed = urlsplit(self.url)
                port = parsed.port
            except ValueError:
                raise ValueError("Invalid external URL") from None
            if (
                parsed.scheme not in ("https", "http")
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or "\\" in self.url
                or any(ord(c) <= 32 or ord(c) == 127 for c in self.url)
                or (port is not None and port < 1)
            ):
                raise ValueError("Use an HTTP(S) link without credentials")
        if not self.label.strip():
            raise ValueError("Link label is empty")
        return self


class HomeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: Text
    description: Annotated[str, StringConstraints(max_length=1500)] = ""
    links: list[HomeLink] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def title_not_blank(self):
        if not self.title.strip():
            raise ValueError("Block title is empty")
        return self


class HomePage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: Text
    introduction: Annotated[str, StringConstraints(max_length=2000)] = ""
    blocks: list[HomeBlock] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def bounded(self):
        if (
            not self.title.strip()
            or len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 12288
        ):
            raise ValueError("Home page exceeds its text budget")
        return self


def render_home(site, title: str, field_path: str) -> str:
    """All authored fields are text. Destinations stay inside the current entrance."""
    import html
    from urllib.parse import urlencode

    from .root_render import render_root

    def point_href(point_id):
        return html.escape(
            field_path + "?" + urlencode({"p": point_id, "open": point_id}), quote=True
        )

    def text(value):
        return html.escape(value).replace("\n", "<br>")

    page = HomePage.model_validate(site.home_page) if site and site.home_page is not None else None
    heading = page.title if page else title
    source = (
        '<section id="start-page" class="start-page home-blocks"><h1>' + text(heading) + "</h1>"
    )
    if page:
        source += (
            '<p class="home-introduction">'
            + text(page.introduction)
            + '</p><div class="welcome-grid">'
        )
        for block in page.blocks:
            source += '<section class="welcome-card"><h2>' + text(block.title) + "</h2>"
            source += "<p>" + text(block.description) + '</p><div class="welcome-links">'
            for link in block.links:
                if link.point_id:
                    source += (
                        '<a href="' + point_href(link.point_id) + '">' + text(link.label) + "</a>"
                    )
                else:
                    source += (
                        '<a href="'
                        + html.escape(link.url, quote=True)
                        + '" target="_blank" rel="noopener noreferrer">'
                        + text(link.label)
                        + "</a>"
                    )
            source += "</div></section>"
        source += "</div>"
    elif site:
        # A not-yet-customized site shows its own welcome, never someone else's roots.
        body = (
            render_root(site.welcome_body, site.id)
            if site.welcome_source == "git"
            else "<p>" + text(site.welcome_body) + "</p>"
        )
        body = body.replace('href="/?', 'href="' + html.escape(field_path, quote=True) + "?")
        source += (
            '<div class="welcome-grid"><section class="welcome-card">' + body + "</section></div>"
        )
    source += '<div class="welcome-links">'
    if site:
        source += '<a href="' + point_href(site.id) + '">Точка входа / Entrance point</a>'
    source += '<a href="' + point_href("all-sites") + '">Все сайты / All sites</a></div></section>'
    return source
