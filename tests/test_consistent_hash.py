
import hashlib
from storage.consistent_hash import ConsistentHashRing


def test_three_distinct_replicas():
    ring = ConsistentHashRing(
        ["node1", "node2", "node3", "node4"]
    )

    chunk_hash = hashlib.sha256(b"test").hexdigest()
    nodes = ring.get_nodes(chunk_hash, 3)

    assert len(nodes) == 3
    assert len(set(nodes)) == 3


def test_limited_movement():
    old_ring = ConsistentHashRing(
        ["node1", "node2", "node3", "node4"]
    )

    new_ring = ConsistentHashRing(
        ["node1", "node2", "node3", "node4", "node5"]
    )

    hashes = [
        hashlib.sha256(str(i).encode()).hexdigest()
        for i in range(1000)
    ]

    moved = sum(
        old_ring.get_nodes(h, 1) != new_ring.get_nodes(h, 1)
        for h in hashes
    )

    print(f"\nMoved primary placements: {moved}/1000")

    assert 0 < moved < 500
