
import hashlib
import logging
import threading
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from sqlalchemy import select

from metadata.database import SessionLocal, ErasureChunk
from storage.erasure import encode_data, decode_data
from storage.erasure_distributor import NODES

router = APIRouter(tags=["Integrity Scrubbing"])
logger = logging.getLogger(__name__)

scrub_lock = threading.Lock()

last_result = {
    "status": "not_run",
    "checked_chunks": 0,
    "checked_shards": 0,
    "repaired_shards": 0,
    "unrecoverable_chunks": 0,
    "repair_failures": 0,
    "last_run": None,
}


def valid_hash(data, expected_hash):
    return hashlib.sha256(data).hexdigest() == expected_hash


def scrub_erasure():
    global last_result

    if not scrub_lock.acquire(blocking=False):
        return {"status": "already_running"}

    result = {
        "status": "completed",
        "checked_chunks": 0,
        "checked_shards": 0,
        "repaired_shards": 0,
        "unrecoverable_chunks": 0,
        "repair_failures": 0,
        "last_run": None,
    }

    try:
        with SessionLocal() as db:
            chunks = db.scalars(select(ErasureChunk)).all()

            with httpx.Client(timeout=10.0) as client:
                for chunk in chunks:
                    result["checked_chunks"] += 1

                    valid_shards = []
                    valid_indices = []
                    missing_or_corrupt = []

                    # Verify all six shard locations.
                    for shard in chunk.shards:
                        result["checked_shards"] += 1

                        try:
                            node_url = NODES[shard["node"]]

                            response = client.get(
                                f"{node_url}/chunks/{shard['hash']}"
                            )
                            response.raise_for_status()

                            data = response.content

                            if not valid_hash(data, shard["hash"]):
                                raise ValueError("Hash mismatch")

                            valid_shards.append(data)
                            valid_indices.append(shard["index"])

                        except (
                            httpx.HTTPError,
                            KeyError,
                            ValueError,
                        ):
                            missing_or_corrupt.append(shard)

                    if not missing_or_corrupt:
                        continue

                    if len(valid_shards) < 4:
                        result["unrecoverable_chunks"] += 1

                        logger.error(
                            "Cannot recover chunk %s: only %d shards",
                            chunk.original_hash,
                            len(valid_shards),
                        )
                        continue

                    # Reconstruct original data from four shards.
                    original = decode_data(
                        valid_shards[:4],
                        valid_indices[:4],
                        chunk.original_size,
                    )

                    if not valid_hash(
                        original,
                        chunk.original_hash,
                    ):
                        result["unrecoverable_chunks"] += 1
                        logger.error(
                            "Reconstructed hash mismatch: %s",
                            chunk.original_hash,
                        )
                        continue

                    # Generate the original six shards again.
                    encoded = encode_data(original)

                    for shard in missing_or_corrupt:
                        index = shard["index"]
                        expected_data = encoded["shards"][index]

                        if not valid_hash(
                            expected_data,
                            shard["hash"],
                        ):
                            result["repair_failures"] += 1
                            logger.error(
                                "Regenerated shard hash mismatch: %s",
                                shard["hash"],
                            )
                            continue

                        try:
                            url = (
                                f"{NODES[shard['node']]}"
                                f"/chunks/{shard['hash']}"
                            )

                            # Remove a damaged replica if present.
                            # A missing replica returns 404.
                            old_response = client.delete(url)

                            if old_response.status_code not in (
                                200, 204, 404,
                            ):
                                old_response.raise_for_status()

                            response = client.put(
                                url,
                                content=expected_data,
                            )
                            response.raise_for_status()

                            # Verify that the repaired shard is readable.
                            check = client.get(url)
                            check.raise_for_status()

                            if not valid_hash(
                                check.content,
                                shard["hash"],
                            ):
                                raise ValueError(
                                    "Repaired shard verification failed"
                                )

                            result["repaired_shards"] += 1

                            logger.info(
                                "SCRUB REPAIRED shard=%s node=%s",
                                shard["hash"],
                                shard["node"],
                            )

                        except (
                            httpx.HTTPError,
                            KeyError,
                            ValueError,
                        ) as error:
                            result["repair_failures"] += 1

                            logger.warning(
                                "SCRUB REPAIR FAILED shard=%s: %s",
                                shard["hash"],
                                error,
                            )

        result["last_run"] = datetime.now(
            timezone.utc
        ).isoformat()

        last_result = result.copy()

        logger.info("Scrub completed: %s", result)
        return result

    except Exception:
        logger.exception("Integrity scrub failed")

        result["status"] = "failed"
        result["last_run"] = datetime.now(
            timezone.utc
        ).isoformat()

        last_result = result.copy()
        raise

    finally:
        scrub_lock.release()


@router.get("/scrub/status")
def scrub_status():
    return last_result


@router.post("/scrub/run")
def run_scrub():
    return scrub_erasure()
