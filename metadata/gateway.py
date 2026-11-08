
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func

from metadata.database import (
    SessionLocal,
    Bucket,
    BucketStoragePolicy,
    StoredObject,
    ChunkReference,
)
from storage.distributor import download_file


router = APIRouter(tags=["Gateway"])

VALID_MODES = {"replication", "erasure"}


def validate_mode(mode):
    if mode not in VALID_MODES:
        raise HTTPException(
            400,
            "Mode must be replication or erasure",
        )


def get_bucket_mode(db, bucket):
    policy = db.get(BucketStoragePolicy, bucket)
    return policy.mode if policy else "replication"


# ---------------------------------
# CREATE BUCKET
# ---------------------------------

@router.post("/buckets/{name}")
def create_bucket(
    name: str,
    mode: str = Query(default="replication"),
):
    if not re.fullmatch(
        r"[a-z0-9][a-z0-9.-]{2,62}",
        name,
    ):
        raise HTTPException(400, "Invalid bucket name")

    validate_mode(mode)

    with SessionLocal() as db:
        if db.get(Bucket, name):
            raise HTTPException(
                409,
                "Bucket already exists",
            )

        db.add(Bucket(name=name))
        db.add(
            BucketStoragePolicy(
                bucket=name,
                mode=mode,
            )
        )

        db.commit()

    return {
        "bucket": name,
        "mode": mode,
        "created": True,
    }


# ---------------------------------
# LIST BUCKETS
# ---------------------------------

@router.get("/buckets")
def list_buckets():
    with SessionLocal() as db:
        buckets = db.scalars(select(Bucket)).all()

        return [
            {
                "name": bucket.name,
                "created_at": bucket.created_at,
                "mode": get_bucket_mode(db, bucket.name),
            }
            for bucket in buckets
        ]


# ---------------------------------
# GET BUCKET STORAGE MODE
# ---------------------------------

@router.get("/buckets/{name}/mode")
def get_storage_mode(name: str):
    with SessionLocal() as db:
        if not db.get(Bucket, name):
            raise HTTPException(404, "Bucket not found")

        return {
            "bucket": name,
            "mode": get_bucket_mode(db, name),
        }


# ---------------------------------
# CHANGE BUCKET STORAGE MODE
# ---------------------------------

@router.put("/buckets/{name}/mode")
def change_storage_mode(
    name: str,
    mode: str = Query(...),
):
    validate_mode(mode)

    with SessionLocal() as db:
        if not db.get(Bucket, name):
            raise HTTPException(404, "Bucket not found")

        current = get_bucket_mode(db, name)

        if current == mode:
            return {
                "bucket": name,
                "mode": mode,
                "message": "Mode already selected",
            }

        object_count = db.scalar(
            select(func.count(StoredObject.id)).where(
                StoredObject.bucket == name
            )
        )

        if object_count:
            raise HTTPException(
                409,
                "Cannot change mode of a non-empty bucket",
            )

        policy = db.get(BucketStoragePolicy, name)

        if policy is None:
            policy = BucketStoragePolicy(
                bucket=name,
                mode=mode,
            )
            db.add(policy)
        else:
            policy.mode = mode

        db.commit()

    return {
        "bucket": name,
        "mode": mode,
        "message": "Storage mode updated",
    }


# ---------------------------------
# OBJECT METADATA
# ---------------------------------

@router.get("/object-info/{bucket}/{key:path}")
def object_info(bucket: str, key: str):
    with SessionLocal() as db:
        obj = db.scalar(
            select(StoredObject)
            .where(
                StoredObject.bucket == bucket,
                StoredObject.key == key,
            )
            .order_by(StoredObject.version.desc())
        )

        if obj is None:
            raise HTTPException(
                404,
                "Object not found",
            )

        return {
            "bucket": obj.bucket,
            "key": obj.key,
            "size": obj.size,
            "version": obj.version,
            "chunk_count": len(obj.chunk_hashes),
            "chunk_hashes": obj.chunk_hashes,
            "created_at": obj.created_at,
            "storage_mode": get_bucket_mode(db, bucket),
        }


# ---------------------------------
# BYTE-RANGE DOWNLOAD
# ---------------------------------

@router.get("/range/{bucket}/{key:path}")
def download_range(
    bucket: str,
    key: str,
    range_header: str | None = Header(
        default=None,
        alias="Range",
    ),
):
    with SessionLocal() as db:
        obj = db.scalar(
            select(StoredObject)
            .where(
                StoredObject.bucket == bucket,
                StoredObject.key == key,
            )
            .order_by(StoredObject.version.desc())
        )

        if obj is None:
            raise HTTPException(404, "Object not found")

        if get_bucket_mode(db, bucket) == "erasure":
            raise HTTPException(
                501,
                "Erasure downloads will be integrated in Step 21.2B",
            )

        size = obj.size

        chunks = db.scalars(
            select(ChunkReference)
            .where(ChunkReference.object_id == obj.id)
            .order_by(ChunkReference.chunk_index)
        ).all()

        manifest = {
            "chunks": [
                {
                    "hash": chunk.chunk_hash,
                    "nodes": chunk.nodes,
                }
                for chunk in chunks
            ]
        }

    if size == 0:
        raise HTTPException(
            416,
            "Empty object has no byte ranges",
        )

    if range_header:
        match = re.fullmatch(
            r"bytes=(\d+)-(\d*)",
            range_header.strip(),
        )

        if not match:
            raise HTTPException(
                416,
                "Invalid byte range",
            )

        start = int(match.group(1))
        end = (
            int(match.group(2))
            if match.group(2)
            else size - 1
        )
    else:
        start, end = 0, size - 1

    if start >= size or end < start:
        raise HTTPException(
            416,
            "Range not satisfiable",
        )

    end = min(end, size - 1)

    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp_path = temp.name

    try:
        download_file(manifest, temp_path)
    except Exception as error:
        Path(temp_path).unlink(missing_ok=True)

        raise HTTPException(
            503,
            f"Download failed: {error}",
        )

    def stream():
        try:
            with open(temp_path, "rb") as file:
                file.seek(start)
                remaining = end - start + 1

                while remaining > 0:
                    data = file.read(
                        min(65536, remaining)
                    )

                    if not data:
                        break

                    remaining -= len(data)
                    yield data
        finally:
            Path(temp_path).unlink(missing_ok=True)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }

    if range_header:
        headers["Content-Range"] = (
            f"bytes {start}-{end}/{size}"
        )

    return StreamingResponse(
        stream(),
        status_code=206 if range_header else 200,
        headers=headers,
        media_type="application/octet-stream",
    )
