
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime, timezone
import time
from metadata.database import init_db
from metadata.object_api import router as object_router

app = FastAPI(title="Metadata Service")
app.include_router(object_router)
@app.on_event("startup")
def startup():
    init_db()

nodes = {}

HEARTBEAT_TIMEOUT = 15


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
        "last_seen": time.time()
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
            "status": "healthy" if healthy else "offline",
            "last_seen": datetime.fromtimestamp(
                node["last_seen"], timezone.utc
            ).isoformat()
        })

    return result


@app.get("/health")
def health():
    return {"status": "healthy"}
