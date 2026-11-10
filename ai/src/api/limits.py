from starlette.responses import JSONResponse


class LimitJSONBody:
    """Bound streamed and content-length request bodies before FastAPI parses JSON."""

    def __init__(self, app, limit: int):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        size = headers.get(b"content-length", b"0")

        async def reject():
            await JSONResponse(
                {
                    "error": {
                        "code": "request_too_large",
                        "message": "Request body exceeds limit.",
                        "stage": "request",
                        "retryable": False,
                    }
                },
                status_code=413,
            )(scope, receive, send)

        if not size.isdigit() or len(size) > 18 or int(size) > self.limit:
            return await reject()
        body = bytearray()
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            chunk = msg.get("body", b"")
            if len(body) + len(chunk) > self.limit:
                return await reject()
            body.extend(chunk)
            if not msg.get("more_body"):
                break
        sent = False

        async def replay():
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)
