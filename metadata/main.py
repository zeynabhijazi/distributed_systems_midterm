
import asyncio
import logging
import time

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

from metadata.database import init_db
from metadata.object_api import router as object_router
from metadata.gateway import router as gateway_router
from metadata.search_api import router as search_router
from metadata.security import security_middleware
from metadata.repair import repair_chunks
from metadata.scrubber import (
    router as scrub_router,
    scrub_erasure,
)
from metadata.job_api import router as job_router
from metadata.metrics import (
    router as metrics_router,
    metrics_middleware,
    update_node_metrics,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

nodes = {}
HEARTBEAT_TIMEOUT = 15


async def repair_loop():
    while True:
        await asyncio.sleep(15)

        try:
            result = await asyncio.to_thread(repair_chunks)
            logger.info("Repair check: %s", result)
        except Exception:
            logger.exception("Repair cycle failed")


async def scrub_loop():
    while True:
        await asyncio.sleep(60)

        try:
            result = await asyncio.to_thread(scrub_erasure)
            logger.info("Integrity scrub: %s", result)
        except Exception:
            logger.exception("Scrub cycle failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    repair_task = asyncio.create_task(repair_loop())
    scrub_task = asyncio.create_task(scrub_loop())

    try:
        yield
    finally:
        repair_task.cancel()
        scrub_task.cancel()

        await asyncio.gather(
            repair_task,
            scrub_task,
            return_exceptions=True
        )


app = FastAPI(
    title="Metadata Service",
    lifespan=lifespan
)

app.include_router(object_router)
app.include_router(gateway_router)
app.include_router(search_router)
app.include_router(scrub_router)
app.include_router(job_router)
app.include_router(metrics_router)
app.middleware("http")(metrics_middleware)

app.middleware("http")(security_middleware)


class Heartbeat(BaseModel):
    node_id: str
    free_space: int
    chunk_count: int


@app.post("/heartbeat")
def receive_heartbeat(heartbeat: Heartbeat):
    nodes[heartbeat.node_id] = {
        "node_id": heartbeat.node_id,
        "free_space": heartbeat.free_space,
        "chunk_count": heartbeat.chunk_count,
        "last_seen": time.time(),
    }

    return {"message": "Heartbeat received"}


@app.get("/nodes")
def get_nodes():
    result = []

    for node in nodes.values():
        healthy = (
            time.time() - node["last_seen"]
            < HEARTBEAT_TIMEOUT
        )

        result.append({
            "node_id": node["node_id"],
            "free_space": node["free_space"],
            "chunk_count": node["chunk_count"],
            "status": (
                "healthy" if healthy else "offline"
            ),
            "last_seen": datetime.fromtimestamp(
                node["last_seen"],
                timezone.utc
            ).isoformat()
        })

    return result


@app.get(
    "/cluster/status",
    tags=["Cluster Monitoring"]
)
def cluster_status():
    all_nodes = get_nodes()
    update_node_metrics(all_nodes)
    return {
        "total_nodes": len(all_nodes),
        "healthy_nodes": sum(
            n["status"] == "healthy"
            for n in all_nodes
        ),
        "offline_nodes": sum(
            n["status"] == "offline"
            for n in all_nodes
        ),
        "nodes": all_nodes
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
