import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_COUNTS = {
    "applicants.csv": 3000,
    "quotes.csv": 4000,
    "policies.csv": 2000,
    "renewals.csv": 1200,
}


def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def row_count(path):
    with path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        return max(sum(1 for _ in csv.reader(file)) - 1, 0)


def generate_dataset(output_dir, seed, scale):
    command = [
        sys.executable,
        "-m",
        "insurance_workflow.generator",
        "--output",
        str(output_dir),
        "--seed",
        str(seed),
        "--scale",
        str(scale),
    ]

    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
    )


def collect_manifest(directory):
    manifest_path = directory / "source_manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Missing source manifest: {manifest_path}"
        )

    with manifest_path.open(
        "r", encoding="utf-8"
    ) as file:
        manifest = json.load(file)

    # The generator's manifest must contain file paths,
    # SHA-256 hashes, and byte sizes.
    if not isinstance(manifest.get("files"), list):
        raise ValueError(
            "Unexpected source_manifest.json format."
        )

    results = {}

    for entry in manifest["files"]:
        relative_path = entry.get("path")
        expected_hash = entry.get("sha256")
        expected_bytes = entry.get("bytes")

        if not relative_path or not expected_hash:
            raise ValueError(
                f"Invalid manifest entry: {entry}"
            )

        file_path = directory / relative_path

        if not file_path.is_file():
            raise FileNotFoundError(
                f"Manifest file not found: {file_path}"
            )

        actual_hash = sha256_file(file_path)
        actual_bytes = file_path.stat().st_size

        if actual_hash != expected_hash:
            raise ValueError(
                f"Manifest checksum mismatch: {relative_path}"
            )

        if (
            expected_bytes is not None
            and actual_bytes != expected_bytes
        ):
            raise ValueError(
                f"Manifest size mismatch: {relative_path}"
            )

        results[relative_path] = {
            "sha256": actual_hash,
            "bytes": actual_bytes,
        }

    return results


def validate_dataset(directory):
    command = [
        sys.executable,
        "-m",
        "insurance_workflow.validator",
        "--data",
        str(directory),
    ]

    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Verify deterministic insurance dataset generation."
        )
    )

    parser.add_argument("--seed", type=int, default=20261022)
    parser.add_argument("--scale", type=int, default=1)

    args = parser.parse_args()

    if args.scale <= 0:
        parser.error("--scale must be greater than zero.")

    with tempfile.TemporaryDirectory(
        prefix="insurance_reproducibility_"
    ) as temporary_directory:

        temporary_root = Path(temporary_directory)
        run1 = temporary_root / "run1"
        run2 = temporary_root / "run2"

        print("Generating dataset: run 1")
        generate_dataset(run1, args.seed, args.scale)

        print("\nGenerating dataset: run 2")
        generate_dataset(run2, args.seed, args.scale)

        print("\nChecking required record counts")

        for filename, expected_count in REQUIRED_COUNTS.items():
            file1 = run1 / filename
            file2 = run2 / filename

            if not file1.is_file() or not file2.is_file():
                raise FileNotFoundError(
                    f"Missing required dataset: {filename}"
                )

            count1 = row_count(file1)
            count2 = row_count(file2)

            print(
                f"{filename}: run1={count1}, "
                f"run2={count2}, expected={expected_count}"
            )

            if count1 != count2:
                raise AssertionError(
                    f"Row counts differ for {filename}"
                )

            if count1 != expected_count * args.scale:
                raise AssertionError(
                    f"Unexpected row count for {filename}"
                )

        print("\nChecking manifest checksums")

        manifest1 = collect_manifest(run1)
        manifest2 = collect_manifest(run2)

        if manifest1 != manifest2:
            raise AssertionError(
                "Generated files differ between runs."
            )

        print(
            f"PASS: {len(manifest1)} manifested files "
            "have identical SHA-256 checksums and sizes."
        )

        print("\nValidating run 1")
        validate_dataset(run1)

        print("\nValidating run 2")
        validate_dataset(run2)

        print("\nPASS: Reproducibility verification completed.")


if __name__ == "__main__":
    try:
        main()
    except (
        AssertionError,
        FileNotFoundError,
        ValueError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"\nFAIL: {error}", file=sys.stderr)
        sys.exit(1)
