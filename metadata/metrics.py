
import time

from fastapi import APIRouter, Request
from fastapi.responses import Response
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

router = APIRouter(tags=["Monitoring"])

REQUEST_COUNT = Counter(
    "storage_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

REQUEST_LATENCY = Histogram(
    "storage_http_request_duration_seconds",
    "HTTP request processing duration",
    ["method", "path"],
)

HEALTHY_NODES = Gauge(
    "storage_healthy_nodes",
    "Number of healthy storage nodes",
)

OFFLINE_NODES = Gauge(
    "storage_offline_nodes",
    "Number of offline storage nodes",
)

NODE_CHUNKS = Gauge(
    "storage_node_chunks",
    "Number of chunks on each storage node",
    ["node_id"],
)

NODE_FREE_SPACE = Gauge(
    "storage_node_free_bytes",
    "Available storage space per node",
    ["node_id"],
)


async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()

    response = await call_next(request)

    duration = time.perf_counter() - start
    path = request.scope.get("route")
    path = path.path if path else request.url.path

    REQUEST_COUNT.labels(
        request.method, path, response.status_code
    ).inc()

    REQUEST_LATENCY.labels(
        request.method, path
    ).observe(duration)

    return response


def update_node_metrics(nodes):
    healthy = sum(
        node["status"] == "healthy"
        for node in nodes
    )

    offline = sum(
        node["status"] == "offline"
        for node in nodes
    )

    HEALTHY_NODES.set(healthy)
    OFFLINE_NODES.set(offline)

    for node in nodes:
        NODE_CHUNKS.labels(
            node_id=node["node_id"]
        ).set(node["chunk_count"])

        NODE_FREE_SPACE.labels(
            node_id=node["node_id"]
        ).set(node["free_space"])


@router.get("/metrics")
def metrics():
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
