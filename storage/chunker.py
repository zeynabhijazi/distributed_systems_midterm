
import hashlib
from pathlib import Path

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB


def chunk_file(file_path, chunk_size=CHUNK_SIZE):
    """
    Split a file into fixed-size chunks.
    Yield each chunk's hash and binary data.
    """

    with open(file_path, "rb") as file:
        while True:
            data = file.read(chunk_size)

            if not data:
                break

            chunk_hash = hashlib.sha256(data).hexdigest()

            yield {
                "hash": chunk_hash,
                "size": len(data),
                "data": data
            }


def get_file_metadata(file_path):
    """
    Calculate file size and ordered chunk hashes.
    """

    file_path = Path(file_path)

    chunks = []

    for chunk in chunk_file(file_path):
        chunks.append({
            "hash": chunk["hash"],
            "size": chunk["size"]
        })

    return {
        "filename": file_path.name,
        "size": file_path.stat().st_size,
        "chunk_count": len(chunks),
        "chunks": chunks
    }
