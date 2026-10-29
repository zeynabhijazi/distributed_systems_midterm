
from storage.chunker import get_file_metadata
import sys

if len(sys.argv) != 2:
    print("Usage: python -m scripts.test_chunking <file>")
    sys.exit(1)

metadata = get_file_metadata(sys.argv[1])

print("Filename:", metadata["filename"])
print("File size:", metadata["size"], "bytes")
print("Total chunks:", metadata["chunk_count"])

for index, chunk in enumerate(metadata["chunks"], start=1):
    print(
        f"Chunk {index}: "
        f"size={chunk['size']} "
        f"hash={chunk['hash']}"
    )
