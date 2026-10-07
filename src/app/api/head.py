"""Answer HEAD wherever GET is answered (BUG-20).

RFC 9110 9.1 requires a general-purpose server to support HEAD for every
resource that supports GET. FastAPI registers only the methods a route names,
so every GET route - the health probes included - answered HEAD with 405.

A HEAD request is run as the GET it describes, and the body is dropped on the
way out. Status and headers (Content-Length included, which RFC 9110 9.3.2
allows) are exactly the GET's, so the two cannot drift apart.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class HeadAsGetMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "HEAD":
            await self.app(scope, receive, send)
            return

        async def send_without_body(message: Message) -> None:
            if message["type"] == "http.response.body":
                if message.get("more_body", False):
                    return
                message = {"type": "http.response.body", "body": b"", "more_body": False}
            await send(message)

        await self.app({**scope, "method": "GET"}, receive, send_without_body)
