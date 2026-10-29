
from pathlib import Path

from storage.distributor import (
    distribute_file,
    download_file
)

original = Path("sample.bin")
restored = Path("restored.bin")

if not original.exists():
    original.write_bytes(b"A" * (10 * 1024 * 1024))

print("Uploading...")
manifest = distribute_file(original)

print("\nDownloading...")
download_file(manifest, restored)

assert original.read_bytes() == restored.read_bytes()

print("\nSUCCESS: Original and downloaded files match!")
print("Total chunks:", manifest["chunk_count"])
