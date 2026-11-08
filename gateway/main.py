
import os
import socket

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

app = FastAPI(title="Storage API Gateway")

BACKEND_URL = os.getenv(
    "BACKEND_URL",
    "http://metadata:8000"
).rstrip("/")

INSTANCE = os.getenv(
    "GATEWAY_INSTANCE",
    socket.gethostname()
)

HOP_HEADERS = {
    "host",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
}


@app.get("/instance")
def instance():
    return {"gateway": INSTANCE}


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "gateway": INSTANCE,
    }


@app.api_route(
    "/{path:path}",
    methods=[
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "PATCH",
        "HEAD",
        "OPTIONS",
    ],
)
async def proxy(request: Request, path: str):
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=10,
            read=None,
            write=None,
            pool=10,
        )
    )

    raw_path = request.scope.get(
        "raw_path",
        request.url.path.encode()
    ).decode("ascii")

    target = BACKEND_URL + raw_path

    if request.url.query:
        target += "?" + request.url.query

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in HOP_HEADERS
    }

    headers["accept-encoding"] = "identity"

    try:
        outgoing = client.build_request(
            method=request.method,
            url=target,
            headers=headers,
            content=request.stream(),
        )

        response = await client.send(
            outgoing,
            stream=True,
        )

    except httpx.HTTPError as error:
        await client.aclose()

        return JSONResponse(
            status_code=503,
            content={
                "detail": str(error)
            },
        )

    response_headers = {
        k: v
        for k, v in response.headers.items()
        if k.lower() not in HOP_HEADERS
    }

    response_headers["X-Gateway-Instance"] = INSTANCE

    async def close_connections():
        await response.aclose()
        await client.aclose()

    return StreamingResponse(
        response.aiter_raw(),
        status_code=response.status_code,
        headers=response_headers,
        background=BackgroundTask(close_connections),
    )
