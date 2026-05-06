"""
HTTP reverse-proxy middleware.

When a request arrives with a Host header that matches a Route in the DB,
this middleware forwards the request to the configured target and streams
the response back. Everything else falls through to FastAPI normally.
"""

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import StreamingResponse, Response
from sqlalchemy.orm import Session

from .database import SessionLocal, Route


async def _stream_response(client: httpx.AsyncClient, req: httpx.Request):
    """Stream a proxied response back to the client."""
    async with client.stream(
        req.method,
        req.url,
        headers=req.headers,
        content=req.content,
    ) as resp:
        async def body_iter():
            async for chunk in resp.aiter_bytes():
                yield chunk

        return StreamingResponse(
            body_iter(),
            status_code=resp.status_code,
            headers=dict(resp.headers),
        )


class ReverseProxyMiddleware(BaseHTTPMiddleware):
    """
    Intercepts requests whose Host header matches a configured route.
    Non-matching requests fall through to the normal FastAPI router.
    """

    # Paths that should NEVER be proxied (the management UI itself)
    PASSTHROUGH_PREFIXES = ("/api/", "/static/", "/", "/_")

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0].lower()

        # Always pass through the management UI paths when accessed directly
        if host in ("localhost", "127.0.0.1", "0.0.0.0"):
            return await call_next(request)

        # Look up the route in the DB
        db: Session = SessionLocal()
        try:
            route = (
                db.query(Route)
                .filter(Route.hostname == host, Route.enabled == True)
                .first()
            )
        finally:
            db.close()

        if route is None:
            # No matching route — pass through (404 will come from FastAPI)
            return await call_next(request)

        # Build the target URL
        target = route.target
        if not target.startswith(("http://", "https://")):
            target = f"http://{target}"

        path = request.url.path
        query = request.url.query
        target_url = f"{target}{path}"
        if query:
            target_url += f"?{query}"

        # Forward the request
        headers = dict(request.headers)
        headers["host"] = route.target.split(":")[0]  # rewrite Host header
        headers.pop("x-forwarded-for", None)

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                body = await request.body()
                proxy_req = client.build_request(
                    request.method,
                    target_url,
                    headers=headers,
                    content=body,
                )
                resp = await client.send(proxy_req, stream=True)

                async def body_iter():
                    async for chunk in resp.aiter_bytes():
                        yield chunk

                return StreamingResponse(
                    body_iter(),
                    status_code=resp.status_code,
                    headers={
                        k: v
                        for k, v in resp.headers.items()
                        if k.lower()
                        not in ("transfer-encoding", "content-encoding", "content-length")
                    },
                )
        except httpx.ConnectError:
            return Response(
                content=f"<h2>Proxy Error</h2><p>Could not connect to <code>{route.target}</code></p>",
                status_code=502,
                media_type="text/html",
            )
        except Exception as exc:
            return Response(
                content=f"<h2>Proxy Error</h2><p>{exc}</p>",
                status_code=500,
                media_type="text/html",
            )
