"""
Blender-side worker for the asset library: per .uemodel piece, build a tiny
.blend that links its materials from the shared _Materials.blend, marks the
imported object as an asset, attaches an icon preview, and writes a
catalog UUID.

Heavy lifting is reused from BuildGLBWorker:
  - addon enabling
  - scene clearing
  - .uemodel import
  - material slot resolution
  - MI/Hybrid material build (used as a fallback when a slot has no
    matching material in _Materials.blend)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

import bpy


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tools" / "ModelData"))
sys.path.insert(0, str(_REPO_ROOT / "tools" / "AssetLibrary"))

from BuildGLBWorker import (  # noqa: E402
    _build_materials,
    _clear_scene,
    _enable_required_addons,
    _import_uemodel,
    _read_uemodel_materials,
)


def _parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    p = argparse.ArgumentParser()
    p.add_argument("--task-file", required=True)
    return p.parse_args(argv)


def _emit_result(obj: dict) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    sys.stdout.write("RESULT:" + json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _link_shared_materials(materials_blend: Path, wanted_names: list[str]) -> dict[str, bpy.types.Material]:
    """Link the named materials from materials_blend into the current file
    (link=True so they remain references). Returns {name: linked_material}."""
    if not wanted_names or not materials_blend.is_file():
        return {}
    linked: dict[str, bpy.types.Material] = {}
    with bpy.data.libraries.load(str(materials_blend), link=True) as (data_from, data_to):
        available = set(data_from.materials)
        data_to.materials = [n for n in wanted_names if n in available]
    # data_to.materials is populated AFTER the with-block. Look up the linked datablocks.
    for mat in data_to.materials:
        if mat is not None:
            linked[mat.name] = mat
    return linked


def _link_manifest_materials(manifest_path: Path, wanted_names: list[str]) -> dict[str, bpy.types.Material]:
    if not wanted_names or not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_name = manifest.get("by_name") or {}
    manifest_dir = manifest_path.parent
    wanted_by_blend: dict[Path, list[str]] = {}
    for name in wanted_names:
        locations = by_name.get(name) or []
        if not locations:
            continue
        rel_blend = locations[0].get("blend")
        material_name = locations[0].get("material_name") or name
        if not rel_blend:
            continue
        wanted_by_blend.setdefault((manifest_dir / rel_blend).resolve(), []).append(material_name)

    linked: dict[str, bpy.types.Material] = {}
    for blend_path, names in wanted_by_blend.items():
        if not blend_path.is_file():
            continue
        with bpy.data.libraries.load(str(blend_path), link=True) as (data_from, data_to):
            available = set(data_from.materials)
            data_to.materials = [name for name in sorted(set(names)) if name in available]
        for mat in data_to.materials:
            if mat is not None:
                linked[mat.name] = mat
    return linked


def _swap_in_linked_materials(
    linked: dict[str, bpy.types.Material],
    objects: list[bpy.types.Object] | None = None,
) -> tuple[int, list[str]]:
    """For every object's material slot whose current material's name matches
    a linked material, replace it with the linked one and remove the orphan
    local material. Returns (slots_swapped, list_of_unmatched_slot_names)."""
    swapped = 0
    unmatched: list[str] = []
    locals_to_purge: set[str] = set()

    scan_objects = objects if objects is not None else list(bpy.data.objects)
    for obj in scan_objects:
        if not hasattr(obj, "material_slots"):
            continue
        for slot in obj.material_slots:
            local = slot.material
            if local is None:
                unmatched.append(f"<empty:{obj.name}>")
                continue
            if local.library is not None:
                # Already linked — nothing to do.
                continue
            target = linked.get(local.name)
            if target is None:
                unmatched.append(local.name)
                continue
            local_name = local.name
            slot.material = target
            swapped += 1
            locals_to_purge.add(local_name)

    # Purge locals that are now orphaned (no remaining users).
    for name in locals_to_purge:
        m = bpy.data.materials.get(name)
        if m is not None and m.users == 0:
            try:
                bpy.data.materials.remove(m)
            except Exception:
                pass
    return swapped, sorted(set(unmatched))


def _new_objects_since(before: set[bpy.types.Object]) -> list[bpy.types.Object]:
    return [obj for obj in bpy.data.objects if obj not in before]


def _component_roots(objects: list[bpy.types.Object]) -> list[bpy.types.Object]:
    object_set = set(objects)
    roots = [obj for obj in objects if obj.parent not in object_set]
    return roots or objects


def _apply_component_transform(objects: list[bpy.types.Object], transform: dict) -> None:
    """Apply a conservative UE-relative transform to imported component roots.

    UE locations are centimeters. UEFormat imports geometry at 0.01 scale, so
    component locations are converted to meters here.
    """
    if not transform:
        return
    loc = transform.get("location") or {}
    rot = transform.get("rotation") or {}
    scale = transform.get("scale") or {}
    for obj in _component_roots(objects):
        if loc:
            obj.location.x += float(loc.get("X", 0.0)) * 0.01
            obj.location.y += -float(loc.get("Y", 0.0)) * 0.01
            obj.location.z += float(loc.get("Z", 0.0)) * 0.01
        if scale:
            obj.scale.x *= float(scale.get("X", 1.0))
            obj.scale.y *= float(scale.get("Y", 1.0))
            obj.scale.z *= float(scale.get("Z", 1.0))
        if rot:
            obj.rotation_euler.x += math.radians(float(rot.get("Roll", 0.0)))
            obj.rotation_euler.y += math.radians(float(rot.get("Pitch", 0.0)))
            obj.rotation_euler.z += math.radians(-float(rot.get("Yaw", 0.0)))


def _entry_material_refs(entry: dict) -> tuple[list[str], list[str]]:
    materials_block = entry.get("Materials", {}) or {}
    mi_paths_rel = list(
        materials_block.get("material_json_paths")
        or materials_block.get("material_instance_json_paths")
        or []
    )
    hybrid_paths_rel = list(entry.get("MaterialsHybrid", {}).get("texture_image_paths", []))
    return mi_paths_rel, hybrid_paths_rel


def _import_component(
    *,
    component: dict,
    source_root: Path,
    data_roots: list[Path],
    materials_blend: Path,
    materials_manifest: Path | None,
    material_mode: str,
    pack_unmatched_textures: bool,
) -> tuple[list[bpy.types.Object], dict]:
    entry = component.get("source_entry") or {}
    if not entry:
        raise RuntimeError(f"component has no source_entry: {component.get('component_name')}")

    model_rel = entry["path"]
    uemodel_abs = (source_root / model_rel).resolve()
    if not uemodel_abs.is_file():
        raise FileNotFoundError(f".uemodel not found: {uemodel_abs}")

    mat_slots = _read_uemodel_materials(uemodel_abs)
    slot_names = [s.get("name") for s in mat_slots if s.get("name")]
    mi_paths_rel, hybrid_paths_rel = _entry_material_refs(entry)

    before = set(bpy.data.objects)
    _import_uemodel(uemodel_abs)
    imported = _new_objects_since(before)
    _apply_component_transform(imported, component.get("transform") or {})

    linked: dict[str, bpy.types.Material] = {}
    swapped = 0
    unmatched = sorted(set(slot_names))
    if material_mode != "none":
        if materials_manifest is not None and materials_manifest.is_file():
            linked = _link_manifest_materials(materials_manifest, slot_names)
        else:
            linked = _link_shared_materials(materials_blend, slot_names)
        swapped, unmatched = _swap_in_linked_materials(linked, imported)

    unmatched_built: dict | None = None
    if unmatched and material_mode == "fallback":
        overall, reports = _build_materials(
            mat_slots, mi_paths_rel, hybrid_paths_rel, source_root, data_roots,
        )
        unmatched_built = {"overall": overall, "reports": reports}
        if pack_unmatched_textures:
            try:
                bpy.ops.file.pack_all()
            except RuntimeError:
                pass

    report = {
        "component_name": component.get("component_name"),
        "component_type": component.get("component_type"),
        "model_rel": model_rel,
        "object_count": len(imported),
        "slot_count": len(mat_slots),
        "linked_materials": list(linked.keys()),
        "swapped_slots": swapped,
        "unmatched_slots": unmatched,
        "unmatched_built": unmatched_built,
        "transform_applied": bool(component.get("transform")),
    }
    return imported, report


def _pick_asset_object() -> bpy.types.Object | None:
    """Return the most likely 'main' imported object to mark as the asset.
    UEFormat typically imports a single mesh per LOD; if there are multiple,
    pick the one with the most polygons."""
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        return None
    if len(meshes) == 1:
        return meshes[0]
    return max(meshes, key=lambda o: len(o.data.polygons) if o.data else 0)


def _join_meshes_if_multiple() -> bpy.types.Object | None:
    """If the import produced multiple mesh objects, join them into one so the
    asset is a single object."""
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(meshes) <= 1:
        return meshes[0] if meshes else None
    # Pick join target = largest mesh by polygon count.
    target = max(meshes, key=lambda o: len(o.data.polygons) if o.data else 0)
    try:
        bpy.ops.object.select_all(action="DESELECT")
    except RuntimeError:
        pass
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = target
    try:
        bpy.ops.object.join()
    except RuntimeError as e:
        sys.stderr.write(f"[warn] join failed: {e}\n")
    return target


def _attach_preview(obj: bpy.types.Object, icon_path: Path) -> bool:
    if not icon_path.is_file():
        return False
    try:
        with bpy.context.temp_override(id=obj):
            bpy.ops.ed.lib_id_load_custom_preview(filepath=str(icon_path))
        return True
    except Exception as e:
        sys.stderr.write(f"[warn] preview load failed for {obj.name}: {e}\n")
        return False


def _mark_as_asset(obj: bpy.types.Object, *, catalog_id: str, catalog_path: str,
                   description: str, tags: list[str], icon_path: Path | None) -> dict:
    obj.asset_mark()
    ad = obj.asset_data
    # Blender stores both UUID and a human path "fallback" in the .blend.
    ad.catalog_id = catalog_id
    try:
        ad.catalog_simple_name = catalog_path
    except AttributeError:
        # Older Blender API may not expose this; ignore.
        pass
    if description:
        ad.description = description
    for tag in tags:
        if tag and tag not in {t.name for t in ad.tags}:
            ad.tags.new(tag)
    preview_attached = False
    if icon_path is not None:
        preview_attached = _attach_preview(obj, icon_path)
    return {"preview_attached": preview_attached}


def _save_blend(blend_path: Path) -> None:
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    # Suppress .blend1 backup writes -- they double our shipped payload.
    try:
        bpy.context.preferences.filepaths.save_version = 0
    except Exception:
        pass
    bpy.ops.wm.save_as_mainfile(
        filepath=str(blend_path),
        compress=True,
        copy=False,
        relative_remap=True,
    )


def main() -> int:
    t0 = time.time()
    try:
        args = _parse_args()
        task = json.loads(Path(args.task_file).read_text(encoding="utf-8"))

        source_root = Path(task["source_root"]).resolve()
        data_roots = [Path(root).resolve() for root in task.get("data_roots", [])]
        materials_blend = Path(task["materials_blend"]).resolve()
        materials_manifest_raw = task.get("materials_manifest")
        materials_manifest = Path(materials_manifest_raw).resolve() if materials_manifest_raw else None
        out_blend = Path(task["out_blend"]).resolve()
        entry = task["entry"]
        catalog_id = task["catalog_id"]
        catalog_path = task["catalog_path"]
        icon_path_raw = task.get("icon_path")
        icon_path = Path(icon_path_raw).resolve() if icon_path_raw else None
        tags = list(task.get("tags") or [])
        description = task.get("description") or ""
        if "material_mode" in task:
            material_mode = str(task.get("material_mode") or "fallback")
        else:
            material_mode = "fallback" if bool(task.get("pack_unmatched_textures", True)) else "light"
        if material_mode not in {"fallback", "light", "none"}:
            material_mode = "fallback"
        pack_unmatched_textures = bool(task.get("pack_unmatched_textures", material_mode == "fallback"))
        asset_stem = task.get("asset_stem") or ""
        asset_metadata = dict(task.get("asset_metadata") or {})

        model_rel = entry["path"]

        _enable_required_addons()
        _clear_scene()

        component_specs = list(asset_metadata.get("components") or [])
        if not component_specs:
            component_specs = [{
                "component_name": "primary",
                "component_type": "Model",
                "source_entry": entry,
                "source_root": str(source_root),
                "transform": {},
            }]

        component_reports: list[dict] = []
        imported_objects: list[bpy.types.Object] = []
        for component in component_specs:
            component_source_root = Path(component.get("source_root") or source_root).resolve()
            imported, report = _import_component(
                component=component,
                source_root=component_source_root,
                data_roots=data_roots,
                materials_blend=materials_blend,
                materials_manifest=materials_manifest,
                material_mode=material_mode,
                pack_unmatched_textures=pack_unmatched_textures,
            )
            imported_objects.extend(imported)
            component_reports.append(report)

        # Optional: collapse multi-mesh imports into one object so the asset
        # is a single drag-drop unit.
        _join_meshes_if_multiple()
        asset_obj = _pick_asset_object()
        if asset_obj is None:
            raise RuntimeError("no mesh objects after import; cannot mark asset")

        # In catalog-target mode the asset name is the BuildingPieceData stem,
        # not necessarily the source SM stem. This lets shared meshes become
        # distinct drag-drop assets with distinct runtime indexes.
        stem = asset_stem or Path(model_rel).stem
        asset_obj.name = stem
        if asset_obj.data is not None:
            asset_obj.data.name = stem

        asset_kind = asset_metadata.get("asset_kind") or "model"
        asset_obj["rsdw_asset_kind"] = str(asset_kind)
        if asset_metadata.get("source_model_refs"):
            asset_obj["rsdw_source_model_refs"] = json.dumps(asset_metadata["source_model_refs"], ensure_ascii=False)
        class_name = asset_metadata.get("class_name") or ""
        if class_name:
            asset_obj["rsdw_class_name"] = str(class_name)
        if asset_metadata.get("bp_class"):
            asset_obj["rsdw_bp_class"] = str(asset_metadata["bp_class"])
        if asset_metadata.get("runtime_path"):
            asset_obj["rsdw_runtime_path"] = str(asset_metadata["runtime_path"])
        if asset_metadata.get("bp_json_relative"):
            asset_obj["rsdw_bp_json_relative"] = str(asset_metadata["bp_json_relative"])
        if asset_metadata.get("assembly_status"):
            asset_obj["rsdw_assembly_status"] = str(asset_metadata["assembly_status"])
        if asset_metadata.get("piece_data_index") is not None:
            asset_obj["rsdw_piece_data_index"] = int(asset_metadata["piece_data_index"])
        if asset_metadata.get("piece_data_name"):
            asset_obj["rsdw_piece_data_name"] = str(asset_metadata["piece_data_name"])
        if asset_metadata.get("item_json_relative"):
            asset_obj["rsdw_item_json_relative"] = str(asset_metadata["item_json_relative"])
        if asset_metadata.get("item_type"):
            asset_obj["rsdw_item_type"] = str(asset_metadata["item_type"])
        if asset_metadata.get("item_name"):
            asset_obj["rsdw_item_name"] = str(asset_metadata["item_name"])
        if asset_metadata.get("primary_model_ref"):
            asset_obj["rsdw_primary_model_ref"] = str(asset_metadata["primary_model_ref"])
        if asset_metadata.get("asset_stem"):
            asset_obj["rsdw_catalog_asset_stem"] = str(asset_metadata["asset_stem"])
        if asset_metadata.get("source_sm_stem"):
            asset_obj["rsdw_source_sm_stem"] = str(asset_metadata["source_sm_stem"])
        if asset_metadata.get("display_name"):
            asset_obj["rsdw_display_name"] = str(asset_metadata["display_name"])

        mark_report = _mark_as_asset(
            asset_obj,
            catalog_id=catalog_id,
            catalog_path=catalog_path,
            description=description,
            tags=tags,
            icon_path=icon_path,
        )

        _save_blend(out_blend)

        _emit_result({
            "status": "success",
            "model_rel": model_rel,
            "out_blend": str(out_blend),
            "asset_object": asset_obj.name,
            "asset_metadata": asset_metadata,
            "catalog_path": catalog_path,
            "component_reports": component_reports,
            "component_count": len(component_reports),
            "slot_count": sum(int(report.get("slot_count") or 0) for report in component_reports),
            "linked_materials": sorted({
                name
                for report in component_reports
                for name in (report.get("linked_materials") or [])
            }),
            "swapped_slots": sum(int(report.get("swapped_slots") or 0) for report in component_reports),
            "unmatched_slots": sorted({
                name
                for report in component_reports
                for name in (report.get("unmatched_slots") or [])
            }),
            "unmatched_built": [report.get("unmatched_built") for report in component_reports if report.get("unmatched_built")],
            "preview_attached": mark_report["preview_attached"],
            "duration_s": round(time.time() - t0, 3),
        })
        return 0
    except Exception as e:
        _emit_result({
            "status": "failed",
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "duration_s": round(time.time() - t0, 3),
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
