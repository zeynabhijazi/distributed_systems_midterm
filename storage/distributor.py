
import hashlib
import httpx

from storage.chunker import chunk_file
from storage.consistent_hash import ConsistentHashRing


import os

IN_DOCKER = os.getenv("IN_DOCKER", "false").lower() == "true"

if IN_DOCKER:
    NODES = {
        f"node{i}": f"http://node{i}:8000"
        for i in range(1, 5)
    }
else:
    NODES = {
        f"node{i}": f"http://localhost:{8000+i}"
        for i in range(1, 5)
    }
REPLICATION_FACTOR = 3


def distribute_file(file_path):
    ring = ConsistentHashRing(list(NODES.keys()))

    results = []
    total_bytes = 0

    with httpx.Client(timeout=30.0) as client:
        for index, chunk in enumerate(chunk_file(file_path)):
            chunk_hash = chunk["hash"]
            target_nodes = ring.get_nodes(
                chunk_hash,
                REPLICATION_FACTOR
            )

            successful_nodes = []

            for node in target_nodes:
                url = f"{NODES[node]}/chunks/{chunk_hash}"

                try:
                    response = client.put(
                        url,
                        content=chunk["data"]
                    )
                    response.raise_for_status()
                    successful_nodes.append(node)

                except httpx.HTTPError as error:
                    print(f"Failed on {node}: {error}")

            if len(successful_nodes) != REPLICATION_FACTOR:
                raise RuntimeError(
                    f"Chunk {index} has only "
                    f"{len(successful_nodes)} replicas"
                )

            results.append({
                "index": index,
                "hash": chunk_hash,
                "size": chunk["size"],
                "nodes": successful_nodes
            })

            total_bytes += chunk["size"]

            print(
                f"Chunk {index + 1}: "
                f"{chunk_hash[:12]}... -> "
                f"{successful_nodes}"
            )

    return {
        "size": total_bytes,
        "chunk_count": len(results),
        "chunks": results
    }


def download_file(manifest, output_path):
    with httpx.Client(timeout=30.0) as client:
        with open(output_path, "wb") as output:
            for chunk in manifest["chunks"]:
                recovered = False

                for node in chunk["nodes"]:
                    try:
                        response = client.get(
                            f"{NODES[node]}/chunks/{chunk['hash']}"
                        )
                        response.raise_for_status()

                        data = response.content

                        if hashlib.sha256(data).hexdigest() != chunk["hash"]:
                            continue

                        output.write(data)
                        recovered = True
                        break

                    except httpx.HTTPError:
                        continue

                if not recovered:
                    raise RuntimeError(
                        f"Cannot recover chunk {chunk['hash']}"
                    )

    print(f"File reconstructed: {output_path}")
