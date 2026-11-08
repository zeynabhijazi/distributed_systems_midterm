
import tempfile
from pathlib import Path

import httpx

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    HTTPException,
)
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import select, func

from metadata.database import (
    SessionLocal,
    StoredObject,
    ChunkReference,
    StoredChunk,
    Bucket,
    BucketStoragePolicy,
    ErasureChunk,
    ErasureShard,
)

from storage.chunker import chunk_file

from storage.distributor import (
    distribute_file,
    download_file,
    NODES as REPLICA_NODES,
)

from storage.erasure_distributor import (
    store_erasure_chunk,
    retrieve_erasure_chunk,
    NODES as ERASURE_NODES,
)


router = APIRouter(
    prefix="/objects",
    tags=["Objects"],
)


# ========================================
# HELPER FUNCTIONS
# ========================================

def get_mode(db, bucket):
    policy = db.get(BucketStoragePolicy, bucket)

    if policy is not None:
        return policy.mode

    # Legacy buckets created before storage
    # policies were introduced use replication.
    return "replication"


def get_latest_object(db, bucket, key):
    obj = db.scalar(
        select(StoredObject)
        .where(
            StoredObject.bucket == bucket,
            StoredObject.key == key,
        )
        .order_by(
            StoredObject.version.desc()
        )
    )

    if obj is None:
        raise HTTPException(
            status_code=404,
            detail="Object not found",
        )

    return obj


def object_mode(db, obj):
    # Erasure manifests identify erasure-coded
    # objects independently of bucket policies.
    erasure_row = db.scalar(
        select(ErasureChunk.id)
        .where(ErasureChunk.object_id == obj.id)
        .limit(1)
    )

    if erasure_row is not None:
        return "erasure"

    # A nonempty legacy object with replication
    # references stays in replication mode.
    replica_row = db.scalar(
        select(ChunkReference.id)
        .where(ChunkReference.object_id == obj.id)
        .limit(1)
    )

    if replica_row is not None:
        return "replication"

    return get_mode(db, obj.bucket)


def build_erasure_manifest(file_path):
    chunks = []
    total_size = 0

    for index, chunk in enumerate(chunk_file(file_path)):
        encoded = store_erasure_chunk(
            chunk["data"]
        )

        chunks.append({
            "index": index,
            "original_hash": encoded["original_hash"],
            "original_size": encoded["original_size"],
            "shards": encoded["shards"],
        })

        total_size += chunk["size"]

    return {
        "size": total_size,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }


# ========================================
# UPLOAD OBJECT
# ========================================

