from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import bpy


REPO = Path(__file__).resolve().parents[2]
DEFAULT_TARGET_FILE = REPO / "tools" / "AssetLibrary" / "catalog_asset_targets.json"
DEFAULT_LIBRARY_ROOT = REPO / "_build" / "extension"
DEFAULT_OUT = REPO / "tools" / "AssetLibrary" / "catalog_asset_metadata_report.json"


def _argv_after_double_dash() -> list[str]:
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


def _category_to_subdir(catalog_path: str) -> Path:
    return Path(*["_".join(part.split()) for part in catalog_path.split("/")])


def _blend_path(library_root: Path, target: dict[str, Any]) -> Path:
    return library_root / _category_to_subdir(target.get("catalog_path") or "") / f"{target.get('asset_stem')}.blend"


def _asset_objects() -> list[bpy.types.Object]:
    return [obj for obj in bpy.data.objects if obj.asset_data is not None]


def _obj_prop(obj: bpy.types.Object, key: str) -> Any:
    return obj.get(key)


def _identity_transform_errors(obj: bpy.types.Object, *, eps: float = 1e-5) -> list[str]:
    errors: list[str] = []
    if obj.parent is not None:
        errors.append(f"asset object has parent {obj.parent.name!r}")
    if obj.type != "MESH":
        errors.append(f"asset object type {obj.type!r} != 'MESH'")
    for row in range(4):
        for col in range(4):
            expected = 1.0 if row == col else 0.0
            if abs(float(obj.matrix_world[row][col]) - expected) > eps:
                errors.append("asset object matrix_world is not identity")
                return errors
    return errors


def _validate_target(library_root: Path, target: dict[str, Any]) -> dict[str, Any]:
    blend_path = _blend_path(library_root, target)
    base = {
        "target_id": target.get("target_id"),
        "asset_stem": target.get("asset_stem"),
        "blend": str(blend_path),
    }
    if not blend_path.is_file():
        return {**base, "ok": False, "errors": ["missing blend file"]}

    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    asset_objects = _asset_objects()
    if not asset_objects:
        return {**base, "ok": False, "errors": ["no asset-marked object"]}

    obj = next((candidate for candidate in asset_objects if candidate.name == target.get("asset_stem")), asset_objects[0])
    errors: list[str] = []

    expected_kind = str(target.get("asset_kind") or "building_piece")
    actual_kind = str(_obj_prop(obj, "rsdw_asset_kind") or "")
    if actual_kind != expected_kind:
        errors.append(f"rsdw_asset_kind {actual_kind!r} != {expected_kind!r}")

    common_props = [
        ("rsdw_catalog_asset_stem", "asset_stem"),
    ]
    if target.get("display_name"):
        common_props.append(("rsdw_display_name", "display_name"))
    if target.get("preview_mode"):
        common_props.append(("rsdw_preview_mode", "preview_mode"))
    if target.get("icon_source"):
        common_props.append(("rsdw_icon_source", "icon_source"))
    if expected_kind in {"bp", "building_piece"}:
        common_props.append(("rsdw_bp_class", "bp_class"))
    if expected_kind == "bp":
        common_props.extend([
            ("rsdw_runtime_path", "runtime_path"),
            ("rsdw_bp_json_relative", "bp_json_relative"),
            ("rsdw_assembly_status", "assembly_status"),
        ])
        if _obj_prop(obj, "rsdw_bp_root_normalized") is not True:
            errors.append("rsdw_bp_root_normalized is not True")
        if str(_obj_prop(obj, "rsdw_bp_root_normalization") or "") != "baked_mesh_v1":
            errors.append("rsdw_bp_root_normalization is not 'baked_mesh_v1'")
        errors.extend(_identity_transform_errors(obj))
    if expected_kind == "item":
        common_props.extend([
            ("rsdw_item_json_relative", "item_json_relative"),
            ("rsdw_item_type", "item_type"),
            ("rsdw_item_name", "item_name"),
            ("rsdw_primary_model_ref", "primary_model_ref"),
        ])

    if expected_kind == "building_piece":
        expected_index = int(target.get("piece_data_index"))
        try:
            actual_index = int(_obj_prop(obj, "rsdw_piece_data_index"))
        except (TypeError, ValueError):
            actual_index = None
        if actual_index != expected_index:
            errors.append(f"piece_data_index {actual_index!r} != {expected_index!r}")
        common_props.append(("rsdw_piece_data_name", "piece_data_name"))

    for prop_name, target_key in common_props:
        if target.get(target_key) is None:
            continue
        actual = str(_obj_prop(obj, prop_name) or "")
        expected = str(target.get(target_key) or "")
        if actual != expected:
            errors.append(f"{prop_name} {actual!r} != {expected!r}")

    expected_icon_path = str(target.get("icon_path") or "")
    actual_icon_path = str(_obj_prop(obj, "rsdw_icon_path") or "")
    if expected_icon_path:
        if actual_icon_path != expected_icon_path:
            errors.append(f"rsdw_icon_path {actual_icon_path!r} != {expected_icon_path!r}")
    elif actual_icon_path:
        errors.append(f"unexpected rsdw_icon_path {actual_icon_path!r}")

    return {
        **base,
        "ok": not errors,
        "errors": errors,
        "asset_object": obj.name,
        "asset_kind": expected_kind,
        "asset_object_count": len(asset_objects),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify catalog asset .blend metadata.")
    parser.add_argument("--target-file", type=Path, default=DEFAULT_TARGET_FILE)
    parser.add_argument("--library-root", type=Path, default=DEFAULT_LIBRARY_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only-list", type=Path, default=None,
                        help="Optional newline-delimited target_id/source path list to verify.")
    parser.add_argument("--limit", type=int, default=0, help="Validate only the first N targets. 0 validates all.")
    args = parser.parse_args(argv if argv is not None else _argv_after_double_dash())

    target_doc = json.loads(args.target_file.read_text(encoding="utf-8"))
    targets = list(target_doc.get("targets") or [])
    if args.only_list is not None:
        wanted = set()
        for line in args.only_list.read_text(encoding="utf-8").splitlines():
            cleaned = line.strip().lstrip("\ufeff")
            if cleaned and not cleaned.startswith("#"):
                wanted.add(cleaned)
        targets = [
            target for target in targets
            if target.get("target_id") in wanted or target.get("source_entry_path") in wanted
        ]
    if args.limit > 0:
        targets = targets[:args.limit]

    results = [_validate_target(args.library_root, target) for target in targets]
    failures = [result for result in results if not result.get("ok")]
    report = {
        "schema": "rsdwtools.asset_library.catalog_asset_metadata_report.v1",
        "target_file": str(args.target_file),
        "library_root": str(args.library_root),
        "checked": len(results),
        "ok": len(results) - len(failures),
        "failed": len(failures),
        "failure_examples": failures[:20],
    }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
