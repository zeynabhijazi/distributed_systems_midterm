
import hashlib
import bisect


class ConsistentHashRing:
    def __init__(self, nodes, virtual_nodes=100):
        self.ring = []
        self.node_map = {}

        for node in nodes:
            for i in range(virtual_nodes):
                key = f"{node}:{i}"
                position = self._hash(key)

                self.ring.append(position)
                self.node_map[position] = node

        self.ring.sort()

    def _hash(self, value):
        return int(
            hashlib.sha256(value.encode()).hexdigest(),
            16
        )

    def get_nodes(self, chunk_hash, replicas=3):
        if not self.ring:
            raise ValueError("No storage nodes available")

        position = int(chunk_hash, 16)
        index = bisect.bisect_left(self.ring, position)

        selected = []
        visited = set()

        for i in range(len(self.ring)):
            ring_position = self.ring[
                (index + i) % len(self.ring)
            ]

            node = self.node_map[ring_position]

            if node not in visited:
                visited.add(node)
                selected.append(node)

            if len(selected) == replicas:
                break

        if len(selected) < replicas:
            raise ValueError("Not enough distinct storage nodes")

        return selected
