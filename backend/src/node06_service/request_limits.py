from starlette.responses import JSONResponse


class AuthBodyLimit:
    """Bound actual bytes before JSON/Pydantic parsing, including chunked bodies."""

    def __init__(self, app, maximum=16384):
        self.app = app
        self.maximum = maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(
            (
                "/api/v1/moderation/",
                "/api/v1/auth/",
                "/editor/confirm/",
                "/api/v1/sites",
                "/api/v1/points",
                "/api/v1/proposals",
                "/api/v1/people",
                "/api/v1/me/",
                "/api/v1/profile-links/",
            )
        ):
            return await self.app(scope, receive, send)
        maximum = self.maximum if scope["path"].startswith("/api/v1/auth/") else 65536
        if scope["path"].startswith("/api/v1/profile-links/"):
            maximum = 4096
        chunks = bytearray()
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > maximum:
                response = JSONResponse(
                    {
                        "code": "REQUEST_TOO_LARGE",
                        "message": "Request exceeds the management body limit.",
                    },
                    status_code=413,
                    headers={"Cache-Control": "no-store"},
                )
                return await response(scope, receive, send)
            chunks.extend(body)
            if not message.get("more_body", False):
                break

        consumed = False

        async def buffered_receive():
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": bytes(chunks), "more_body": False}

        return await self.app(scope, buffered_receive, send)
