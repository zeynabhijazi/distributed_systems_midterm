
import os
import hashlib
import httpx

from storage.chunker import chunk_file
from storage.consistent_hash import ConsistentHashRing


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

N = 3
W = 2
R = 2


def distribute_file(file_path):
    ring = ConsistentHashRing(list(NODES.keys()))
    results = []
    total_bytes = 0

    with httpx.Client(timeout=5.0) as client:
        for index, chunk in enumerate(chunk_file(file_path)):
            chunk_hash = chunk["hash"]
            target_nodes = ring.get_nodes(chunk_hash, N)
            successful_nodes = []

            for node in target_nodes:
                try:
                    response = client.put(
                        f"{NODES[node]}/chunks/{chunk_hash}",
                        content=chunk["data"]
                    )
                    response.raise_for_status()
                    successful_nodes.append(node)

                except httpx.HTTPError as error:
                    print(f"Write failed on {node}: {error}")

            if len(successful_nodes) < W:
                raise RuntimeError(
                    f"Write quorum failed for chunk {index}: "
                    f"{len(successful_nodes)}/{W}"
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
                f"{len(successful_nodes)}/{N} replicas written"
            )

    return {
        "size": total_bytes,
        "chunk_count": len(results),
        "chunks": results
    }


def download_file(manifest, output_path):
    with httpx.Client(timeout=5.0) as client:
        with open(output_path, "wb") as output:
            for chunk in manifest["chunks"]:
                verified = []

                for node in chunk["nodes"]:
                    try:
                        response = client.get(
                            f"{NODES[node]}/chunks/{chunk['hash']}"
                        )
                        response.raise_for_status()

                        data = response.content

                        if hashlib.sha256(data).hexdigest() != chunk["hash"]:
                            print(f"Corrupt chunk on {node}")
                            continue

                        verified.append(data)

                        if len(verified) >= R:
                            break

                    except httpx.HTTPError as error:
                        print(f"Read failed on {node}: {error}")

                if len(verified) < R:
                    raise RuntimeError(
                        f"Read quorum failed for {chunk['hash']}: "
                        f"{len(verified)}/{R}"
                    )

                output.write(verified[0])

    print(f"File reconstructed: {output_path}")
