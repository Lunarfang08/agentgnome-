from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimit:
    """Bound buffered JSON before framework parsing, including chunked requests."""

    def __init__(self, app: ASGIApp, maximum: int = 1048576):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        messages: list[Message] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > self.maximum:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [(b"content-type", b"application/problem+json")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b'{"type":"about:blank","title":"Request too large",'
                        b'"status":413,"code":"body_limit"}',
                    }
                )
                return
            messages.append(message)
            if not message.get("more_body", False):
                break
        index = 0

        async def buffered() -> Message:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, buffered, send)
