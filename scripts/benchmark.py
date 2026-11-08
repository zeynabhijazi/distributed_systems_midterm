
import argparse
import csv
import hashlib
import os
import random
import tempfile
import time
from pathlib import Path

import httpx


BASE_URL = "http://localhost:8005"
HEADERS = {"X-API-Key": "exam-demo-key"}
RESULT_DIR = Path("benchmark-results")


def generate_file(path, size):
    hasher = hashlib.sha256()

    with open(path, "wb") as f:
        remaining = size

        while remaining > 0:
            data = os.urandom(min(1024 * 1024, remaining))
            f.write(data)
            hasher.update(data)
            remaining -= len(data)

    return hasher.hexdigest()


def check_response(response):
    if not response.is_success:
        raise RuntimeError(
            f"HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )


def benchmark(count, min_kb, max_kb, bucket):
    RESULT_DIR.mkdir(exist_ok=True)

    records = []
    uploaded = []
    errors = []

    with httpx.Client(timeout=600.0) as client:
        # Create a dedicated benchmark bucket.
        response = client.post(
            f"{BASE_URL}/buckets/{bucket}",
            headers=HEADERS,
        )

        if response.status_code not in (200, 201, 409):
            check_response(response)

        print(f"Benchmark bucket: {bucket}")
        print(f"Files to test: {count}")
        print(f"File size range: {min_kb}-{max_kb} KB")

        # ----------------------------
        # UPLOAD TEST
        # ----------------------------
        print("\nStarting uploads...")

        for index in range(count):
            size = random.randint(min_kb, max_kb) * 1024
            key = f"benchmark-{index:05d}.bin"

            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / key
                original_hash = generate_file(path, size)

                start = time.perf_counter()

                try:
                    with open(path, "rb") as f:
                        response = client.post(
                            f"{BASE_URL}/objects/{bucket}/{key}",
                            headers=HEADERS,
                            files={"file": (key, f)},
                        )

                    check_response(response)

                    duration = time.perf_counter() - start

                    uploaded.append({
                        "key": key,
                        "size": size,
                        "hash": original_hash,
                    })

                    records.append({
                        "operation": "upload",
                        "file": key,
                        "size_bytes": size,
                        "duration_seconds": round(duration, 4),
                        "success": True,
                    })

                except Exception as exc:
                    errors.append(f"Upload {key}: {exc}")
                    print(f"FAILED upload: {key}: {exc}")

            if (index + 1) % 100 == 0 or index + 1 == count:
                print(f"Uploaded {index + 1}/{count}")

        # ----------------------------
        # DOWNLOAD TEST
        # ----------------------------
        print("\nStarting downloads...")

        for index, item in enumerate(uploaded, start=1):
            start = time.perf_counter()

            try:
                hasher = hashlib.sha256()
                downloaded_size = 0

                with client.stream(
                    "GET",
                    f"{BASE_URL}/objects/{bucket}/{item['key']}",
                    headers=HEADERS,
                ) as response:
                    response.raise_for_status()

                    for data in response.iter_bytes(
                        chunk_size=1024 * 1024
                    ):
                        hasher.update(data)
                        downloaded_size += len(data)

                duration = time.perf_counter() - start

                valid = (
                    hasher.hexdigest() == item["hash"]
                    and downloaded_size == item["size"]
                )

                records.append({
                    "operation": "download",
                    "file": item["key"],
                    "size_bytes": downloaded_size,
                    "duration_seconds": round(duration, 4),
                    "success": valid,
                })

                if not valid:
                    errors.append(
                        f"Integrity mismatch: {item['key']}"
                    )

            except Exception as exc:
                errors.append(
                    f"Download {item['key']}: {exc}"
                )
                print(f"FAILED download: {item['key']}: {exc}")

            if index % 100 == 0 or index == len(uploaded):
                print(f"Downloaded {index}/{len(uploaded)}")

    # ----------------------------
    # SAVE RESULTS
    # ----------------------------
    result_path = RESULT_DIR / f"{bucket}.csv"

    with open(result_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "operation",
                "file",
                "size_bytes",
                "duration_seconds",
                "success",
            ],
        )
        writer.writeheader()
        writer.writerows(records)

    print("\n========== BENCHMARK RESULTS ==========")

    for operation in ("upload", "download"):
        matching = [
            r for r in records
            if r["operation"] == operation
        ]

        successful = [
            r for r in matching if r["success"]
        ]

        total_bytes = sum(
            r["size_bytes"] for r in successful
        )

        total_time = sum(
            r["duration_seconds"] for r in matching
        )

        throughput = (
            (total_bytes / 1024 / 1024) / total_time
            if total_time > 0 else 0
        )

        print(f"\n{operation.upper()}")
        print(f"Successful files: {len(successful)}/{count}")
        print(f"Total time: {total_time:.2f} seconds")
        print(f"Throughput: {throughput:.2f} MiB/s")

    print(f"\nErrors: {len(errors)}")
    print(f"CSV results: {result_path}")

    for error in errors[:10]:
        print("ERROR:", error)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--min-kb", type=int, default=1)
    parser.add_argument("--max-kb", type=int, default=50)
    parser.add_argument(
        "--bucket",
        default="benchmark-small"
    )

    args = parser.parse_args()

    if (
        args.count < 1
        or args.min_kb < 1
        or args.max_kb < args.min_kb
    ):
        parser.error("Invalid count or size range")

    benchmark(
        args.count,
        args.min_kb,
        args.max_kb,
        args.bucket,
    )
