
import hashlib
import random
from pathlib import Path

MIN_SIZE = 2 * 1024 * 1024
AVG_SIZE = 4 * 1024 * 1024
MAX_SIZE = 8 * 1024 * 1024

# Deterministic lookup table for gear hashing.
_rng = random.Random(42)
GEAR = [_rng.getrandbits(64) for _ in range(256)]
MASK = AVG_SIZE - 1
HASH_MASK = (1 << 64) - 1


def fastcdc_chunks(
    data: bytes,
    min_size=MIN_SIZE,
    avg_size=AVG_SIZE,
    max_size=MAX_SIZE
):
    """
    Simplified FastCDC-style content-defined chunking.

    Chunk boundaries depend on data content rather
    than fixed file offsets.
    """

    if not (0 < min_size <= avg_size <= max_size):
        raise ValueError("Invalid chunk size configuration")

    if avg_size & (avg_size - 1):
        raise ValueError("Average size must be a power of two")

    chunks = []
    start = 0
    length = len(data)

    mask = avg_size - 1

    while start < length:
        end_limit = min(start + max_size, length)
        minimum_end = min(start + min_size, end_limit)

        if minimum_end == end_limit:
            end = end_limit
        else:
            rolling_hash = 0
            end = minimum_end

            while end < end_limit:
                rolling_hash = (
                    (rolling_hash << 1) + GEAR[data[end]]
                ) & HASH_MASK

                end += 1

                if (rolling_hash & mask) == 0:
                    break

        chunk = data[start:end]

        chunks.append({
            "index": len(chunks),
            "hash": hashlib.sha256(chunk).hexdigest(),
            "size": len(chunk),
            "data": chunk,
        })

        start = end

    return chunks


def chunk_file_fastcdc(path):
    """
    Reads a file and returns content-defined chunks.
    """
    data = Path(path).read_bytes()
    return fastcdc_chunks(data)


def reconstruct_chunks(chunks):
    return b"".join(chunk["data"] for chunk in chunks)