@router.post("/{bucket}/{key:path}")
def upload_object(
    bucket: str,
    key: str,
    file: UploadFile = File(...),
):
    if not key:
        raise HTTPException(
            400,
            "Object key cannot be empty",
        )

    # Preserve compatibility with existing
    # legacy buckets and objects.
    with SessionLocal() as db:
        bucket_exists = db.get(Bucket, bucket)

        legacy_object_exists = db.scalar(
            select(StoredObject.id)
            .where(StoredObject.bucket == bucket)
            .limit(1)
        )

        if (
            bucket_exists is None
            and legacy_object_exists is None
        ):
            raise HTTPException(
                404,
                "Bucket not found",
            )

        mode = get_mode(db, bucket)

    temp_path = None

    try:
        # Save uploaded file to temporary disk.
        with tempfile.NamedTemporaryFile(
            delete=False
        ) as temp:
            temp_path = temp.name

            while True:
                data = file.file.read(
                    1024 * 1024
                )

                if not data:
                    break

                temp.write(data)

        # Store file using selected bucket mode.
        try:
            if mode == "erasure":
                manifest = build_erasure_manifest(
                    temp_path
                )
            else:
                manifest = distribute_file(
                    temp_path
                )

        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail=f"Storage failed: {error}",
            )

        # Save object and chunk metadata.
        with SessionLocal() as db:
            latest = db.scalar(
                select(func.max(StoredObject.version))
                .where(
                    StoredObject.bucket == bucket,
                    StoredObject.key == key,
                )
            )

            version = (latest or 0) + 1

            hashes = [
                (
                    chunk["original_hash"]
                    if mode == "erasure"
                    else chunk["hash"]
                )
                for chunk in manifest["chunks"]
            ]

            obj = StoredObject(
                bucket=bucket,
                key=key,
                size=manifest["size"],
                version=version,
                chunk_hashes=hashes,
            )

            db.add(obj)
            db.flush()

            for chunk in manifest["chunks"]:

                # -------------------------
                # ERASURE-CODED STORAGE
                # -------------------------
                if mode == "erasure":
                    db.add(
                        ErasureChunk(
                            object_id=obj.id,
                            chunk_index=chunk["index"],
                            original_hash=chunk["original_hash"],
                            original_size=chunk["original_size"],
                            shards=chunk["shards"],
                        )
                    )

                    for shard in chunk["shards"]:
                        stored = db.get(
                            ErasureShard,
                            shard["hash"],
                        )

                        if stored is None:
                            db.add(
                                ErasureShard(
                                    hash=shard["hash"],
                                    ref_count=1,
                                    nodes=[shard["node"]],
                                )
                            )

                            # Ensure subsequent chunks in
                            # the same transaction can
                            # find the new shard.
                            db.flush()

                        else:
                            stored.ref_count += 1

                            stored.nodes = sorted(
                                set(stored.nodes)
                                | {shard["node"]}
                            )

                # -------------------------
                # REPLICATED STORAGE
                # -------------------------
                else:
                    stored = db.get(
                        StoredChunk,
                        chunk["hash"],
                    )

                    if stored is None:
                        db.add(
                            StoredChunk(
                                hash=chunk["hash"],
                                size=chunk["size"],
                                ref_count=1,
                                nodes=chunk["nodes"],
                            )
                        )

                        db.flush()

                    else:
                        stored.ref_count += 1

                        stored.nodes = sorted(
                            set(stored.nodes)
                            | set(chunk["nodes"])
                        )

                    db.add(
                        ChunkReference(
                            object_id=obj.id,
                            chunk_index=chunk["index"],
                            chunk_hash=chunk["hash"],
                            nodes=chunk["nodes"],
                        )
                    )

            db.commit()

        return {
            "message": "Object uploaded successfully",
            "bucket": bucket,
            "key": key,
            "version": version,
            "size": manifest["size"],
            "chunks": len(manifest["chunks"]),
            "storage_mode": mode,
        }

    finally:
        file.file.close()

        if temp_path is not None:
            Path(temp_path).unlink(
                missing_ok=True
            )


# ========================================
# LIST OBJECTS
# ========================================

@router.get("/")
def list_objects(
    bucket: str | None = None,
):
    with SessionLocal() as db:
        query = (
            select(StoredObject)
            .order_by(StoredObject.id.desc())
        )

        if bucket:
            query = query.where(
                StoredObject.bucket == bucket
            )

        objects = db.scalars(query).all()

        return [
            {
                "bucket": obj.bucket,
                "key": obj.key,
                "version": obj.version,
                "size": obj.size,
                "created_at": obj.created_at,
            }
            for obj in objects
        ]


# ========================================
# DOWNLOAD OBJECT
# ========================================

@router.get("/{bucket}/{key:path}")
def get_object(bucket: str, key: str):
    with SessionLocal() as db:
        obj = get_latest_object(
            db, bucket, key
        )

        mode = object_mode(db, obj)

        if mode == "erasure":
            rows = db.scalars(
                select(ErasureChunk)
                .where(
                    ErasureChunk.object_id == obj.id
                )
                .order_by(
                    ErasureChunk.chunk_index
                )
            ).all()

            if obj.size > 0 and not rows:
                raise HTTPException(
                    503,
                    "Erasure manifest missing",
                )

            manifest = {
                "chunks": [
                    {
                        "original_hash": row.original_hash,
                        "original_size": row.original_size,
                        "shards": row.shards,
                    }
                    for row in rows
                ]
            }

        else:
            rows = db.scalars(
                select(ChunkReference)
                .where(
                    ChunkReference.object_id == obj.id
                )
                .order_by(
                    ChunkReference.chunk_index
                )
            ).all()

            if obj.size > 0 and not rows:
                raise HTTPException(
                    503,
                    "Replication manifest missing",
                )

            chunks = []

            for row in rows:
                stored = db.get(
                    StoredChunk,
                    row.chunk_hash,
                )

                # Prefer updated replica locations
                # produced by the repair worker.
                nodes = (
                    stored.nodes
                    if stored is not None
                    else row.nodes
                )

                chunks.append({
                    "hash": row.chunk_hash,
                    "nodes": nodes,
                })

            manifest = {
                "chunks": chunks
            }

    # Reconstruct downloaded file.
    with tempfile.NamedTemporaryFile(
        delete=False
    ) as temp:
        temp_path = temp.name

    try:
        if mode == "erasure":
            with open(
                temp_path, "wb"
            ) as output:
                for chunk in manifest["chunks"]:
                    data = retrieve_erasure_chunk(
                        chunk
                    )

                    output.write(data)

        else:
            download_file(
                manifest,
                temp_path,
            )

    except Exception as error:
        Path(temp_path).unlink(
            missing_ok=True
        )

        raise HTTPException(
            status_code=503,
            detail=f"Download failed: {error}",
        )

    return FileResponse(
        path=temp_path,
        filename=Path(key).name,
        media_type="application/octet-stream",
        background=BackgroundTask(
            lambda: Path(temp_path).unlink(
                missing_ok=True
            )
        ),
    )


