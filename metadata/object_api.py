
import os
import tempfile
from pathlib import Path

from fastapi import (
    APIRouter, UploadFile, File,
    HTTPException
)
from fastapi.responses import FileResponse
from sqlalchemy import select, func

from metadata.database import (
    SessionLocal, StoredObject, ChunkReference
)
from storage.distributor import (
    distribute_file, download_file
)

router = APIRouter(prefix="/objects", tags=["Objects"])


@router.post("/{bucket}/{key:path}")
def upload_object(bucket: str, key: str, file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp_path = temp.name
        while data := file.file.read(1024 * 1024):
            temp.write(data)

    try:
        manifest = distribute_file(temp_path)

        with SessionLocal() as db:
            latest = db.scalar(
                select(func.max(StoredObject.version)).where(
                    StoredObject.bucket == bucket,
                    StoredObject.key == key
                )
            )
            version = (latest or 0) + 1

            obj = StoredObject(
                bucket=bucket,
                key=key,
                size=manifest["size"],
                version=version,
                chunk_hashes=[
                    c["hash"] for c in manifest["chunks"]
                ]
            )
            db.add(obj)
            db.flush()

            for chunk in manifest["chunks"]:
                db.add(ChunkReference(
                    object_id=obj.id,
                    chunk_index=chunk["index"],
                    chunk_hash=chunk["hash"],
                    nodes=chunk["nodes"]
                ))

            db.commit()

            return {
                "message": "Object uploaded",
                "bucket": bucket,
                "key": key,
                "version": version,
                "size": obj.size,
                "chunks": len(manifest["chunks"])
            }
    finally:
        os.unlink(temp_path)


@router.get("/{bucket}/{key:path}")
def get_object(bucket: str, key: str):
    with SessionLocal() as db:
        obj = db.scalar(
            select(StoredObject)
            .where(
                StoredObject.bucket == bucket,
                StoredObject.key == key
            )
            .order_by(StoredObject.version.desc())
        )

        if obj is None:
            raise HTTPException(404, "Object not found")

        chunks = db.scalars(
            select(ChunkReference)
            .where(ChunkReference.object_id == obj.id)
            .order_by(ChunkReference.chunk_index)
        ).all()

        manifest = {
            "chunks": [
                {
                    "hash": c.chunk_hash,
                    "nodes": c.nodes
                }
                for c in chunks
            ]
        }

    temp_path = tempfile.mktemp()
    try:
        download_file(manifest, temp_path)
    except Exception as error:
        Path(temp_path).unlink(missing_ok=True)
        raise HTTPException(503, str(error))

    return FileResponse(
        temp_path,
        filename=Path(key).name,
        background=__import__(
            "starlette.background", fromlist=["BackgroundTask"]
        ).BackgroundTask(lambda: Path(temp_path).unlink(missing_ok=True))
    )


@router.get("/")
def list_objects(bucket: str | None = None):
    with SessionLocal() as db:
        query = select(StoredObject).order_by(
            StoredObject.id.desc()
        )

        if bucket:
            query = query.where(StoredObject.bucket == bucket)

        objects = db.scalars(query).all()

        return [
            {
                "bucket": o.bucket,
                "key": o.key,
                "version": o.version,
                "size": o.size,
                "created_at": o.created_at
            }
            for o in objects
        ]


@router.delete("/{bucket}/{key:path}")
def delete_object(bucket: str, key: str):
    with SessionLocal() as db:
        objects = db.scalars(
            select(StoredObject).where(
                StoredObject.bucket == bucket,
                StoredObject.key == key
            )
        ).all()

        if not objects:
            raise HTTPException(404, "Object not found")

        for obj in objects:
            db.query(ChunkReference).filter(
                ChunkReference.object_id == obj.id
            ).delete()
            db.delete(obj)

        db.commit()

    return {"message": "Object metadata deleted"}
