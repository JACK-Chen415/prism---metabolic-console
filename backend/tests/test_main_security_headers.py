import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.main import health_check, request_context_middleware


@pytest.mark.asyncio
async def test_health_response_includes_request_id_and_security_headers():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/health",
            "headers": [(b"x-request-id", b"test-request-id")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )

    async def call_next(_request):
        return JSONResponse(await health_check())

    response = await request_context_middleware(request, call_next)

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "camera=()" in response.headers["Permissions-Policy"]
    assert "microphone=()" in response.headers["Permissions-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
