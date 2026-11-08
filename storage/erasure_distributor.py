
import hashlib
import os

import httpx

from storage.erasure import encode_data, decode_data


IN_DOCKER = os.getenv("IN_DOCKER", "false").lower() == "true"

if IN_DOCKER:
    NODES = {
        f"node{i}": f"http://node{i}:8000"
        for i in range(1, 7)
    }
else:
    NODES = {
        "node1": "http://localhost:8001",
        "node2": "http://localhost:8002",
        "node3": "http://localhost:8003",
        "node4": "http://localhost:8004",
        "node5": "http://localhost:8006",
        "node6": "http://localhost:8007",
    }


def store_erasure_chunk(data: bytes):
    encoded = encode_data(data)

    manifest = {
        "original_hash": hashlib.sha256(data).hexdigest(),
        "original_size": encoded["original_size"],
        "shards": [],
    }

    with httpx.Client(timeout=15.0) as client:
        for index, shard in enumerate(encoded["shards"]):
            node = f"node{index + 1}"
            shard_hash = hashlib.sha256(shard).hexdigest()

            response = client.put(
                f"{NODES[node]}/chunks/{shard_hash}",
                content=shard,
            )
            response.raise_for_status()

            manifest["shards"].append({
                "index": index,
                "node": node,
                "hash": shard_hash,
            })

    return manifest


def retrieve_erasure_chunk(manifest):
    available_shards = []
    available_indices = []

    with httpx.Client(timeout=5.0) as client:
        for item in manifest["shards"]:
            try:
                response = client.get(
                    f"{NODES[item['node']]}/chunks/{item['hash']}"
                )
                response.raise_for_status()

                shard = response.content

                if hashlib.sha256(shard).hexdigest() != item["hash"]:
                    continue

                available_shards.append(shard)
                available_indices.append(item["index"])

                if len(available_shards) == 4:
                    break

            except httpx.HTTPError:
                continue

    if len(available_shards) < 4:
        raise RuntimeError(
            "Erasure recovery failed: fewer than 4 valid shards"
        )

    data = decode_data(
        available_shards,
        available_indices,
        manifest["original_size"],
    )

    if hashlib.sha256(data).hexdigest() != manifest["original_hash"]:
        raise RuntimeError("Recovered data failed SHA-256 verification")

    return data
