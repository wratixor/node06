from importlib.resources import files

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from .account_ui import CSS, HEADERS

router = APIRouter(prefix="/sites")


@router.get("/", response_class=HTMLResponse)
def sites_page(request: Request):
    # The address is read separately by JS, never interpolated into executable code.
    return HTMLResponse(
        files("node06_service").joinpath("ui/sites.html").read_text(encoding="utf-8"),
        headers={
            **HEADERS,
            "Content-Security-Policy": HEADERS["Content-Security-Policy"]
            + "; frame-src "
            + (request.app.state.settings.embed_origin or "'none'"),
        },
    )


@router.get("/client.js")
def sites_script():
    return Response(
        files("node06_service").joinpath("ui/sites.js").read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers=HEADERS,
    )


@router.get("/style.css")
def sites_style():
    return Response(
        CSS
        + """
main{max-width:1100px}.columns{display:grid;grid-template-columns:1fr 1.5fr;gap:2rem}
a{color:#b9e5ec}ul{padding-left:1.3rem}li{margin:.6rem 0}li button{text-align:left}
textarea{min-height:8rem}#proof{font-size:.85rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}
#conflict{border:2px solid #e4bd79;padding:1rem}button:disabled{opacity:.5;cursor:wait}
@media(max-width:760px){.columns{grid-template-columns:1fr}main{margin:1rem auto}}
""",
        media_type="text/css",
        headers=HEADERS,
    )
