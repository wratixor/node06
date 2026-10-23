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
<h1>Профиль</h1>
<button id="community-refresh" type="button">Обновить</button>
<p id="community-status" role="status">Проверяем вход…</p>
<nav id="profile-tabs" aria-label="Разделы профиля"></nav>
<form id="profile-filter" class="point-search" role="search">
<input id="profile-query" type="search" placeholder="Фильтр" maxlength="128"
aria-label="Поиск в загруженном списке" autocomplete="off">
<button type="submit" aria-label="Поиск"><svg viewBox="0 0 24 24" aria-hidden="true">
<circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m16 16 5 5"></path>
</svg></button></form>
<button id="choose-point" type="button">Выбрать точку</button>
<details id="my-color" hidden>
<summary>Мой цвет</summary>
<form id="color-form">
<label>Красный<input id="color-r" type="range" min="1" max="255" value="128"></label>
<label>Зелёный<input id="color-g" type="range" min="1" max="255" value="128"></label>
<label>Синий<input id="color-b" type="range" min="1" max="255" value="128"></label>
<output id="color-preview">#808080</output>
<button type="submit" data-requires-auth="true">Сохранить цвет</button>
</form>
</details>
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
<button id="confirm-support" hidden type="button">Поддержать новую основную версию</button>
<button id="block-point" hidden type="button">Блокировать эту версию</button>
<button id="unblock-point" hidden type="button">Снять блокировку</button>
<button id="favorite-point" hidden type="button">В избранное</button>
<p id="protection">
</p>
<div id="proposals">
</div>
<form id="proposal-form" hidden>
<h2>Предложить новую версию</h2>
<button id="proposal-link" type="button">Ссылка</button>
<ul id="proposal-links">
</ul>
<label>Новый текст<textarea id="proposal-body" maxlength="8192" rows="10" required>
</textarea>
</label>
<button id="submit-proposal" type="submit">Предложить версию</button>
</form>
</section>
<section data-profile-panel="subscriptions">
<h2>Подписки</h2>
<ul id="my-subscriptions">
</ul>
<button id="more-subscriptions" hidden>Ещё подписки</button>
</section>
<section data-profile-panel="blocks">
<h2>Блокировки</h2>
<ul id="my-blocks"></ul>
<button id="more-blocks" hidden type="button">Ещё блокировки</button>
</section><section data-profile-panel="inbox">
<h2>Лента</h2>
<ul id="inbox">
</ul>
<button id="more-inbox" hidden>Ещё уведомления</button>
</section>
<section data-profile-panel="trust">
<h2>Доверие</h2>
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
<section data-profile-panel="news">
<h2>Обновления Git</h2>
<ul id="news">
</ul>
<button id="more-news" hidden>Ещё обновления</button>
</section>
<section data-profile-panel="points"><h2>Мои точки</h2><ul id="profile-points"></ul>
<button id="more-points" type="button" hidden>Ещё точки</button></section>
<section data-profile-panel="favorites"><h2>Избранное</h2><ul id="profile-favorites"></ul></section>
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
body[data-page=community] main{max-width:980px;margin:1rem auto;padding-top:8px}
body[data-page=community] h1{font-size:28px;margin:8px 0}
body[data-page=community] h2{font-size:19px;margin:10px 0}
body[data-page=community] button{font-size:14px;padding:5px 9px}
body[data-page=community] ul{list-style:none;padding:0;margin:8px 0}
body[data-page=community] li{border-bottom:1px solid var(--line);padding:5px 0;
display:flex;align-items:center;flex-wrap:wrap;gap:6px}
body[data-page=community] li .profile-point{flex:1;min-width:120px;text-align:left;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#profile-filter{margin:8px 0;width:100%;max-width:400px}
#profile-filter input{margin:0}
#profile-tabs{display:flex;gap:5px;flex-wrap:wrap;margin:12px 0}
#profile-tabs button[aria-selected=true]{border-color:var(--text);background:var(--panel)}
#profile-tabs button{margin:0}
#choose-point,#community-refresh{font-size:13px}
#community-status{font-size:13px;color:var(--muted);margin:6px 0}
[data-profile-panel]{border-top:1px solid var(--line);padding:8px 0}
body[data-page=community] #my-color{font-size:14px;margin:8px 0}
body[data-page=community] #color-form{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
body[data-page=community] #color-form label{font-size:12px;margin:5px 0;max-width:150px}
body[data-page=community] .site-header{position:static}
body[data-page=community] nav{flex-wrap:wrap;align-items:center}
body[data-page=community] pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}
body[data-page=community] li,body[data-page=community] h2{overflow-wrap:anywhere}
#color-preview{display:inline-block;padding:8px;border:1px solid #8292a2;
color:#fff;text-shadow:0 1px 3px #000}
#my-color input{max-width:320px}
.community-comparison{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.community-version{min-width:0;border:1px solid #293442;padding:12px}
.community-proposal{border-top:1px solid #8292a2;padding-top:16px;margin-top:24px}
@media(max-width:650px){.community-comparison{grid-template-columns:1fr}}
""",
        media_type="text/css",
        headers=HEADERS,
    )
