#!/usr/bin/env python3
from __future__ import annotations

import html
import hashlib
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



def synthetic_coordinates(point_id: str) -> list[float]:
    """Deterministic six positive coordinates for the static root era.

    They are only a navigation scaffold. The social backend will replace them
    with coordinates derived from user reactions while preserving the same
    six-component contract.
    """
    digest = hashlib.sha256(point_id.encode("utf-8")).digest()
    return [1.0 + digest[i] / 255.0 * 5.0 for i in range(6)]

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
        href = f"/{lang}/?p={target}&open={target}"
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
        return f'<a class="point-link" data-point-id="{html.escape(target, quote=True)}" href="/{lang}/?p={html.escape(target, quote=True)}&open={html.escape(target, quote=True)}">{html.escape(label)}</a>'

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
        '<a href="/">NODE06</a>'
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
            "coordinates": synthetic_coordinates(p.id),
            "coordinate_source": "synthetic-root",
        })

        # Keep stable point URLs as compatibility/deep-link entry points, but the map remains primary.
        target = f"/{p.lang}/?p={p.id}&open={p.id}"
        redirect = f'''<!doctype html><html lang="{p.lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="0;url={target}"><link rel="canonical" href="{target}"><title>node06 · {html.escape(p.id)}</title></head><body><p><a href="{target}">Open in field</a></p></body></html>'''
        write(DIST / p.lang / "p" / p.id / "index.html", redirect)

    write(DIST / "data" / "points.json", json.dumps(index, ensure_ascii=False, indent=2))

    langs = sorted({p.lang for p in points.values()})
    for lang in langs:
        lang_points = [p for p in points.values() if p.lang == lang]
        if lang == "ru":
            mode_buttons = '<span class="control-label">режим</span><button data-mode="explore">ИССЛЕДОВАНИЕ</button><button data-mode="read">ЧТЕНИЕ</button><button data-mode="feed">ЛЕНТА</button>'
            layout_buttons = '<span class="control-label">текст</span><button data-layout="side">СПРАВА</button><button data-layout="below">СНИЗУ</button><button data-layout="overlay">ПОВЕРХ</button>'
            field_hint = 'drag / стрелки / WASD · wheel / Q/E — масштаб'
        else:
            mode_buttons = '<span class="control-label">mode</span><button data-mode="explore">EXPLORE</button><button data-mode="read">READ</button><button data-mode="feed">FEED</button>'
            layout_buttons = '<span class="control-label">text</span><button data-layout="side">RIGHT</button><button data-layout="below">BELOW</button><button data-layout="overlay">OVERLAY</button>'
            field_hint = 'drag / arrows / WASD · wheel / Q/E — zoom'
        view_buttons = '<span class="control-label">view</span><button data-view="left">◀</button><button data-view="up">▲</button><button data-view="reset">◎</button><button data-view="down">▼</button><button data-view="right">▶</button>'
        field_body = f'''<section class="field-shell">
<div class="field-head"><div><div class="eyebrow">FIELD / DEPTH 2</div><h1><a href="/">NODE06</a></h1><div class="field-center">center: <span id="field-center-id"></span></div></div>
<div id="field-controls" class="field-controls"><div class="control-group">{mode_buttons}</div><div class="control-group">{layout_buttons}</div><div class="control-group">{view_buttons}</div></div></div>
<div class="field-workspace" data-layout="side"><div class="field-stage"><div id="field-map" class="field-map" aria-label="Point field" tabindex="0"></div><aside id="hover-card" class="hover-card" hidden></aside><div class="field-help">{field_hint}</div></div>
<aside id="point-panel" class="point-panel"><button id="point-panel-close" class="point-panel-close" type="button">×</button><div id="point-panel-body"></div></aside></div></section>'''
        write(DIST / lang / "index.html", shell("FIELD", field_body, lang, "field"))
        write(DIST / lang / "field" / "index.html", shell("FIELD", field_body, lang, "field"))

        sorted_recent = sorted(lang_points, key=lambda p: p.updated_at, reverse=True)
        rows = "".join(
            f'<li><time>{p.updated_at[:10]}</time><a href="/{lang}/?p={p.id}&open={p.id}">{html.escape(preview(p.text, 150))}</a><span>{len(p.links)} links</span></li>'
            for p in sorted_recent
        )
        recent_body = f'<section class="recent"><div class="eyebrow">ROOT ACTIVITY</div><h1>RECENT</h1><ul>{rows}</ul></section>'
        write(DIST / lang / "recent" / "index.html", shell("RECENT", recent_body, lang, "recent"))

        if lang == "ru":
            about_text = '''<section class="prose"><div class="eyebrow">PROTOCOL / 0</div><h1>Что это</h1>
<p>NODE06 сейчас является статическим полем корневых точек. Каждая точка — текстовый Markdown-файл. Точки соединяются взаимными ссылками и не имеют заранее заданного типа.</p>
<p>Карта первична: выбор точки всегда переносит центр поля. В режиме чтения текст выбранной точки открывается автоматически; в режиме исследования остаётся только карта; лента показывает последние изменения.</p>
<p>Позже появится социальный слой: регистрация, пользовательские точки, поддержка и несогласие, передача части влияния другим людям и вычисляемая карта общественного отношения.</p>
<p>Сейчас здесь нет пользователей, веса или социального цвета. Для навигации корневые точки временно получают воспроизводимые синтетические шесть координат; будущий backend заменит их координатами, возникающими из пользовательских реакций.</p>
<p>NODE06 основан на <a href="https://github.com/wratixor/hexrelatum" target="_blank" rel="noopener noreferrer">Hexrelatum</a>. Исходники NODE06 и карта лицензий опубликованы в <a href="https://github.com/wratixor/node06" target="_blank" rel="noopener noreferrer">репозитории</a>.</p></section>'''
        else:
            about_text = '''<section class="prose"><div class="eyebrow">PROTOCOL / 0</div><h1>What this is</h1>
<p>NODE06 is currently a static field of root points. Every point is a Markdown text file. Points are connected by reciprocal links and have no predefined content type.</p>
<p>The map is primary: selecting a point always recenters the field. Reading mode opens the selected text automatically; Explore keeps only the map; Feed shows the latest changes.</p>
<p>A social layer is planned: registration, user-created points, support and opposition, delegation of influence to other people, and an emergent map of collective perception.</p>
<p>There are no users, weight or social color yet. For navigation, root points temporarily receive reproducible synthetic six-component coordinates; the future backend will replace them with coordinates emerging from user reactions.</p>
<p>NODE06 is based on <a href="https://github.com/wratixor/hexrelatum" target="_blank" rel="noopener noreferrer">Hexrelatum</a>. NODE06 source code and its licensing map are published in the <a href="https://github.com/wratixor/node06" target="_blank" rel="noopener noreferrer">repository</a>.</p></section>'''
        write(DIST / lang / "about" / "index.html", shell("ABOUT", about_text, lang, "about"))

    # Bilingual entrance. Languages are separate points, not localization identities.
    root = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>node06</title><link rel="stylesheet" href="/assets/site.css"></head><body><main class="language-gate"><div class="eyebrow">NODE06 / ROOT ERA</div><h1>NODE06</h1><div class="welcome-grid">
