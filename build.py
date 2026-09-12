#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
STATIC = ROOT / "static"
DIST = ROOT / "dist"

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((md://([a-z0-9-]+))\)")
EXT_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
ID_RE = re.compile(r"^[a-z0-9-]+$")

@dataclass
class Point:
    id: str
    lang: str
    source: Path
    text: str
    links: list[str]
    created_at: str
    updated_at: str


def iso_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[`*_>#]", "", text)
    return " ".join(text.split())


def preview(text: str, limit: int = 220) -> str:
    plain = strip_markdown(text)
    if len(plain) <= limit:
        return plain
    return plain[: limit - 1].rstrip() + "…"


def render_inline(text: str, point_ids: set[str], lang: str) -> str:
    escaped = html.escape(text, quote=False)

    def internal(match: re.Match[str]) -> str:
        label = html.escape(match.group(1), quote=False)
        target = match.group(3)
        href = f"/{lang}/p/{target}/"
        return f'<a class="point-link" data-point-id="{target}" href="{href}">{label}</a>'

    def external(match: re.Match[str]) -> str:
        label = html.escape(match.group(1), quote=False)
        url = html.escape(match.group(2), quote=True)
        return f'<a class="external-link" href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'

    # Work on the original text in two passes to avoid escaping URLs twice.
    result = text
    result = MD_LINK_RE.sub(lambda m: f"@@INTERNAL:{m.group(1)}|{m.group(3)}@@", result)
    result = EXT_LINK_RE.sub(lambda m: f"@@EXTERNAL:{m.group(1)}|{m.group(2)}@@", result)
    result = html.escape(result, quote=False)

    def restore_internal(m: re.Match[str]) -> str:
        label, target = m.group(1), m.group(2)
        return f'<a class="point-link" data-point-id="{html.escape(target, quote=True)}" href="/{lang}/p/{html.escape(target, quote=True)}/">{html.escape(label)}</a>'

    def restore_external(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2)
        return f'<a class="external-link" href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(label)}</a>'

    result = re.sub(r"@@INTERNAL:([^|@]+)\|([^@]+)@@", restore_internal, result)
    result = re.sub(r"@@EXTERNAL:([^|@]+)\|([^@]+)@@", restore_external, result)
    return result


def render_markdown(text: str, point_ids: set[str], lang: str) -> str:
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text.strip()) if c.strip()]
    out: list[str] = []
    for chunk in chunks:
        lines = chunk.splitlines()
        if all(line.lstrip().startswith("- ") for line in lines):
            items = "".join(f"<li>{render_inline(line.lstrip()[2:], point_ids, lang)}</li>" for line in lines)
            out.append(f"<ul>{items}</ul>")
        else:
            body = "<br>".join(render_inline(line, point_ids, lang) for line in lines)
            out.append(f"<p>{body}</p>")
    return "\n".join(out)


def load_points() -> dict[str, Point]:
    points: dict[str, Point] = {}
    errors: list[str] = []

    for lang_dir in sorted(p for p in CONTENT.iterdir() if p.is_dir()):
        lang = lang_dir.name
        for path in sorted(lang_dir.glob("*.md")):
            pid = path.stem
            if not ID_RE.fullmatch(pid):
                errors.append(f"Invalid point id {pid!r}: use [a-z0-9-]+")
                continue
            if pid in points:
                errors.append(f"Duplicate point id: {pid} ({points[pid].source} and {path})")
                continue
            text = path.read_text(encoding="utf-8").strip()
            links = [m.group(3) for m in MD_LINK_RE.finditer(text)]
            stamp = iso_mtime(path)
            points[pid] = Point(pid, lang, path, text, links, stamp, stamp)

    if errors:
        raise SystemExit("\n".join(errors))
    return points


def validate(points: dict[str, Point]) -> None:
    errors: list[str] = []
    for p in points.values():
        for target in p.links:
            if target not in points:
                errors.append(f"{p.id}: broken md:// link to {target}")
                continue
            if p.id not in points[target].links:
                errors.append(f"{p.id} <-> {target}: link is not symmetric; add md://{p.id} to {points[target].source.relative_to(ROOT)}")
    if errors:
        raise SystemExit("Link validation failed:\n" + "\n".join(f"- {e}" for e in errors))


def shell(title: str, body: str, lang: str, page_kind: str, point_id: str = "") -> str:
    nav = (
        f'<a href="/{lang}/">NODE06</a>'
        f'<a href="/{lang}/recent/">RECENT</a>'
        f'<a href="/{lang}/about/">ABOUT</a>'
    )
    return f'''<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>{html.escape(title)} · node06</title>
<link rel="stylesheet" href="/assets/site.css">
</head>
<body data-page="{page_kind}" data-lang="{lang}" data-point-id="{html.escape(point_id, quote=True)}">
<header class="site-header"><nav>{nav}</nav><span class="status">ROOT ERA / STATIC FIELD</span></header>
<main>{body}</main>
<footer>node06 · static root field · social layer planned · <a href="https://github.com/wratixor/hexrelatum" target="_blank" rel="noopener noreferrer">Hexrelatum</a> · <a href="https://github.com/wratixor/node06" target="_blank" rel="noopener noreferrer">source</a></footer>
<script src="/assets/site.js" defer></script>
</body>
</html>'''


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build() -> None:
    points = load_points()
    validate(points)

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    shutil.copytree(STATIC, DIST / "assets")

    index = []
    for p in points.values():
        neighbors = sorted(set(p.links))
        index.append({
            "id": p.id,
            "lang": p.lang,
            "file": str(p.source.relative_to(ROOT)).replace("\\", "/"),
            "links": neighbors,
            "degree": len(neighbors),
            "created_at": p.created_at,
            "last_interaction_at": p.updated_at,
            "preview": preview(p.text),
            "html": render_markdown(p.text, set(points), p.lang),
            "origin": "root",
        })

        # Keep stable point URLs as compatibility/deep-link entry points, but the map remains primary.
        target = f"/{p.lang}/?open={p.id}"
        redirect = f'''<!doctype html><html lang="{p.lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="0;url={target}"><link rel="canonical" href="{target}"><title>node06 · {html.escape(p.id)}</title></head><body><p><a href="{target}">Open in field</a></p></body></html>'''
        write(DIST / p.lang / "p" / p.id / "index.html", redirect)

    write(DIST / "data" / "points.json", json.dumps(index, ensure_ascii=False, indent=2))

    langs = sorted({p.lang for p in points.values()})
    for lang in langs:
        lang_points = [p for p in points.values() if p.lang == lang]
        field_hint = "наведите на сферу · кликните для открытия" if lang == "ru" else "hover a sphere · click to open"
        field_body = f'''<section class="field-shell"><div class="field-head"><div><div class="eyebrow">FIELD / DEPTH 2</div><h1>NODE06</h1><div class="field-center">center: <span id="field-center-id"></span></div></div><div id="field-legend">{field_hint}</div></div><div id="field-map" class="field-map" aria-label="Point field"></div><aside id="hover-card" class="hover-card" hidden></aside></section>
<div id="point-modal" class="point-modal" hidden><article class="point-modal-panel" role="dialog" aria-modal="true"><div class="point-modal-actions"><button id="point-modal-focus" type="button"></button><button id="point-modal-close" class="point-modal-close" type="button">×</button></div><div id="point-modal-body"></div></article></div>'''
        write(DIST / lang / "index.html", shell("FIELD", field_body, lang, "field"))
        # Legacy /field/ URL remains as the same primary map rather than a separate section.
        write(DIST / lang / "field" / "index.html", shell("FIELD", field_body, lang, "field"))

        sorted_recent = sorted(lang_points, key=lambda p: p.updated_at, reverse=True)
        rows = "".join(
            f'<li><time>{p.updated_at[:10]}</time><a href="/{lang}/?open={p.id}">{html.escape(preview(p.text, 150))}</a><span>{len(p.links)} links</span></li>'
            for p in sorted_recent
        )
        recent_body = f'<section class="recent"><div class="eyebrow">ROOT ACTIVITY</div><h1>RECENT</h1><ul>{rows}</ul></section>'
        write(DIST / lang / "recent" / "index.html", shell("RECENT", recent_body, lang, "recent"))

        if lang == "ru":
            about_text = '''<section class="prose"><div class="eyebrow">PROTOCOL / 0</div><h1>Что это</h1>
<p>NODE06 сейчас является статическим полем корневых точек. Каждая точка — текстовый Markdown-файл. Точки соединяются взаимными ссылками и не имеют заранее заданного типа.</p>
<p>Позже появится социальный слой: регистрация, создание пользовательских точек, поддержка и несогласие, передача части влияния другим людям, временная лента и вычисляемая карта общественного отношения.</p>
<p>Сейчас здесь нет пользователей, веса, координат или социального цвета. Это намеренно.</p>
<p>NODE06 основан на <a href="https://github.com/wratixor/hexrelatum" target="_blank" rel="noopener noreferrer">Hexrelatum</a>. Исходники NODE06 и карта лицензий опубликованы в <a href="https://github.com/wratixor/node06" target="_blank" rel="noopener noreferrer">репозитории</a>.</p><p><a href="/en/about/">English root</a></p></section>'''
        else:
            about_text = '''<section class="prose"><div class="eyebrow">PROTOCOL / 0</div><h1>What this is</h1>
<p>NODE06 is currently a static field of root points. Every point is a Markdown text file. Points are connected by reciprocal links and have no predefined content type.</p>
<p>A social layer is planned: registration, user-created points, support and opposition, delegation of influence to other people, a chronological feed, and an emergent map of collective perception.</p>
<p>There are no users, weight, coordinates or social color yet. That is intentional.</p>
<p>NODE06 is based on <a href="https://github.com/wratixor/hexrelatum" target="_blank" rel="noopener noreferrer">Hexrelatum</a>. NODE06 source code and its licensing map are published in the <a href="https://github.com/wratixor/node06" target="_blank" rel="noopener noreferrer">repository</a>.</p><p><a href="/ru/about/">Русская точка</a></p></section>'''
        write(DIST / lang / "about" / "index.html", shell("ABOUT", about_text, lang, "about"))

    # neutral entrance
    root = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>node06</title><link rel="stylesheet" href="/assets/site.css"></head><body><main class="language-gate"><div class="eyebrow">NODE06 / ROOT ERA</div><h1>Choose an entry point</h1><div class="actions"><a href="/ru/">Русский</a><a href="/en/">English</a></div></main></body></html>'''
    write(DIST / "index.html", root)
    print(f"Built {len(points)} points into {DIST}")


if __name__ == "__main__":
    build()
