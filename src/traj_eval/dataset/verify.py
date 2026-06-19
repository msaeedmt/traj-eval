from __future__ import annotations

import json
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
EXPECTED_FATE_DIFFICULTY = {
    "FATEH": "Hard (FATE-H)",
    "FATEM": "Medium (FATE-M)",
    "FATEX": "Expert (FATE-X)",
}
EXPECTED_LEANCAT_METADATA = 100


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def count_lean_files(path: Path) -> int:
    if not path.is_dir():
        raise FileNotFoundError(f"missing directory: {path}")
    return sum(1 for child in path.iterdir() if child.is_file() and child.suffix == ".lean")


def count_json_entries(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError(f"missing file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return len(json.load(handle))


def read_json(path: Path) -> object:
    if not path.is_file():
        raise FileNotFoundError(f"missing file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def count_labeled_lean_files(path: Path, label: str) -> int:
    if not path.is_dir():
        raise FileNotFoundError(f"missing directory: {path}")
    expected = f"Difficulty: {label}"
    return sum(
        1
        for child in path.iterdir()
        if child.is_file() and child.suffix == ".lean" and expected in child.read_text(encoding="utf-8")
    )


def count_labeled_leancat_files(dataset_root: Path) -> int:
    metadata = read_json(dataset_root / "LeanCat" / "metadata.json")
    if not isinstance(metadata, dict):
        raise TypeError("LeanCat metadata must be a JSON object")

    labeled = 0
    for problem_id, entry in metadata.items():
        if not isinstance(entry, dict) or "level" not in entry:
            raise KeyError(f"LeanCat metadata entry missing level: {problem_id}")
        lean_file = dataset_root / "LeanCat" / "CAT_statement" / f"S_{problem_id}.lean"
        if f"Difficulty: {entry['level']}" in lean_file.read_text(encoding="utf-8"):
            labeled += 1
    return labeled


def require_equal(name: str, actual: int | str, expected: int | str) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"ok {name}: {actual}")


def run_lake_build(dataset_root: Path) -> None:
    print("running lake build in dataset/ ...")
    subprocess.run(["lake", "build"], cwd=dataset_root, check=True)


def main() -> int:
    dataset_root = repo_root() / "dataset" / "Lean"
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"missing dataset root: {dataset_root}")

    toolchain = (dataset_root / "lean-toolchain").read_text(encoding="utf-8").strip()
    require_equal("lean-toolchain", toolchain, EXPECTED_TOOLCHAIN)

    for relative, expected in EXPECTED_COUNTS.items():
        require_equal(relative, count_lean_files(dataset_root / relative), expected)

    metadata = count_json_entries(dataset_root / "LeanCat" / "metadata.json")
    require_equal("LeanCat metadata entries", metadata, EXPECTED_LEANCAT_METADATA)
    require_equal("LeanCat difficulty labels", count_labeled_leancat_files(dataset_root), EXPECTED_LEANCAT_METADATA)

    for relative, label in EXPECTED_FATE_DIFFICULTY.items():
        require_equal(
            f"{relative} difficulty labels",
            count_labeled_lean_files(dataset_root / relative, label),
            EXPECTED_COUNTS[relative],
        )

    run_lake_build(dataset_root)
    print("dataset verification passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"dataset verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
