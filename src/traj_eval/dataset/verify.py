from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_TOOLCHAIN = "leanprover/lean4:v4.30.0"
EXPECTED_DIFFICULTIES = {"easy": 10, "medium": 10, "hard": 10}
REQUIRED_METADATA_FIELDS = {"id", "module", "source", "source_id", "difficulty", "imports"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def module_to_path(dataset_root: Path, module: str) -> Path:
    return dataset_root / Path(*module.split(".")).with_suffix(".lean")


def require_equal(name: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"ok {name}: {actual}")


def require_same_items(name: str, actual: list[str], expected: list[str]) -> None:
    actual_set = set(actual)
    expected_set = set(expected)
    if actual_set != expected_set or len(actual) != len(expected):
        missing = sorted(expected_set - actual_set)
        extra = sorted(actual_set - expected_set)
        raise AssertionError(f"{name}: missing={missing}, extra={extra}")
    print(f"ok {name}: {len(actual)}")


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"missing file: {path}")
    print(f"ok file: {path.relative_to(repo_root())}")


def load_metadata(path: Path) -> list[dict[str, Any]]:
    require_file(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise AssertionError("metadata.json must contain a JSON list")
    for index, record in enumerate(data):
        if not isinstance(record, dict):
            raise AssertionError(f"metadata record {index} must be an object")
    return data


def validate_metadata(records: list[dict[str, Any]], dataset_root: Path) -> list[str]:
    require_equal("metadata records", len(records), 30)

    ids: list[str] = []
    modules: list[str] = []
    difficulties: list[str] = []

    for index, record in enumerate(records):
        missing = REQUIRED_METADATA_FIELDS - record.keys()
        if missing:
            raise AssertionError(f"metadata record {index} missing fields: {sorted(missing)}")

        record_id = record["id"]
        module = record["module"]
        difficulty = record["difficulty"]
        imports = record["imports"]

        if not isinstance(record_id, str) or not record_id:
            raise AssertionError(f"metadata record {index} has invalid id")
        if not isinstance(module, str) or not module.startswith("MiniFATELeanCat."):
            raise AssertionError(f"metadata record {index} has invalid module: {module!r}")
        if not isinstance(difficulty, str) or difficulty not in EXPECTED_DIFFICULTIES:
            raise AssertionError(f"metadata record {index} has invalid difficulty: {difficulty!r}")
        if not isinstance(record["source"], str) or not record["source"]:
            raise AssertionError(f"metadata record {index} has invalid source")
        if not isinstance(record["source_id"], str) or not record["source_id"]:
            raise AssertionError(f"metadata record {index} has invalid source_id")
        if not isinstance(imports, list) or not all(isinstance(item, str) for item in imports):
            raise AssertionError(f"metadata record {index} has invalid imports")

        require_file(module_to_path(dataset_root, module))
        ids.append(record_id)
        modules.append(module)
        difficulties.append(difficulty)

    require_equal("metadata ids unique", len(set(ids)), len(ids))
    require_equal("metadata modules unique", len(set(modules)), len(modules))
    require_equal("difficulty counts", dict(Counter(difficulties)), EXPECTED_DIFFICULTIES)
    return modules


def benchmark_imports(path: Path) -> list[str]:
    require_file(path)
    modules: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            modules.append(stripped.removeprefix("import ").strip())
    return modules


def validate_lean_files(dataset_root: Path, modules: list[str]) -> None:
    benchmark_root = dataset_root / "MiniFATELeanCat"
    if not benchmark_root.is_dir():
        raise FileNotFoundError(f"missing benchmark root: {benchmark_root}")

    expected_paths = {module_to_path(dataset_root, module).resolve() for module in modules}
    actual_paths = {path.resolve() for path in benchmark_root.rglob("*.lean")}
    if actual_paths != expected_paths:
        missing = sorted(str(path.relative_to(dataset_root)) for path in expected_paths - actual_paths)
        extra = sorted(str(path.relative_to(dataset_root)) for path in actual_paths - expected_paths)
        raise AssertionError(f"MiniFATELeanCat files mismatch; missing={missing}, extra={extra}")
    print(f"ok MiniFATELeanCat lean files: {len(actual_paths)}")


def run_lake_build(dataset_root: Path) -> None:
    print("running lake build in dataset/Lean ...")
    subprocess.run(["lake", "build"], cwd=dataset_root, check=True)


def verify_public_lean_dataset(dataset_root: Path | None = None, run_lake: bool = False) -> None:
    root = dataset_root or repo_root() / "dataset" / "Lean"
    if not root.is_dir():
        raise FileNotFoundError(f"missing public Lean dataset root: {root}")

    require_file(root / "lean-toolchain")
    require_file(root / "lakefile.lean")
    require_file(root / "Benchmarks.lean")

    toolchain = (root / "lean-toolchain").read_text(encoding="utf-8").strip()
    require_equal("lean-toolchain", toolchain, EXPECTED_TOOLCHAIN)

    records = load_metadata(root / "metadata.json")
    modules = validate_metadata(records, root)
    validate_lean_files(root, modules)

    imports = benchmark_imports(root / "Benchmarks.lean")
    require_same_items("Benchmarks.lean imports", imports, modules)

    if run_lake:
        run_lake_build(root)

    print("public Lean dataset verification passed")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the public Lean benchmark dataset.")
    parser.add_argument(
        "--run-lake",
        action="store_true",
        help="also run `lake build` in dataset/Lean",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    verify_public_lean_dataset(run_lake=args.run_lake)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"dataset verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
