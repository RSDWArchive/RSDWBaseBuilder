"""Verify asset-library icon, preview, and material quality.

The metadata verifier checks RSDW custom properties inside .blend files. This
script checks pipeline quality signals that live in the target manifest and
asset-build progress manifest.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
DEFAULT_TARGET_FILE = REPO / "tools" / "AssetLibrary" / "asset_library_targets.json"
DEFAULT_PROGRESS_FILE = REPO / "_build" / "AssetLibraryProgress.json"
DEFAULT_OUT = REPO / "tools" / "AssetLibrary" / "asset_library_quality_report.json"

EXPECTED_TARGET_SOURCE_PATHS = {
    "BUILDPIECE_Beam_Horizontal_Half_Thick": "RSDragonwilds/Content/Art/Env/Base_Building/BuildingKit/Tier1/SM_BB_T1_Beam_Thick_Med_Horizontal.uemodel",
    "ITEM_Resources_Bones_CorruptedBonemeal": "RSDragonwilds/Content/Art/Item/Resources/Bone_Meal/SM_Bone_Meal_01.uemodel",
}

FORBIDDEN_VISUAL_COLLISIONS = (
    (
        "BUILDPIECE_Beam_Horizontal_Half_Thick",
        "BUILDPIECE_Stairs_45",
    ),
    (
        "ITEM_Resources_Bones_CorruptedBonemeal",
        "ITEM_Resources_Bones_CorruptedBones",
    ),
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _filter_targets(targets: list[dict[str, Any]], only_list: Path | None) -> list[dict[str, Any]]:
    if only_list is None:
        return targets
    wanted = set()
    for line in only_list.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip().lstrip("\ufeff")
        if cleaned and not cleaned.startswith("#"):
            wanted.add(cleaned)
    return [
        target for target in targets
        if target.get("target_id") in wanted or target.get("source_entry_path") in wanted
    ]


def _target_icon_preview_report(
    targets: list[dict[str, Any]],
    *,
    allow_missing_required_icons: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    icon_counts: Counter[str] = Counter()
    preview_counts: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []

    for target in targets:
        kind = str(target.get("asset_kind") or "")
        preview_mode = str(target.get("preview_mode") or "")
        icon_path = str(target.get("icon_path") or "")
        icon_source = str(target.get("icon_source") or "")
        icon_exists = bool(icon_path and Path(icon_path).is_file())

        icon_counts[f"{kind}:{'resolved' if icon_exists else 'missing'}"] += 1
        preview_counts[f"{kind}:{preview_mode or 'unspecified'}"] += 1

        allow_generated_preview = (
            allow_missing_required_icons
            and not icon_exists
            and preview_mode == "generated"
            and icon_source == "missing"
        )

        if kind in {"building_piece", "item"}:
            if preview_mode != "custom_icon" and not allow_generated_preview:
                failures.append({
                    "target_id": target.get("target_id"),
                    "asset_kind": kind,
                    "reason": f"expected custom_icon preview_mode, got {preview_mode!r}",
                })
            if not icon_exists and not allow_generated_preview:
                failures.append({
                    "target_id": target.get("target_id"),
                    "asset_kind": kind,
                    "reason": "required icon_path missing or not found",
                    "icon_path": icon_path,
                    "icon_source": icon_source,
                })
            if icon_source in {"category_fallback", "icon_map", "blender_generated"}:
                failures.append({
                    "target_id": target.get("target_id"),
                    "asset_kind": kind,
                    "reason": f"non-authoritative icon_source {icon_source!r}",
                })

        if kind == "bp":
            if icon_path:
                failures.append({
                    "target_id": target.get("target_id"),
                    "asset_kind": kind,
                    "reason": "BP target should not carry an icon_path; use Blender default previews",
                    "icon_path": icon_path,
                    "icon_source": icon_source,
                })
            if preview_mode != "generated":
                failures.append({
                    "target_id": target.get("target_id"),
                    "asset_kind": kind,
                    "reason": f"BP target should use generated preview, got {preview_mode!r}",
                })
            if icon_source in {"category_fallback", "icon_map"}:
                failures.append({
                    "target_id": target.get("target_id"),
                    "asset_kind": kind,
                    "reason": f"BP target uses non-default icon source {icon_source!r}",
                })

    return {
        "checked": len(targets),
        "icon_counts": dict(sorted(icon_counts.items())),
        "preview_mode_counts": dict(sorted(preview_counts.items())),
    }, failures


def _source_refs(target: dict[str, Any]) -> tuple[str, ...]:
    refs = target.get("source_model_refs") or []
    if not refs and target.get("source_entry_path"):
        refs = [target.get("source_entry_path")]
    return tuple(sorted(str(ref) for ref in refs if ref))


def _target_source_regression_report(targets: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    by_stem = {
        str(target.get("asset_stem") or ""): target
        for target in targets
        if target.get("asset_stem")
    }

    checked_expected_sources = 0
    for asset_stem, expected_path in EXPECTED_TARGET_SOURCE_PATHS.items():
        target = by_stem.get(asset_stem)
        if not target:
            continue
        checked_expected_sources += 1
        refs = _source_refs(target)
        if expected_path not in refs:
            failures.append({
                "target_id": target.get("target_id"),
                "asset_kind": target.get("asset_kind"),
                "asset_stem": asset_stem,
                "reason": "target source path regressed",
                "expected_source_entry_path": expected_path,
                "actual_source_model_refs": list(refs),
            })

    for left_stem, right_stem in FORBIDDEN_VISUAL_COLLISIONS:
        left = by_stem.get(left_stem)
        right = by_stem.get(right_stem)
        if not left or not right:
            continue
        left_refs = _source_refs(left)
        right_refs = _source_refs(right)
        if left_refs and left_refs == right_refs:
            failures.append({
                "target_id": left.get("target_id"),
                "asset_kind": left.get("asset_kind"),
                "asset_stem": left_stem,
                "reason": f"visual source collides with {right_stem}",
                "shared_source_model_refs": list(left_refs),
            })

    return {
        "checked": checked_expected_sources,
        "expected_source_checks": len(EXPECTED_TARGET_SOURCE_PATHS),
        "forbidden_collision_pairs": len(FORBIDDEN_VISUAL_COLLISIONS),
    }, failures


def _progress_entry(progress: dict[str, Any], target: dict[str, Any]) -> dict[str, Any] | None:
    entries = progress.get("entries") or {}
    return (
        entries.get(str(target.get("target_id") or ""))
        or entries.get(str(target.get("source_entry_path") or ""))
    )


def _materialized_slots(record: dict[str, Any]) -> int:
    quality = record.get("material_quality") or {}
    try:
        return int(quality.get("materialized_slot_count") or 0)
    except (TypeError, ValueError):
        return 0


def _slot_count(record: dict[str, Any]) -> int:
    quality = record.get("material_quality") or {}
    try:
        return int(quality.get("slot_count") or 0)
    except (TypeError, ValueError):
        return 0


def _build_quality_report(
    targets: list[dict[str, Any]],
    progress: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    preview_sources: Counter[str] = Counter()
    material_modes: Counter[str] = Counter()
    material_totals: Counter[str] = Counter()

    for target in targets:
        target_id = str(target.get("target_id") or "")
        kind = str(target.get("asset_kind") or "")
        expected_preview = str(target.get("preview_mode") or "")
        record = _progress_entry(progress, target)
        if record is None:
            failures.append({"target_id": target_id, "asset_kind": kind, "reason": "missing progress record"})
            continue
        if record.get("status") != "success":
            failures.append({
                "target_id": target_id,
                "asset_kind": kind,
                "reason": f"build status is {record.get('status')!r}",
                "error": record.get("error"),
            })
            continue

        preview_source = str(record.get("preview_source") or "")
        preview_sources[f"{kind}:{preview_source or 'missing'}"] += 1
        material_modes[str(record.get("material_mode") or "unknown")] += 1

        if kind == "bp":
            audit = record.get("bp_root_audit") or {}
            if record.get("bp_root_normalized") is not True:
                failures.append({
                    "target_id": target_id,
                    "asset_kind": kind,
                    "reason": "BP asset root was not normalized",
                    "bp_root_audit": audit,
                })
            elif audit and audit.get("root_identity_ok") is not True:
                failures.append({
                    "target_id": target_id,
                    "asset_kind": kind,
                    "reason": "BP asset root identity audit failed",
                    "bp_root_audit": audit,
                })

        if expected_preview == "custom_icon":
            if preview_source != "custom_icon" or not record.get("preview_attached"):
                failures.append({
                    "target_id": target_id,
                    "asset_kind": kind,
                    "reason": f"expected custom icon preview, got {preview_source!r}",
                    "preview_error": record.get("preview_error"),
                })
        elif expected_preview == "generated":
            if preview_source not in {"generated", "blender_default"} or not record.get("preview_generated"):
                failures.append({
                    "target_id": target_id,
                    "asset_kind": kind,
                    "reason": f"expected generated preview, got {preview_source!r}",
                    "preview_error": record.get("preview_error"),
                })

        quality = record.get("material_quality") or {}
        for key in (
            "slot_count",
            "linked_slot_count",
            "material_report_count",
            "fallback_built_report_count",
            "base_color_slot_count",
            "mi_slot_count",
            "hybrid_slot_count",
            "texture_slot_count",
            "color_only_slot_count",
            "none_slot_count",
            "materialized_slot_count",
        ):
            try:
                material_totals[key] += int(quality.get(key) or 0)
            except (TypeError, ValueError):
                pass

        material_mode = str(record.get("material_mode") or "")
        if material_mode in {"optimized-pbr", "fallback", "base-color"} and _slot_count(record) > 0 and _materialized_slots(record) <= 0:
            failures.append({
                "target_id": target_id,
                "asset_kind": kind,
                "reason": f"{material_mode} material mode produced no materialized slots",
                "unmatched_slots": record.get("unmatched_slots") or [],
            })
        if material_mode == "base-color" and _slot_count(record) > 0:
            quality = record.get("material_quality") or {}
            try:
                base_color_slot_count = int(quality.get("base_color_slot_count") or 0)
            except (TypeError, ValueError):
                base_color_slot_count = 0
            if base_color_slot_count <= 0:
                failures.append({
                    "target_id": target_id,
                    "asset_kind": kind,
                    "reason": "base-color material mode produced no flat-color slots",
                    "unmatched_slots": record.get("unmatched_slots") or [],
                })

    return {
        "checked": len(targets),
        "preview_source_counts": dict(sorted(preview_sources.items())),
        "material_mode_counts": dict(sorted(material_modes.items())),
        "material_totals": dict(sorted(material_totals.items())),
    }, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify asset-library quality coverage.")
    parser.add_argument("--target-file", type=Path, default=DEFAULT_TARGET_FILE)
    parser.add_argument("--progress-file", type=Path, default=None)
    parser.add_argument("--materials-manifest", type=Path, default=None)
    parser.add_argument("--only-list", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--allow-missing-required-icons", action="store_true",
                        help="Allow item/building-piece targets to use generated previews when archive icons are missing.")
    args = parser.parse_args(argv)

    target_doc = _load_json(args.target_file)
    targets = _filter_targets(list(target_doc.get("targets") or []), args.only_list)

    target_report, target_failures = _target_icon_preview_report(
        targets,
        allow_missing_required_icons=args.allow_missing_required_icons,
    )
    source_regression_report, source_regression_failures = _target_source_regression_report(targets)
    build_report: dict[str, Any] | None = None
    build_failures: list[dict[str, Any]] = []
    if args.progress_file is not None:
        progress = _load_json(args.progress_file)
        build_report, build_failures = _build_quality_report(targets, progress)

    shared_materials_summary = None
    if args.materials_manifest is not None and args.materials_manifest.is_file():
        manifest = _load_json(args.materials_manifest)
        shared_materials_summary = manifest.get("summary")

    failures = [*target_failures, *source_regression_failures, *build_failures]
    if build_report and shared_materials_summary:
        optimized_count = int((build_report.get("material_mode_counts") or {}).get("optimized-pbr") or 0)
        web_hits = int(shared_materials_summary.get("web_texture_hit_count") or 0)
        if optimized_count > 0 and web_hits <= 0:
            failures.append({
                "reason": "optimized-pbr shared materials did not use any RSDWModel WebP textures",
                "web_texture_hit_count": web_hits,
            })
    report = {
        "schema": "RSDWBaseBuilder.AssetLibraryQualityReport.v1",
        "target_file": str(args.target_file),
        "progress_file": str(args.progress_file) if args.progress_file else None,
        "materials_manifest": str(args.materials_manifest) if args.materials_manifest else None,
        "target_quality": target_report,
        "source_regressions": source_regression_report,
        "build_quality": build_report,
        "shared_materials_summary": shared_materials_summary,
        "failed": len(failures),
        "failure_examples": failures[:50],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
