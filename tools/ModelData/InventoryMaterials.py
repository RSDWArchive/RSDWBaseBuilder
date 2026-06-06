"""
Inventory unique material JSONs referenced by model inventory or asset targets.

  tools/ModelData/MaterialInventory.json
    {
      "unique_count": N,
      "materials": [
        {
          "key": "<rel_path_to_mi_json>",
          "stem": "MI_BB_Tier1_Wood",
          "ref_count": 73,
          "sample_meshes": ["...", "...", "..."]
        },
        ...
      ],
      "meshes_with_no_material": [...],
      "meshes_with_multi_material": {...}
    }
  tools/ModelData/MaterialInventory.report.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_SM_DATA = REPO / "tools" / "ModelData" / "SM_Data.json"
DEFAULT_SK_DATA = REPO / "tools" / "ModelData" / "SK_Data.json"
DEFAULT_TARGET_FILE = REPO / "tools" / "AssetLibrary" / "asset_library_targets.json"
DEFAULT_OUT_DIR = REPO / "tools" / "ModelData"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _entry_key(entry: dict[str, Any]) -> str:
    return str(entry.get("path") or entry.get("name") or "")


def _entries_from_model_data(paths: list[Path]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        doc = _load_json(path)
        for entry in doc.get("entries") or []:
            key = _entry_key(entry)
            if key and key not in seen:
                seen.add(key)
                out.append(entry)
    return out


def _entries_from_targets(path: Path) -> list[dict[str, Any]]:
    doc = _load_json(path)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in doc.get("targets") or []:
        candidates = []
        if isinstance(target.get("source_entry"), dict):
            candidates.append(target["source_entry"])
        for component in target.get("components") or []:
            if isinstance(component, dict) and isinstance(component.get("source_entry"), dict):
                candidates.append(component["source_entry"])
        for entry in candidates:
            key = _entry_key(entry)
            if key and key not in seen:
                seen.add(key)
                out.append(entry)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sm-data", type=Path, default=None,
                    help="Legacy alias for --model-data. Defaults to SM/SK data when no target file is supplied.")
    ap.add_argument("--model-data", type=Path, action="append", default=None,
                    help="Model inventory JSON. Repeatable.")
    ap.add_argument("--target-file", type=Path, default=None,
                    help="Unified asset-library targets; inventories only models used by planned assets.")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    if args.target_file is not None:
        entries = _entries_from_targets(args.target_file)
        source = str(args.target_file)
    else:
        model_data = args.model_data or []
        if args.sm_data is not None:
            model_data.insert(0, args.sm_data)
        if not model_data:
            model_data = [DEFAULT_SM_DATA, DEFAULT_SK_DATA]
        entries = _entries_from_model_data(model_data)
        source = ", ".join(str(path) for path in model_data)

    refs: dict[str, list[str]] = defaultdict(list)
    no_mat: list[str] = []
    multi_mat: dict[str, int] = {}

    for e in entries:
        mat_paths = (e.get("Materials", {}) or {}).get("material_json_paths") or []
        if not mat_paths:
            no_mat.append(e["path"])
            continue
        if len(mat_paths) > 1:
            multi_mat[e["path"]] = len(mat_paths)
        for m in mat_paths:
            refs[m].append(e["path"])

    materials = [
        {
            "key": k,
            "stem": Path(k).stem,
            "ref_count": len(meshes),
            "sample_meshes": meshes[:3],
        }
        for k, meshes in sorted(refs.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]

    out = {
        "manifest_schema": "RSDWBaseBuilder.MaterialInventory.v1",
        "source": source,
        "total_meshes": len(entries),
        "meshes_with_material": len(entries) - len(no_mat),
        "unique_count": len(materials),
        "materials": materials,
        "meshes_with_no_material": no_mat,
        "meshes_with_multi_material": multi_mat,
    }

    out_json = args.out_dir / "MaterialInventory.json"
    out_json.write_text(json.dumps(out, indent=2), encoding="utf-8")

    lines = [
        f"Total meshes:               {len(entries)}",
        f"  with >=1 material:        {len(entries) - len(no_mat)}",
        f"  with no material JSON:    {len(no_mat)}",
        f"  with >1 material slots:   {len(multi_mat)}",
        f"Unique material JSONs:      {len(materials)}",
        "",
        "Top 30 most-referenced materials:",
    ]
    for m in materials[:30]:
        lines.append(f"  {m['ref_count']:5d}  {m['stem']:50s}  {m['key']}")
    lines.append("")
    lines.append("Bottom 10 least-referenced:")
    for m in materials[-10:]:
        lines.append(f"  {m['ref_count']:5d}  {m['stem']:50s}  {m['key']}")

    out_txt = args.out_dir / "MaterialInventory.report.txt"
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Unique materials: {len(materials)} across {len(entries)} meshes")
    print(f"  no_material: {len(no_mat)}, multi_material: {len(multi_mat)}")
    print(f"Wrote {out_json.name} and {out_txt.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
