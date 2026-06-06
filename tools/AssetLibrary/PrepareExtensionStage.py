"""Prepare a clean Blender extension staging directory.

The public repository keeps source/runtime files under addon/, while generated
release artifacts live under _build/ and dist/. This script copies only the
files that belong in the extension zip into a staging folder.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "RSDWBaseBuilder.ExtensionStage.v1"

ROOT_FILES = (
    "__init__.py",
    "blender_manifest.toml",
)
README_FILE = "README.md"
RUNTIME_DIRS = (
    "data",
    "templates",
)
CURRENT_ASSET_DIRS = (
    "Building",
    "Crafting_Stations",
    "Decorations",
    "Farming",
    "Furniture",
    "Misc",
)
CATALOG_FILES = (
    "blender_assets.cats.txt",
)
EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "_build",
    "dist",
    "PipelineLogs",
    "tools",
    "_local",
    "CatalogData",
}
EXCLUDED_SUFFIXES = (
    ".blend1",
    ".pyc",
    ".pyo",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _copy_ignore(_dir: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(name)
        if name in EXCLUDED_DIRS or path.suffix.lower() in EXCLUDED_SUFFIXES:
            ignored.add(name)
    return ignored


def _copy_file(src: Path, dst: Path, copied: list[Path]) -> None:
    if not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    copied.append(dst)


def _copy_dir(src: Path, dst: Path, copied: list[Path]) -> None:
    if not src.is_dir():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_copy_ignore)
    copied.extend(path for path in dst.rglob("*") if path.is_file())


def prepare_stage(
    *,
    source_root: Path,
    stage_dir: Path,
    build_root: Path,
    include_current_assets: bool,
    clean: bool,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    stage_dir = stage_dir.resolve()
    build_root = build_root.resolve()

    if not (source_root / "blender_manifest.toml").is_file():
        raise SystemExit(f"source root does not look like the extension repo: {source_root}")

    if clean and stage_dir.exists():
        if stage_dir == source_root or not _is_relative_to(stage_dir, build_root):
            raise SystemExit(f"refusing to clean stage outside build root: {stage_dir}")
        shutil.rmtree(stage_dir)

    stage_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    skipped_missing: list[str] = []

    for rel in ROOT_FILES:
        src = source_root / rel
        if src.is_file():
            _copy_file(src, stage_dir / rel, copied)
        else:
            skipped_missing.append(rel)

    readme_src = source_root / README_FILE
    if not readme_src.is_file():
        readme_src = _repo_root() / README_FILE
    if readme_src.is_file():
        _copy_file(readme_src, stage_dir / README_FILE, copied)
    else:
        skipped_missing.append(README_FILE)

    for rel in RUNTIME_DIRS:
        src = source_root / rel
        if src.is_dir():
            _copy_dir(src, stage_dir / rel, copied)
        else:
            skipped_missing.append(rel)

    for rel in CATALOG_FILES:
        src = source_root / rel
        if src.is_file():
            _copy_file(src, stage_dir / rel, copied)

    if include_current_assets:
        for rel in CURRENT_ASSET_DIRS:
            src = source_root / rel
            if src.is_dir():
                _copy_dir(src, stage_dir / rel, copied)
            else:
                skipped_missing.append(rel)

    total_bytes = sum(path.stat().st_size for path in copied if path.is_file())
    return {
        "schema": SCHEMA,
        "generated_at_utc": _now_iso(),
        "source_root": str(source_root),
        "stage_dir": str(stage_dir),
        "include_current_assets": include_current_assets,
        "clean": clean,
        "copied_files": len(copied),
        "copied_bytes": total_bytes,
        "copied_mb": round(total_bytes / (1024 * 1024), 3),
        "skipped_missing": skipped_missing,
    }


def main(argv: list[str] | None = None) -> int:
    repo = _repo_root()
    parser = argparse.ArgumentParser(description="Prepare a clean Blender extension stage.")
    parser.add_argument("--source-root", type=Path, default=repo / "addon")
    parser.add_argument("--build-root", type=Path, default=repo / "_build")
    parser.add_argument("--stage-dir", type=Path, default=None)
    parser.add_argument("--include-current-assets", action="store_true")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--out-manifest", type=Path, default=None)
    args = parser.parse_args(argv)

    build_root = args.build_root
    stage_dir = args.stage_dir or (build_root / "extension")
    report = prepare_stage(
        source_root=args.source_root,
        stage_dir=stage_dir,
        build_root=build_root,
        include_current_assets=args.include_current_assets,
        clean=args.clean,
    )

    out_manifest = args.out_manifest or (build_root / "extension_stage_manifest.json")
    out_manifest.parent.mkdir(parents=True, exist_ok=True)
    out_manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**report, "manifest": str(out_manifest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
