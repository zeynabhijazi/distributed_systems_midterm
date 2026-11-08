
import hashlib
import logging

import httpx
from sqlalchemy import select

from metadata.database import SessionLocal, StoredChunk
from storage.consistent_hash import ConsistentHashRing
from storage.distributor import NODES, N

logger = logging.getLogger(__name__)


def repair_chunks():
    repaired = 0
    under_replicated = 0

    ring = ConsistentHashRing(list(NODES.keys()))

    with SessionLocal() as db:
        chunks = db.scalars(select(StoredChunk)).all()

        with httpx.Client(timeout=5.0) as client:
            for chunk in chunks:
                desired_nodes = ring.get_nodes(chunk.hash, N)
                healthy_copies = []
                chunk_data = None

                
                candidates = list(dict.fromkeys(
                    list(chunk.nodes) + desired_nodes
                ))

                for node in candidates:
                    try:
                        response = client.get(
                            f"{NODES[node]}/chunks/{chunk.hash}"
                        )
                        response.raise_for_status()

                        data = response.content

                        if hashlib.sha256(data).hexdigest() != chunk.hash:
                            logger.warning(
                                "Corrupt replica: %s on %s",
                                chunk.hash, node
                            )
                            continue

                        healthy_copies.append(node)
                        chunk_data = data

                    except (httpx.HTTPError, KeyError):
                        continue

                if chunk_data is None:
                    under_replicated += 1
                    logger.error(
                        "No readable replicas for %s",
                        chunk.hash
                    )
                    continue

                for node in desired_nodes:
                    if node in healthy_copies:
                        continue

                    try:
                        response = client.put(
                            f"{NODES[node]}/chunks/{chunk.hash}",
                            content=chunk_data
                        )
                        response.raise_for_status()

                        healthy_copies.append(node)
                        repaired += 1

                        logger.info(
                            "Repaired %s on %s",
                            chunk.hash, node
                        )

                    except (httpx.HTTPError, KeyError):
                        logger.warning(
                            "Repair pending: %s on %s",
                            chunk.hash, node
                        )

                chunk.nodes = sorted(set(healthy_copies))

                if len(healthy_copies) < N:
                    under_replicated += 1

            db.commit()

    return {
        "repaired_replicas": repaired,
        "under_replicated_chunks": under_replicated
    }
