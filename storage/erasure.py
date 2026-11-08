
from zfec import Encoder, Decoder

DATA_SHARDS = 4
PARITY_SHARDS = 2
TOTAL_SHARDS = DATA_SHARDS + PARITY_SHARDS


def encode_data(data: bytes):
    original_size = len(data)

    block_size = max(
        1,
        (original_size + DATA_SHARDS - 1) // DATA_SHARDS
    )

    padded_size = block_size * DATA_SHARDS
    padded = data.ljust(padded_size, b"\x00")

    blocks = [
        padded[i * block_size:(i + 1) * block_size]
        for i in range(DATA_SHARDS)
    ]

    encoder = Encoder(DATA_SHARDS, TOTAL_SHARDS)
    shards = encoder.encode(blocks)

    return {
        "shards": list(shards),
        "original_size": original_size,
        "data_shards": DATA_SHARDS,
        "total_shards": TOTAL_SHARDS
    }


def decode_data(shards, shard_indices, original_size):
    if len(shards) < DATA_SHARDS:
        raise ValueError("At least four shards are required")

    decoder = Decoder(DATA_SHARDS, TOTAL_SHARDS)

    recovered_blocks = decoder.decode(
        shards[:DATA_SHARDS],
        shard_indices[:DATA_SHARDS]
    )

    return b"".join(recovered_blocks)[:original_size]
