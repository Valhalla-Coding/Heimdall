"""
HTTP reverse-proxy middleware.

When a request arrives with a Host header that matches a Route in the DB,
this middleware either:
  - Serves web/index.html  -- if the host matches a device's own *.local hostname
  - Forwards the request   -- if the host matches a service route
  - Falls through          -- for localhost/management UI access
"""

from pathlib import Path

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import StreamingResponse, Response, FileResponse

from .database import SessionLocal, Route, Device

WEB_DIR = Path(__file__).parent.parent / "web"


class ReverseProxyMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0].lower()

        # Always pass through for localhost / management UI
        if host in ("localhost", "127.0.0.1", "0.0.0.0", ""):
            return await call_next(request)

        db = SessionLocal()
        try:
            route = (
                db.query(Route)
                .filter(Route.hostname == host, Route.enabled == True)
                .first()
            )
            devices = db.query(Device).filter(Device.active == True).all()
            device_root = any(
                host == f"{d.hostname}.local" or host == f"www.{d.hostname}.local"
                for d in devices
            )
        finally:
            db.close()

        # Serve landing page for device root hostnames (e.g. oden.local)
        if device_root:
            landing = WEB_DIR / "index.html"
            if landing.exists():
                return FileResponse(str(landing))
            return Response(
                content="<h2>Landing page not found.</h2>",
                status_code=404,
                media_type="text/html",
            )

        # No matching route -- pass through to FastAPI
        if route is None:
            return await call_next(request)

        # Forward to the target service
        target = route.target
        if not target.startswith(("http://", "https://")):
            target = f"http://{target}"

        path = request.url.path
        query = request.url.query
        target_url = f"{target}{path}"
        if query:
            target_url += f"?{query}"

        headers = dict(request.headers)
        headers["host"] = route.target.split(":")[0]
        headers.pop("x-forwarded-for", None)

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                body = await request.body()
                proxy_req = client.build_request(
                    request.method, target_url, headers=headers, content=body,
                )
                resp = await client.send(proxy_req, stream=True)

                async def body_iter():
                    async for chunk in resp.aiter_bytes():
                        yield chunk

                return StreamingResponse(
                    body_iter(),
                    status_code=resp.status_code,
                    headers={
                        k: v for k, v in resp.headers.items()
                        if k.lower() not in (
                            "transfer-encoding", "content-encoding", "content-length"
                        )
                    },
                )
        except httpx.ConnectError:
            return Response(
                content=f"<h2>502 — Could not connect</h2><p><code>{route.target}</code> is not reachable.</p>",
                status_code=502,
                media_type="text/html",
            )
        except Exception as exc:
            return Response(
                content=f"<h2>502 — Proxy error</h2><p>{exc}</p>",
                status_code=502,
                media_type="text/html",
            )
