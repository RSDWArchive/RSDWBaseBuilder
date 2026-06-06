"""
Build a class_name -> mesh-stem mapping for Dragonwilds base-building actors.

Each Blueprint actor (e.g. BP_BaseBuilding_Lodestone) wraps exactly one
StaticMesh (SM_*) or SkeletalMesh (SK_*) component. The CUE4Parse JSON
dumps under RSDWArchive include those refs. This script walks all of them
and emits:

  tools/ModelData/BPMap.json  -- { "BP_Foo_C": "SM_Foo_01", ... }

The class_name field in our building JSON exports
(e.g. "BlueprintGeneratedClass /Game/.../BP_Foo.BP_Foo_C") can be matched
against this map to find the right asset in the Blender library.

Usage:
  python tools/ModelData/BuildBPMap.py
  python tools/ModelData/BuildBPMap.py --validate building_json_examples/building
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT = REPO / "tools" / "ModelData" / "BPMap.json"

OBJECTPATH_RX = re.compile(r'"ObjectPath"\s*:\s*"([^"]+)"')
MESH_LEAF_RX = re.compile(r"/(SM_[A-Za-z0-9_]+|SK_[A-Za-z0-9_]+)\.\d+$")


def _latest_archive_json_root() -> Path:
    root = Path(r"E:/Github/RSDWArchive")
    versions = []
    if root.is_dir():
        for child in root.iterdir():
            parts = child.name.split(".")
            if child.is_dir() and parts and all(part.isdigit() for part in parts):
                versions.append(child)
    if versions:
        versions.sort(key=lambda path: tuple(int(part) for part in path.name.split(".")))
        return versions[-1] / "json"
    return Path(r"E:/Github/RSDWArchive/0.11.1.4/json")


def _scan_bp(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    # Grab the first ObjectPath that looks like an SM_ or SK_ asset under /Art/.
    for m in OBJECTPATH_RX.finditer(text):
        v = m.group(1)
        if "/Art/" not in v:
            continue
        leaf = MESH_LEAF_RX.search(v)
        if leaf:
            return leaf.group(1)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-root", type=Path, default=_latest_archive_json_root())
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--validate", type=Path, default=None,
                    help="Optional folder of building JSON exports to report coverage against.")
    args = ap.parse_args()

    if not args.json_root.is_dir():
        print(f"json root not found: {args.json_root}", file=sys.stderr)
        return 2

    print(f"Scanning {args.json_root} for BP_*.json...")
    mapping: dict[str, str] = {}
    skipped = 0
    bp_total = 0
    for dp, _dn, fns in os.walk(args.json_root):
        for fn in fns:
            if not (fn.startswith("BP_") and fn.endswith(".json")):
                continue
            bp_total += 1
            mesh = _scan_bp(Path(dp) / fn)
            if not mesh:
                skipped += 1
                continue
            stem = fn[:-5]  # strip .json
            # The class_name in building JSON is `<stem>_C`; record under that.
            mapping[stem + "_C"] = mesh

    print(f"  scanned {bp_total} BP_*.json, mapped {len(mapping)}, skipped {skipped}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "json_root": str(args.json_root),
                "count": len(mapping),
                "mapping": mapping,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"  wrote {args.out}")

    if args.validate and args.validate.is_dir():
        from collections import Counter
        all_classes: Counter[str] = Counter()
        for f in sorted(args.validate.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for pc in d.get("pieces", []):
                cn = pc.get("class_name", "")
                short = cn.rsplit("/", 1)[-1].rsplit(".", 1)[-1]
                if short:
                    all_classes[short] += 1

        unmapped = [c for c in all_classes if c not in mapping]
        mapped = len(all_classes) - len(unmapped)
        print()
        print(f"Validation against {args.validate}:")
        print(f"  distinct classes used: {len(all_classes)}")
        print(f"  mapped:                 {mapped}")
        print(f"  unmapped:               {len(unmapped)}")
        if unmapped:
            print("  unmapped sample:")
            for c in sorted(unmapped)[:30]:
                print(f"    {c}  ({all_classes[c]} pieces)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
