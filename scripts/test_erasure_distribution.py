
from storage.erasure_distributor import (
    store_erasure_chunk,
    retrieve_erasure_chunk
)

original = b"Erasure Coding Distributed Test" * 10000

manifest = store_erasure_chunk(original)

print("Stored six shards across six nodes")

recovered = retrieve_erasure_chunk(manifest)

assert recovered == original

print("SUCCESS: Data recovered correctly")
