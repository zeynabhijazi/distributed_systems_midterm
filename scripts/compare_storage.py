
import csv
from pathlib import Path

RESULTS_DIR = Path("benchmark-results")

WORKLOADS = {
    "Small Files": RESULTS_DIR / "benchmark-small.csv",
    "Large Files": RESULTS_DIR / "benchmark-large.csv",
}

MIB = 1024 * 1024


def read_workload(path):
    if not path.exists():
        print(f"Missing benchmark file: {path}")
        return None

    files = {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            if row["operation"] != "upload":
                continue

            if row["success"].lower() != "true":
                continue

            files[row["file"]] = int(row["size_bytes"])

    return list(files.values())


def calculate_comparison(sizes):
    logical_bytes = sum(sizes)

    # Replication: three complete copies.
    replication_storage = logical_bytes * 3

    # Reed-Solomon 4+2: six shards,
    # each approximately 1/4 of original size.
    # Include block-padding overhead.
    erasure_storage = sum(
        ((size + 3) // 4) * 6
        for size in sizes
    )

    # Model repair of one lost replica/shard
    # per file or chunk.
    #
    # Replication: read one complete copy,
    # then write one complete replacement.
    replication_repair = logical_bytes * 2

    # Erasure: read four data-sized shards,
    # then write one replacement shard.
    erasure_repair = sum(
        ((size + 3) // 4) * 5
        for size in sizes
    )

    return {
        "logical_mib": logical_bytes / MIB,
        "replication_storage_mib": replication_storage / MIB,
        "erasure_storage_mib": erasure_storage / MIB,
        "replication_repair_mib": replication_repair / MIB,
        "erasure_repair_mib": erasure_repair / MIB,
        "storage_saving_percent": (
            100 * (
                1 - erasure_storage / replication_storage
            )
            if replication_storage else 0
        ),
    }


def main():
    RESULTS_DIR.mkdir(exist_ok=True)

    output_path = RESULTS_DIR / "storage-comparison.csv"

    results = []

    for workload, path in WORKLOADS.items():
        sizes = read_workload(path)

        if sizes is None:
            continue

        if not sizes:
            print(f"No successful uploads in {path}")
            continue

        result = calculate_comparison(sizes)

        print(f"\n{'=' * 50}")
        print(workload)
        print(f"{'=' * 50}")
        print("Files:", len(sizes))

        print(
            f"Logical data: "
            f"{result['logical_mib']:.2f} MiB"
        )

        print(
            f"Replication storage: "
            f"{result['replication_storage_mib']:.2f} MiB"
        )

        print(
            f"Erasure storage: "
            f"{result['erasure_storage_mib']:.2f} MiB"
        )

        print(
            f"Storage saving: "
            f"{result['storage_saving_percent']:.2f}%"
        )

        print("\nModeled repair traffic:")

        print(
            f"Replication: "
            f"{result['replication_repair_mib']:.2f} MiB"
        )

        print(
            f"Erasure coding: "
            f"{result['erasure_repair_mib']:.2f} MiB"
        )

        results.append({
            "workload": workload,
            "file_count": len(sizes),
            **{
                key: round(value, 3)
                for key, value in result.items()
            },
        })

    if not results:
        print("\nNo benchmark results available.")
        return

    with open(
        output_path,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=results[0].keys(),
        )

        writer.writeheader()
        writer.writerows(results)

    print(f"\nComparison saved to: {output_path}")
    print("SUCCESS: Comparison completed")


if __name__ == "__main__":
    main()
