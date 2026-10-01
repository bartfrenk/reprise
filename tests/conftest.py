from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer


@dataclass(slots=True)
class Site:
    """A local web server standing in for the sites the converters fetch from."""

    base: str = ""
    # Path -> (status, body).
    pages: dict[str, tuple[int, bytes]] = field(default_factory=dict)
    user_agents: list[str | None] = field(default_factory=list)

    def serve(self, path: str, body: str | bytes, status: int = 200) -> str:
        self.pages[path] = (status, body.encode() if isinstance(body, str) else body)
        return self.base + path


@pytest.fixture
async def site() -> AsyncIterator[Site]:
    site = Site()

    async def handler(request: web.Request) -> web.Response:
        site.user_agents.append(request.headers.get("User-Agent"))
        status, body = site.pages.get(request.path, (404, b""))
        return web.Response(status=status, body=body)

    app = web.Application()
    _ = app.router.add_get("/{path:.*}", handler)
    async with TestServer(app) as server:
        site.base = str(server.make_url("")).rstrip("/")
        yield site
