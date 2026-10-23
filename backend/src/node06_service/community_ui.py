"""First-party subscriptions, proposals, explicit ballots, trust and inbox."""

from hashlib import sha256
from importlib.resources import files

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from .account_ui import CSS, HEADERS

router = APIRouter(prefix="/community")
PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<title>NODE06 — сообщество</title>
<link rel="stylesheet" href="/assets/site.css">
<link rel="stylesheet" href="/community/style.css">
<script src="/assets/point-picker.js" defer>
</script>
<script src="/community/client.js" defer>
</script>
</head>
<body data-page="community" data-hosted="true" data-point-picker="true">
<header class="site-header">
<nav>
<a href="/">Вики</a>
<a href="/editor/">Мои точки</a>
<a href="/account/">Аккаунт</a>
</nav>
</header>
<main>
<h1>Версии и поддержка</h1>
<button id="community-refresh" type="button">Обновить</button>
<p id="community-status" role="status">Проверяем вход…</p>
<p>Смысловая ссылка не означает поддержку. Подписка не голосует за правку.
В решении учитывается влияние явных голосов, а не число людей.</p>
<button id="choose-point" type="button">Выбрать точку</button>
<section id="selected-point" hidden>
<h2 id="point-name">
</h2>
<p id="point-origin">
</p>
<p>
<a id="point-address">Открыть в поле</a>
</p>
<pre id="point-current">
</pre>
<p id="support-status">
</p>
<button id="support-point" hidden type="button">Подписаться на эту версию</button>
<p id="protection">
</p>
<div id="proposals">
</div>
<form id="proposal-form" hidden>
<h2>Предложить новую версию</h2>
<p>Одно предложение на пользователя за любые 24 часа на сервере.
Одновременно открыто одно предложение на точку. Само предложение не голосует.</p>
<label>Язык<input id="proposal-lang" value="und" maxlength="35" required>
</label>
<label>Новый текст<textarea id="proposal-body" maxlength="8192" rows="10" required>
</textarea>
</label>
<button id="proposal-link" type="button">Связать выделенные слова / добавить связь</button>
<p>Выберите 1–16 связанных точек.</p>
<ul id="proposal-links">
</ul>
<button id="submit-proposal" type="submit">Предложить версию</button>
</form>
</section>
<section>
<h2>Мои подписки</h2>
<ul id="my-subscriptions">
</ul>
<button id="more-subscriptions" hidden>Ещё подписки</button>
</section>
<section>
<h2>Личная лента и уведомления</h2>
<ul id="inbox">
</ul>
<button id="more-inbox" hidden>Ещё уведомления</button>
</section>
<section>
<h2>Доверие людям</h2>
<p id="my-influence">
</p>
<form id="people-form">
<label>Имя пользователя<input id="people-query" maxlength="64" required>
</label>
<button type="submit">Найти пользователя</button>
</form>
<ul id="people-results">
</ul>
<ul id="my-trust">
</ul>
</section>
<section>
<h2>Обновления из Git</h2>
<p>Точки из репозиториев меняются их администраторами.
Поддержка переносится автоматически; обновления остаются в ченжлоге.</p>
<ul id="news">
</ul>
<button id="more-news" hidden>Ещё обновления</button>
</section>
<noscript>Для этого интерфейса нужен JavaScript.</noscript>
</main>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
def page(request: Request):
    value = PAGE
    bundle = getattr(request.app.state, "hosted_bundle", None)
    if bundle:
        for name in ("site.css", "point-picker.js"):
            version = sha256((bundle.directory / "assets" / name).read_bytes()).hexdigest()[:12]
            value = value.replace(f"/assets/{name}", f"/assets/{name}?v={version}")
    return HTMLResponse(value, headers=HEADERS)


@router.get("/client.js")
def script():
    return Response(
        files("node06_service").joinpath("ui/community.js").read_text(),
        media_type="application/javascript",
        headers=HEADERS,
    )


@router.get("/style.css")
def style():
    return Response(
        CSS
        + """
body[data-page=community] main{max-width:980px;margin:1rem auto}
body[data-page=community] .site-header{position:static}
body[data-page=community] nav{flex-wrap:wrap;align-items:center}
body[data-page=community] pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}
body[data-page=community] li,body[data-page=community] h2{overflow-wrap:anywhere}
.community-comparison{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.community-version{min-width:0;border:1px solid #293442;padding:12px}
.community-proposal{border-top:1px solid #8292a2;padding-top:16px;margin-top:24px}
@media(max-width:650px){.community-comparison{grid-template-columns:1fr}}
""",
        media_type="text/css",
        headers=HEADERS,
    )
