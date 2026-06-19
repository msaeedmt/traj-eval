from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXPECTED_TOOLCHAIN = "leanprover/lean4:v4.30.0"
EXPECTED_COUNTS = {
    "FATEH": 100,
    "FATEM": 150,
    "FATEX": 100,
    "LeanCat/CAT_statement": 100,
}
EXPECTED_LEANCAT_RECORDS = 100


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def count_lean_files(path: Path) -> int:
    if not path.is_dir():
        raise FileNotFoundError(f"missing directory: {path}")
    return sum(1 for child in path.iterdir() if child.is_file() and child.suffix == ".lean")


def count_jsonl_records(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError(f"missing file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def require_equal(name: str, actual: int | str, expected: int | str) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"ok {name}: {actual}")


def run_lake_build(dataset_root: Path) -> None:
    print("running lake build in dataset/ ...")
    subprocess.run(["lake", "build"], cwd=dataset_root, check=True)


def main() -> int:
    dataset_root = repo_root() / "dataset"
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"missing dataset root: {dataset_root}")

    toolchain = (dataset_root / "lean-toolchain").read_text(encoding="utf-8").strip()
    require_equal("lean-toolchain", toolchain, EXPECTED_TOOLCHAIN)

    for relative, expected in EXPECTED_COUNTS.items():
        require_equal(relative, count_lean_files(dataset_root / relative), expected)

    records = count_jsonl_records(dataset_root / "LeanCat" / "records.jsonl")
    require_equal("LeanCat records", records, EXPECTED_LEANCAT_RECORDS)

    run_lake_build(dataset_root)
    print("dataset verification passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"dataset verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
