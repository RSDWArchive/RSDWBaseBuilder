"""
Generate `blender_assets.cats.txt` for the asset library based on the catalog
paths used by the per-piece worker. Reads SM_Data.json, runs each entry's
path through tools/AssetLibrary/catalog.categorize, expands every parent
level, and emits a deterministic UUIDv5 row for each unique path.

Format:
    VERSION 1
    <UUID>:<catalog/path>:<simple name>

The driver writes to <library_root>/blender_assets.cats.txt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import categorize, catalog_uuid, expand_catalog_paths  # noqa: E402


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-file", type=Path,
                   default=_repo_root() / "tools" / "ModelData" / "SM_Data.json")
    p.add_argument("--library-root", type=Path,
                   default=_repo_root() / "_build" / "extension")
    p.add_argument("--out", type=Path, default=None,
                   help="Override output path (default: <library_root>/blender_assets.cats.txt)")
    p.add_argument("--target-file", type=Path, default=None,
                   help="Catalog-shaped targets from BuildCatalogAssetTargets.py.")
    args = p.parse_args()

    paths: set[str] = set()
    if args.target_file is not None:
        doc = json.loads(args.target_file.read_text(encoding="utf-8"))
        targets = doc.get("targets", [])
        if not targets:
            print("No targets in target file.", file=sys.stderr)
            return 1
        catalog_paths = [target.get("catalog_path", "Misc") for target in targets]
    else:
        inv = json.loads(args.data_file.read_text(encoding="utf-8"))
        entries = inv.get("entries", [])
        if not entries:
            print("No entries in data file.", file=sys.stderr)
            return 1
        catalog_paths = [categorize(e["path"]) for e in entries]

    for cat in catalog_paths:
        for level in expand_catalog_paths(cat):
            paths.add(level)

    out_path = args.out or (args.library_root / "blender_assets.cats.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# This is an Asset Catalog Definition file for Blender.",
        "#",
        "# Empty lines and lines starting with # will be ignored.",
        "# The first non-ignored line should be the version indicator.",
        '# Other lines are of the format "UUID:catalog/path:simple name"',
        "",
        "VERSION 1",
        "",
    ]
    for path in sorted(paths):
        uid = str(catalog_uuid(path))
        simple = path.split("/")[-1]
        lines.append(f"{uid}:{path}:{simple}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(paths)} catalog entries -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
