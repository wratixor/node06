"""Small escaped Markdown renderer; no raw HTML, images, templates or execution."""

import html
import re
from urllib.parse import urlencode, urlsplit

from .root_import import LINK, POINT


def render_root(body: str, site_id: str) -> str:
    def inline(text: str) -> str:
        chunks = []
        end = 0
        # Code spans remain literal; links inside them do not create graph edges.
        for token in re.finditer(r"(`+).*?\1|(?<![!\\])\[[^\]\n]*\]\([^\s()]+\)", text):
            chunks.append(html.escape(text[end : token.start()]))
            raw = token.group()
            match = LINK.fullmatch(raw)
            if not match:
                chunks.append("<code>" + html.escape(raw) + "</code>")
            else:
                target = match[1]
                label = html.escape(raw[1 : raw.index("](")])
                pid = None
                if target.startswith("md://local/"):
                    local = target.removeprefix("md://local/")
                    pid = site_id if local == "welcome" else f"r_{site_id[2:]}_{local}"
                elif target.startswith("md://point/"):
                    pid = target.removeprefix("md://point/")
                if pid and POINT.fullmatch(pid):
                    href = html.escape("/?" + urlencode({"p": pid, "open": pid}), quote=True)
                    chunks.append(
                        f'<a class="point-link" data-point-id="{pid}" href="{href}">{label}</a>'
                    )
                elif urlsplit(target).scheme in ("https", "http"):
                    href = html.escape(target, quote=True)
                    chunks.append(
                        f'<a href="{href}" target="_blank" rel="noopener noreferrer">{label}</a>'
                    )
                else:
                    chunks.append(html.escape(raw))
            end = token.end()
        chunks.append(html.escape(text[end:]))
        return "".join(chunks)

    result = []
    fence = None
    for line in body.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker and fence is None:
            fence = marker[1]
            result.append("<pre><code>")
        elif (
            marker
            and fence
            and marker[1][0] == fence[0]
            and len(marker[1]) >= len(fence)
            and not line[marker.end() :].strip()
        ):
            fence = None
            result.append("</code></pre>")
        elif fence:
            result.append(html.escape(line) + "\n")
        elif heading := re.match(r"^(#{1,6})\s+(.*)$", line):
            level = len(heading[1])
            result.append(f"<h{level}>{inline(heading[2])}</h{level}>")
        elif line.strip():
            result.append("<p>" + inline(line) + "</p>")
    if fence:
        result.append("</code></pre>")
    return "\n".join(result)
