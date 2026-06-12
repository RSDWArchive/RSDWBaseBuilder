"""
Blender-side worker for the asset library: per .uemodel piece, build a tiny
.blend that links its materials from the shared _Materials.blend, marks the
imported object as an asset, attaches or generates a preview, and writes a
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
import colorsys
import hashlib
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

import bpy
from mathutils import Matrix


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tools" / "ModelData"))
sys.path.insert(0, str(_REPO_ROOT / "tools" / "AssetLibrary"))

import BuildGLBWorker as base  # noqa: E402
from BuildGLBWorker import (  # noqa: E402
    _build_materials,
    _clear_scene,
    _enable_required_addons,
    _ensure_use_nodes,
    _get_bsdf,
    _import_uemodel,
    _load_material_json_data,
    _read_uemodel_materials,
    _resolve_material_json_for_slot,
)
from OptimizedTextures import compact_web_texture_stats, install_web_texture_loader  # noqa: E402


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


def _identity_matrix4() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _mat3_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [sum(a[row][idx] * b[idx][col] for idx in range(3)) for col in range(3)]
        for row in range(3)
    ]


def _quat_to_matrix3(quat: dict) -> list[list[float]]:
    x = float(quat.get("X", 0.0) or 0.0)
    y = float(quat.get("Y", 0.0) or 0.0)
    z = float(quat.get("Z", 0.0) or 0.0)
    w = float(quat.get("W", 1.0) or 1.0)
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length <= 0.0:
        return [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    x /= length
    y /= length
    z /= length
    w /= length
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return [
        [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
        [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
        [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
    ]


def _rotator_to_matrix3(rot: dict) -> list[list[float]]:
    pitch = math.radians(float(rot.get("Pitch", 0.0) or 0.0))
    yaw = math.radians(float(rot.get("Yaw", 0.0) or 0.0))
    roll = math.radians(float(rot.get("Roll", 0.0) or 0.0))

    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cr, sr = math.cos(roll), math.sin(roll)

    rz = [
        [cy, -sy, 0.0],
        [sy, cy, 0.0],
        [0.0, 0.0, 1.0],
    ]
    ry = [
        [cp, 0.0, sp],
        [0.0, 1.0, 0.0],
        [-sp, 0.0, cp],
    ]
    rx = [
        [1.0, 0.0, 0.0],
        [0.0, cr, -sr],
        [0.0, sr, cr],
    ]
    return _mat3_mul(_mat3_mul(rz, ry), rx)


def _matrix_from_component_parts(transform: dict, *, flip_pitch_roll: bool = False) -> list[list[float]]:
    loc = transform.get("location") or {}
    scale = transform.get("scale") or {}
    sx = float(scale.get("X", 1.0) or 1.0)
    sy = float(scale.get("Y", 1.0) or 1.0)
    sz = float(scale.get("Z", 1.0) or 1.0)

    rot = dict(transform.get("rotation") or {})
    if flip_pitch_roll:
        rot["Pitch"] = -float(rot.get("Pitch", 0.0) or 0.0)
        rot["Roll"] = -float(rot.get("Roll", 0.0) or 0.0)

    if not rot and isinstance(transform.get("rotation_quat"), dict):
        rot3 = _quat_to_matrix3(transform["rotation_quat"])
    else:
        rot3 = _rotator_to_matrix3(rot)

    m = _identity_matrix4()
    for row in range(3):
        m[row][0] = rot3[row][0] * sx
        m[row][1] = rot3[row][1] * sy
        m[row][2] = rot3[row][2] * sz
    m[0][3] = float(loc.get("X", 0.0) or 0.0)
    m[1][3] = float(loc.get("Y", 0.0) or 0.0)
    m[2][3] = float(loc.get("Z", 0.0) or 0.0)
    return m


def _apply_component_transform(
    objects: list[bpy.types.Object],
    transform: dict,
    *,
    flip_pitch_roll: bool = False,
) -> None:
    """Apply a conservative UE-relative transform to imported component roots.

    UE locations are centimeters. UEFormat imports geometry at 0.01 scale, so
    component locations are converted to meters here.
    """
    if not transform:
        return
    matrix_rows = None if flip_pitch_roll else transform.get("matrix")
    if matrix_rows:
        component_matrix = _blender_matrix_from_ue_matrix(matrix_rows)
        for obj in _component_roots(objects):
            obj.matrix_world = component_matrix @ obj.matrix_world
        return

    if flip_pitch_roll:
        component_matrix = _blender_matrix_from_ue_matrix(
            _matrix_from_component_parts(transform, flip_pitch_roll=True)
        )
        for obj in _component_roots(objects):
            obj.matrix_world = component_matrix @ obj.matrix_world
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


def _blender_matrix_from_ue_matrix(matrix_rows: object) -> Matrix:
    rows = list(matrix_rows or [])
    if len(rows) < 4:
        return Matrix.Identity(4)
    try:
        m = [[float(rows[row][col]) for col in range(4)] for row in range(4)]
    except Exception:
        return Matrix.Identity(4)

    # Target-builder matrices are UE-space, in centimeters, using the same
    # actor-root coordinate system as exported JSON. Convert with the Y mirror
    # and centimeter-to-meter scale used elsewhere in the addon.
    return Matrix((
        (m[0][0], -m[0][1], m[0][2], m[0][3] * 0.01),
        (-m[1][0], m[1][1], -m[1][2], -m[1][3] * 0.01),
        (m[2][0], -m[2][1], m[2][2], m[2][3] * 0.01),
        (0.0, 0.0, 0.0, 1.0),
    ))


def _remove_object(obj: bpy.types.Object) -> None:
    data = getattr(obj, "data", None)
    try:
        bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:
        return
    if data is not None and getattr(data, "users", 1) == 0:
        try:
            bpy.data.meshes.remove(data)
        except Exception:
            pass


def _bake_mesh_to_actor_root(obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> bool:
    if obj.type != "MESH" or obj.data is None:
        return False
    old_mesh = obj.data
    world = obj.matrix_world.copy()
    try:
        eval_obj = obj.evaluated_get(depsgraph)
        try:
            new_mesh = bpy.data.meshes.new_from_object(
                eval_obj,
                preserve_all_data_layers=True,
                depsgraph=depsgraph,
            )
        except TypeError:
            new_mesh = bpy.data.meshes.new_from_object(eval_obj, depsgraph=depsgraph)
    except Exception:
        new_mesh = old_mesh.copy()

    if new_mesh is None:
        return False
    new_mesh.name = old_mesh.name
    new_mesh.transform(world)

    obj.parent = None
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.data = new_mesh
    for modifier in list(obj.modifiers):
        try:
            obj.modifiers.remove(modifier)
        except Exception:
            pass
    for constraint in list(obj.constraints):
        try:
            obj.constraints.remove(constraint)
        except Exception:
            pass
    obj.matrix_world = Matrix.Identity(4)

    if old_mesh.users == 0:
        try:
            bpy.data.meshes.remove(old_mesh)
        except Exception:
            pass
    return True


def _asset_root_identity_errors(obj: bpy.types.Object | None, *, eps: float = 1e-5) -> list[str]:
    if obj is None:
        return ["missing asset object"]
    errors: list[str] = []
    if obj.type != "MESH":
        errors.append(f"asset object type is {obj.type!r}, expected 'MESH'")
    if obj.parent is not None:
        errors.append(f"asset object still has parent {obj.parent.name!r}")
    ident = Matrix.Identity(4)
    mw = obj.matrix_world
    for row in range(4):
        for col in range(4):
            if abs(float(mw[row][col]) - float(ident[row][col])) > eps:
                errors.append("asset object matrix_world is not identity")
                return errors
    return errors


def _normalize_visual_asset_root(schema: str) -> tuple[bpy.types.Object | None, dict]:
    mesh_objects = [obj for obj in list(bpy.data.objects) if obj.type == "MESH"]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    baked = 0
    failed: list[str] = []
    for obj in mesh_objects:
        if _bake_mesh_to_actor_root(obj, depsgraph):
            baked += 1
        else:
            failed.append(obj.name)

    removed_non_mesh = 0
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            _remove_object(obj)
            removed_non_mesh += 1

    asset_obj = _join_meshes_if_multiple()
    if asset_obj is not None:
        asset_obj.parent = None
        asset_obj.matrix_parent_inverse = Matrix.Identity(4)
        asset_obj.matrix_world = Matrix.Identity(4)

    errors = _asset_root_identity_errors(asset_obj)
    return asset_obj, {
        "schema": schema,
        "normalized": not errors and not failed,
        "baked_mesh_count": baked,
        "failed_meshes": failed,
        "removed_non_mesh_count": removed_non_mesh,
        "root_identity_ok": not errors,
        "root_identity_errors": errors,
    }


def _normalize_bp_asset_root() -> tuple[bpy.types.Object | None, dict]:
    return _normalize_visual_asset_root("RSDWBaseBuilder.BPRootNormalization.v1")


def _normalize_building_piece_visual_root() -> tuple[bpy.types.Object | None, dict]:
    return _normalize_visual_asset_root("RSDWBaseBuilder.BuildingPieceVisualRootNormalization.v1")


def _entry_material_refs(entry: dict) -> tuple[list[str], list[str]]:
    materials_block = entry.get("Materials", {}) or {}
    mi_paths_rel = list(
        materials_block.get("material_json_paths")
        or materials_block.get("material_instance_json_paths")
        or []
    )
    hybrid_paths_rel = list(entry.get("MaterialsHybrid", {}).get("texture_image_paths", []))
    return mi_paths_rel, hybrid_paths_rel


_BASE_COLOR_KEYS = (
    "BaseColor",
    "Base Color",
    "BaseColour",
    "Base Colour",
    "Color",
    "Colour",
    "Albedo",
    "Diffuse",
    "DiffuseColor",
    "Tint",
    "BaseColorTint",
)

_SEMANTIC_BASE_COLORS: list[tuple[tuple[str, ...], tuple[float, float, float, float]]] = [
    (("wood", "log", "timber", "oak", "yew", "ash"), (0.46, 0.30, 0.15, 1.0)),
    (("stone", "rock", "granite", "slate", "brick"), (0.48, 0.48, 0.44, 1.0)),
    (("metal", "iron", "steel", "bronze", "copper"), (0.58, 0.54, 0.48, 1.0)),
    (("leaf", "grass", "moss", "vine", "plant", "foliage"), (0.28, 0.48, 0.22, 1.0)),
    (("leather", "hide", "fur"), (0.42, 0.25, 0.13, 1.0)),
    (("cloth", "linen", "fabric", "canvas"), (0.58, 0.48, 0.36, 1.0)),
    (("bone", "skull"), (0.72, 0.67, 0.52, 1.0)),
    (("glass", "water", "ice", "crystal"), (0.42, 0.64, 0.78, 0.9)),
    (("fire", "flame", "ember", "torch"), (0.90, 0.42, 0.10, 1.0)),
]


def _color_key(text: object) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _rgba_from_value(value: object) -> tuple[float, float, float, float] | None:
    if isinstance(value, dict):
        source = value.get("SpecifiedColor") if isinstance(value.get("SpecifiedColor"), dict) else value
        keys = ("R", "G", "B", "A")
        if not all(key in source for key in keys[:3]):
            return None
        try:
            rgba = [float(source.get(key, 1.0 if key == "A" else 0.0)) for key in keys]
        except (TypeError, ValueError):
            return None
    elif isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            rgba = [float(value[0]), float(value[1]), float(value[2]), float(value[3]) if len(value) > 3 else 1.0]
        except (TypeError, ValueError):
            return None
    else:
        return None

    if max(rgba[:3]) > 1.0:
        rgba[:3] = [channel / 255.0 for channel in rgba[:3]]
    return tuple(_clamp01(channel) for channel in rgba)  # type: ignore[return-value]


def _base_color_from_material_json(mi_json_abs: Path | None) -> tuple[tuple[float, float, float, float] | None, str]:
    if mi_json_abs is None:
        return None, ""
    data = _load_material_json_data(mi_json_abs)
    if not data:
        return None, ""
    colors = (data.get("Parameters") or {}).get("Colors") or {}
    if not isinstance(colors, dict):
        return None, ""

    wanted = {_color_key(key): key for key in _BASE_COLOR_KEYS}
    for raw_key, raw_value in colors.items():
        normalized = _color_key(raw_key)
        if normalized not in wanted:
            continue
        rgba = _rgba_from_value(raw_value)
        if rgba is not None:
            return rgba, str(raw_key)
    return None, ""


def _fallback_base_color(slot_name: str, material_path: str) -> tuple[float, float, float, float]:
    text = f"{slot_name} {material_path}".lower()
    for needles, rgba in _SEMANTIC_BASE_COLORS:
        if any(needle in text for needle in needles):
            return rgba

    digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).digest()
    hue = int.from_bytes(digest[:2], "big") / 65535.0
    saturation = 0.32 + (digest[2] / 255.0) * 0.18
    value = 0.58 + (digest[3] / 255.0) * 0.20
    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
    return (r, g, b, 1.0)


def _assign_flat_base_color(mat: bpy.types.Material, rgba: tuple[float, float, float, float]) -> None:
    mat.diffuse_color = rgba
    _ensure_use_nodes(mat)
    bsdf = _get_bsdf(mat)
    if bsdf is None:
        return
    if "Base Color" in bsdf.inputs:
        bsdf.inputs["Base Color"].default_value = rgba
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.82
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = rgba[3]
        if rgba[3] < 1.0:
            mat.blend_method = "BLEND"


def _build_base_color_materials(
    mat_slots: list[dict],
    mi_paths_rel: list[str],
    source_root: Path,
    data_roots: list[Path] | None = None,
) -> tuple[str, list[dict]]:
    reports: list[dict] = []
    built = 0
    missing = 0

    for slot in mat_slots:
        slot_name = slot.get("name") or ""
        slot_path = slot.get("path") or ""
        mat = bpy.data.materials.get(slot_name) if slot_name else None
        report = {"slot": slot_name, "material_path": slot_path}
        if mat is None:
            missing += 1
            reports.append({**report, "source": "missing_material"})
            continue

        mi_abs = _resolve_material_json_for_slot(slot_name, slot_path, mi_paths_rel, source_root, data_roots)
        rgba, color_param = _base_color_from_material_json(mi_abs)
        color_source = "mi_parameter" if rgba is not None else "fallback"
        if rgba is None:
            rgba = _fallback_base_color(slot_name, slot_path)

        _assign_flat_base_color(mat, rgba)
        built += 1
        reports.append({
            **report,
            "source": "base_color",
            "mi": mi_abs.name if mi_abs else None,
            "color_source": color_source,
            "color_param": color_param,
            "color": [round(channel, 4) for channel in rgba],
        })

    if built and not missing:
        overall = "base_color"
    elif built:
        overall = "mixed"
    else:
        overall = "none"
    return overall, reports


def _import_component(
    *,
    component: dict,
    source_root: Path,
    data_roots: list[Path],
    materials_blend: Path,
    materials_manifest: Path | None,
    material_mode: str,
    pack_unmatched_textures: bool,
    flip_component_pitch_roll: bool,
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
    _apply_component_transform(
        imported,
        component.get("transform") or {},
        flip_pitch_roll=flip_component_pitch_roll,
    )

    linked: dict[str, bpy.types.Material] = {}
    swapped = 0
    unmatched = sorted(set(slot_names))
    unmatched_built: dict | None = None
    base_color_built: dict | None = None
    if material_mode == "base-color":
        overall, reports = _build_base_color_materials(
            mat_slots, mi_paths_rel, source_root, data_roots,
        )
        base_color_built = {"overall": overall, "reports": reports}
        unmatched = sorted({
            report.get("slot") or ""
            for report in reports
            if report.get("source") != "base_color" and report.get("slot")
        })
    elif material_mode != "none":
        if materials_manifest is not None and materials_manifest.is_file():
            linked = _link_manifest_materials(materials_manifest, slot_names)
        else:
            linked = _link_shared_materials(materials_blend, slot_names)
        swapped, unmatched = _swap_in_linked_materials(linked, imported)

    if unmatched and material_mode in {"fallback", "optimized-pbr"}:
        unmatched_set = set(unmatched)
        mat_slots_to_build = [
            slot for slot in mat_slots
            if (slot.get("name") or "") in unmatched_set
        ]
        overall, reports = _build_materials(
            mat_slots_to_build, mi_paths_rel, hybrid_paths_rel, source_root, data_roots,
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
        "base_color_built": base_color_built,
        "transform_applied": bool(component.get("transform")),
        "flip_pitch_roll": bool(flip_component_pitch_roll),
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


def _attach_preview(obj: bpy.types.Object, icon_path: Path) -> tuple[bool, str | None]:
    if not icon_path.is_file():
        return False, "icon file missing"
    try:
        with bpy.context.temp_override(id=obj):
            bpy.ops.ed.lib_id_load_custom_preview(filepath=str(icon_path))
        return True, None
    except Exception as e:
        sys.stderr.write(f"[warn] preview load failed for {obj.name}: {e}\n")
        return False, str(e)


def _generate_preview(obj: bpy.types.Object) -> tuple[bool, str | None]:
    try:
        with bpy.context.temp_override(id=obj):
            bpy.ops.ed.lib_id_generate_preview()
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        return True, None
    except Exception as e:
        sys.stderr.write(f"[warn] preview generation failed for {obj.name}: {e}\n")
        return False, str(e)


def _mark_as_asset(obj: bpy.types.Object, *, catalog_id: str, catalog_path: str,
                   description: str, tags: list[str], icon_path: Path | None,
                   preview_mode: str) -> dict:
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

    preview_mode = (preview_mode or ("custom_icon" if icon_path else "generated")).strip().lower()
    preview_attached = False
    preview_generated = False
    preview_source = "none"
    preview_error = None

    if preview_mode == "custom_icon" and icon_path is not None:
        preview_attached, preview_error = _attach_preview(obj, icon_path)
        if preview_attached:
            preview_source = "custom_icon"
        else:
            # Forcing lib_id_generate_preview in background Blender can crash
            # after save on some linked/skinned BP assets. Leaving no custom
            # preview lets Blender's asset browser generate its normal object
            # thumbnail when the library is opened.
            preview_generated = True
            preview_source = "blender_default_after_custom_icon_failed"
    elif preview_mode != "none":
        preview_generated = True
        preview_source = "blender_default"

    return {
        "preview_attached": preview_attached,
        "preview_generated": preview_generated,
        "preview_source": preview_source,
        "preview_error": preview_error,
    }


def _material_quality(component_reports: list[dict]) -> dict:
    mi_slots = 0
    hybrid_slots = 0
    base_color_slots = 0
    none_slots = 0
    texture_slots = 0
    color_only_slots = 0
    material_report_count = 0
    fallback_report_count = 0

    for component in component_reports:
        base_color = component.get("base_color_built") or {}
        for report in base_color.get("reports") or []:
            material_report_count += 1
            if report.get("source") == "base_color":
                base_color_slots += 1
                color_only_slots += 1
            else:
                none_slots += 1

        built = component.get("unmatched_built") or {}
        for report in built.get("reports") or []:
            material_report_count += 1
            fallback_report_count += 1
            source = report.get("source")
            roles = list(report.get("roles") or [])
            params = list(report.get("params") or [])
            hybrid = report.get("hybrid_fallback") or {}
            hybrid_roles = list(hybrid.get("roles") or [])
            if source == "mi" and (roles or params):
                mi_slots += 1
                if roles:
                    texture_slots += 1
                elif params:
                    color_only_slots += 1
            elif source == "hybrid" and roles:
                hybrid_slots += 1
                texture_slots += 1
            elif hybrid.get("source") == "hybrid" and hybrid_roles:
                hybrid_slots += 1
                texture_slots += 1
            else:
                none_slots += 1

    linked_slot_count = sum(int(report.get("swapped_slots") or 0) for report in component_reports)
    slot_count = sum(int(report.get("slot_count") or 0) for report in component_reports)
    return {
        "slot_count": slot_count,
        "linked_slot_count": linked_slot_count,
        "material_report_count": material_report_count,
        "fallback_built_report_count": fallback_report_count,
        "base_color_slot_count": base_color_slots,
        "mi_slot_count": mi_slots,
        "hybrid_slot_count": hybrid_slots,
        "texture_slot_count": texture_slots,
        "color_only_slot_count": color_only_slots,
        "none_slot_count": none_slots,
        "materialized_slot_count": linked_slot_count + mi_slots + hybrid_slots + base_color_slots,
    }


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
        preview_mode = str(task.get("preview_mode") or ("custom_icon" if icon_path else "generated"))
        icon_source = str(task.get("icon_source") or "")
        tags = list(task.get("tags") or [])
        description = task.get("description") or ""
        if "material_mode" in task:
            material_mode = str(task.get("material_mode") or "fallback")
        else:
            material_mode = "fallback" if bool(task.get("pack_unmatched_textures", True)) else "light"
        if material_mode not in {"fallback", "optimized-pbr", "base-color", "light", "none"}:
            material_mode = "fallback"
        pack_unmatched_textures = bool(task.get("pack_unmatched_textures", material_mode in {"fallback", "optimized-pbr"}))
        asset_stem = task.get("asset_stem") or ""
        asset_metadata = dict(task.get("asset_metadata") or {})
        web_assets_manifest_raw = task.get("web_assets_manifest")
        web_assets_manifest = Path(web_assets_manifest_raw).resolve() if web_assets_manifest_raw else None

        model_rel = entry["path"]

        _enable_required_addons()
        _clear_scene()
        web_texture_stats = install_web_texture_loader(
            base,
            source_root=source_root,
            data_roots=data_roots,
            manifest_path=web_assets_manifest,
        )

        asset_kind = asset_metadata.get("asset_kind") or "model"
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
                flip_component_pitch_roll=asset_kind == "building_piece",
            )
            imported_objects.extend(imported)
            component_reports.append(report)

        bp_root_report: dict | None = None
        building_piece_root_report: dict | None = None

        # BP assets represent Unreal actors. Bake component offsets into the
        # mesh data so the Blender asset object itself stays at the actor root.
        if asset_kind == "bp":
            asset_obj, bp_root_report = _normalize_bp_asset_root()
        elif (
            asset_kind == "building_piece"
            and asset_metadata.get("building_piece_visual_transform_source") == "matching_bp_visual_component"
        ):
            # Some buildable actors rotate/offset their visible mesh under the
            # actor root. Bake that visual transform into the mesh so imported
            # objects still export only their game actor/root transform.
            asset_obj, building_piece_root_report = _normalize_building_piece_visual_root()
        else:
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

        asset_obj["rsdw_asset_kind"] = str(asset_kind)
        if asset_kind == "bp":
            asset_obj["rsdw_bp_root_normalized"] = bool(bp_root_report and bp_root_report.get("normalized"))
            asset_obj["rsdw_bp_root_normalization"] = "baked_mesh_v1"
            if bp_root_report:
                asset_obj["rsdw_bp_root_identity_ok"] = bool(bp_root_report.get("root_identity_ok"))
        if asset_kind == "building_piece" and building_piece_root_report is not None:
            asset_obj["rsdw_building_piece_visual_root_normalized"] = bool(building_piece_root_report.get("normalized"))
            asset_obj["rsdw_building_piece_visual_root_normalization"] = "baked_mesh_v1"
            asset_obj["rsdw_building_piece_visual_root_identity_ok"] = bool(
                building_piece_root_report.get("root_identity_ok")
            )
        if asset_metadata.get("building_piece_visual_transform_source"):
            asset_obj["rsdw_building_piece_visual_transform_source"] = str(
                asset_metadata["building_piece_visual_transform_source"]
            )
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
        if preview_mode:
            asset_obj["rsdw_preview_mode"] = preview_mode
        if icon_source:
            asset_obj["rsdw_icon_source"] = icon_source
        if icon_path is not None:
            asset_obj["rsdw_icon_path"] = str(icon_path)

        mark_report = _mark_as_asset(
            asset_obj,
            catalog_id=catalog_id,
            catalog_path=catalog_path,
            description=description,
            tags=tags,
            icon_path=icon_path,
            preview_mode=preview_mode,
        )
        asset_obj["rsdw_preview_source"] = str(mark_report.get("preview_source") or "")

        _save_blend(out_blend)

        material_quality = _material_quality(component_reports)

        _emit_result({
            "status": "success",
            "model_rel": model_rel,
            "out_blend": str(out_blend),
            "asset_object": asset_obj.name,
            "asset_metadata": asset_metadata,
            "catalog_path": catalog_path,
            "component_reports": component_reports,
            "component_count": len(component_reports),
            "building_piece_root_normalization": building_piece_root_report,
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
            "base_color_built": [report.get("base_color_built") for report in component_reports if report.get("base_color_built")],
            "preview_attached": mark_report["preview_attached"],
            "preview_generated": mark_report["preview_generated"],
            "preview_source": mark_report["preview_source"],
            "preview_error": mark_report["preview_error"],
            "bp_root_normalized": bool(bp_root_report and bp_root_report.get("normalized")),
            "bp_root_audit": bp_root_report,
            "material_quality": material_quality,
            "web_texture_stats": compact_web_texture_stats(web_texture_stats),
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
