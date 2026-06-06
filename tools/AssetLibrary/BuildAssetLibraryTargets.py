"""Build the unified BP/building-piece/item asset-library target manifest.

This script consumes completed RSDWArchive and RSDWModel outputs. It does not
run either upstream pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import categorize  # noqa: E402


SCHEMA = "RSDWBaseBuilder.AssetLibraryTargets.v1"
REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "tools" / "AssetLibrary" / "asset_library_targets.json"
DEFAULT_BUILDING_TARGETS = REPO / "tools" / "AssetLibrary" / "catalog_asset_targets.json"
DEFAULT_LIBRARY_ROOT = REPO / "_build" / "extension"
DEFAULT_ARCHIVE_ROOT = Path(r"E:/Github/RSDWArchive")
DEFAULT_MODEL_ROOT = Path(r"E:/Github/RSDWModel")

MODEL_STEM_RE = re.compile(r"\b(?:SM|SK)_[A-Za-z0-9_]+")
MODEL_FILE_RE = re.compile(r"\b(?:SM|SK)_[A-Za-z0-9_]+\.uemodel$", re.IGNORECASE)
COMPONENT_TYPES = {
    "StaticMeshComponent",
    "InstancedStaticMeshComponent",
    "HierarchicalInstancedStaticMeshComponent",
    "SkeletalMeshComponent",
}
MODEL_REF_KEYS = {
    "StaticMesh",
    "SkeletalMesh",
    "SkinnedAsset",
    "OverrideMesh",
    "Mesh",
    "ArrowShaftMesh",
    "ArrowHeadMesh",
}
MODEL_REF_LEAF_KEYS = {"AssetPathName", "ObjectPath"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _safe_stem(text: str, fallback: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_")
    return stem or fallback


def _unique_stem(base: str, used: set[str]) -> str:
    stem = _safe_stem(base, "Asset")
    if stem not in used:
        used.add(stem)
        return stem
    idx = 2
    while f"{stem}_{idx}" in used:
        idx += 1
    out = f"{stem}_{idx}"
    used.add(out)
    return out


def _version_roots(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [
        child for child in root.iterdir()
        if child.is_dir() and re.match(r"^\d+(?:\.\d+)+$", child.name)
    ]


def _version_key(path: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in path.name.split(".") if part.isdigit())


def _detect_version(archive_root: Path, model_root: Path) -> str:
    archive_versions = {path.name for path in _version_roots(archive_root)}
    model_versions = {path.name for path in _version_roots(model_root)}
    common = sorted(archive_versions & model_versions, key=lambda v: tuple(int(p) for p in v.split(".")))
    if not common:
        raise SystemExit("Could not detect a matching Archive/Model version. Pass --version.")
    return common[-1]


def _model_data_files(model_version_root: Path) -> list[Path]:
    return [
        model_version_root / "ModelData" / "SM_Data.json",
        model_version_root / "ModelData" / "SK_Data.json",
    ]


def _default_item_data(archive_root: Path) -> Path:
    return archive_root / "website" / "tools" / "ItemData" / "ItemData.json"


def _default_bp_data(archive_root: Path) -> Path:
    return archive_root / "website" / "tools" / "BPData" / "BPData.json"


def _catalog_subdir(catalog_path: str) -> Path:
    return Path(*["_".join(part.split()) for part in catalog_path.split("/")])


def _planned_blend_rel(catalog_path: str, asset_stem: str) -> str:
    return (_catalog_subdir(catalog_path) / f"{asset_stem}.blend").as_posix()


def _strip_unreal_ref(raw: str) -> str:
    text = str(raw).strip().replace("\\", "/")
    if not text:
        return ""
    if "'" in text:
        parts = [part for idx, part in enumerate(text.split("'")) if idx % 2 == 1]
        if parts:
            text = parts[-1]
    if " " in text and text.split(" ", 1)[0] in {"StaticMesh", "SkeletalMesh", "Object", "Texture2D"}:
        text = text.split(" ", 1)[1].strip()
    text = text.strip("\"'")
    if text.startswith("Class'") or text.startswith("BlueprintGeneratedClass"):
        return ""
    return text


def _path_without_object_suffix(text: str) -> str:
    if "." not in text:
        return text
    base, leaf = text.rsplit(".", 1)
    if leaf.isdigit() or MODEL_STEM_RE.fullmatch(leaf) or leaf.endswith("_C"):
        return base
    return text


def _normalize_model_path(raw: str) -> tuple[str, str]:
    """Return (normalized inventory path, model stem), or ("", "")."""
    text = _strip_unreal_ref(raw)
    if not text or not MODEL_STEM_RE.search(text):
        return "", ""
    if ":" in text:
        text = text.split(":", 1)[0]
    if text.startswith("/"):
        mount_parts = text.strip("/").split("/")
        if len(mount_parts) < 2:
            return "", ""
        mount = mount_parts[0]
        rest = "/".join(mount_parts[1:])
        rest = _path_without_object_suffix(rest)
        stem = Path(rest).name
        if not MODEL_STEM_RE.fullmatch(stem):
            return "", ""
        if mount == "Game":
            return f"RSDragonwilds/Content/{rest}.uemodel", stem
        if mount == "Engine":
            return f"Engine/Content/{rest}.uemodel", stem
        if mount == "Script":
            return "", ""
        return f"RSDragonwilds/Plugins/GameFeatures/{mount}/Content/{rest}.uemodel", stem

    marker = "RSDragonwilds/"
    if marker in text:
        text = text[text.index(marker):]
    elif text.startswith("Engine/"):
        pass
    else:
        match = MODEL_STEM_RE.search(text)
        return "", match.group(0) if match else ""

    text = _path_without_object_suffix(text)
    if not MODEL_FILE_RE.search(text):
        text = f"{text}.uemodel"
    stem = Path(text).stem
    if not MODEL_STEM_RE.fullmatch(stem):
        return "", ""
    return text, stem


def _iter_model_ref_values(value: Any, trail: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, child in value.items():
            key_s = str(key)
            next_trail = (*trail, key_s)
            if key_s in MODEL_REF_LEAF_KEYS and isinstance(child, str) and MODEL_STEM_RE.search(child):
                yield ".".join(next_trail), child
            elif key_s in MODEL_REF_KEYS:
                yield from _iter_model_ref_values(child, next_trail)
            else:
                yield from _iter_model_ref_values(child, next_trail)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from _iter_model_ref_values(child, (*trail, str(idx)))


def _load_model_inventory(model_root: Path, model_data_files: list[Path]) -> dict[str, Any]:
    by_path: dict[str, dict[str, Any]] = {}
    by_stem: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_counts: dict[str, int] = {}

    for data_file in model_data_files:
        doc = _load_json(data_file)
        entries = list(doc.get("entries") or [])
        source_counts[str(data_file)] = len(entries)
        for entry in entries:
            path = str(entry.get("path") or "")
            if not path:
                continue
            rec = {
                "entry": entry,
                "path": path,
                "stem": Path(path).stem,
                "source_root": str(model_root.resolve()),
                "source_inventory": str(data_file.resolve()),
            }
            by_path[path.lower()] = rec
            by_stem[rec["stem"]].append(rec)

    return {
        "by_path": by_path,
        "by_stem": by_stem,
        "source_counts": source_counts,
        "entry_count": len(by_path),
    }


def _resolve_model_ref(raw: str, inventory: dict[str, Any]) -> dict[str, Any]:
    norm_path, stem = _normalize_model_path(raw)
    if norm_path:
        rec = inventory["by_path"].get(norm_path.lower())
        if rec:
            return {**rec, "raw": raw, "normalized_path": norm_path, "resolution": "exact"}
    if stem:
        stem_matches = inventory["by_stem"].get(stem) or []
        if len(stem_matches) == 1:
            rec = stem_matches[0]
            return {**rec, "raw": raw, "normalized_path": norm_path, "resolution": "unique_stem"}
        if len(stem_matches) > 1:
            return {
                "raw": raw,
                "normalized_path": norm_path,
                "stem": stem,
                "unresolved_reason": "ambiguous_stem",
                "candidates": [m["path"] for m in stem_matches[:20]],
            }
    return {
        "raw": raw,
        "normalized_path": norm_path,
        "stem": stem,
        "unresolved_reason": "missing_model_inventory",
    }


def _resolved_refs_from_value(value: Any, inventory: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved_by_path: dict[str, dict[str, Any]] = {}
    unresolved: dict[str, dict[str, Any]] = {}
    for trail, raw in _iter_model_ref_values(value):
        rec = _resolve_model_ref(raw, inventory)
        rec = {**rec, "field": trail}
        if rec.get("entry"):
            resolved_by_path.setdefault(rec["path"], rec)
        else:
            key = f"{rec.get('normalized_path')}|{rec.get('stem')}|{raw}"
            unresolved.setdefault(key, rec)
    return list(resolved_by_path.values()), list(unresolved.values())


def _display_from_item(item: dict[str, Any], key: str) -> str:
    props = item.get("properties") or {}
    enrichment = item.get("enrichment") or {}
    for candidate in (
        enrichment.get("displayName"),
        enrichment.get("name"),
        props.get("DisplayName"),
        props.get("Name"),
        item.get("name"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return Path(key).stem


def _item_catalog_path(key: str, item: dict[str, Any]) -> str:
    item_type = str(item.get("type") or "").strip()
    if item_type and item_type.lower() not in {"itemdata", "item"}:
        return f"Items/{item_type}"
    parts = Path(key.replace("\\", "/")).parts
    for marker in ("Items", "ItemData", "Equipment"):
        if marker in parts:
            idx = parts.index(marker)
            if idx + 1 < len(parts) - 1:
                return f"Items/{parts[idx + 1].replace('_', ' ')}"
    return "Items/Misc"


def _bp_catalog_path(bp_info: dict[str, Any]) -> str:
    runtime = str(bp_info.get("runtimePath") or "")
    package = str(bp_info.get("packagePath") or "")
    path = runtime or package
    parts = [part for part in path.strip("/").replace("\\", "/").split("/") if part]
    if not parts:
        return "BP/Misc"
    mount = "Game" if parts[0] == "Game" else parts[0]
    folders = parts[1:-1] if runtime else parts[:-1]
    useful = [part.replace("_", " ") for part in folders[:2]]
    return "/".join(["BP", mount, *useful]) if useful else f"BP/{mount}"


def _transform_from_props(props: dict[str, Any]) -> dict[str, Any]:
    transform: dict[str, Any] = {}
    rel = props.get("RelativeTransform")
    if isinstance(rel, dict):
        loc = rel.get("Translation")
        rot = rel.get("Rotation")
        scale = rel.get("Scale3D")
    else:
        loc = props.get("RelativeLocation")
        rot = props.get("RelativeRotation")
        scale = props.get("RelativeScale3D")
    if isinstance(loc, dict):
        transform["location"] = {
            axis: float(loc.get(axis, 0.0) or 0.0)
            for axis in ("X", "Y", "Z")
        }
    if isinstance(rot, dict):
        if {"Pitch", "Yaw", "Roll"} & set(rot):
            transform["rotation"] = {
                axis: float(rot.get(axis, 0.0) or 0.0)
                for axis in ("Pitch", "Yaw", "Roll")
            }
        elif {"X", "Y", "Z", "W"} <= set(rot):
            transform["rotation_quat"] = {
                axis: float(rot.get(axis, 0.0) or 0.0)
                for axis in ("X", "Y", "Z", "W")
            }
    if isinstance(scale, dict):
        transform["scale"] = {
            axis: float(scale.get(axis, 1.0) or 1.0)
            for axis in ("X", "Y", "Z")
        }
    return transform


def _component_refs_from_bp(bp_json: Any, inventory: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    components: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    if not isinstance(bp_json, list):
        return components, unresolved

    for idx, export in enumerate(bp_json):
        if not isinstance(export, dict) or export.get("Type") not in COMPONENT_TYPES:
            continue
        props = export.get("Properties") or {}
        if not isinstance(props, dict):
            continue
        best_ref = None
        best_field = ""
        for field in MODEL_REF_KEYS:
            if field not in props:
                continue
            refs, misses = _resolved_refs_from_value(props[field], inventory)
            unresolved.extend({**miss, "component": export.get("Name"), "component_index": idx} for miss in misses)
            if refs:
                best_ref = refs[0]
                best_field = field
                break
        if not best_ref:
            continue
        components.append({
            "component_name": export.get("Name") or f"component_{idx}",
            "component_type": export.get("Type"),
            "field": best_field,
            "source_entry_path": best_ref["path"],
            "source_entry": best_ref["entry"],
            "source_root": best_ref["source_root"],
            "source_inventory": best_ref["source_inventory"],
            "model_stem": best_ref["stem"],
            "transform": _transform_from_props(props),
        })
    return components, unresolved


def _dedupe_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for component in components:
        transform_key = json.dumps(component.get("transform") or {}, sort_keys=True)
        key = (component.get("source_entry_path") or "", transform_key)
        if key in seen:
            continue
        seen.add(key)
        out.append(component)
    return out


def _build_item_targets(
    *,
    item_data: Path,
    inventory: dict[str, Any],
    used_stems: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    doc = _load_json(item_data)
    targets: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for key, item in sorted((doc.get("entries") or {}).items()):
        counts["entries"] += 1
        refs, misses = _resolved_refs_from_value(item, inventory)
        if misses:
            unresolved.extend({**miss, "asset_kind": "item", "item_json_relative": key} for miss in misses)
        if not refs:
            counts["without_model_refs"] += 1
            continue
        primary = next((ref for ref in refs if ref.get("field", "").endswith("StaticMesh.AssetPathName")), refs[0])
        display = _display_from_item(item, key)
        asset_stem = _unique_stem(Path(key).stem, used_stems)
        catalog_path = _item_catalog_path(key, item)
        target = {
            "asset_kind": "item",
            "target_id": f"item:{key}",
            "asset_stem": asset_stem,
            "display_name": display,
            "catalog_path": catalog_path,
            "source_entry_path": primary["path"],
            "source_entry": primary["entry"],
            "source_root": primary["source_root"],
            "source_inventory": primary["source_inventory"],
            "source_model_refs": [ref["path"] for ref in refs],
            "components": [{
                "component_name": "primary",
                "component_type": "ItemVisual",
                "source_entry_path": primary["path"],
                "source_entry": primary["entry"],
                "source_root": primary["source_root"],
                "source_inventory": primary["source_inventory"],
                "model_stem": primary["stem"],
                "transform": {},
            }],
            "item_json_relative": key,
            "item_type": item.get("type") or "",
            "item_name": item.get("name") or "",
            "primary_model_ref": primary["path"],
            "planned_blend_rel": _planned_blend_rel(catalog_path, asset_stem),
        }
        targets.append(target)
        counts["with_model_refs"] += 1
    return targets, unresolved, counts


def _build_bp_targets(
    *,
    bp_data: Path,
    archive_json_root: Path,
    inventory: dict[str, Any],
    used_stems: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    doc = _load_json(bp_data)
    targets: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for bp_class, bp_info in sorted((doc.get("blueprints") or {}).items()):
        counts["blueprints"] += 1
        rel = bp_info.get("jsonRelative") or ""
        bp_json_path = archive_json_root / rel
        if not bp_json_path.is_file():
            skipped.append({
                "asset_kind": "bp",
                "bp_class": bp_class,
                "reason": "bp_json_missing",
                "jsonRelative": rel,
            })
            counts["json_missing"] += 1
            continue
        try:
            bp_json = _load_json(bp_json_path)
        except Exception as exc:
            skipped.append({
                "asset_kind": "bp",
                "bp_class": bp_class,
                "reason": f"bp_json_parse_failed: {exc}",
                "jsonRelative": rel,
            })
            counts["json_parse_failed"] += 1
            continue

        components, component_misses = _component_refs_from_bp(bp_json, inventory)
        components = _dedupe_components(components)
        unresolved.extend({**miss, "asset_kind": "bp", "bp_class": bp_class} for miss in component_misses)

        if not components:
            refs, misses = _resolved_refs_from_value(bp_json, inventory)
            unresolved.extend({**miss, "asset_kind": "bp", "bp_class": bp_class} for miss in misses)
            for ref in refs:
                components.append({
                    "component_name": "representative",
                    "component_type": "FallbackModelRef",
                    "source_entry_path": ref["path"],
                    "source_entry": ref["entry"],
                    "source_root": ref["source_root"],
                    "source_inventory": ref["source_inventory"],
                    "model_stem": ref["stem"],
                    "transform": {},
                })
            components = _dedupe_components(components)

        if not components:
            skipped.append({
                "asset_kind": "bp",
                "bp_class": bp_class,
                "reason": "no_resolved_model_refs",
                "jsonRelative": rel,
            })
            counts["without_model_refs"] += 1
            continue

        primary = components[0]
        display = bp_class.removesuffix("_C").replace("BP_", "").replace("_", " ").strip() or bp_class
        asset_stem = _unique_stem(bp_class, used_stems)
        catalog_path = _bp_catalog_path(bp_info)
        transformed = sum(1 for c in components if c.get("transform"))
        if len(components) == 1:
            assembly_status = "single_model"
        elif transformed:
            assembly_status = "assembled"
        else:
            assembly_status = "representative_multi_model_no_transforms"
        target = {
            "asset_kind": "bp",
            "target_id": f"bp:{bp_class}",
            "asset_stem": asset_stem,
            "display_name": display,
            "catalog_path": catalog_path,
            "source_entry_path": primary["source_entry_path"],
            "source_entry": primary["source_entry"],
            "source_root": primary["source_root"],
            "source_inventory": primary["source_inventory"],
            "source_model_refs": [component["source_entry_path"] for component in components],
            "components": components,
            "bp_class": bp_class,
            "class_name": f"BlueprintGeneratedClass {bp_info.get('runtimePath') or bp_info.get('classPath') or bp_class}",
            "runtime_path": bp_info.get("runtimePath") or "",
            "bp_json_relative": rel,
            "package_path": bp_info.get("packagePath") or "",
            "assembly_status": assembly_status,
            "component_count": len(components),
            "planned_blend_rel": _planned_blend_rel(catalog_path, asset_stem),
        }
        targets.append(target)
        counts["with_model_refs"] += 1
        if len(components) > 1:
            counts["multi_component"] += 1
    return targets, unresolved, skipped, counts


def _load_building_targets(path: Path, used_stems: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    doc = _load_json(path)
    targets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for target in doc.get("targets") or []:
        asset_stem = _unique_stem(target.get("asset_stem") or target.get("target_id") or "BuildingPiece", used_stems)
        catalog_path = "Building Pieces/" + str(target.get("catalog_path") or "Misc")
        out = dict(target)
        out.update({
            "asset_kind": "building_piece",
            "asset_stem": asset_stem,
            "catalog_path": catalog_path,
            "source_model_refs": [target.get("source_entry_path")],
            "components": [{
                "component_name": "primary",
                "component_type": "BuildingPieceVisual",
                "source_entry_path": target.get("source_entry_path"),
                "source_entry": target.get("source_entry"),
                "source_root": target.get("source_root"),
                "source_inventory": target.get("source_inventory"),
                "model_stem": target.get("source_sm_stem"),
                "transform": {},
            }],
            "planned_blend_rel": _planned_blend_rel(catalog_path, asset_stem),
        })
        targets.append(out)

    for target in doc.get("unresolved") or []:
        unresolved.append({**target, "asset_kind": "building_piece"})
    for target in doc.get("ignored") or []:
        skipped.append({**target, "asset_kind": "building_piece"})
    return targets, unresolved, skipped, doc.get("summary") or {}


def _smoke_target_ids(targets: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for target in targets:
        by_kind[target.get("asset_kind", "")].append(target)
    for kind in ("building_piece", "item"):
        out.extend(t["target_id"] for t in by_kind.get(kind, [])[:5])
    bp_targets = by_kind.get("bp", [])
    out.extend([t["target_id"] for t in bp_targets if int(t.get("component_count") or 1) == 1][:5])
    out.extend([t["target_id"] for t in bp_targets if int(t.get("component_count") or 1) > 1][:5])
    seen: set[str] = set()
    return [tid for tid in out if not (tid in seen or seen.add(tid))]


def build_targets(args: argparse.Namespace) -> dict[str, Any]:
    version = args.version or _detect_version(args.archive_root, args.model_root)
    archive_version_root = (args.archive_root / version).resolve()
    model_version_root = (args.model_root / version).resolve()
    archive_json_root = (args.archive_json_root or archive_version_root / "json").resolve()
    item_data = (args.item_data or _default_item_data(args.archive_root)).resolve()
    bp_data = (args.bp_data or _default_bp_data(args.archive_root)).resolve()
    model_data_files = [path.resolve() for path in (args.model_data or _model_data_files(model_version_root))]

    required = [
        (archive_version_root, "archive version root"),
        (model_version_root, "model version root"),
        (archive_json_root, "archive json root"),
        (item_data, "ItemData.json"),
        (bp_data, "BPData.json"),
        (args.building_targets, "building target file"),
        *[(path, path.name) for path in model_data_files],
    ]
    missing = [f"{label}: {path}" for path, label in required if not path.exists()]
    if missing:
        raise SystemExit("Missing required input(s):\n  " + "\n  ".join(missing))

    inventory = _load_model_inventory(model_version_root, model_data_files)
    used_stems: set[str] = set()

    building_targets, building_unresolved, building_skipped, building_summary = _load_building_targets(
        args.building_targets, used_stems,
    )
    item_targets, item_unresolved, item_counts = _build_item_targets(
        item_data=item_data,
        inventory=inventory,
        used_stems=used_stems,
    )
    bp_targets, bp_unresolved, bp_skipped, bp_counts = _build_bp_targets(
        bp_data=bp_data,
        archive_json_root=archive_json_root,
        inventory=inventory,
        used_stems=used_stems,
    )

    targets = [*building_targets, *item_targets, *bp_targets]
    unresolved = [*building_unresolved, *item_unresolved, *bp_unresolved]
    skipped = [*building_skipped, *bp_skipped]
    kind_counts = Counter(target.get("asset_kind") for target in targets)
    unique_model_refs = {
        ref for target in targets
        for ref in (target.get("source_model_refs") or [])
        if ref
    }
    unresolved_unique = {
        item.get("normalized_path") or item.get("stem") or item.get("raw")
        for item in unresolved
    }
    summary = {
        "target_count": len(targets),
        "targets_by_kind": dict(sorted(kind_counts.items())),
        "unique_model_refs": len(unique_model_refs),
        "unresolved_model_ref_records": len(unresolved),
        "unresolved_unique_model_refs": len(unresolved_unique),
        "skipped": len(skipped),
        "building_source_summary": building_summary,
        "item_counts": dict(sorted(item_counts.items())),
        "bp_counts": dict(sorted(bp_counts.items())),
        "model_inventory_entries": inventory["entry_count"],
    }

    return {
        "schema": SCHEMA,
        "version": version,
        "generated_at_utc": _now_iso(),
        "inputs": {
            "archive_version_root": str(archive_version_root),
            "model_version_root": str(model_version_root),
            "archive_json_root": str(archive_json_root),
            "item_data": str(item_data),
            "bp_data": str(bp_data),
            "building_targets": str(args.building_targets.resolve()),
            "model_data": [str(path) for path in model_data_files],
        },
        "summary": summary,
        "smoke_target_ids": _smoke_target_ids(targets),
        "targets": targets,
        "unresolved": unresolved,
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build unified asset-library targets.")
    parser.add_argument("--version", default=None)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("--model-root", type=Path, default=DEFAULT_MODEL_ROOT)
    parser.add_argument("--archive-json-root", type=Path, default=None)
    parser.add_argument("--item-data", type=Path, default=None)
    parser.add_argument("--bp-data", type=Path, default=None)
    parser.add_argument("--model-data", type=Path, action="append", default=None)
    parser.add_argument("--building-targets", type=Path, default=DEFAULT_BUILDING_TARGETS)
    parser.add_argument("--library-root", type=Path, default=DEFAULT_LIBRARY_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true", help="Validate and print summary without writing --out.")
    args = parser.parse_args(argv)

    doc = build_targets(args)
    print(json.dumps(doc["summary"], indent=2))
    print("Smoke targets:", len(doc.get("smoke_target_ids") or []))
    if not args.dry_run:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote targets -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
