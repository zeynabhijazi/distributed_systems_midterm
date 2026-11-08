
import os
import time
import threading
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

API_KEY = os.getenv("API_KEY", "exam-demo-key")
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "120"))
WINDOW = 60

requests_by_client = defaultdict(deque)
lock = threading.Lock()


async def security_middleware(request: Request, call_next):
    if request.url.path in (
    "/health",
    "/docs",
    "/openapi.json",
    "/heartbeat",
    "/metrics",
):
        return await call_next(request)

    if request.headers.get("X-API-Key") != API_KEY:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key"}
        )

    client_id = request.client.host if request.client else "unknown"
    now = time.monotonic()

    with lock:
        timestamps = requests_by_client[client_id]

        while timestamps and now - timestamps[0] >= WINDOW:
            timestamps.popleft()

        if len(timestamps) >= RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"}
            )

        timestamps.append(now)

    return await call_next(request)
