import uvicorn

from .config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run("node06_service.main:app", host=settings.host, port=settings.port, reload=False)
