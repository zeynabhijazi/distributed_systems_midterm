
from storage.erasure import encode_data, decode_data


def test_erasure_coding():
    original = b"Distributed Storage Framework" * 1000

    encoded = encode_data(original)

    assert len(encoded["shards"]) == 6

    # Simulate losing two shards.
    available_indices = [0, 2, 4, 5]

    available_shards = [
        encoded["shards"][i]
        for i in available_indices
    ]

    recovered = decode_data(
        available_shards,
        available_indices,
        encoded["original_size"]
    )

    assert recovered == original


def test_empty_data():
    original = b""

    encoded = encode_data(original)

    recovered = decode_data(
        encoded["shards"][:4],
        [0, 1, 2, 3],
        encoded["original_size"]
    )

    assert recovered == original
