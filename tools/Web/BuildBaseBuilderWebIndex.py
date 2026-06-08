"""Build the compact browser index for the RSDW Base Builder website.

The browser editor consumes BaseBuilder placement/export metadata and loads
visual models from RSDWModel WebAssets. This script joins those two indexes and
keeps local absolute paths out of the generated website payload.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "RSDWBaseBuilder.WebIndex.v1"
DEFAULT_MODEL_ROOT = Path(r"E:/Github/RSDWModel")
ITEM_ACTOR_CLASS = (
    "BlueprintGeneratedClass "
    "/Game/Gameplay/WorldItems/BP_RuntimeSpawnedWorldItem.BP_RuntimeSpawnedWorldItem_C"
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _shorten_class(class_name: str) -> str:
    if not class_name:
        return ""
    tail = class_name.rsplit("/", 1)[-1]
    return tail.rsplit(".", 1)[-1]


def _class_path_from_class_name(class_name: str) -> str:
    text = str(class_name or "").strip()
    prefix = "BlueprintGeneratedClass "
    if text.startswith(prefix):
        return text[len(prefix):].strip()
    return text


def _unreal_asset_path_from_json_relative(json_relative: str, asset_name: str = "") -> str:
    rel = str(json_relative or "").replace("\\", "/")
    if rel.endswith(".json"):
        rel = rel[:-5]
    if not rel:
        return ""
    stem = asset_name or rel.rsplit("/", 1)[-1]
    if rel.startswith("RSDragonwilds/Content/"):
        body = rel[len("RSDragonwilds/Content/"):]
        return f"/Game/{body}.{stem}"
    marker = "RSDragonwilds/Plugins/GameFeatures/"
    if rel.startswith(marker):
        rest = rel[len(marker):]
        parts = rest.split("/", 2)
        if len(parts) == 3 and parts[1] == "Content":
            return f"/{parts[0]}/{parts[2]}.{stem}"
    return f"/Game/{stem}.{stem}"


def _archive_texture_relative_path(icon_path: Any, version: str) -> str:
    text = str(icon_path or "").replace("\\", "/")
    if not text:
        return ""
    version_marker = f"/{version}/textures/"
    marker_at = text.find(version_marker)
    if marker_at >= 0:
        return f"textures/{text[marker_at + len(version_marker):]}"
    texture_marker = "textures/RSDragonwilds/"
    marker_at = text.find(texture_marker)
    if marker_at >= 0:
        return text[marker_at:]
    content_marker = "RSDragonwilds/Content/"
    marker_at = text.find(content_marker)
    if marker_at >= 0:
        return f"textures/{text[marker_at:]}"
    return ""


def _safe_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value.strip())
    return cleaned.strip("._") or "asset"


def _relative_web_path(path: Path, website_root: Path) -> str:
    try:
        return path.resolve().relative_to(website_root.resolve()).as_posix()
    except ValueError:
        return ""


def _compact_transform(transform: Any) -> dict[str, Any]:
    if not isinstance(transform, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("matrix", "location", "rotation", "rotation_quat", "scale"):
        value = transform.get(key)
        if value not in (None, {}, []):
            out[key] = value
    return out


def _is_absolute_local_path(value: str) -> bool:
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return True
    return value.startswith("\\\\")


def _find_absolute_strings(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(_find_absolute_strings(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_absolute_strings(child, f"{path}[{index}]"))
    elif isinstance(value, str) and _is_absolute_local_path(value):
        found.append(f"{path}: {value}")
    return found


def _model_index_by_path(model_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = model_index.get("models")
    if not isinstance(rows, list):
        raise SystemExit("RSDWModel model-index.json is missing a models array.")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "")
        if path:
            out[path] = row
    return out


def _target_kind(target: dict[str, Any]) -> str:
    return str(target.get("asset_kind") or target.get("kind") or "")


def _target_export_metadata(target: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind == "building_piece":
        class_name = str(target.get("class_name") or "")
        short = str(target.get("bp_class") or _shorten_class(class_name))
        return {
            "bp_class": short,
            "class_name": class_name,
            "piece_data_index": target.get("piece_data_index"),
            "piece_data_name": str(target.get("piece_data_name") or ""),
            "source_sm_stem": str(target.get("source_sm_stem") or ""),
            "catalog_asset_stem": str(target.get("asset_stem") or ""),
            "default_stability": int(target.get("stability") or 3000),
            "is_ghosted": False,
        }
    if kind == "item":
        item_name = str(target.get("item_name") or target.get("asset_stem") or "")
        item_json_relative = str(target.get("item_json_relative") or "")
        return {
            "actor_class": ITEM_ACTOR_CLASS,
            "item_asset_name": item_name,
            "item_asset_path": _unreal_asset_path_from_json_relative(item_json_relative, item_name),
            "item_source": "ItemData",
            "item_count": 1,
            "item_json_relative": item_json_relative,
        }
    if kind == "bp":
        actor_class = str(target.get("class_name") or "")
        class_path = str(target.get("runtime_path") or target.get("class_path") or "")
        if not class_path:
            class_path = _class_path_from_class_name(actor_class)
        return {
            "bp_class": str(target.get("bp_class") or _shorten_class(actor_class)),
            "actor_class": actor_class,
            "class_path": class_path,
            "runtime_path": str(target.get("runtime_path") or class_path),
        }
    return {}


def _component_rows(
    target: dict[str, Any],
    *,
    model_by_path: dict[str, dict[str, Any]],
    missing_model_refs: set[str],
) -> list[dict[str, Any]]:
    components = target.get("components")
    if not isinstance(components, list):
        components = []
    out: list[dict[str, Any]] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        ref = str(component.get("source_entry_path") or "")
        if not ref and isinstance(component.get("source_entry"), dict):
            ref = str(component["source_entry"].get("path") or "")
        if not ref:
            continue
        model = model_by_path.get(ref)
        if model is None:
            missing_model_refs.add(ref)
            continue
        out.append({
            "name": str(component.get("component_name") or "component"),
            "type": str(component.get("component_type") or ""),
            "model_ref": ref,
            "model_kind": str(model.get("kind") or ""),
            "model_name": str(model.get("displayName") or model.get("name") or ""),
            "gltf_path": str(model.get("gltfPath") or ""),
            "bin_path": str(model.get("binPath") or ""),
            "transform": _compact_transform(component.get("transform")),
        })
    return out


def build_index(
    *,
    target_file: Path,
    model_index_file: Path,
    snaps_file: Path,
    out_file: Path,
    bp_web_preview_root: Path | None = None,
    require_bp_web_previews: bool = False,
) -> dict[str, Any]:
    targets_doc = load_json(target_file)
    model_index = load_json(model_index_file)
    snaps_doc = load_json(snaps_file) if snaps_file.is_file() else {"pieces": {}}
    version = str(targets_doc.get("version") or model_index.get("datasetVersion") or "")
    website_root = out_file.resolve().parent
    if bp_web_preview_root is None and version:
        bp_web_preview_root = website_root / "previews" / version / "bp"
    if bp_web_preview_root is not None:
        bp_web_preview_root = bp_web_preview_root.resolve()
    model_by_path = _model_index_by_path(model_index)
    targets = targets_doc.get("targets")
    if not isinstance(targets, list):
        raise SystemExit(f"target file is missing targets array: {target_file}")

    rows: list[dict[str, Any]] = []
    missing_model_refs: set[str] = set()
    all_source_model_refs: set[str] = set()
    used_model_refs: set[str] = set()
    used_gltf_paths: set[str] = set()
    missing_bp_web_previews: list[str] = []
    used_snaps: dict[str, Any] = {}
    snaps_by_class = snaps_doc.get("pieces") if isinstance(snaps_doc, dict) else {}
    if not isinstance(snaps_by_class, dict):
        snaps_by_class = {}

    for target in targets:
        if not isinstance(target, dict):
            continue
        kind = _target_kind(target)
        for ref in target.get("source_model_refs") or []:
            ref_text = str(ref or "")
            if not ref_text:
                continue
            all_source_model_refs.add(ref_text)
            if ref_text not in model_by_path:
                missing_model_refs.add(ref_text)
        components = _component_rows(target, model_by_path=model_by_path, missing_model_refs=missing_model_refs)
        for component in components:
            used_model_refs.add(component["model_ref"])
            if component["gltf_path"]:
                used_gltf_paths.add(component["gltf_path"])

        export_metadata = _target_export_metadata(target, kind)
        icon_path = _archive_texture_relative_path(target.get("icon_path"), version)
        web_preview_path = ""
        if kind == "bp" and bp_web_preview_root is not None:
            expected_preview = bp_web_preview_root / f"{_safe_stem(str(target.get('target_id') or ''))}.webp"
            if expected_preview.is_file():
                web_preview_path = _relative_web_path(expected_preview, website_root)
            else:
                missing_bp_web_previews.append(str(target.get("target_id") or target.get("asset_stem") or ""))
        snap_class = export_metadata.get("bp_class") if kind == "building_piece" else ""
        if snap_class and snap_class in snaps_by_class:
            used_snaps[str(snap_class)] = snaps_by_class[snap_class]

        search_text = " ".join(
            str(value or "")
            for value in (
                target.get("asset_stem"),
                target.get("display_name"),
                target.get("catalog_path"),
                target.get("class_name"),
                target.get("bp_class"),
                target.get("item_name"),
                target.get("item_type"),
            )
        ).lower()

        rows.append({
            "target_id": str(target.get("target_id") or ""),
            "asset_kind": kind,
            "asset_stem": str(target.get("asset_stem") or ""),
            "display_name": str(target.get("display_name") or target.get("asset_stem") or ""),
            "catalog_path": str(target.get("catalog_path") or ""),
            "preview_mode": str(target.get("preview_mode") or ""),
            "icon_path": icon_path,
            "icon_source_repo": "RSDWArchive" if icon_path else "",
            "web_preview_path": web_preview_path,
            "components": components,
            "export": export_metadata,
            "snap_class": str(snap_class or ""),
            "search_text": search_text,
        })

    if missing_model_refs:
        examples = "\n  ".join(sorted(missing_model_refs)[:20])
        raise SystemExit(
            f"{len(missing_model_refs)} BaseBuilder model ref(s) were missing from RSDWModel model-index.json:\n  {examples}"
        )

    if require_bp_web_previews and missing_bp_web_previews:
        examples = "\n  ".join(missing_bp_web_previews[:20])
        raise SystemExit(
            f"{len(missing_bp_web_previews)} BP browser preview(s) were missing:\n  {examples}"
        )

    source_summary = dict(targets_doc.get("summary") or {})
    summary = dict(source_summary)
    source_unresolved_records = summary.pop("unresolved_model_ref_records", 0)
    source_unresolved_unique = summary.pop("unresolved_unique_model_refs", 0)
    summary.update({
        "web_target_count": len(rows),
        "unique_model_refs": len(all_source_model_refs),
        "unique_component_model_refs": len(used_model_refs),
        "unique_gltf_paths": len(used_gltf_paths),
        "snap_class_count": len(used_snaps),
        "web_icon_count": sum(1 for row in rows if row.get("icon_path")),
        "web_preview_count": sum(1 for row in rows if row.get("web_preview_path")),
        "bp_web_preview_missing": len(missing_bp_web_previews),
        "browser_unresolved_model_refs": 0,
        "source_unresolved_model_ref_records": source_unresolved_records,
        "source_unresolved_unique_model_refs": source_unresolved_unique,
    })
    out = {
        "schema": SCHEMA,
        "generated_at_utc": now_iso(),
        "version": version,
        "sources": {
            "target_schema": str(targets_doc.get("schema") or ""),
            "model_index_schema": str(model_index.get("schema") or ""),
            "model_repo": "RSDWArchive/RSDWModel",
            "model_branch": "main",
            "bp_web_preview_root": _relative_web_path(bp_web_preview_root, website_root) if bp_web_preview_root else "",
        },
        "summary": summary,
        "targets": rows,
        "snaps": used_snaps,
    }
    absolute_strings = _find_absolute_strings(out)
    if absolute_strings:
        raise SystemExit("Refusing to write web index with local absolute paths:\n  " + "\n  ".join(absolute_strings[:50]))
    write_json(out_file, out)
    return out


def parse_args() -> argparse.Namespace:
    root = repo_root()
    parser = argparse.ArgumentParser(description="Build the RSDWBaseBuilder browser app index.")
    parser.add_argument("--target-file", type=Path, default=root / "tools" / "AssetLibrary" / "asset_library_targets.json")
    parser.add_argument("--model-index", type=Path, default=DEFAULT_MODEL_ROOT / "website" / "model-index.json")
    parser.add_argument("--snaps", type=Path, default=root / "addon" / "data" / "Snaps.json")
    parser.add_argument("--out", type=Path, default=root / "website" / "basebuilder-index.json")
    parser.add_argument("--bp-web-preview-root", type=Path, default=None)
    parser.add_argument("--require-bp-web-previews", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = build_index(
        target_file=args.target_file.resolve(),
        model_index_file=args.model_index.resolve(),
        snaps_file=args.snaps.resolve(),
        out_file=args.out.resolve(),
        bp_web_preview_root=args.bp_web_preview_root.resolve() if args.bp_web_preview_root else None,
        require_bp_web_previews=args.require_bp_web_previews,
    )
    print(json.dumps({
        "out": str(args.out),
        "version": out["version"],
        "target_count": out["summary"]["web_target_count"],
        "unique_model_refs": out["summary"]["unique_model_refs"],
        "unique_component_model_refs": out["summary"]["unique_component_model_refs"],
        "snap_class_count": out["summary"]["snap_class_count"],
        "web_icon_count": out["summary"]["web_icon_count"],
        "web_preview_count": out["summary"]["web_preview_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
