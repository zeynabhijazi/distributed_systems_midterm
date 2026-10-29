
from pathlib import Path
import hashlib

from storage.chunker import chunk_file, get_file_metadata


def test_fixed_size_chunking(tmp_path):
    file_path = tmp_path / "test_file.bin"

    # Generate a 10 MiB test file
    with open(file_path, "wb") as f:
        f.write(b"A" * (10 * 1024 * 1024))

    chunks = list(chunk_file(file_path))

    assert len(chunks) == 3

    assert chunks[0]["size"] == 4 * 1024 * 1024
    assert chunks[1]["size"] == 4 * 1024 * 1024
    assert chunks[2]["size"] == 2 * 1024 * 1024

    # Verify the SHA-256 hash of every chunk
    for chunk in chunks:
        assert hashlib.sha256(
            chunk["data"]
        ).hexdigest() == chunk["hash"]

    # Reconstruct the original file
    reconstructed = b"".join(
        chunk["data"] for chunk in chunks
    )

    assert reconstructed == file_path.read_bytes()


def test_file_metadata(tmp_path):
    file_path = tmp_path / "example.txt"
    file_path.write_text("Distributed Storage Framework")

    metadata = get_file_metadata(file_path)

    assert metadata["filename"] == "example.txt"
    assert metadata["chunk_count"] == 1
    assert len(metadata["chunks"][0]["hash"]) == 64
    assert metadata["size"] == file_path.stat().st_size