<section class="welcome-card" lang="en"><h2>Welcome to the field.</h2><p>NODE06 is an experimental graph of points. A point may be a word, a thought, a link or a longer text. The map comes first; texts are opened from inside it. The current root era is static. A social layer is planned.</p><div class="welcome-links"><a href="/en/?p=node06-en&open=node06-en">NODE06</a><a href="/en/?p=point-en&open=point-en">POINT</a><a href="/en/?p=field-en&open=field-en">FIELD</a><a href="/en/?p=root-era-en&open=root-era-en">ROOT ERA</a></div></section>
<section class="welcome-card" lang="ru"><h2>Добро пожаловать в поле.</h2><p>NODE06 — экспериментальный граф точек. Точкой может быть слово, мысль, ссылка или длинный текст. Карта первична, тексты открываются из неё. Сейчас идёт статическая корневая эпоха. Позже появится социальный слой.</p><div class="welcome-links"><a href="/ru/?p=node06-ru&open=node06-ru">NODE06</a><a href="/ru/?p=point-ru&open=point-ru">ТОЧКА</a><a href="/ru/?p=field-ru&open=field-ru">ПОЛЕ</a><a href="/ru/?p=root-era-ru&open=root-era-ru">КОРНЕВАЯ ЭПОХА</a></div></section>
</div></main><footer>node06 · <a href="https://github.com/wratixor/hexrelatum" target="_blank" rel="noopener noreferrer">Hexrelatum</a> · <a href="https://github.com/wratixor/node06" target="_blank" rel="noopener noreferrer">source</a></footer></body></html>'''
    write(DIST / "index.html", root)
    print(f"Built {len(points)} points into {DIST}")


if __name__ == "__main__":
    build()
