
import argparse
import hashlib
import json
from pathlib import Path

from storage.erasure_distributor import (
    store_erasure_chunk,
    retrieve_erasure_chunk
)

TEST_DIR = Path("test-files")
ORIGINAL = TEST_DIR / "erasure-original.bin"
RECOVERED = TEST_DIR / "erasure-recovered.bin"
MANIFEST = TEST_DIR / "erasure-manifest.json"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def store():
    TEST_DIR.mkdir(exist_ok=True)

    original_data = (
        b"Distributed Storage Erasure Coding Test\n"
        * 10000
    )

    ORIGINAL.write_bytes(original_data)

    manifest = store_erasure_chunk(original_data)

    MANIFEST.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8"
    )

    print("Original SHA-256:", sha256(original_data))
    print("Original size:", len(original_data), "bytes")
    print("Shards stored:", len(manifest["shards"]))

    for shard in manifest["shards"]:
        print(
            f"Shard {shard['index']} "
            f"stored on {shard['node']}"
        )

    print("SUCCESS: Six shards stored")


def recover():
    if not MANIFEST.exists():
        print("ERROR: Manifest not found")
        return

    manifest = json.loads(
        MANIFEST.read_text(encoding="utf-8")
    )

    recovered_data = retrieve_erasure_chunk(manifest)

    RECOVERED.write_bytes(recovered_data)

    original_data = ORIGINAL.read_bytes()

    original_hash = sha256(original_data)
    recovered_hash = sha256(recovered_data)

    print("Original SHA-256: ", original_hash)
    print("Recovered SHA-256:", recovered_hash)

    if original_hash == recovered_hash:
        print("SUCCESS: Data recovered after node failures")
    else:
        print("FAILED: Hash mismatch")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["store", "recover"]
    )

    args = parser.parse_args()

    if args.action == "store":
        store()
    else:
        recover()
