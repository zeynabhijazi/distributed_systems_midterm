
import hashlib
import os
from pathlib import Path

from storage.chunker import chunk_file
from storage.fastcdc import (
    chunk_file_fastcdc,
    reconstruct_chunks
)

TEST_DIR = Path("test-files/fastcdc")
TEST_DIR.mkdir(parents=True, exist_ok=True)

ORIGINAL = TEST_DIR / "original.bin"
MODIFIED = TEST_DIR / "modified.bin"

FILE_SIZE = 24 * 1024 * 1024


def create_test_files():
    if not ORIGINAL.exists():
        print("Generating original 24 MiB file...")
        ORIGINAL.write_bytes(os.urandom(FILE_SIZE))

    data = ORIGINAL.read_bytes()

    # Insert 100 bytes after the first 100 KiB.
    modified = (
        data[:100 * 1024]
        + b"X" * 100
        + data[100 * 1024:]
    )

    MODIFIED.write_bytes(modified)


def calculate_similarity(original_chunks, modified_chunks):
    original_hashes = {
        chunk["hash"] for chunk in original_chunks
    }

    modified_hashes = {
        chunk["hash"] for chunk in modified_chunks
    }

    shared = original_hashes & modified_hashes

    return len(shared)


def test_algorithm(name, function):
    original_chunks = list(function(ORIGINAL))
    modified_chunks = list(function(MODIFIED))

    original_bytes = b"".join(
        chunk["data"] for chunk in original_chunks
    )

    modified_bytes = b"".join(
        chunk["data"] for chunk in modified_chunks
    )

    assert hashlib.sha256(original_bytes).digest() == hashlib.sha256(
        ORIGINAL.read_bytes()
    ).digest()

    assert hashlib.sha256(modified_bytes).digest() == hashlib.sha256(
        MODIFIED.read_bytes()
    ).digest()

    shared = calculate_similarity(
        original_chunks,
        modified_chunks
    )

    print(f"\n{name}")
    print("-" * 40)
    print("Original chunks:", len(original_chunks))
    print("Modified chunks:", len(modified_chunks))
    print("Shared chunks:", shared)

    original_sizes = [
        chunk["size"] for chunk in original_chunks
    ]

    print(
        "Average chunk size:",
        round(sum(original_sizes) / len(original_sizes) / 1024 / 1024, 2),
        "MiB"
    )

    return shared


def main():
    create_test_files()

    print("Original file:", ORIGINAL)
    print("Modified file:", MODIFIED)
    print("Inserted bytes: 100")

    fixed_shared = test_algorithm(
        "FIXED-SIZE CHUNKING",
        chunk_file
    )

    cdc_shared = test_algorithm(
        "CONTENT-DEFINED CHUNKING",
        chunk_file_fastcdc
    )

    print("\n========== COMPARISON ==========")
    print("Fixed-size shared chunks:", fixed_shared)
    print("FastCDC-style shared chunks:", cdc_shared)

    if cdc_shared > fixed_shared:
        print(
            "RESULT: Content-defined chunking reused more chunks."
        )
    elif cdc_shared == fixed_shared:
        print(
            "RESULT: Both algorithms reused the same number of chunks."
        )
    else:
        print(
            "RESULT: Fixed-size chunking reused more chunks in this test."
        )


if __name__ == "__main__":
    main()
