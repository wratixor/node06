"""First-party subscriptions, proposals, explicit ballots, trust and inbox."""

from hashlib import sha256
from importlib.resources import files

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from .account_ui import CSS, HEADERS
from .personal_ui import navigation

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
<script src="/assets/personal-feed.js" defer></script>
<script src="/community/client.js" defer>
</script>
</head>
<body data-page="community" data-hosted="true" data-point-picker="true">
{personal_navigation}
<main>
<div class="profile-heading"><h1>Профиль</h1>
<button id="community-refresh" type="button">Обновить</button></div>
<p id="community-status" role="status">Проверяем вход…</p>
<nav id="profile-tabs" aria-label="Разделы профиля"></nav>
<form id="profile-filter" class="point-search" role="search">
<input id="profile-query" type="search" placeholder="Фильтр" maxlength="128"
aria-label="Поиск в загруженном списке" autocomplete="off">
<button type="submit" aria-label="Поиск"><svg viewBox="0 0 24 24" aria-hidden="true">
<circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m16 16 5 5"></path>
</svg></button></form>
<button id="choose-point" type="button">Выбрать точку</button>
<section data-profile-panel="color" hidden>
<details id="my-color" open hidden>
<summary>Мой цвет</summary>
<form id="color-form" novalidate>
<svg id="color-radar" viewBox="0 0 300 300" role="group" aria-label="Мой цвет"></svg>
<details id="color-values"><summary>Точные значения</summary>
<div class="profile-stats">
<label class="coordinate coordinate-0"><span aria-hidden="true"></span>
<input id="coordinate-0" data-coordinate="0" aria-label="Красная координата"
 type="number" min="1" max="65535" step="1" value="128" required></label>
<label class="coordinate coordinate-1"><span aria-hidden="true"></span>
<input id="coordinate-1" data-coordinate="1" aria-label="Голубая координата"
 type="number" min="1" max="65535" step="1" value="128" required></label>
<label class="coordinate coordinate-2"><span aria-hidden="true"></span>
<input id="coordinate-2" data-coordinate="2" aria-label="Зелёная координата"
 type="number" min="1" max="65535" step="1" value="128" required></label>
<label class="coordinate coordinate-3"><span aria-hidden="true"></span>
<input id="coordinate-3" data-coordinate="3" aria-label="Пурпурная координата"
 type="number" min="1" max="65535" step="1" value="128" required></label>
<label class="coordinate coordinate-4"><span aria-hidden="true"></span>
<input id="coordinate-4" data-coordinate="4" aria-label="Синяя координата"
 type="number" min="1" max="65535" step="1" value="128" required></label>
<label class="coordinate coordinate-5"><span aria-hidden="true"></span>
<input id="coordinate-5" data-coordinate="5" aria-label="Жёлтая координата"
 type="number" min="1" max="65535" step="1" value="128" required></label>
</div></details>
<output id="color-preview" aria-label="Итоговый цвет">#808080</output>
<button type="submit" data-requires-auth="true">Сохранить</button>
</form>
</details></section>
<details id="selected-point" hidden>
<summary id="point-name"></summary>
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
</details>
<section data-profile-panel="feed"><h2>Лента</h2>
<div id="creation-feed"></div></section>
<section data-profile-panel="subscriptions">
<h2>Подписки</h2>
<ul id="my-subscriptions">
</ul>
<button id="more-subscriptions" hidden>Ещё подписки</button>
</section>
<section data-profile-panel="blocks">
<h2>Блокировки</h2>
<h3>Точки</h3><ul id="my-blocks"></ul>
<button id="more-blocks" hidden type="button">Ещё блокировки</button>
<h3>Авторы</h3><ul id="my-blocked-people"></ul>
<button id="more-people-blocks" hidden type="button">Ещё авторы</button>
</section><section data-profile-panel="inbox">
<h2>Уведомления</h2>
<ul id="inbox">
</ul>
<button id="more-inbox" hidden>Ещё уведомления</button>
</section>
<section data-profile-panel="trust">
<h2>Подписки на авторов</h2>
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
</html>""".replace("{personal_navigation}", navigation("profile"))


@router.get("/", response_class=HTMLResponse)
def page(request: Request):
    value = PAGE
    bundle = getattr(request.app.state, "hosted_bundle", None)
    if bundle:
        for name in ("site.css", "point-picker.js", "personal-feed.js"):
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
.profile-heading{display:flex;align-items:center;justify-content:space-between;gap:8px}
#selected-point{border:1px solid var(--line);padding:10px;margin:12px 0}
#selected-point>summary{cursor:pointer;overflow-wrap:anywhere;font-size:16px}
#choose-point,#community-refresh{font-size:13px}
#community-status{font-size:13px;color:var(--muted);margin:6px 0}
[data-profile-panel]{border-top:1px solid var(--line);padding:8px 0}
body[data-page=community] #my-color{font-size:14px;margin:8px 0}
body[data-page=community] #color-form{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
#color-radar{display:block;width:230px;max-width:100%;height:auto;flex:0 0 auto;touch-action:none}
#color-radar .radar-ring{fill:none;stroke:var(--line);stroke-width:1}
#color-radar .radar-area{fill:var(--radar-color,var(--ink));fill-opacity:.35;
stroke:var(--radar-color,var(--muted));stroke-width:1}
#color-radar [role=slider]{cursor:grab;outline:none}
#color-radar [role=slider]:focus .radar-dot{stroke:var(--ink);stroke-width:3}
#color-radar [aria-disabled=true]{opacity:.5;cursor:default}
#color-values{flex-basis:100%;margin:0 0 6px}
#color-values summary{cursor:pointer;font-size:13px;margin-bottom:8px}
.profile-stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 14px;
width:100%;max-width:420px}
body[data-page=community] #color-form label{font-size:13px;margin:0;min-width:0}
.profile-stats .coordinate{display:flex;align-items:stretch;border:1px solid var(--line)}
.profile-stats .coordinate span{width:10px;flex:none;background:var(--coordinate)}
.coordinate-0{--coordinate:#ee484a}.coordinate-1{--coordinate:#00d2dc}
.coordinate-2{--coordinate:#3ece70}.coordinate-3{--coordinate:#d646d6}
.coordinate-4{--coordinate:#4170ee}.coordinate-5{--coordinate:#f0cd2c}
.profile-stats input{width:100%;min-width:0;padding:5px 8px;border:0}
#color-preview:empty{visibility:hidden}
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
