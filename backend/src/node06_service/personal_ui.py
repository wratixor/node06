"""Shared first-party navigation. No session data or cross-origin capabilities."""

from html import escape


def navigation(current: str) -> str:
    items = (
        ("wiki", "/", "Вики"),
        ("profile", "/community/", "Профиль"),
        ("directory", "/directory/", "Пользователи и рейтинги"),
        ("sites", "/sites/", "Мои сайты"),
        ("editor", "/editor/", "Новая точка"),
        ("moderation", "/moderation/", "Жалобы"),
        ("account", "/account/", "Вход и безопасность"),
    )
    links = []
    for key, url, title in items:
        active = ' aria-current="page"' if key == current else ""
        # Authentication must not replace an editor containing an unsaved draft.
        target = (
            ' target="_blank" rel="noopener"' if current == "editor" and key == "account" else ""
        )
        links.append(f'<a href="{escape(url, quote=True)}"{active}{target}>{escape(title)}</a>')
    return (
        '<header class="site-header personal-header">'
        '<nav aria-label="Личные разделы">' + "".join(links) + "</nav></header>"
    )


CSS = """
.personal-header{position:static;border-bottom:1px solid #293442;padding:10px 16px}
.personal-header nav{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;
max-width:1100px;margin:auto}
.personal-header a{color:inherit;font:14px/1.4 system-ui;padding:6px 9px;
border:1px solid transparent;text-decoration:none}
.personal-header a:hover,.personal-header a[aria-current=page]{border-color:#8292a2;
background:#131b25}
.personal-header a:focus-visible{outline:2px solid #8ee4ea;outline-offset:2px}
.personal-header~main{margin:1rem auto}
.personal-header~main h1{font-size:28px;margin:8px 0}
@media(max-width:480px){.personal-header{padding:8px}.personal-header a{padding:5px 6px}}
"""
