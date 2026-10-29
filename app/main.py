
from fastapi import FastAPI, Request, HTTPException, Response
from pathlib import Path
import hashlib

app = FastAPI(title="Distributed Storage Node")

# Directory for storing chunks
STORAGE_DIR = Path("data/node1")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
def root():
    return {
        "message": "Storage Node is running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "node": "node1"
    }


@app.put("/chunks/{chunk_hash}")
async def put_chunk(chunk_hash: str, request: Request):

    # Read the uploaded binary data
    data = await request.body()

    # Calculate the SHA-256 hash
    calculated_hash = hashlib.sha256(data).hexdigest()

    # Verify the provided hash
    if calculated_hash != chunk_hash:
        raise HTTPException(
            status_code=400,
            detail="Chunk hash mismatch"
        )

    # Determine where the chunk will be saved
    chunk_path = STORAGE_DIR / chunk_hash

    # Avoid storing an identical chunk twice
    if chunk_path.exists():
        return {
            "message": "Chunk already exists",
            "hash": chunk_hash,
            "size": len(data)
        }

    # Save the chunk to disk
    chunk_path.write_bytes(data)

    return {
        "message": "Chunk stored successfully",
        "hash": chunk_hash,
        "size": len(data)
    }


@app.get("/chunks/{chunk_hash}")
def get_chunk(chunk_hash: str):

    # Validate the hash format
    if len(chunk_hash) != 64 or any(
        c not in "0123456789abcdef" for c in chunk_hash
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid SHA-256 hash"
        )

    # Locate the chunk on disk
    chunk_path = STORAGE_DIR / chunk_hash

    # Check whether the chunk exists
    if not chunk_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Chunk not found"
        )

    # Read the stored binary data
    data = chunk_path.read_bytes()

    # Recalculate SHA-256 to verify integrity
    calculated_hash = hashlib.sha256(data).hexdigest()

    if calculated_hash != chunk_hash:
        raise HTTPException(
            status_code=409,
            detail="Chunk corrupted: SHA-256 mismatch"
        )

    # Return the original binary content
    return Response(
        content=data,
        media_type="application/octet-stream"
    )


@app.head("/chunks/{chunk_hash}")
def head_chunk(chunk_hash: str):

    # Validate the SHA-256 hash format
    if len(chunk_hash) != 64 or any(
        c not in "0123456789abcdef" for c in chunk_hash
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid SHA-256 hash"
        )

    # Locate the chunk
    chunk_path = STORAGE_DIR / chunk_hash

    # Check whether it exists
    if not chunk_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Chunk not found"
        )

    # Read the chunk to verify its integrity
    data = chunk_path.read_bytes()

    calculated_hash = hashlib.sha256(data).hexdigest()

    if calculated_hash != chunk_hash:
        raise HTTPException(
            status_code=409,
            detail="Chunk corrupted: SHA-256 mismatch"
        )

    # Return headers only, without chunk content
    return Response(
        status_code=200,
        headers={
            "Content-Length": str(len(data)),
            "ETag": f'"{chunk_hash}"',
            "X-Chunk-Hash": chunk_hash
        }
    )