# ========================================
# DELETE OBJECT
# ========================================

@router.delete("/{bucket}/{key:path}")
def delete_object(bucket: str, key: str):
    unused_chunks = []

    with SessionLocal() as db:
        objects = db.scalars(
            select(StoredObject)
            .where(
                StoredObject.bucket == bucket,
                StoredObject.key == key,
            )
        ).all()

        if not objects:
            raise HTTPException(
                status_code=404,
                detail="Object not found",
            )

        # Delete all object versions.
        for obj in objects:
            mode = object_mode(db, obj)

            if mode == "erasure":
                rows = db.scalars(
                    select(ErasureChunk)
                    .where(
                        ErasureChunk.object_id == obj.id
                    )
                ).all()

                for row in rows:
                    for shard in row.shards:
                        stored = db.get(
                            ErasureShard,
                            shard["hash"],
                        )

                        if stored is not None:
                            stored.ref_count -= 1

                            if stored.ref_count <= 0:
                                unused_chunks.append({
                                    "hash": stored.hash,
                                    "nodes": list(
                                        stored.nodes
                                    ),
                                    "mode": "erasure",
                                })

                                db.delete(stored)
                                db.flush()

                    db.delete(row)

            else:
                rows = db.scalars(
                    select(ChunkReference)
                    .where(
                        ChunkReference.object_id == obj.id
                    )
                ).all()

                for row in rows:
                    stored = db.get(
                        StoredChunk,
                        row.chunk_hash,
                    )

                    if stored is not None:
                        stored.ref_count -= 1

                        if stored.ref_count <= 0:
                            unused_chunks.append({
                                "hash": stored.hash,
                                "nodes": list(
                                    stored.nodes
                                ),
                                "mode": "replication",
                            })

                            db.delete(stored)
                            db.flush()

                    db.delete(row)

            db.delete(obj)

        db.commit()

    # Remove unused chunks from physical nodes.
    removed = 0
    failed = []

    # Avoid repeating identical delete requests.
    deletion_targets = set()

    for chunk in unused_chunks:
        for node in chunk["nodes"]:
            deletion_targets.add(
                (
                    chunk["mode"],
                    node,
                    chunk["hash"],
                )
            )

    with httpx.Client(
        timeout=10.0
    ) as client:
        for mode, node, chunk_hash in deletion_targets:
            nodes = (
                ERASURE_NODES
                if mode == "erasure"
                else REPLICA_NODES
            )

            try:
                response = client.delete(
                    f"{nodes[node]}/chunks/{chunk_hash}"
                )

                if response.status_code in (
                    200, 204, 404
                ):
                    removed += 1

                else:
                    failed.append({
                        "hash": chunk_hash,
                        "node": node,
                        "status": response.status_code,
                    })

            except (
                httpx.HTTPError,
                KeyError,
            ) as error:
                failed.append({
                    "hash": chunk_hash,
                    "node": node,
                    "error": str(error),
                })

    return {
        "message": "Object deleted successfully",
        "unused_chunks": len(unused_chunks),
        "replicas_removed_or_absent": removed,
        "failed_replicas": failed,
    }
