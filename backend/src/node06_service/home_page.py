"""Owner-controlled entrance navigation. Blocks are not graph edges or votes."""

import json
from typing import Annotated, Literal
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


Language = Annotated[
    str,
    StringConstraints(strict=True, max_length=35, pattern=r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$"),
]


class HomeContent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: Text
    introduction: Annotated[str, StringConstraints(max_length=2000)] = ""
    blocks: list[HomeBlock] = Field(default_factory=list, max_length=12)
    entrance_label: Text = "Entrance point"
    all_sites_label: Text = "All sites"

    @model_validator(mode="after")
    def not_blank(self):
        if not all(s.strip() for s in (self.title, self.entrance_label, self.all_sites_label)):
            raise ValueError("Home labels must not be blank")
        return self


class HomePage(HomeContent):
    default_language: Language = "und"
    translations: dict[Language, HomeContent] = Field(default_factory=dict, max_length=8)

    def variants(self):
        return [self, *self.translations.values()]

    @model_validator(mode="after")
    def bounded(self):
        value = self.model_dump()
        if self.default_language == "und" and not self.translations:
            # Preserve the entire former valid range for existing one-language homes.
            # Added default metadata must not make a previously valid 12KiB home fail.
            value.pop("default_language")
            value.pop("translations")
            for key in ("entrance_label", "all_sites_label"):
                if value[key] == type(self).model_fields[key].default:
                    value.pop(key)
        if (
            len(json.dumps(value, ensure_ascii=False).encode()) > 12288
            or sum(len(page.blocks) for page in self.variants()) > 12
        ):
            raise ValueError("Home page exceeds its text budget")
        languages = [self.default_language.lower(), *(key.lower() for key in self.translations)]
        if len(set(languages)) != len(languages):
            raise ValueError("Each home language must be unique")
        return self


HomeSource = Literal["auto", "git", "ui", "welcome"]


def resolve_home(ui_page: dict | None, git_page: dict | None, preference: HomeSource):
    """Explicit modes never silently substitute the other source."""
    if preference in ("auto", "git") and git_page is not None:
        return git_page, "git"
    if preference in ("auto", "ui") and ui_page is not None:
        return ui_page, "ui"
    return None, "welcome"


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

    config = None
    if site:
        config, _source = resolve_home(
            site.home_page,
            getattr(site, "git_home_page", None),
            getattr(site, "home_page_source", "ui" if site.home_page is not None else "auto"),
        )
    page = HomePage.model_validate(config) if config is not None else None
    if page:
        from .home_render import render_layout

        return render_layout(page.model_dump(), site.id, field_path)
    source = '<section id="start-page" class="start-page home-blocks"><h1>' + text(title) + "</h1>"
    if site:
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
