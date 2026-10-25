"""Escaped, script-free layout renderer shared by the stdlib builder and service.

The service validates HomePage before calling this; the builder owns its literal.
Each complete variant keeps its own destinations. No graph translation is inferred.
"""

from html import escape
from urllib.parse import urlencode


def render_layout(page: dict, site_id: str | None, field_path: str = "/") -> str:
    def text(value):
        return escape(value).replace("\n", "<br>")

    def point_link(label, point_id):
        href = field_path + "?" + urlencode({"p": point_id, "open": point_id})
        return (
            f'<a href="{escape(href, quote=True)}" data-point-id="{escape(point_id, quote=True)}">'
            + text(label)
            + "</a>"
        )

    default = page.get("default_language", "und")
    variants = {default: page, **page.get("translations", {})}
    # Per-entrance preference: choosing a language on one wiki does not force others.
    key = site_id or "static"
    source = (
        '<section id="start-page" class="start-page home-blocks" '
        f'data-home-default="{escape(default, quote=True)}" '
        f'data-home-key="{escape(key, quote=True)}">'
    )
    if len(variants) > 1:
        source += (
            '<label class="home-language-control" hidden>◉ '
            '<select data-home-language-select aria-label="Language">'
        )
        for language in variants:
            source += f'<option value="{escape(language, quote=True)}">{escape(language)}</option>'
        source += "</select></label>"
    for language, value in variants.items():
        attr = escape(language, quote=True)
        source += (
            f'<div data-home-language="{attr}" lang="{attr}"'
            + (" hidden" if language != default else "")
            + "><h1>"
            + text(value["title"])
            + "</h1>"
        )
        source += '<p class="home-introduction">' + text(value.get("introduction", "")) + "</p>"
        source += '<div class="welcome-grid">'
        for block in value.get("blocks", []):
            source += '<section class="welcome-card"><h2>' + text(block["title"]) + "</h2>"
            source += "<p>" + text(block.get("description", "")) + '</p><div class="welcome-links">'
            for link in block.get("links", []):
                if link.get("point_id"):
                    source += point_link(link["label"], link["point_id"])
                else:
                    source += (
                        f'<a href="{escape(link["url"], quote=True)}" '
                        'target="_blank" rel="noopener noreferrer">' + text(link["label"]) + "</a>"
                    )
            source += "</div></section>"
        source += '</div><div class="welcome-links">'
        if site_id:
            source += point_link(value.get("entrance_label", "Entrance point"), site_id)
            source += point_link(value.get("all_sites_label", "All sites"), "all-sites")
        source += "</div></div>"
    return source + "</section>"
