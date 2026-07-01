"""RSDW Base Builder Blender extension.

Combines three things:
  1. Auto-registers this folder as a Blender Asset Library on enable.
  2. Adds an N-panel (3D Viewport > Sidebar > RSDW) with operators to
     import/export player base layouts captured by the in-game tool.
  3. Imports a building JSON file (`rsdwtools.buildings.v1`) by linking
     the matching `<SM_*>.blend` from this library for every piece, then
     placing the linked instance with the recorded transform.

Coordinate system mapping
-------------------------
Unreal Engine: left-handed, Z-up, units = centimeters
                X = forward, Y = right, Z = up
                Yaw is rotation around Z (degrees, +CCW looking down -Z)
Blender:       right-handed, Z-up, units = meters
                X = right, Y = forward, Z = up

Conversion used:
    bx =  x_ue / 100
    by = -y_ue / 100      # flip Y to convert handedness
    bz =  z_ue / 100
    yaw_b = -yaw_ue        # negate to compensate for Y flip

Pieces are recentered around the median X/Y so the imported base sits
near the world origin instead of at the absolute world coords (which can
be hundreds of meters away).
"""

# NOTE: do NOT add `from __future__ import annotations` here. Blender's
# bpy.props decorator-style PropertyGroup definitions read the class
# annotations at register() time and would fail to resolve string-form
# names like `BoolProperty` against the module globals.

import json
import math
import os
import shutil
import time

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Euler, Matrix, Quaternion, Vector


ASSET_LIBRARY_NAME = "RSDW Base Builder"
PANEL_CATEGORY = "RSDW Base Builder"
TEMPLATE_BLEND_REL = os.path.join("templates", "basebuilding.blend")
BPMAP_JSON_REL = os.path.join("data", "BPMap.json")
SNAPS_JSON_REL = os.path.join("data", "Snaps.json")
PIECE_DATA_JSON_REL = os.path.join("data", "PieceDataMap.json")
STABILITY_JSON_REL = os.path.join("data", "StabilityMap.json")
STABILITY_PROFILE_JSON_REL = os.path.join("data", "StabilityProfileMap.json")
COLLECTION_NAME_PREFIX = "RSDW_Building_"

# Stability fallback for pieces whose class isn't in StabilityMap.json.
# 3000 sits above all observed per-class maxes (~3215) and well above the
# game's 'supported' threshold for any structural piece. The game clamps
# to the per-piece-data max on load, so over-shooting is harmless.
DEFAULT_STABILITY = 3000

# Blender does not expose Assign Shortcut on every add-on panel button, so we
# register an editable keymap entry for the diagnose helper.
_addon_keymaps: list = []


# ---------- helpers ----------

def _addon_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _bpmap_path() -> str:
    return os.path.join(_addon_dir(), BPMAP_JSON_REL)


_bpmap_cache: dict | None = None
_blend_index_cache: dict | None = None
_snaps_cache: dict | None = None
_rev_bpmap_cache: dict | None = None
_piece_data_cache: dict | None = None
_stability_cache: dict | None = None
_stability_profile_cache: dict | None = None


def _load_bpmap() -> dict:
    global _bpmap_cache
    if _bpmap_cache is None:
        path = _bpmap_path()
        if not os.path.isfile(path):
            _bpmap_cache = {}
        else:
            with open(path, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            _bpmap_cache = dict(d.get("mapping") or {})
    return _bpmap_cache


def _load_snaps() -> dict:
    global _snaps_cache
    if _snaps_cache is None:
        path = os.path.join(_addon_dir(), SNAPS_JSON_REL)
        if not os.path.isfile(path):
            _snaps_cache = {}
        else:
            with open(path, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            _snaps_cache = dict(d.get("pieces") or {})
    return _snaps_cache


def _reverse_bpmap() -> dict:
    """SM_stem -> first matching BP class_name (e.g. 'BP_Foo_C')."""
    global _rev_bpmap_cache
    if _rev_bpmap_cache is None:
        rev: dict = {}
        for cls, mesh in _load_bpmap().items():
            rev.setdefault(mesh, cls)
        _rev_bpmap_cache = rev
    return _rev_bpmap_cache


def _load_piece_data_map() -> dict:
    """Short BP class name -> {piece_data_index, piece_data_name}.

    Generated from the runtime building catalog by
    tools/AssetLibrary/BuildPieceDataMap.py. Used by the export
    operator to fill in piece_data_* for drag-dropped pieces.
    """
    global _piece_data_cache
    if _piece_data_cache is None:
        path = os.path.join(_addon_dir(), PIECE_DATA_JSON_REL)
        if not os.path.isfile(path):
            _piece_data_cache = {}
        else:
            with open(path, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            _piece_data_cache = dict(d.get("mapping") or {})
    return _piece_data_cache


def _load_stability_map() -> dict:
    """Short BP class name -> {max, min, samples} stability values.

    Harvested offline from the example building JSONs by
    tools/AssetLibrary/BuildStabilityMap.py. Used to seed a sensible
    'fully supported' value on Blender-built pieces that have no
    runtime-propagated stability.
    """
    global _stability_cache
    if _stability_cache is None:
        path = os.path.join(_addon_dir(), STABILITY_JSON_REL)
        if not os.path.isfile(path):
            _stability_cache = {}
        else:
            with open(path, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            _stability_cache = dict(d.get("mapping") or {})
    return _stability_cache


def _recommended_stability(short_class_name: str) -> int:
    """Return the recommended stability value for a piece of the given
    short BP class name. Falls back to ``DEFAULT_STABILITY`` if unknown."""
    entry = _load_stability_map().get(short_class_name)
    if entry is None:
        return DEFAULT_STABILITY
    try:
        return int(round(float(entry.get("max", DEFAULT_STABILITY))))
    except Exception:
        return DEFAULT_STABILITY


def _load_stability_profile_map() -> dict:
    """Returns the full StabilityProfileMap doc:
      { 'profiles': { name: {max,min,vert_loss,horiz_loss}, ... },
        'default_snapping_radius_cm': float,
        'mapping': { BP_class_C: {profile, snapping_radius_cm}, ... } }

    Harvested from the game archive by
    tools/AssetLibrary/BuildStabilityProfileMap.py. Drives the
    structural-stability validator.
    """
    global _stability_profile_cache
    if _stability_profile_cache is None:
        path = os.path.join(_addon_dir(), STABILITY_PROFILE_JSON_REL)
        if not os.path.isfile(path):
            _stability_profile_cache = {
                "profiles": {},
                "default_snapping_radius_cm": 80.0,
                "mapping": {},
            }
        else:
            with open(path, "r", encoding="utf-8") as fh:
                _stability_profile_cache = json.load(fh)
    return _stability_profile_cache


def _resolve_stability_for_export(obj, short_class_name: str) -> int:
    """Pick the stability value to write for an object on export.

    Uses the stamped ``rsdw_stability`` custom prop when present and
    positive (round-trip case), otherwise falls back to the per-class
    recommended max so Blender-built pieces ship with realistic numbers
    instead of stability=1 (which the game treats as 'broken')."""
    raw = obj.get("rsdw_stability")
    if isinstance(raw, (int, float)) and raw > 0:
        return int(round(float(raw)))
    return _recommended_stability(short_class_name)


def _build_blend_index() -> dict:
    """Index every <stem>.blend under the addon folder by its stem (case-insensitive)."""
    global _blend_index_cache
    if _blend_index_cache is None:
        idx: dict = {}
        root = _addon_dir()
        for dirpath, _dn, fns in os.walk(root):
            for fn in fns:
                if not fn.lower().endswith(".blend"):
                    continue
                stem = fn[:-6]
                if stem.startswith("_"):
                    continue
                idx.setdefault(stem.lower(), os.path.join(dirpath, fn))
        _blend_index_cache = idx
    return _blend_index_cache


def _shorten_class(class_name: str) -> str:
    """`BlueprintGeneratedClass /Game/.../BP_Foo.BP_Foo_C` -> `BP_Foo_C`."""
    if not class_name:
        return ""
    tail = class_name.rsplit("/", 1)[-1]
    return tail.rsplit(".", 1)[-1]


def _asset_stem_from_piece_data_name(piece_data_name: str) -> str:
    text = (piece_data_name or "").removeprefix("BuildingPieceData ").strip()
    if not text:
        return ""
    return text.rsplit("/", 1)[-1].split(".", 1)[0]


def _resolve_mesh_stem(class_name: str):
    short = _shorten_class(class_name)
    if not short:
        return None
    return _load_bpmap().get(short)


def _ensure_collection(name: str) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _unique_collection_name(base_name: str) -> str:
    if base_name not in bpy.data.collections:
        return base_name
    idx = 1
    while True:
        name = f"{base_name}.{idx:03d}"
        if name not in bpy.data.collections:
            return name
        idx += 1


def _find_layer_collection(layer_collection, collection):
    if layer_collection.collection == collection:
        return layer_collection
    for child in layer_collection.children:
        found = _find_layer_collection(child, collection)
        if found is not None:
            return found
    return None


def _set_active_collection(context, collection) -> None:
    try:
        context.view_layer.update()
        layer_collection = _find_layer_collection(
            context.view_layer.layer_collection, collection,
        )
        if layer_collection is not None:
            context.view_layer.active_layer_collection = layer_collection
    except Exception:
        pass


def _collection_objects_recursive(collection) -> list:
    seen_ids: set = set()
    out: list = []

    def _walk(coll):
        for obj in coll.objects:
            if id(obj) in seen_ids:
                continue
            seen_ids.add(id(obj))
            out.append(obj)
        for child in coll.children:
            _walk(child)

    if collection is not None:
        _walk(collection)
    return out


def _scene_objects(context) -> list:
    try:
        return list(context.scene.objects)
    except Exception:
        return []


def _collection_parent_map(scene) -> dict:
    parents: dict = {}

    def _walk(coll):
        for child in coll.children:
            parents[child] = coll
            _walk(child)

    try:
        _walk(scene.collection)
    except Exception:
        pass
    return parents


def _collection_lineage(collection, parent_map: dict) -> list:
    out = []
    seen: set[int] = set()
    cur = collection
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        out.append(cur)
        cur = parent_map.get(cur)
    return out


def _collection_has_export_metadata(collection) -> bool:
    if collection is None:
        return False
    return any(key in collection for key in (
        "rsdw_recenter_offset_ue",
        "rsdw_source_name",
        "rsdw_source_schema",
        "rsdw_anchor_piece_id",
    ))


def _export_metadata_collection_for_scope(context, objects: list, preferred=None):
    parent_map = _collection_parent_map(context.scene)

    def _nearest_metadata_collection(collection):
        for candidate in _collection_lineage(collection, parent_map):
            if _collection_has_export_metadata(candidate):
                return candidate
        return None

    for seed in (preferred, getattr(context, "collection", None)):
        candidate = _nearest_metadata_collection(seed)
        if candidate is not None:
            return candidate

    candidates = []
    seen_ids: set[int] = set()
    for obj in objects:
        for collection in getattr(obj, "users_collection", []) or []:
            candidate = _nearest_metadata_collection(collection)
            if candidate is not None and id(candidate) not in seen_ids:
                seen_ids.add(id(candidate))
                candidates.append(candidate)

    if len(candidates) == 1:
        return candidates[0]

    build_collections = [
        collection
        for collection in _build_collections_in_scene(context.scene)
        if _collection_has_export_metadata(collection)
    ]
    if len(build_collections) == 1:
        return build_collections[0]
    return preferred


def _has_rsdw_metadata(obj) -> bool:
    return any(key in obj for key in (
        "rsdw_asset_kind",
        "rsdw_class_name",
        "rsdw_bp_class",
        "rsdw_piece_data_index",
        "rsdw_piece_data_name",
        "rsdw_catalog_asset_stem",
        "rsdw_source_sm_stem",
        "rsdw_item_name",
        "rsdw_item_asset_name",
        "rsdw_item_asset_path",
        "rsdw_actor_class",
    ))


def _metadata_object_for(obj):
    if obj is None:
        return None
    if _has_rsdw_metadata(obj):
        return obj
    if obj.type == "EMPTY" and obj.instance_collection is not None:
        for candidate in obj.instance_collection.objects:
            if _has_rsdw_metadata(candidate):
                return candidate
    return obj


def _collection_has_rsdw_pieces(collection) -> bool:
    return any(
        _asset_kind_for_obj(obj) or _resolve_class_for_obj(obj)
        for obj in _collection_objects_recursive(collection)
    )


def _build_collections_in_scene(scene) -> list:
    out: list = []

    def _walk(coll):
        if coll.name.startswith(COLLECTION_NAME_PREFIX):
            out.append(coll)
        elif coll is not scene.collection and _collection_has_rsdw_pieces(coll):
            out.append(coll)
        for child in coll.children:
            _walk(child)

    _walk(scene.collection)
    return out


def _context_build_collection(context):
    coll = context.collection
    if coll is not None and coll.name.startswith(COLLECTION_NAME_PREFIX):
        return coll
    if coll is not None and coll is not context.scene.collection and _collection_has_rsdw_pieces(coll):
        return coll

    obj = context.active_object
    if obj is not None:
        for user_coll in obj.users_collection:
            if user_coll.name.startswith(COLLECTION_NAME_PREFIX) or _collection_has_rsdw_pieces(user_coll):
                return user_coll

    build_collections = _build_collections_in_scene(context.scene)
    if len(build_collections) == 1:
        return build_collections[0]
    return None


def _is_object_hidden_for_export(obj, context=None) -> bool:
    try:
        if obj.hide_get() or obj.hide_render:
            return True
    except Exception:
        pass
    if context is not None:
        try:
            return not bool(obj.visible_get(view_layer=context.view_layer))
        except TypeError:
            try:
                return not bool(obj.visible_get())
            except Exception:
                return False
        except Exception:
            return False
    return False


def _asset_kind_for_obj(obj) -> str:
    meta = _metadata_object_for(obj) or obj
    kind = str(meta.get("rsdw_asset_kind", "") or "").strip().lower()
    if kind:
        return kind
    if meta.get("rsdw_item_name") or meta.get("rsdw_item_asset_name") or meta.get("rsdw_item_asset_path"):
        return "item"
    if meta.get("rsdw_piece_data_name") or meta.get("rsdw_piece_data_index") is not None:
        return "building_piece"
    if meta.get("rsdw_actor_class") or meta.get("rsdw_runtime_path") or meta.get("rsdw_bp_json_relative"):
        return "bp"
    return ""


def _is_building_piece_obj(obj) -> bool:
    kind = _asset_kind_for_obj(obj)
    if kind:
        return kind == "building_piece"
    return bool(_resolve_class_for_obj(obj))


def _is_item_obj(obj) -> bool:
    return _asset_kind_for_obj(obj) == "item"


def _is_actor_obj(obj) -> bool:
    return _asset_kind_for_obj(obj) == "bp"


def _copy_custom_props(src, dst) -> None:
    for key in src.keys():
        try:
            dst[key] = src[key]
        except Exception:
            pass


def _load_asset_source(stem: str, blend_path: str, linked_assets: dict):
    cached = linked_assets.get(stem)
    if cached is not None:
        return cached
    with bpy.data.libraries.load(blend_path, link=True) as (df, dt):
        if stem in df.objects:
            dt.objects = [stem]
        else:
            dt.objects = list(df.objects)[:1]
    if not dt.objects or dt.objects[0] is None:
        return None
    src = dt.objects[0]
    linked_assets[stem] = src
    return src


def _instantiate_asset(
    *,
    stem: str,
    name: str,
    blend_index: dict,
    linked_assets: dict,
    collection,
):
    blend_path = blend_index.get(stem.lower())
    if not blend_path:
        return None, "missing_blend"
    src = _load_asset_source(stem, blend_path, linked_assets)
    if src is None:
        return None, "missing_object"

    inst = bpy.data.objects.new(name=name or stem, object_data=getattr(src, "data", None))
    if src.type == "EMPTY" and getattr(src, "instance_collection", None) is not None:
        inst.empty_display_type = src.empty_display_type
        inst.empty_display_size = src.empty_display_size
        inst.instance_type = "COLLECTION"
        inst.instance_collection = src.instance_collection
    _copy_custom_props(src, inst)
    collection.objects.link(inst)
    return inst, ""


def _ue_row_to_blender_matrix(
    row: dict,
    scale: float,
    ox: float,
    oy: float,
    oz: float,
    *,
    flip_roll: bool = True,
    flip_pitch: bool = True,
) -> Matrix:
    loc = Vector((
        (float(row.get("x", 0.0)) - ox) * scale,
        -(float(row.get("y", 0.0)) - oy) * scale,
        (float(row.get("z", 0.0)) - oz) * scale,
    ))
    # UE Rotator axes map through the same Y mirror used for position. Match
    # the browser builder's JSON boundary: pitch and roll are both mirrored,
    # while yaw is mirrored through Blender's Z axis below.
    roll_sign = -1.0 if flip_roll else 1.0
    pitch_sign = -1.0 if flip_pitch else 1.0
    rot = Euler((
        math.radians(roll_sign * float(row.get("roll", 0.0))),
        math.radians(pitch_sign * float(row.get("pitch", 0.0))),
        math.radians(-float(row.get("yaw", 0.0))),
    ), "XYZ")
    scl = Vector((
        float(row.get("scale_x", 1.0) or 1.0),
        float(row.get("scale_y", 1.0) or 1.0),
        float(row.get("scale_z", 1.0) or 1.0),
    ))
    return Matrix.LocRotScale(loc, rot.to_quaternion(), scl)


def _apply_ue_transform(
    obj,
    row: dict,
    scale: float,
    ox: float,
    oy: float,
    oz: float,
    *,
    flip_roll: bool = True,
    flip_pitch: bool = True,
) -> None:
    obj.matrix_world = _ue_row_to_blender_matrix(
        row,
        scale,
        ox,
        oy,
        oz,
        flip_roll=flip_roll,
        flip_pitch=flip_pitch,
    )


def _round_transform_value(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def _ue_transform_from_matrix(
    mw: Matrix,
    scale: float,
    ox: float,
    oy: float,
    oz: float,
    *,
    flip_roll: bool = True,
    flip_pitch: bool = True,
) -> dict:
    loc, rot, scl = mw.decompose()
    try:
        eul = rot.to_euler("XYZ")
    except Exception:
        eul = Euler((0.0, 0.0, 0.0), "XYZ")
    roll = math.degrees(eul.x)
    if flip_roll:
        roll = -roll
    pitch = math.degrees(eul.y)
    if flip_pitch:
        pitch = -pitch
    return {
        "x": _round_transform_value((loc.x / scale) + ox),
        "y": _round_transform_value((-loc.y / scale) + oy),
        "z": _round_transform_value((loc.z / scale) + oz),
        "pitch": _round_transform_value(pitch),
        "yaw": _round_transform_value(-math.degrees(eul.z)),
        "roll": _round_transform_value(roll),
        "scale_x": _round_transform_value(scl.x, 6),
        "scale_y": _round_transform_value(scl.y, 6),
        "scale_z": _round_transform_value(scl.z, 6),
    }


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


def _class_path_from_class_name(class_name: str) -> str:
    text = str(class_name or "").strip()
    prefix = "BlueprintGeneratedClass "
    if text.startswith(prefix):
        return text[len(prefix):].strip()
    return text


def _select_objects(context, objects: list) -> None:
    for obj in context.scene.objects:
        try:
            obj.select_set(False)
        except RuntimeError:
            pass
    for obj in objects:
        try:
            obj.select_set(True)
        except RuntimeError:
            pass
    if objects:
        try:
            context.view_layer.objects.active = objects[0]
        except Exception:
            pass


# ---------- asset library registration ----------

def _find_library(name: str):
    libs = bpy.context.preferences.filepaths.asset_libraries
    for lib in libs:
        if lib.name == name:
            return lib
    return None


def _register_asset_library() -> None:
    prefs = bpy.context.preferences.filepaths
    path = _addon_dir()
    existing = _find_library(ASSET_LIBRARY_NAME)
    if existing is not None:
        if os.path.normcase(existing.path) != os.path.normcase(path):
            existing.path = path
        return
    new_lib = prefs.asset_libraries.new(name=ASSET_LIBRARY_NAME, directory=path)
    if not new_lib.path:
        new_lib.path = path
    if new_lib.name != ASSET_LIBRARY_NAME:
        new_lib.name = ASSET_LIBRARY_NAME


def _unregister_asset_library() -> None:
    libs = bpy.context.preferences.filepaths.asset_libraries
    target = None
    for lib in libs:
        if lib.name == ASSET_LIBRARY_NAME:
            target = lib
            break
    if target is not None:
        libs.remove(target)


# ---------- properties ----------

class RSDWSettings(PropertyGroup):
    recenter: BoolProperty(
        name="Recenter at origin",
        description="Subtract the median X/Y/Z so the imported base sits near the world origin",
        default=True,
    )  # type: ignore[valid-type]
    include_ghosted: BoolProperty(
        name="Include ghosted pieces",
        description="Import pieces marked is_ghosted (preview/unbuilt)",
        default=False,
    )  # type: ignore[valid-type]
    scale: FloatProperty(
        name="Unit scale",
        description="UE units are centimeters; default 0.01 converts to meters",
        default=0.01,
        min=1e-6,
        soft_min=0.001,
        soft_max=1.0,
    )  # type: ignore[valid-type]
    auto_snap: BoolProperty(
        name="Auto-snap drops",
        description=(
            "When on, pieces dragged from the asset browser auto-snap to the "
            "nearest compatible plug on a sibling piece in the same collection"
        ),
        default=True,
        update=lambda self, ctx: _on_auto_snap_toggled(ctx),
    )  # type: ignore[valid-type]
    auto_snap_max_distance: FloatProperty(
        name="Auto-snap radius (m)",
        description="Only snap to plugs within this radius of the dropped piece",
        default=3.0,
        min=0.0,
        soft_max=20.0,
    )  # type: ignore[valid-type]
    auto_snap_align_rotation: BoolProperty(
        name="Align rotation on auto-snap",
        description=(
            "If on, also rotate the dropped piece to align with the plug. "
            "If off, only translate so the plug pair coincides"
        ),
        default=False,
    )  # type: ignore[valid-type]
    surface_snap_inset: FloatProperty(
        name="Surface fallback overlap (m)",
        description=(
            "For pieces without game snap-points, overlap bounding-box "
            "surfaces by this amount when snapping so tiny gaps do not "
            "break in-game support"
        ),
        default=0.005,
        min=0.0,
        soft_max=0.05,
    )  # type: ignore[valid-type]
    lint_tolerance: FloatProperty(
        name="Snap tolerance (m)",
        description=(
            "Two plugs are considered 'engaged' (snapped) when their world "
            "positions are within this distance. The game treats <=2cm as "
            "tightly snapped"
        ),
        default=0.02,
        min=0.0,
        soft_max=0.10,
    )  # type: ignore[valid-type]
    stability_fragile_hops: bpy.props.IntProperty(
        name="Fragile hop threshold",
        description=(
            "Flag structural pieces whose shortest path to an anchor "
            "(foundation/prop/farm-plot) is at least this many snaps "
            "deep. 0 = disable fragile flagging (only report fully "
            "isolated pieces)"
        ),
        default=0,
        min=0,
        soft_max=20,
    )  # type: ignore[valid-type]


# ---------- import operator ----------

class RSDW_OT_NewBuildCollection(Operator):
    bl_idname = "rsdw.new_build_collection"
    bl_label = "New Build"
    bl_description = (
        "Create and activate a fresh RSDW build collection with auto-snap on, "
        "ready for asset-browser drag and drop"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        settings: RSDWSettings = scene.rsdw_settings
        name = _unique_collection_name(COLLECTION_NAME_PREFIX + "NewBase")
        coll = bpy.data.collections.new(name)
        scene.collection.children.link(coll)
        _set_active_collection(context, coll)
        settings.auto_snap = True
        _on_auto_snap_toggled(context)
        self.report({"INFO"}, f"Ready: {coll.name}. Drag pieces from the RSDW asset library.")
        return {"FINISHED"}


class RSDW_OT_ImportBuildingJson(Operator):
    bl_idname = "rsdw.import_building_json"
    bl_label = "Import Dragonwilds Building JSON..."
    bl_description = (
        "Import a player base captured by the in-game RSDWTools building dump "
        "(schema rsdwtools.buildings.v1). Each piece is linked from the "
        "matching .blend in this library and placed with its recorded transform."
    )
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})  # type: ignore[valid-type]

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        path = bpy.path.abspath(self.filepath)
        if not os.path.isfile(path):
            self.report({"ERROR"}, f"File not found: {path}")
            return {"CANCELLED"}

        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except Exception as e:
            self.report({"ERROR"}, f"Failed to read JSON: {e}")
            return {"CANCELLED"}

        pieces = list(data.get("pieces") or [])
        items = list(data.get("items") or [])
        actors = list(data.get("actors") or [])
        if not pieces and not items and not actors:
            self.report({"WARNING"}, "No pieces, items, or actors found in JSON")
            return {"CANCELLED"}

        settings: RSDWSettings = context.scene.rsdw_settings
        bpmap = _load_bpmap()
        blend_index = _build_blend_index()
        if pieces and not bpmap:
            self.report({"ERROR"},
                        "BPMap.json missing from addon. Reinstall the extension.")
            return {"CANCELLED"}
        if not blend_index:
            self.report({"ERROR"},
                        "No .blend asset files found next to the addon.")
            return {"CANCELLED"}

        base_name = data.get("name") or os.path.splitext(os.path.basename(path))[0]
        coll = _ensure_collection(COLLECTION_NAME_PREFIX + base_name)
        _set_active_collection(context, coll)

        if not settings.include_ghosted:
            pieces = [p for p in pieces if not p.get("is_ghosted")]

        ox = oy = oz = 0.0
        recenter_rows = [*pieces, *items, *actors]
        if settings.recenter and recenter_rows:
            xs = sorted(float(p.get("x", 0.0)) for p in recenter_rows)
            ys = sorted(float(p.get("y", 0.0)) for p in recenter_rows)
            zs = sorted(float(p.get("z", 0.0)) for p in recenter_rows)
            mid = len(xs) // 2
            ox, oy, oz = xs[mid], ys[mid], zs[mid]

        # Stash the recenter offset and the source schema header on the
        # collection so export can re-apply the offset and preserve the
        # original `name` / `schema` fields verbatim.
        coll["rsdw_recenter_offset_ue"] = (float(ox), float(oy), float(oz))
        coll["rsdw_source_name"] = str(data.get("name") or base_name)
        coll["rsdw_source_schema"] = str(data.get("schema") or "rsdwtools.buildings.v1")

        # Restore anchor selection from the source JSON, if present. Stored
        # on the collection so the UI/export can round-trip it without
        # touching the per-piece custom props.
        anchor_pid = data.get("anchor_piece_id")
        if isinstance(anchor_pid, (int, float)) and int(anchor_pid) > 0:
            coll["rsdw_anchor_piece_id"] = int(anchor_pid)
        elif "rsdw_anchor_piece_id" in coll:
            del coll["rsdw_anchor_piece_id"]

        scale = float(settings.scale)
        unmapped: dict = {}
        no_blend: dict = {}
        placed = 0
        placed_items = 0
        placed_actors = 0

        # Cache loaded source asset objects per stem so re-using the same blend
        # within one import doesn't trigger a fresh library load each time.
        linked_assets: dict = {}

        for pc in pieces:
            class_name = pc.get("class_name", "")
            asset_stem = _asset_stem_from_piece_data_name(pc.get("piece_data_name", ""))
            mesh_stem = _resolve_mesh_stem(class_name)
            stem = asset_stem if asset_stem and asset_stem.lower() in blend_index else mesh_stem
            short = _shorten_class(class_name)
            if not stem:
                unmapped[short] = unmapped.get(short, 0) + 1
                continue

            inst, reason = _instantiate_asset(
                stem=stem,
                name=stem,
                blend_index=blend_index,
                linked_assets=linked_assets,
                collection=coll,
            )
            if inst is None:
                no_blend[stem] = no_blend.get(stem, 0) + 1
                continue

            _apply_ue_transform(inst, pc, scale, ox, oy, oz)

            # Stash original game data on the object so export is lossless
            # even if the user renames it or duplicates it.
            inst["rsdw_asset_kind"] = "building_piece"
            inst["rsdw_class_name"] = class_name
            inst["rsdw_bp_class"] = short
            inst["rsdw_piece_id"] = int(pc.get("piece_id", 0) or 0)
            inst["rsdw_piece_data_index"] = int(pc.get("piece_data_index", 0) or 0)
            inst["rsdw_piece_data_name"] = str(pc.get("piece_data_name", "") or "")
            if pc.get("spud_guid"):
                inst["rsdw_spud_guid"] = str(pc.get("spud_guid") or "")
            if asset_stem:
                inst["rsdw_catalog_asset_stem"] = asset_stem
            if mesh_stem:
                inst["rsdw_source_sm_stem"] = mesh_stem
            # Preserve the source stability if present and > 0; otherwise
            # fall back to the per-class recommended max so re-export of a
            # JSON missing the field doesn't downgrade the build.
            short_cn = class_name.rsplit("/", 1)[-1].rsplit(".", 1)[-1]
            raw_stab = pc.get("stability")
            if isinstance(raw_stab, (int, float)) and raw_stab > 0:
                inst["rsdw_stability"] = int(round(float(raw_stab)))
            else:
                inst["rsdw_stability"] = _recommended_stability(short_cn)
            inst["rsdw_is_ghosted"] = bool(pc.get("is_ghosted", False))
            placed += 1

        for item in items:
            stem = str(item.get("item_asset_name") or "").strip()
            if not stem:
                asset_path = str(item.get("item_asset_path") or "")
                stem = asset_path.rsplit("/", 1)[-1].split(".", 1)[0]
            if not stem:
                unmapped["item"] = unmapped.get("item", 0) + 1
                continue
            inst, reason = _instantiate_asset(
                stem=stem,
                name=str(item.get("actor_name") or stem),
                blend_index=blend_index,
                linked_assets=linked_assets,
                collection=coll,
            )
            if inst is None:
                no_blend[stem] = no_blend.get(stem, 0) + 1
                continue
            _apply_ue_transform(inst, item, scale, ox, oy, oz)
            inst["rsdw_asset_kind"] = "item"
            inst["rsdw_actor_name"] = str(item.get("actor_name") or inst.name)
            inst["rsdw_actor_class"] = str(item.get("actor_class") or "")
            inst["rsdw_item_asset_name"] = stem
            inst["rsdw_item_name"] = stem
            inst["rsdw_item_asset_path"] = str(item.get("item_asset_path") or "")
            inst["rsdw_item_source"] = str(item.get("item_source") or "ItemData")
            try:
                inst["rsdw_item_count"] = int(item.get("count", 1) or 1)
            except (TypeError, ValueError):
                inst["rsdw_item_count"] = 1
            placed_items += 1

        for actor in actors:
            actor_class = str(actor.get("actor_class") or actor.get("class_path") or "")
            stem = _shorten_class(actor_class)
            if not stem:
                unmapped["actor"] = unmapped.get("actor", 0) + 1
                continue
            inst, reason = _instantiate_asset(
                stem=stem,
                name=str(actor.get("actor_name") or stem),
                blend_index=blend_index,
                linked_assets=linked_assets,
                collection=coll,
            )
            if inst is None:
                no_blend[stem] = no_blend.get(stem, 0) + 1
                continue
            _apply_ue_transform(inst, actor, scale, ox, oy, oz)
            inst["rsdw_asset_kind"] = "bp"
            inst["rsdw_actor_name"] = str(actor.get("actor_name") or inst.name)
            inst["rsdw_actor_class"] = actor_class
            inst["rsdw_actor_class_path"] = str(actor.get("class_path") or _class_path_from_class_name(actor_class))
            inst["rsdw_bp_class"] = stem
            placed_actors += 1

        msg = (
            f"Placed {placed}/{len(pieces)} pieces, "
            f"{placed_items}/{len(items)} items, "
            f"{placed_actors}/{len(actors)} actors in '{coll.name}'."
        )
        if unmapped:
            top = sorted(unmapped.items(), key=lambda kv: -kv[1])[:5]
            msg += f"  {sum(unmapped.values())} unmapped class(es): " + \
                   ", ".join(f"{k} x{v}" for k, v in top)
        if no_blend:
            top = sorted(no_blend.items(), key=lambda kv: -kv[1])[:5]
            msg += f"  {sum(no_blend.values())} mesh(es) not in library: " + \
                   ", ".join(f"{k} x{v}" for k, v in top)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


# ---------- export operator ----------

class RSDW_OT_ExportBuildingJson(Operator):
    bl_idname = "rsdw.export_building_json"
    bl_label = "Export Dragonwilds Building JSON..."
    bl_description = (
        "Export visible RSDW objects in the scene back to building JSON. "
        "Objects in hidden collections are ignored."
    )
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})  # type: ignore[valid-type]

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = "exported_building.json"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        preferred_coll = _context_build_collection(context)
        scene_objects = _scene_objects(context)
        visible_objects = [
            obj for obj in scene_objects
            if not _is_object_hidden_for_export(obj, context)
        ]
        coll = _export_metadata_collection_for_scope(context, visible_objects, preferred=preferred_coll)

        preflight = _run_build_preflight(
            context,
            coll,
            select_problems=True,
            objects=scene_objects,
            scope_name="Visible scene",
        )
        if preflight.get("unknown_runtime_index", 0):
            self.report(
                {"ERROR"},
                f"Cannot export: {preflight['unknown_runtime_index']} piece(s) are missing runtime piece data.",
            )
            return {"CANCELLED"}
        if not (
            preflight.get("exportable_pieces", 0)
            or preflight.get("exportable_items", 0)
            or preflight.get("exportable_actors", 0)
        ):
            self.report({"ERROR"}, "No visible export-ready RSDW objects in this scene.")
            return {"CANCELLED"}
        if coll is not None:
            _set_active_collection(context, coll)

        # Reverse map: SM stem -> class_name. If multiple BPs share a mesh
        # we keep the first one (round-tripping is lossy for those props).
        bpmap = _load_bpmap()
        rev: dict = {}
        for cls, mesh in bpmap.items():
            rev.setdefault(mesh, cls)

        settings: RSDWSettings = context.scene.rsdw_settings
        scale = float(settings.scale)
        if scale <= 0:
            self.report({"ERROR"}, "Invalid scale.")
            return {"CANCELLED"}

        # Export scope is scene-wide visibility, not collection membership.
        # This lets users organize a build across multiple collections while
        # hiding collections to exclude WIP/reference objects from export.
        all_objs = [
            obj for obj in visible_objects
            if _is_building_piece_obj(obj) or _is_item_obj(obj) or _is_actor_obj(obj)
        ]

        if not all_objs:
            self.report({"ERROR"}, "No visible RSDW objects in the scene.")
            return {"CANCELLED"}

        # Re-apply the recenter offset captured at import time so positions
        # round-trip back into the game's world coordinate frame.
        roff = coll.get("rsdw_recenter_offset_ue") if coll is not None else None
        if roff is not None and len(roff) == 3:
            ox, oy, oz = float(roff[0]), float(roff[1]), float(roff[2])
        else:
            ox = oy = oz = 0.0

        # Build a stem -> first-known-full-class-path index from the imported
        # objects so newly drag-dropped pieces can inherit a real game asset
        # path from a sibling of the same class instead of a synthesized one.
        stem_to_full_class: dict = {}
        # Also build a class_name -> {piece_data_index, piece_data_name} index
        # from imported siblings, used as the first-choice fallback for fresh
        # drag-dropped pieces that carry no rsdw_piece_data_* props.
        class_to_piece_data: dict = {}
        # Track piece_ids already in use so newly added pieces get a fresh
        # id beyond the max instead of clashing with an existing one.
        max_id = 0
        for o in all_objs:
            meta = _metadata_object_for(o) or o
            cn = meta.get("rsdw_class_name", "")
            if cn and "/" in cn:
                short = cn.rsplit("/", 1)[-1].rsplit(".", 1)[-1]
                stem = str(meta.get("rsdw_source_sm_stem", "") or bpmap.get(short, ""))
                if stem and stem not in stem_to_full_class:
                    stem_to_full_class[stem] = cn
            pdi = int(meta.get("rsdw_piece_data_index", 0) or 0)
            pdn = str(meta.get("rsdw_piece_data_name", "") or "")
            if cn and pdn and cn not in class_to_piece_data:
                class_to_piece_data[cn] = (pdi, pdn)
            pid = int(o.get("rsdw_piece_id", 0) or 0)
            if pid > 0:
                if pid > max_id:
                    max_id = pid

        piece_data_map = _load_piece_data_map()
        next_id = max_id + 1
        allocated_ids: set = set()

        pieces = []
        items = []
        actors = []
        skipped = 0
        hidden = int(preflight.get("hidden_objects", 0) or 0)
        # Pieces whose runtime index we don't know -- the game's spawn
        # RPC takes only the int index so emitting them would silently
        # fail in-game. Collect for an honest error report.
        unknown_index_classes: dict = {}
        for i, obj in enumerate(all_objs):
            if _is_item_obj(obj) or _is_actor_obj(obj):
                continue
            if not _is_building_piece_obj(obj):
                skipped += 1
                continue

            # Prefer the original class_name stashed at import time -- this is
            # the only lossless path when several BPs share the same SM mesh.
            meta = _metadata_object_for(obj) or obj
            class_name = str(meta.get("rsdw_class_name", "") or "")
            stem = str(meta.get("rsdw_source_sm_stem", "") or obj.name.split(".")[0])
            if not class_name:
                cls_short = _resolve_class_for_obj(obj) or rev.get(stem)
                if not cls_short:
                    skipped += 1
                    continue
                # If the same SM stem was already imported with a real game
                # path, reuse that path verbatim. Falls back to a synthesized
                # /Game/Gameplay/BaseBuilding/Actors/ path otherwise.
                inherited = stem_to_full_class.get(stem)
                if inherited:
                    class_name = inherited
                else:
                    class_name = (
                        f"BlueprintGeneratedClass /Game/Gameplay/BaseBuilding/Actors/"
                        f"{cls_short[:-2]}.{cls_short}"
                    )

            mw = obj.matrix_world
            transform = _ue_transform_from_matrix(mw, scale, ox, oy, oz)

            # Preserve the original piece_id when present so the game can
            # round-trip stable references; mint a fresh one beyond the max
            # observed id for drag-dropped pieces (or duplicates that share
            # an id with an existing piece).
            pid = int(obj.get("rsdw_piece_id", 0) or 0)
            if pid <= 0 or pid in allocated_ids:
                while next_id in allocated_ids:
                    next_id += 1
                pid = next_id
                next_id += 1
            allocated_ids.add(pid)

            # Resolve piece_data_index/name. Order:
            #   1. Custom props stamped at import time.
            #   2. A sibling in this collection that imported the same class.
            #   3. The shipped PieceDataMap harvested from example saves.
            short_cn = class_name.rsplit("/", 1)[-1].rsplit(".", 1)[-1] if class_name else ""
            raw_obj_pdi = meta.get("rsdw_piece_data_index")
            pdi_known = raw_obj_pdi is not None and raw_obj_pdi != ""
            pdi = int(raw_obj_pdi) if pdi_known else 0
            pdn = str(meta.get("rsdw_piece_data_name", "") or "")
            if not pdn:
                sib = class_to_piece_data.get(class_name)
                if sib is not None:
                    pdi, pdn = sib
                    pdi_known = True
                else:
                    entry = piece_data_map.get(short_cn)
                    if entry:
                        # piece_data_index may be null in the map for
                        # archive-only entries (subsystem index unknown).
                        raw_pdi = entry.get("piece_data_index")
                        pdi_known = raw_pdi is not None
                        pdi = int(raw_pdi) if pdi_known else 0
                        pdn = str(entry.get("piece_data_name", "") or "")

            # Refuse to emit pieces with no real runtime index. The game's
            # Server_SpawnBuilding takes the int index and silently does
            # nothing on a stale/unknown value, so exporting these would
            # produce a base where some pieces just never appear.
            if not pdi_known or pdi < 0 or not pdn:
                unknown_index_classes[short_cn or class_name] = (
                    unknown_index_classes.get(short_cn or class_name, 0) + 1
                )
                skipped += 1
                continue

            row = {
                "piece_id": pid,
                "piece_data_index": pdi,
                "piece_data_name": pdn,
                "class_name": class_name,
                **transform,
                "stability": _resolve_stability_for_export(
                    obj if obj.get("rsdw_stability") is not None else meta,
                    short_cn,
                ),
                "is_ghosted": bool(meta.get("rsdw_is_ghosted", obj.get("rsdw_is_ghosted", False))),
            }
            if meta.get("rsdw_spud_guid"):
                row["spud_guid"] = str(meta.get("rsdw_spud_guid") or "")
            pieces.append(row)

        for obj in all_objs:
            if not _is_item_obj(obj):
                continue
            meta = _metadata_object_for(obj) or obj
            item_name = str(
                meta.get("rsdw_item_asset_name")
                or meta.get("rsdw_item_name")
                or obj.name.split(".")[0]
            )
            item_path = str(meta.get("rsdw_item_asset_path") or "")
            if not item_path:
                item_path = _unreal_asset_path_from_json_relative(
                    str(meta.get("rsdw_item_json_relative") or ""),
                    item_name,
                )
            try:
                item_count = int(meta.get("rsdw_item_count", 1) or 1)
            except (TypeError, ValueError):
                item_count = 1
            items.append({
                "actor_name": str(meta.get("rsdw_actor_name") or obj.name),
                "actor_class": str(
                    meta.get("rsdw_actor_class")
                    or "BlueprintGeneratedClass /Game/Gameplay/WorldItems/BP_RuntimeSpawnedWorldItem.BP_RuntimeSpawnedWorldItem_C"
                ),
                "item_asset_name": item_name,
                "item_asset_path": item_path,
                "item_source": str(meta.get("rsdw_item_source") or "ItemData"),
                "count": item_count,
                **_ue_transform_from_matrix(obj.matrix_world, scale, ox, oy, oz),
            })

        for obj in all_objs:
            if not _is_actor_obj(obj):
                continue
            meta = _metadata_object_for(obj) or obj
            actor_class = str(meta.get("rsdw_actor_class") or meta.get("rsdw_class_name") or "")
            class_path = str(
                meta.get("rsdw_actor_class_path")
                or meta.get("rsdw_runtime_path")
                or _class_path_from_class_name(actor_class)
            )
            if not actor_class and class_path:
                actor_class = f"BlueprintGeneratedClass {class_path}"
            actors.append({
                "actor_name": str(meta.get("rsdw_actor_name") or obj.name),
                "actor_class": actor_class,
                "class_path": class_path,
                **_ue_transform_from_matrix(obj.matrix_world, scale, ox, oy, oz),
            })

        if not pieces and not items and not actors:
            self.report({"ERROR"},
                        "No visible objects in this scene map to exportable RSDW data.")
            return {"CANCELLED"}

        # Prefer the captured source name (the in-game base name as recorded
        # by the game tool) over Blender's COLLECTION_NAME_PREFIX-stripped
        # collection name. Falls back to the collection name if missing.
        name = coll.get("rsdw_source_name") if coll is not None else ""
        if not name:
            name = coll.name if coll is not None else context.scene.name
            if name.startswith(COLLECTION_NAME_PREFIX):
                name = name[len(COLLECTION_NAME_PREFIX):]
        schema = (coll.get("rsdw_source_schema") if coll is not None else "") or "rsdwtools.buildings.v1"

        out = {
            "schema": str(schema),
            "name": str(name),
            "generated_unix": int(time.time()),
            "count": len(pieces),
            "skipped": skipped,
            "item_count": len(items),
            "item_skipped": 0,
            "hidden": hidden,
            "pieces": pieces,
            "items": items,
            "actors": actors,
        }

        # Anchor (single piece per build). Optional; only emitted when the
        # collection has one set AND the piece is still in the export. Game
        # treats a missing anchor block as 'no anchor selected'.
        try:
            anchor_pid = int((coll.get("rsdw_anchor_piece_id", 0) if coll is not None else 0) or 0)
        except (TypeError, ValueError):
            anchor_pid = 0
        if anchor_pid > 0:
            anchor_piece = next(
                (p for p in pieces if int(p.get("piece_id", 0)) == anchor_pid),
                None,
            )
            if anchor_piece is not None:
                out["anchor_piece_id"] = anchor_pid
                out["anchor_piece_data_index"] = int(anchor_piece.get("piece_data_index", 0))
        path = bpy.path.abspath(self.filepath)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(out, fh, indent=2)
        except Exception as e:
            self.report({"ERROR"}, f"Write failed: {e}")
            return {"CANCELLED"}
        msg = f"Wrote {len(pieces)} pieces, {len(items)} items, {len(actors)} actors -> {path}"
        if skipped:
            msg += f"  ({skipped} unmapped)"
        if hidden:
            msg += f"  ({hidden} hidden)"
        if unknown_index_classes:
            top = sorted(unknown_index_classes.items(),
                         key=lambda kv: -kv[1])[:5]
            detail = ", ".join(f"{c}x{n}" for c, n in top)
            self.report({"WARNING"},
                        f"Skipped {sum(unknown_index_classes.values())} piece(s) "
                        f"with unknown runtime piece_data_index: {detail}. "
                        f"Build one of each in-game and re-run "
                        f"BuildPieceDataMap.py to learn the index.")
        self.report({"INFO"}, msg)
        return {"FINISHED"}


# ---------- snapping ----------

def _resolve_class_for_obj(obj) -> str:
    """Get BP_*_C class name for an object.

    Prefers stamped catalog/import metadata, then falls back to old SM-stem
    lookup for legacy assets and simple linked-object drops.
    """
    meta = _metadata_object_for(obj) or obj
    cn = meta.get("rsdw_class_name", "")
    if cn:
        return cn.rsplit("/", 1)[-1].rsplit(".", 1)[-1]
    bp_class = meta.get("rsdw_bp_class", "")
    if bp_class:
        return _shorten_class(str(bp_class))
    source_stem = meta.get("rsdw_source_sm_stem", "")
    if source_stem:
        cls = _reverse_bpmap().get(str(source_stem), "")
        if cls:
            return cls
    if meta is not obj:
        meta_stem = meta.name.split(".")[0]
        cls = _reverse_bpmap().get(meta_stem, "")
        if cls:
            return cls
    stem = obj.name.split(".")[0]
    return _reverse_bpmap().get(stem, "")


_preflight_cache: dict | None = None
_problem_cache: dict | None = None


def _piece_data_for_obj(obj, class_name: str, class_to_piece_data: dict, piece_data_map: dict) -> tuple[bool, int, str]:
    meta = _metadata_object_for(obj) or obj
    raw_pdi = meta.get("rsdw_piece_data_index")
    pdi_known = raw_pdi is not None and raw_pdi != ""
    try:
        pdi = int(raw_pdi) if pdi_known else 0
    except (TypeError, ValueError):
        pdi_known = False
        pdi = 0
    pdn = str(meta.get("rsdw_piece_data_name", "") or "")
    if not pdn:
        sib = class_to_piece_data.get(class_name)
        if sib is not None:
            pdi, pdn = sib
            pdi_known = True
        else:
            short_cn = class_name.rsplit("/", 1)[-1].rsplit(".", 1)[-1] if class_name else _resolve_class_for_obj(obj)
            entry = piece_data_map.get(short_cn)
            if entry:
                raw_map_pdi = entry.get("piece_data_index")
                pdi_known = raw_map_pdi is not None
                pdi = int(raw_map_pdi) if pdi_known else 0
                pdn = str(entry.get("piece_data_name", "") or "")
    return pdi_known and pdi >= 0 and bool(pdn), pdi, pdn


def _run_build_preflight(
    context,
    collection=None,
    select_problems: bool = False,
    objects: list | None = None,
    scope_name: str | None = None,
) -> dict:
    global _preflight_cache
    coll = collection or _context_build_collection(context)
    if objects is None and coll is None:
        _preflight_cache = {
            "collection": "",
            "ready": False,
            "status": "no-build-collection",
            "message": "No active RSDW build collection.",
        }
        return _preflight_cache

    if objects is None:
        objects = _collection_objects_recursive(coll)
    label = scope_name or (coll.name if coll is not None else "Visible scene")
    visible_objects = [obj for obj in objects if not _is_object_hidden_for_export(obj, context)]
    piece_objects = [obj for obj in visible_objects if _is_building_piece_obj(obj)]
    item_objects = [obj for obj in visible_objects if _is_item_obj(obj)]
    actor_objects = [obj for obj in visible_objects if _is_actor_obj(obj)]
    hidden_count = len(objects) - len(visible_objects)

    piece_data_map = _load_piece_data_map()
    snaps = _load_snaps()
    class_to_piece_data: dict = {}
    piece_ids: dict[int, list] = {}
    for obj in piece_objects:
        meta = _metadata_object_for(obj) or obj
        class_name = str(meta.get("rsdw_class_name", "") or "")
        if class_name:
            pdi_known, pdi, pdn = _piece_data_for_obj(obj, class_name, {}, piece_data_map)
            if pdi_known and pdn and class_name not in class_to_piece_data:
                class_to_piece_data[class_name] = (pdi, pdn)
        try:
            pid = int(obj.get("rsdw_piece_id", 0) or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid > 0:
            piece_ids.setdefault(pid, []).append(obj)

    exportable = []
    unknown_runtime = []
    no_class = []
    no_snap = []
    for obj in piece_objects:
        cls_short = _resolve_class_for_obj(obj)
        if not cls_short:
            no_class.append(obj)
            continue
        meta = _metadata_object_for(obj) or obj
        class_name = str(meta.get("rsdw_class_name", "") or "")
        if not class_name:
            class_name = f"BlueprintGeneratedClass /Game/Gameplay/BaseBuilding/Actors/{cls_short[:-2]}.{cls_short}"
        pdi_known, _pdi, _pdn = _piece_data_for_obj(obj, class_name, class_to_piece_data, piece_data_map)
        if pdi_known:
            exportable.append(obj)
        else:
            unknown_runtime.append(obj)
        if cls_short not in snaps:
            no_snap.append(obj)

    duplicate_piece_id_objects = []
    for _pid, objs in piece_ids.items():
        if len(objs) > 1:
            duplicate_piece_id_objects.extend(objs[1:])

    if select_problems:
        _select_objects(context, unknown_runtime)

    ready = (bool(exportable) or bool(item_objects) or bool(actor_objects)) and not unknown_runtime
    status = "ready" if ready else "needs-attention"
    if not exportable and not item_objects and not actor_objects:
        status = "no-exportable-pieces"

    _preflight_cache = {
        "collection": label,
        "ready": ready,
        "status": status,
        "total_objects": len(objects),
        "visible_objects": len(visible_objects),
        "exportable_pieces": len(exportable),
        "exportable_items": len(item_objects),
        "exportable_actors": len(actor_objects),
        "hidden_objects": hidden_count,
        "non_rsdw_objects": len(visible_objects) - len(piece_objects) - len(item_objects) - len(actor_objects),
        "unknown_runtime_index": len(unknown_runtime),
        "no_snap_data": len(no_snap),
        "duplicate_piece_ids": len(duplicate_piece_id_objects),
        "_unknown_runtime_objects": unknown_runtime,
        "_non_rsdw_objects": no_class,
        "_no_snap_objects": no_snap,
        "_duplicate_piece_id_objects": duplicate_piece_id_objects,
        "message": (
            f"{label}: {len(exportable)} export-ready piece(s), "
            f"{len(item_objects)} item(s), {len(actor_objects)} actor(s), "
            f"{len(unknown_runtime)} missing runtime index, "
            f"{hidden_count} hidden."
        ),
    }
    return _preflight_cache


class RSDW_OT_PreflightBuild(Operator):
    bl_idname = "rsdw.preflight_build"
    bl_label = "Check Build"
    bl_description = "Check the active build for export-blocking metadata problems"
    bl_options = {"REGISTER", "UNDO"}

    select_problem_pieces: BoolProperty(
        name="Select problem pieces",
        description="Select pieces that cannot export because their runtime piece data is unknown",
        default=True,
    )  # type: ignore[valid-type]

    def execute(self, context):
        result = _run_build_preflight(context, select_problems=bool(self.select_problem_pieces))
        if not result.get("collection"):
            self.report({"ERROR"}, result.get("message", "No active build."))
            return {"CANCELLED"}
        level = "INFO" if result.get("ready") else "WARNING"
        self.report({level}, result.get("message", "Build checked."))
        return {"FINISHED"}


def _ue_to_blender_pos(p, scale: float) -> Vector:
    """Plug local pos in UE cm -> Blender meters (Y flip for handedness)."""
    return Vector((p[0] * scale, -p[1] * scale, p[2] * scale))


def _ue_to_blender_quat(q) -> Quaternion:
    """UE quat (qx,qy,qz,qw) -> Blender Quaternion (w,x,y,z) with Y-axis mirror.

    Mirroring world axis Y while keeping rotation behaviour equivalent
    requires negating the qx and qz components (Y stays). See math
    derivation in repo notes.
    """
    return Quaternion((float(q[3]), -float(q[0]), float(q[1]), -float(q[2])))


def _plug_local_matrix(plug, scale: float) -> Matrix:
    pos = _ue_to_blender_pos(plug["pos"], scale)
    rot = _ue_to_blender_quat(plug["rot"])
    return Matrix.LocRotScale(pos, rot, None)


def _plugs_compatible(a: dict, b: dict) -> bool:
    """Two plugs may connect when neither side blacklists the other.

    PieceTag is the *piece* role; PlugTag is the *plug* role. The piece
    holding plug A blacklists pieces (PieceIgnoringTypes) and plug roles
    (PlugIgnoringTypes) it refuses to connect to. The check must be
    symmetric.
    """
    if a["plug_tag"] in b["plug_ign"]:
        return False
    if b["plug_tag"] in a["plug_ign"]:
        return False
    if a["piece_tag"] in b["piece_ign"]:
        return False
    if b["piece_tag"] in a["piece_ign"]:
        return False
    return True


def _world_bound_corners(obj) -> list:
    """Return world-space bound-box corners for meshes or collection instances."""
    corners = []
    if obj is None:
        return corners
    if obj.type == "EMPTY" and obj.instance_collection is not None:
        for child in _collection_objects_recursive(obj.instance_collection):
            try:
                child_corners = list(child.bound_box)
            except Exception:
                continue
            if not child_corners:
                continue
            child_world = obj.matrix_world @ child.matrix_world
            for corner in child_corners:
                corners.append(child_world @ Vector(corner))
        return corners
    try:
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ Vector(corner))
    except Exception:
        pass
    return corners


def _orientation_frame(obj) -> Matrix:
    """Object world transform without scale, used as an oriented bounds frame."""
    try:
        loc, rot, _scale = obj.matrix_world.decompose()
        return Matrix.LocRotScale(loc, rot, None)
    except Exception:
        return Matrix.Translation(obj.matrix_world.translation)


def _bounds_in_frame(obj, frame: Matrix):
    corners = _world_bound_corners(obj)
    if not corners:
        return None
    inv = frame.inverted()
    local = [inv @ corner for corner in corners]
    mins = Vector((
        min(v.x for v in local),
        min(v.y for v in local),
        min(v.z for v in local),
    ))
    maxs = Vector((
        max(v.x for v in local),
        max(v.y for v in local),
        max(v.z for v in local),
    ))
    return mins, maxs


def _interval_overlap(a_min: float, a_max: float, b_min: float, b_max: float) -> float:
    return min(a_max, b_max) - max(a_min, b_min)


def _is_rsdw_snap_target(obj) -> bool:
    if obj is None:
        return False
    if not _is_building_piece_obj(obj):
        return False
    if _resolve_class_for_obj(obj):
        return True
    if obj.type == "EMPTY" and obj.instance_collection is not None:
        _stem, cls = _resolve_drop_target(obj)
        return bool(cls)
    return False


def _surface_snap_one(obj, candidates: list, max_distance: float, inset: float) -> str:
    """Bounds-based fallback for pieces that have no game plug data.

    This is intentionally narrower than plug snapping: it only closes the
    nearest pair of overlapping oriented bound-box faces and applies a tiny
    configurable overlap. That avoids visible/support gaps for no-plug props
    without changing the game-authored plug behaviour for normal pieces.
    """
    if not _world_bound_corners(obj):
        return "surface-no-bounds"

    max_distance = float("inf") if float(max_distance) <= 0.0 else float(max_distance)
    inset = max(0.0, float(inset))
    best = None  # (score, candidate, frame, axis, delta_axis)
    for cand in candidates:
        if cand is obj or not _is_rsdw_snap_target(cand):
            continue
        frame = _orientation_frame(cand)
        cand_bounds = _bounds_in_frame(cand, frame)
        obj_bounds = _bounds_in_frame(obj, frame)
        if cand_bounds is None or obj_bounds is None:
            continue
        cmin, cmax = cand_bounds
        omin, omax = obj_bounds
        for axis in range(3):
            other_axes = [i for i in range(3) if i != axis]
            overlaps = [
                _interval_overlap(cmin[i], cmax[i], omin[i], omax[i])
                for i in other_axes
            ]
            if any(v <= 0.0 for v in overlaps):
                continue
            # Mover sits on the positive side of candidate along this axis.
            sep = omin[axis] - cmax[axis]
            if -inset <= sep <= max_distance:
                delta = -sep - inset
                score = abs(sep) - (sum(overlaps) * 0.001)
                if best is None or score < best[0]:
                    best = (score, cand, frame, axis, delta)
            # Mover sits on the negative side of candidate along this axis.
            sep = cmin[axis] - omax[axis]
            if -inset <= sep <= max_distance:
                delta = sep + inset
                score = abs(sep) - (sum(overlaps) * 0.001)
                if best is None or score < best[0]:
                    best = (score, cand, frame, axis, delta)

    if best is None:
        return "surface-out-of-range"

    _score, _cand, frame, axis, delta_axis = best
    local_delta = Vector((0.0, 0.0, 0.0))
    local_delta[axis] = delta_axis
    world_delta = frame.to_3x3() @ local_delta
    obj.matrix_world = Matrix.Translation(world_delta) @ obj.matrix_world
    return "surface-snapped"


class RSDW_OT_SnapToActive(Operator):
    bl_idname = "rsdw.snap_to_active"
    bl_label = "Snap Selected to Active"
    bl_description = (
        "Snap each selected base-building piece to the active piece using "
        "the closest pair of compatible game snap-points (plugs). Pieces "
        "without plug data fall back to tight bounding-box surface contact"
    )
    bl_options = {"REGISTER", "UNDO"}

    max_distance: FloatProperty(
        name="Max plug pair distance (m)",
        description="Only consider plug pairs whose current world distance is within this radius",
        default=2.0,
        min=0.0,
        soft_max=10.0,
    )  # type: ignore[valid-type]
    align_rotation: bpy.props.BoolProperty(
        name="Align rotation to plug",
        description=(
            "If on, also rotate the mover so its plug axes line up with the "
            "anchor's plug. If off (default), only translate so the plug pair "
            "coincides; the mover's existing rotation is preserved"
        ),
        default=False,
    )  # type: ignore[valid-type]

    def execute(self, context):
        anchor = context.active_object
        if anchor is None:
            self.report({"ERROR"}, "No active object.")
            return {"CANCELLED"}
        movers = [o for o in context.selected_objects if o is not anchor]
        if not movers:
            self.report({"ERROR"}, "Select at least two objects (anchor = active).")
            return {"CANCELLED"}

        snaps = _load_snaps()
        if not snaps:
            self.report({"ERROR"}, "Snaps.json missing from addon. Reinstall the extension.")
            return {"CANCELLED"}

        anchor_cls = _resolve_class_for_obj(anchor)
        anchor_data = snaps.get(anchor_cls)
        if not anchor_data and not _is_rsdw_snap_target(anchor):
            self.report({"ERROR"},
                        f"No snap data for active object class '{anchor_cls or anchor.name}'.")
            return {"CANCELLED"}

        scale = float(context.scene.rsdw_settings.scale)
        surface_inset = float(context.scene.rsdw_settings.surface_snap_inset)
        anchor_world_plugs = []
        if anchor_data:
            anchor_world_plugs = [
                (p, anchor.matrix_world @ _plug_local_matrix(p, scale))
                for p in anchor_data["plugs"]
            ]

        snapped = 0
        skipped: list = []
        max_d2 = float(self.max_distance) ** 2
        for mv in movers:
            cls = _resolve_class_for_obj(mv)
            data = snaps.get(cls)
            if not data or not anchor_data:
                status = _surface_snap_one(
                    mv, [anchor], float(self.max_distance), surface_inset,
                )
                if status == "surface-snapped":
                    snapped += 1
                else:
                    reason = "no plugs" if not data else "active has no plugs"
                    skipped.append(f"{mv.name}({reason}; {status})")
                continue

            best = None  # (dist2, plug_a, mat_a_local, plug_b, mat_b_world)
            for plug_a in data["plugs"]:
                mat_a_local = _plug_local_matrix(plug_a, scale)
                cur_a_world = mv.matrix_world @ mat_a_local
                cur_a_pos = cur_a_world.translation
                for plug_b, mat_b_world in anchor_world_plugs:
                    if not _plugs_compatible(plug_a, plug_b):
                        continue
                    d2 = (mat_b_world.translation - cur_a_pos).length_squared
                    if max_d2 > 0.0 and d2 > max_d2:
                        continue
                    if best is None or d2 < best[0]:
                        best = (d2, plug_a, mat_a_local, plug_b, mat_b_world)

            if best is None:
                skipped.append(f"{mv.name}(no compatible pair in range)")
                continue

            _d2, _pa, mat_a_local, _pb, mat_b_world = best
            if self.align_rotation:
                # Place mover so its plug_a frame coincides with anchor's
                # plug_b frame in both position and orientation.
                mv.matrix_world = mat_b_world @ mat_a_local.inverted()
            else:
                # Translate-only: preserve the mover's existing rotation, just
                # shift it so plug_a's current world position lands on plug_b.
                cur_a_world_pos = (mv.matrix_world @ mat_a_local).translation
                delta = mat_b_world.translation - cur_a_world_pos
                mv.matrix_world = Matrix.Translation(delta) @ mv.matrix_world
            snapped += 1

        msg = f"Snapped {snapped}/{len(movers)} to '{anchor.name}'."
        if skipped:
            msg += "  Skipped: " + ", ".join(skipped[:5])
            if len(skipped) > 5:
                msg += f" (+{len(skipped) - 5} more)"
        self.report({"INFO" if snapped else "WARNING"}, msg)
        return {"FINISHED"} if snapped else {"CANCELLED"}


# ---------- auto-snap on asset drop ----------

# Names of objects observed on the previous depsgraph update; used to spot
# newly added objects (asset-browser drag-drops) so we can auto-snap them.
_known_object_names: set = set()
# Re-entrancy guard: setting matrix_world inside the handler triggers another
# depsgraph update; this flag suppresses that recursive pass.
_auto_snap_busy: bool = False
# Names of newly-added objects waiting for the asset-browser drop modal to
# finish positioning them. The handler enqueues; a timer drains.
# Each entry: name -> (deadline_time, last_seen_loc_tuple, stable_count)
_pending_snaps: dict = {}
# Timer poll interval (s) and total wait budget (s).
_PENDING_POLL = 0.15
_PENDING_BUDGET = 4.0
# Number of consecutive polls the location must stay unchanged before we
# consider the drop "settled" and run the snap.
_PENDING_STABLE_HITS = 2


def _on_auto_snap_toggled(context) -> None:
    """Snapshot existing objects when the user flips Auto-snap on so we don't
    treat the whole scene as freshly dropped on the next depsgraph update."""
    global _known_object_names
    try:
        scn = context.scene
        _known_object_names = set(o.name for o in scn.objects)
    except Exception:
        _known_object_names = set()


def _find_owning_rsdw_collection(obj):
    """Return the RSDW_Building_* collection that owns obj, else any
    collection containing obj that has snap data on at least one sibling."""
    for c in obj.users_collection:
        if c.name.startswith(COLLECTION_NAME_PREFIX):
            return c
    if obj.users_collection:
        return obj.users_collection[0]
    return None


def _auto_snap_one(obj, settings, scene=None, forced_class: str = "") -> str:
    """Snap obj to nearest compatible plug on any sibling in the scene.

    If ``forced_class`` is provided (e.g. when obj is an Empty representing
    an asset-browser collection-instance whose own name doesn't match an SM
    stem), use that instead of resolving from obj's name.

    Returns a short status string ("snapped", "no-class", "no-plugs",
    "no-siblings", "out-of-range") for diagnostic logging.
    """
    snaps = _load_snaps()
    if not snaps:
        return "no-snaps-data"
    if not _is_building_piece_obj(obj):
        return "not-building-piece"
    cls = forced_class or _resolve_class_for_obj(obj)
    if not cls:
        return "no-class"
    data = snaps.get(cls)
    if not data:
        candidates = list(scene.objects) if scene is not None else list(bpy.context.scene.objects)
        return _surface_snap_one(
            obj,
            candidates,
            float(settings.auto_snap_max_distance),
            float(settings.surface_snap_inset),
        )

    scale = float(settings.scale)
    max_d2 = float(settings.auto_snap_max_distance) ** 2
    mover_plugs = [(p, _plug_local_matrix(p, scale)) for p in data["plugs"]]
    if not mover_plugs:
        return "no-plugs-mover"

    # Search the whole scene so the user's collection layout doesn't matter:
    # any object with snap data participates as a potential anchor.
    candidates = list(scene.objects) if scene is not None else list(bpy.context.scene.objects)

    best = None  # (d2, mat_a_local, mat_b_world)
    sibling_count = 0
    in_range = 0
    for sib in candidates:
        if sib is obj:
            continue
        if not _is_building_piece_obj(sib):
            continue
        if sib.type == "MESH":
            sib_cls = _resolve_class_for_obj(sib)
        elif sib.type == "EMPTY" and sib.instance_collection is not None:
            _stem, sib_cls = _resolve_drop_target(sib)
        else:
            continue
        sib_data = snaps.get(sib_cls)
        if not sib_data:
            continue
        sibling_count += 1
        for plug_b in sib_data["plugs"]:
            mat_b_world = sib.matrix_world @ _plug_local_matrix(plug_b, scale)
            for plug_a, mat_a_local in mover_plugs:
                if not _plugs_compatible(plug_a, plug_b):
                    continue
                cur_a_pos = (obj.matrix_world @ mat_a_local).translation
                d2 = (mat_b_world.translation - cur_a_pos).length_squared
                if max_d2 > 0.0 and d2 > max_d2:
                    continue
                in_range += 1
                if best is None or d2 < best[0]:
                    best = (d2, mat_a_local, mat_b_world)

    if best is None:
        if sibling_count == 0:
            surface_status = _surface_snap_one(
                obj,
                candidates,
                float(settings.auto_snap_max_distance),
                float(settings.surface_snap_inset),
            )
            return "no-siblings" if surface_status == "surface-out-of-range" else surface_status
        return "out-of-range"
    _d2, mat_a_local, mat_b_world = best
    if settings.auto_snap_align_rotation:
        obj.matrix_world = mat_b_world @ mat_a_local.inverted()
    else:
        cur_a_world_pos = (obj.matrix_world @ mat_a_local).translation
        delta = mat_b_world.translation - cur_a_world_pos
        obj.matrix_world = Matrix.Translation(delta) @ obj.matrix_world
    return "snapped"


def _resolve_drop_target(obj):
    """Given a freshly-added scene object, figure out (stem, class_name) for
    auto-snap purposes. Returns (stem, cls) or (None, None) if not ours."""
    if not _is_building_piece_obj(obj):
        return None, None
    rev = _reverse_bpmap()
    stem = obj.name.split(".")[0]
    cls = _resolve_class_for_obj(obj)
    if cls:
        return str(obj.get("rsdw_catalog_asset_stem") or stem), cls
    if obj.type == "MESH" and rev.get(stem):
        return stem, rev[stem]
    if obj.type == "EMPTY" and obj.instance_collection is not None:
        inst = obj.instance_collection
        cand = inst.name.split(".")[0]
        if rev.get(cand):
            return cand, rev[cand]
        for mc in inst.objects:
            mc_cls = _resolve_class_for_obj(mc)
            if mc_cls:
                return str(mc.get("rsdw_catalog_asset_stem") or mc.name.split(".")[0]), mc_cls
            s2 = mc.name.split(".")[0]
            if rev.get(s2):
                return s2, rev[s2]
    return None, None


def _force_upright_xy(obj) -> None:
    """Force world-space X/Y rotation to 0 while preserving yaw, location,
    and scale.

    Asset-browser drops can arrive with small accidental pitch/roll which then
    exports as visually tilted pieces. The game only meaningfully consumes yaw
    for these build pieces, so keep them upright by default.
    """
    try:
        loc, rot, scale = obj.matrix_world.decompose()
        yaw = rot.to_euler("XYZ").z
        rot_m = Euler((0.0, 0.0, yaw), "XYZ").to_matrix().to_4x4()
        scl_m = Matrix.Diagonal((scale.x, scale.y, scale.z, 1.0))
        obj.matrix_world = Matrix.Translation(loc) @ rot_m @ scl_m
    except Exception:
        # Best-effort safety net; if decompose fails, don't block snapping.
        pass


def _drain_pending_snaps():
    """Timer callback. For each queued name, wait until its matrix has stayed
    put for a couple of polls (asset-browser drop finished), then snap.
    Returns next interval in seconds or None to stop the timer."""
    global _auto_snap_busy
    if not _pending_snaps:
        return None
    try:
        scene = bpy.context.scene
        settings = getattr(scene, "rsdw_settings", None)
    except Exception:
        scene = None
        settings = None
    if scene is None or settings is None or not settings.auto_snap:
        _pending_snaps.clear()
        return None

    now = time.monotonic()
    done = []
    for nm, (deadline, last_loc, stable) in list(_pending_snaps.items()):
        obj = scene.objects.get(nm)
        if obj is None:
            done.append(nm)
            continue
        loc = tuple(round(v, 6) for v in obj.matrix_world.translation)
        if loc == last_loc:
            stable += 1
        else:
            stable = 0
            last_loc = loc
        timed_out = now >= deadline
        if stable >= _PENDING_STABLE_HITS or timed_out:
            stem, cls = _resolve_drop_target(obj)
            if cls is None:
                print(f"[RSDW auto-snap] {obj.name} type={obj.type} -> "
                      f"not-an-asset-piece, skip")
                done.append(nm)
                continue
            # Normalize dropped orientation first so accidental pitch/roll from
            # viewport placement doesn't propagate into exports.
            _force_upright_xy(obj)
            print(f"[RSDW auto-snap] {obj.name} type={obj.type} "
                  f"stem={stem!r} class={cls!r} loc={loc} "
                  f"settled={'timeout' if timed_out else 'stable'}")
            _auto_snap_busy = True
            try:
                status = _auto_snap_one(obj, settings, scene=scene,
                                        forced_class=cls)
                # Keep the final transform yaw-only as well.
                _force_upright_xy(obj)
            except Exception as e:
                status = f"error:{e}"
            finally:
                _auto_snap_busy = False
            print(f"[RSDW auto-snap] -> {status}")
            done.append(nm)
        else:
            _pending_snaps[nm] = (deadline, last_loc, stable)
    for nm in done:
        _pending_snaps.pop(nm, None)
    return None if not _pending_snaps else _PENDING_POLL


@bpy.app.handlers.persistent
def _rsdw_auto_snap_handler(scene, depsgraph) -> None:
    global _known_object_names, _auto_snap_busy
    if _auto_snap_busy:
        return
    settings = getattr(scene, "rsdw_settings", None)
    if settings is None or not settings.auto_snap:
        # Keep snapshot fresh so toggling on later starts clean.
        _known_object_names = set(o.name for o in scene.objects)
        return

    current = set(o.name for o in scene.objects)
    added = current - _known_object_names
    _known_object_names = current
    if not added:
        return

    deadline = time.monotonic() + _PENDING_BUDGET
    queued = 0
    for nm in added:
        obj = scene.objects.get(nm)
        if obj is None:
            continue
        # Skip imported pieces so JSON import doesn't trigger a thousand
        # auto-snaps. Catalog asset-browser drops carry class metadata too,
        # but they do not have a runtime piece_id until export.
        if obj.get("rsdw_piece_id", 0):
            continue
        stem, cls = _resolve_drop_target(obj)
        if cls is None:
            # Log once so the user can see why a drop didn't snap.
            print(f"[RSDW auto-snap] new {obj.name} type={obj.type} -> "
                  f"not-an-asset-piece, ignoring")
            continue
        loc = tuple(round(v, 6) for v in obj.matrix_world.translation)
        _pending_snaps[nm] = (deadline, loc, 0)
        queued += 1
        print(f"[RSDW auto-snap] queued {nm} (stem={stem!r}, "
              f"initial_loc={loc}); will snap after drop settles")
    if queued and not bpy.app.timers.is_registered(_drain_pending_snaps):
        bpy.app.timers.register(_drain_pending_snaps,
                                first_interval=_PENDING_POLL)


@bpy.app.handlers.persistent
def _rsdw_load_post(_dummy):
    """Reset the new-object snapshot when a file loads, otherwise stale
    object names can prevent the depsgraph delta from spotting drops."""
    global _known_object_names
    try:
        _known_object_names = set(o.name for o in bpy.context.scene.objects)
    except Exception:
        _known_object_names = set()


class RSDW_OT_DiagnoseAutoSnap(Operator):
    bl_idname = "rsdw.diagnose_auto_snap"
    bl_label = "Diagnose Auto-Snap"
    bl_description = (
        "Run the auto-snap routine on each currently selected object and "
        "print why it succeeded or failed. Use this to debug drag-drops "
        "that aren't snapping"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        sel = list(context.selected_objects)
        if not sel:
            self.report({"ERROR"}, "Select one or more dropped pieces first.")
            return {"CANCELLED"}
        settings = context.scene.rsdw_settings
        scene = context.scene
        results = []
        for obj in sel:
            stem = obj.name.split(".")[0]
            in_bpmap = bool(_reverse_bpmap().get(stem))
            cls = _resolve_class_for_obj(obj)
            line = (
                f"{obj.name} stem={stem} in_bpmap={in_bpmap} class={cls!r} "
                f"users_collection={[c.name for c in obj.users_collection]}"
            )
            print("[RSDW diag] " + line)
            try:
                status = _auto_snap_one(obj, settings, scene=scene)
            except Exception as e:
                status = f"error:{e}"
            print(f"[RSDW diag] -> {status}")
            results.append(f"{obj.name}:{status}")
        self.report({"INFO"}, "  |  ".join(results))
        return {"FINISHED"}


# ---------- isolation linter / plug inspector ----------
#
# These DO NOT validate full structural stability. Plug-pair coincidence
# is only one signal the game uses; floors+walls of different sizes have
# corner plugs at offsets that don't coincide, yet they support each other
# in-game via edge overlap. Use these to find OBVIOUSLY detached pieces
# (no plug engagement at all), not as a final stability oracle.

# Module-level cache for the per-piece inspector. Maps obj.name ->
# list[ (idx:int, plug_tag_short:str, status:str, dist_m:float|None,
#        neighbor_name:str) ]. Status is "snapped" | "free" | "isolated".
_plug_inspect_cache: dict = {}


def _scene_world_plugs(scene, scale: float):
    """Return list of (obj, plug_dict, world_pos_vec) for every object
    in the scene that has snap data."""
    snaps = _load_snaps()
    out = []
    if not snaps:
        return out
    for obj in scene.objects:
        if not _is_building_piece_obj(obj):
            continue
        cls = _resolve_class_for_obj(obj)
        if not cls:
            continue
        data = snaps.get(cls)
        if not data:
            continue
        mw = obj.matrix_world
        for plug in data["plugs"]:
            mat = _plug_local_matrix(plug, scale)
            wpos = (mw @ mat).translation.copy()
            out.append((obj, plug, wpos))
    return out


def _find_best_neighbor(plug, wpos, all_plugs, exclude_obj, max_d: float):
    """Return (dist_m, obj, plug) of nearest *compatible* plug on a
    different object within max_d, or (None, None, None)."""
    max_d2 = (max_d * max_d) if max_d > 0 else float("inf")
    best = None  # (d2, obj, plug)
    for o2, p2, w2 in all_plugs:
        if o2 is exclude_obj:
            continue
        if not _plugs_compatible(plug, p2):
            continue
        d2 = (wpos - w2).length_squared
        if d2 > max_d2:
            continue
        if best is None or d2 < best[0]:
            best = (d2, o2, p2)
    if best is None:
        return None, None, None
    return math.sqrt(best[0]), best[1], best[2]


class RSDW_OT_LintIsolated(Operator):
    bl_idname = "rsdw.lint_isolated"
    bl_label = "Find Isolated Pieces"
    bl_description = (
        "Select pieces whose plugs do NOT engage any compatible plug on "
        "another piece within the snap tolerance. Catches pieces that the "
        "game definitely does not consider snapped to anything (high "
        "confidence). Note: this does NOT validate full structural "
        "stability; it only catches obvious detached pieces"
    )
    bl_options = {"REGISTER", "UNDO"}

    only_in_active_collection: BoolProperty(
        name="Only active collection",
        description="Restrict the lint to objects in the active collection",
        default=False,
    )  # type: ignore[valid-type]

    def execute(self, context):
        scene = context.scene
        settings = scene.rsdw_settings
        scale = float(settings.scale)
        tol = float(settings.lint_tolerance)

        all_plugs = _scene_world_plugs(scene, scale)
        if not all_plugs:
            self.report({"ERROR"}, "No pieces with snap data in scene.")
            return {"CANCELLED"}

        target_objs = None
        if self.only_in_active_collection:
            ac = context.view_layer.active_layer_collection
            if ac and ac.collection:
                target_objs = set(ac.collection.all_objects)

        from collections import defaultdict
        by_obj = defaultdict(list)
        for o, p, w in all_plugs:
            by_obj[o].append((p, w))

        isolated = []
        considered = 0
        for obj, plug_list in by_obj.items():
            if target_objs is not None and obj not in target_objs:
                continue
            considered += 1
            engaged = False
            for plug, wpos in plug_list:
                d, _, _ = _find_best_neighbor(plug, wpos, all_plugs, obj, tol)
                if d is not None:
                    engaged = True
                    break
            if not engaged:
                isolated.append(obj)

        # Update viewport selection.
        for o in scene.objects:
            try:
                o.select_set(False)
            except RuntimeError:
                pass
        for o in isolated:
            try:
                o.select_set(True)
            except RuntimeError:
                pass
        if isolated:
            try:
                context.view_layer.objects.active = isolated[0]
            except Exception:
                pass

        msg = (f"Isolated: {len(isolated)} / {considered} pieces"
               f" (tol={tol*100:.1f} cm). Selected in viewport.")
        self.report({"INFO"}, msg)
        print("[RSDW lint] " + msg)
        for o in isolated[:30]:
            print(f"  - {o.name}  cls={_resolve_class_for_obj(o)}"
                  f"  loc=({o.location.x:.2f},{o.location.y:.2f},{o.location.z:.2f})")
        return {"FINISHED"}


class RSDW_OT_InspectPlugs(Operator):
    bl_idname = "rsdw.inspect_plugs"
    bl_label = "Inspect Active Plugs"
    bl_description = (
        "Compute and cache per-plug engagement status for the active "
        "object: which plugs are snapped to a neighbor (within tolerance) "
        "and which are free. Result is shown in the Plug Status panel"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            self.report({"ERROR"}, "No active object.")
            return {"CANCELLED"}
        scene = context.scene
        scale = float(scene.rsdw_settings.scale)
        tol = float(scene.rsdw_settings.lint_tolerance)

        cls = _resolve_class_for_obj(obj)
        if not cls:
            self.report({"ERROR"}, f"{obj.name}: no RSDW class mapped.")
            _plug_inspect_cache.pop(obj.name, None)
            return {"CANCELLED"}
        snaps = _load_snaps()
        data = snaps.get(cls) if snaps else None
        if not data or not data.get("plugs"):
            self.report({"ERROR"}, f"{cls}: no plug data in Snaps.json.")
            _plug_inspect_cache.pop(obj.name, None)
            return {"CANCELLED"}

        all_plugs = _scene_world_plugs(scene, scale)

        rows = []
        snapped_count = 0
        for i, plug in enumerate(data["plugs"]):
            mat = _plug_local_matrix(plug, scale)
            wpos = (obj.matrix_world @ mat).translation
            d, o2, _ = _find_best_neighbor(plug, wpos, all_plugs, obj, 1.0)
            tag = (plug.get("plug_tag") or "?").rsplit(".", 1)[-1]
            if d is not None and d <= tol:
                rows.append((i, tag, "snapped", d, o2.name))
                snapped_count += 1
            elif d is not None:
                rows.append((i, tag, "free", d, o2.name))
            else:
                rows.append((i, tag, "isolated", None, ""))

        _plug_inspect_cache[obj.name] = rows
        self.report({"INFO"},
                    f"{cls}: {snapped_count}/{len(rows)} plugs snapped.")
        return {"FINISHED"}


# ---------- structural stability validator ----------
#
# We can't faithfully reproduce the in-game stability propagation
# without access to ADominionWorldSettings.BuildingCellSize and the
# private propagation math, so this validator answers a more limited but
# honest question: "is every structural piece connected through some
# chain of compatible plug snaps back to an anchor?"
#
# Anchor classes (from the source -- bForceMaxStability=true): pieces
# whose StabilityProfile is a Foundation, plus all "self-supporting"
# placement profiles (Prop, FarmPlot, Tier_0_*). Structural piece
# classes (Tier{1,2,3}_Base, Tier{1,2,3}_Beam, Stackable_Prop) require
# an anchor to be reachable through compatible plug snaps within the
# per-piece SnappingRadius (default 80 cm, from
# UBuildingSnapComponent.SnappingRadius in BP_BasePiece).
#
# We additionally surface a "fragile" warning for pieces whose shortest
# path to the nearest anchor exceeds the user-configurable hop budget;
# deep chains are most likely to collapse in-game.

_validate_cache: dict | None = None  # last run result for the panel.

# Profile names that REQUIRE an upstream anchor. Everything else
# (foundations, props, farm plots, tier-0 ground pieces, unknowns) is
# treated as self-anchoring (bForceMaxStability=true behaviour).
STRUCTURAL_PROFILES = frozenset({
    "Tier1_Base", "Tier1_Beam",
    "Tier2_Base", "Tier2_Beam",
    "Tier3_Base", "Tier3_Beam",
    "Stackable_Prop",
})


def _is_anchor_profile(profile_name: str) -> bool:
    """Return True for pieces that don't need structural support."""
    if not profile_name:
        return True  # unknown -> conservatively self-anchor.
    return profile_name not in STRUCTURAL_PROFILES


def _validate_stability(scene, scale: float, fragile_hop_threshold: int):
    """Run the connectivity / fragility check. Returns dict:
       { 'pieces': {obj.name: {profile, anchor, hops_to_anchor (or None),
                                isolated, fragile, neighbor_count}},
         'isolated': [obj, ...],   # NO path to any anchor
         'fragile': [obj, ...],    # path exists but >= threshold hops
         'unknown_class': int,
         'considered': int }
    """
    spm = _load_stability_profile_map()
    profiles = spm.get("profiles") or {}
    mapping = spm.get("mapping") or {}
    default_radius_cm = float(spm.get("default_snapping_radius_cm", 80.0))
    snaps = _load_snaps()

    pieces = []
    unknown = 0
    for obj in scene.objects:
        cls = _resolve_class_for_obj(obj)
        if not cls:
            continue
        sd = snaps.get(cls)
        if not sd or not sd.get("plugs"):
            continue
        info = mapping.get(cls)
        if info is None:
            unknown += 1
            profile_name = ""  # treated as self-anchor
            radius_cm = default_radius_cm
        else:
            profile_name = info.get("profile") or ""
            radius_cm = float(info.get("snapping_radius_cm",
                                       default_radius_cm))
        mw = obj.matrix_world
        wplugs = []
        for plug in sd["plugs"]:
            wpos = (mw @ _plug_local_matrix(plug, scale)).translation.copy()
            wplugs.append((plug, wpos))
        pieces.append({
            "obj": obj,
            "class": cls,
            "profile_name": profile_name,
            "radius_cm": radius_cm,
            "wplugs": wplugs,
        })

    n = len(pieces)
    if n == 0:
        return {"pieces": {}, "isolated": [], "fragile": [],
                "unknown_class": 0, "considered": 0}

    # Build neighbor graph via spatial bucketing on plug world positions.
    max_radius_cm = max(p["radius_cm"] for p in pieces)
    cell_m = (max_radius_cm * 0.01) if max_radius_cm > 0 else 1.0

    from collections import defaultdict, deque
    bucket = defaultdict(list)  # (ix,iy,iz) -> list[ (piece_idx, plug, wpos) ]
    for pi, p in enumerate(pieces):
        for plug, wpos in p["wplugs"]:
            key = (int(wpos.x // cell_m),
                   int(wpos.y // cell_m),
                   int(wpos.z // cell_m))
            bucket[key].append((pi, plug, wpos))

    neighbors = [set() for _ in range(n)]
    for pi, p in enumerate(pieces):
        ra_m = p["radius_cm"] * 0.01
        for plug_a, wpos_a in p["wplugs"]:
            kx = int(wpos_a.x // cell_m)
            ky = int(wpos_a.y // cell_m)
            kz = int(wpos_a.z // cell_m)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for (pj, plug_b, wpos_b) in bucket.get(
                                (kx + dx, ky + dy, kz + dz), ()):
                            if pj <= pi:
                                continue
                            if not _plugs_compatible(plug_a, plug_b):
                                continue
                            rb_m = pieces[pj]["radius_cm"] * 0.01
                            r_m = min(ra_m, rb_m)
                            if (wpos_a - wpos_b).length_squared > r_m * r_m:
                                continue
                            neighbors[pi].add(pj)
                            neighbors[pj].add(pi)

    # Multi-source BFS from all anchors.
    is_anchor = [_is_anchor_profile(p["profile_name"]) for p in pieces]
    hops = [None] * n  # None = unreachable from any anchor.
    queue = deque()
    for i, anc in enumerate(is_anchor):
        if anc:
            hops[i] = 0
            queue.append(i)
    while queue:
        i = queue.popleft()
        for j in neighbors[i]:
            if hops[j] is None:
                hops[j] = hops[i] + 1
                queue.append(j)

    isolated = []
    fragile = []
    pieces_out = {}
    for i, p in enumerate(pieces):
        h = hops[i]
        is_iso = (not is_anchor[i]) and h is None
        is_frag = (not is_anchor[i]
                   and h is not None
                   and fragile_hop_threshold > 0
                   and h >= fragile_hop_threshold)
        if is_iso:
            isolated.append(p["obj"])
        elif is_frag:
            fragile.append(p["obj"])
        pieces_out[p["obj"].name] = {
            "profile": p["profile_name"] or "(unknown)",
            "anchor": is_anchor[i],
            "hops_to_anchor": h,
            "isolated": is_iso,
            "fragile": is_frag,
            "neighbor_count": len(neighbors[i]),
        }

    return {
        "pieces": pieces_out,
        "isolated": isolated,
        "fragile": fragile,
        "unknown_class": unknown,
        "considered": n,
    }


class RSDW_OT_ValidateStability(Operator):
    bl_idname = "rsdw.validate_stability"
    bl_label = "Validate Stability"
    bl_description = (
        "Check whether every structural piece (walls, floors, beams) "
        "is connected through a chain of compatible plug snaps back to "
        "an anchor (foundation, prop, farm plot, tier-0). Uses the "
        "per-piece SnappingRadius (default 80 cm, from the game's "
        "UBuildingSnapComponent). Pieces with NO path to an anchor are "
        "selected as 'isolated' (will collapse in-game). Optionally "
        "flags pieces past the hop threshold as 'fragile'"
    )
    bl_options = {"REGISTER", "UNDO"}

    only_in_active_collection: BoolProperty(
        name="Only active collection",
        description="Restrict validation to objects in the active collection",
        default=False,
    )  # type: ignore[valid-type]
    select_fragile: BoolProperty(
        name="Also select fragile",
        description=(
            "Also add pieces whose shortest path to an anchor exceeds "
            "the hop threshold to the selection"
        ),
        default=False,
    )  # type: ignore[valid-type]

    def execute(self, context):
        scene = context.scene
        s = scene.rsdw_settings
        scale = float(s.scale)
        threshold = int(s.stability_fragile_hops)

        spm = _load_stability_profile_map()
        if not spm.get("profiles"):
            self.report({"ERROR"},
                        "StabilityProfileMap.json missing or empty.")
            return {"CANCELLED"}

        result = _validate_stability(scene, scale, threshold)
        if result["considered"] == 0:
            self.report({"ERROR"}, "No pieces with snap data in scene.")
            return {"CANCELLED"}

        target_objs = None
        if self.only_in_active_collection:
            ac = context.view_layer.active_layer_collection
            if ac and ac.collection:
                target_objs = set(ac.collection.all_objects)

        isolated = result["isolated"]
        fragile = result["fragile"]
        if target_objs is not None:
            isolated = [o for o in isolated if o in target_objs]
            fragile = [o for o in fragile if o in target_objs]

        for o in scene.objects:
            try:
                o.select_set(False)
            except RuntimeError:
                pass
        sel_pool = list(isolated)
        if self.select_fragile:
            sel_pool.extend(fragile)
        for o in sel_pool:
            try:
                o.select_set(True)
            except RuntimeError:
                pass
        if sel_pool:
            try:
                context.view_layer.objects.active = sel_pool[0]
            except Exception:
                pass

        global _validate_cache
        _validate_cache = {
            "considered": result["considered"],
            "unknown_class": result["unknown_class"],
            "isolated_count": len(isolated),
            "fragile_count": len(fragile),
            "threshold": threshold,
        }

        msg = (f"Stability: {len(isolated)} isolated, {len(fragile)} fragile "
               f"(>={threshold} hops) / {result['considered']} pieces "
               f"(unknown_class={result['unknown_class']}). "
               f"Selected in viewport.")
        self.report({"INFO"}, msg)
        print("[RSDW stability] " + msg)
        for o in isolated[:30]:
            info = result["pieces"].get(o.name, {})
            print(f"  ISOLATED {o.name}  cls={_resolve_class_for_obj(o)}"
                  f"  profile={info.get('profile')}"
                  f"  neighbors={info.get('neighbor_count')}")
        for o in fragile[:10]:
            info = result["pieces"].get(o.name, {})
            print(f"  FRAGILE  {o.name}  cls={_resolve_class_for_obj(o)}"
                  f"  profile={info.get('profile')}"
                  f"  hops={info.get('hops_to_anchor')}")
        return {"FINISHED"}


class RSDW_OT_FindProblems(Operator):
    bl_idname = "rsdw.find_problems"
    bl_label = "Find Problems"
    bl_description = (
        "Run the friendly build check: export metadata first, then structural "
        "support. Selects the highest-priority pieces that need attention"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        global _problem_cache, _validate_cache
        coll = _context_build_collection(context)
        if coll is None:
            _problem_cache = {
                "collection": "",
                "level": "ERROR",
                "message": "No active build collection.",
                "selected": 0,
            }
            self.report({"ERROR"}, "No active RSDW build collection. Use New Build or select a build piece.")
            return {"CANCELLED"}

        preflight = _run_build_preflight(context, coll, select_problems=False)
        unknown_runtime = list(preflight.get("_unknown_runtime_objects") or [])
        if unknown_runtime:
            _select_objects(context, unknown_runtime)
            _problem_cache = {
                "collection": coll.name,
                "level": "WARNING",
                "message": f"{len(unknown_runtime)} piece(s) missing runtime piece data.",
                "selected": len(unknown_runtime),
            }
            self.report(
                {"WARNING"},
                f"Selected {len(unknown_runtime)} piece(s) missing runtime piece data.",
            )
            return {"FINISHED"}

        scene = context.scene
        settings = scene.rsdw_settings
        spm = _load_stability_profile_map()
        if not spm.get("profiles"):
            _problem_cache = {
                "collection": coll.name,
                "level": "WARNING",
                "message": "Export metadata OK; stability profile data missing.",
                "selected": 0,
            }
            self.report({"WARNING"}, "Export metadata is OK, but stability profile data is missing.")
            return {"FINISHED"}

        result = _validate_stability(scene, float(settings.scale), int(settings.stability_fragile_hops))
        build_objects = set(_collection_objects_recursive(coll))
        isolated = [obj for obj in result.get("isolated", []) if obj in build_objects]
        fragile = [obj for obj in result.get("fragile", []) if obj in build_objects]

        _validate_cache = {
            "considered": result.get("considered", 0),
            "unknown_class": result.get("unknown_class", 0),
            "isolated_count": len(isolated),
            "fragile_count": len(fragile),
            "threshold": int(settings.stability_fragile_hops),
        }

        if isolated:
            _select_objects(context, isolated)
            _problem_cache = {
                "collection": coll.name,
                "level": "WARNING",
                "message": f"{len(isolated)} unsupported structural piece(s).",
                "selected": len(isolated),
            }
            self.report({"WARNING"}, f"Selected {len(isolated)} unsupported structural piece(s).")
            return {"FINISHED"}
        if fragile:
            _select_objects(context, fragile)
            _problem_cache = {
                "collection": coll.name,
                "level": "WARNING",
                "message": f"{len(fragile)} fragile structural piece(s).",
                "selected": len(fragile),
            }
            self.report({"WARNING"}, f"Selected {len(fragile)} fragile structural piece(s).")
            return {"FINISHED"}

        no_snap = int(preflight.get("no_snap_data", 0) or 0)
        duplicate_ids = int(preflight.get("duplicate_piece_ids", 0) or 0)
        hidden = int(preflight.get("hidden_objects", 0) or 0)
        details = []
        if no_snap:
            details.append(f"{no_snap} piece(s) won't auto-snap")
        if duplicate_ids:
            details.append(f"{duplicate_ids} duplicate ID(s) will be fixed on export")
        if hidden:
            details.append(f"{hidden} hidden object(s) skipped")
        suffix = "  " + "; ".join(details) if details else ""
        _problem_cache = {
            "collection": coll.name,
            "level": "INFO",
            "message": "No export-blocking or structural problems found." + suffix,
            "selected": 0,
        }
        self.report({"INFO"}, f"No export-blocking or structural problems found.{suffix}")
        return {"FINISHED"}


# ---------- anchor operators ----------

def _find_object_by_piece_id(coll, piece_id: int):
    if coll is None or piece_id <= 0:
        return None
    for obj in _collection_objects_recursive(coll):
        try:
            pid = int(obj.get("rsdw_piece_id", 0) or 0)
        except (TypeError, ValueError):
            continue
        if pid == piece_id:
            return obj
    return None


def _resolve_anchor_summary(coll) -> tuple[int, str]:
    """Return (anchor_piece_id, label) for the panel. label is empty when none."""
    if coll is None:
        return 0, ""
    try:
        pid = int(coll.get("rsdw_anchor_piece_id", 0) or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid <= 0:
        return 0, ""
    obj = _find_object_by_piece_id(coll, pid)
    if obj is None:
        return pid, f"#{pid} (piece not in build)"
    meta = _metadata_object_for(obj) or obj
    short = _shorten_class(str(meta.get("rsdw_class_name", "") or "")) or obj.name
    return pid, f"#{pid}  {short}"


class RSDW_OT_SetAnchor(Operator):
    bl_idname = "rsdw.set_anchor"
    bl_label = "Set Selected as Anchor"
    bl_description = (
        "Mark the active piece as the build's anchor (single anchor per build). "
        "The anchor's piece_id and piece_data_index are written to the exported JSON"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        coll = _context_build_collection(context)
        if coll is None:
            self.report({"ERROR"}, "No active RSDW build collection.")
            return {"CANCELLED"}
        obj = context.active_object
        if obj is None:
            self.report({"ERROR"}, "Select a build piece first, then run Set Anchor.")
            return {"CANCELLED"}
        try:
            pid = int(obj.get("rsdw_piece_id", 0) or 0)
        except (TypeError, ValueError):
            pid = 0
        coll_objs = _collection_objects_recursive(coll)
        if obj not in coll_objs:
            self.report({"ERROR"}, f"'{obj.name}' is not in the active build collection.")
            return {"CANCELLED"}
        # Mint a fresh piece_id on the fly for drag-dropped pieces that
        # haven't been through an export pass yet. Same allocation strategy
        # the export uses: max(existing) + 1, scoped to this collection.
        if pid <= 0:
            max_id = 0
            for o in coll_objs:
                try:
                    other = int(o.get("rsdw_piece_id", 0) or 0)
                except (TypeError, ValueError):
                    other = 0
                if other > max_id:
                    max_id = other
            pid = max_id + 1
            obj["rsdw_piece_id"] = pid
        coll["rsdw_anchor_piece_id"] = pid
        self.report({"INFO"}, f"Anchor set: piece_id {pid} ({obj.name}).")
        return {"FINISHED"}


class RSDW_OT_ClearAnchor(Operator):
    bl_idname = "rsdw.clear_anchor"
    bl_label = "Clear Anchor"
    bl_description = "Remove the build's anchor assignment"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        coll = _context_build_collection(context)
        if coll is None:
            self.report({"ERROR"}, "No active RSDW build collection.")
            return {"CANCELLED"}
        if "rsdw_anchor_piece_id" in coll:
            del coll["rsdw_anchor_piece_id"]
        self.report({"INFO"}, "Anchor cleared.")
        return {"FINISHED"}


class RSDW_OT_SelectAnchor(Operator):
    bl_idname = "rsdw.select_anchor"
    bl_label = "Select Anchor"
    bl_description = "Select the current anchor piece in the viewport"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        coll = _context_build_collection(context)
        if coll is None:
            self.report({"ERROR"}, "No active RSDW build collection.")
            return {"CANCELLED"}
        try:
            pid = int(coll.get("rsdw_anchor_piece_id", 0) or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid <= 0:
            self.report({"WARNING"}, "No anchor set on this build.")
            return {"CANCELLED"}
        obj = _find_object_by_piece_id(coll, pid)
        if obj is None:
            self.report({"WARNING"}, f"Anchor piece_id {pid} not found in build.")
            return {"CANCELLED"}
        _select_objects(context, [obj])
        try:
            context.view_layer.objects.active = obj
        except Exception:
            pass
        return {"FINISHED"}


# ---------- basebuilding template operator ----------

def _bundled_template_path() -> str:
    return os.path.join(_addon_dir(), TEMPLATE_BLEND_REL)


class RSDW_OT_NewBasebuildingFile(Operator):
    bl_idname = "rsdw.new_basebuilding_file"
    bl_label = "New Basebuilding File..."
    bl_description = (
        "Save a fresh copy of the bundled basebuilding template to a chosen "
        "location and open it. The bundled template inside the addon is "
        "never modified, so this button always produces a clean starting file"
    )
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    filter_glob: StringProperty(default="*.blend", options={"HIDDEN"})  # type: ignore[valid-type]

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = "basebuilding.blend"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        src = _bundled_template_path()
        if not os.path.isfile(src):
            self.report({"ERROR"}, f"Bundled template not found: {src}")
            return {"CANCELLED"}
        dst = bpy.path.abspath(self.filepath)
        if not dst.lower().endswith(".blend"):
            dst += ".blend"
        try:
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            shutil.copyfile(src, dst)
        except Exception as e:
            self.report({"ERROR"}, f"Copy failed: {e}")
            return {"CANCELLED"}
        try:
            bpy.ops.wm.open_mainfile(filepath=dst)
        except Exception as e:
            self.report({"ERROR"}, f"Wrote {dst} but open failed: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"New basebuilding file: {dst}")
        return {"FINISHED"}


# ---------- collection helpers ----------

class RSDW_OT_MoveSelectedToNewCollection(Operator):
    bl_idname = "rsdw.move_selected_to_new_collection"
    bl_label = "Move Selected to New Collection"
    bl_description = (
        "Create a new collection and move every selected object into it, "
        "unlinking them from any other collection they were in"
    )
    bl_options = {"REGISTER", "UNDO"}

    base_name: StringProperty(
        name="Collection Name",
        default="Selected_Objects_Collection",
    )  # type: ignore[valid-type]

    def execute(self, context):
        selected_objects = list(context.selected_objects)
        if not selected_objects:
            self.report({"WARNING"}, "Nothing selected.")
            return {"CANCELLED"}
        name = _unique_collection_name(self.base_name or "Selected_Objects_Collection")
        new_collection = bpy.data.collections.new(name)
        context.scene.collection.children.link(new_collection)
        for obj in selected_objects:
            if obj.name not in new_collection.objects:
                new_collection.objects.link(obj)
            for collection in list(obj.users_collection):
                if collection != new_collection:
                    try:
                        collection.objects.unlink(obj)
                    except Exception:
                        pass
        self.report(
            {"INFO"},
            f"Moved {len(selected_objects)} selected object(s) into '{new_collection.name}'.",
        )
        return {"FINISHED"}


# ---------- N-panel ----------

class RSDW_PT_main(Panel):
    bl_idname = "RSDW_PT_main"
    bl_label = "RSDW Base Builder"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY

    def draw(self, context):
        layout = self.layout
        s: RSDWSettings = context.scene.rsdw_settings

        col = layout.column(align=True)
        col.operator(RSDW_OT_NewBasebuildingFile.bl_idname,
                     text="New Basebuilding File...", icon="FILE_NEW")
        col.operator(RSDW_OT_NewBuildCollection.bl_idname,
                     text="New Build", icon="COLLECTION_NEW")
        col.operator(RSDW_OT_ImportBuildingJson.bl_idname,
                     text="Import Building JSON...", icon="IMPORT")
        col.operator(RSDW_OT_ExportBuildingJson.bl_idname,
                     text="Export Build...", icon="EXPORT")

        layout.separator()
        status = _run_build_preflight(context)
        status_box = layout.box()
        status_box.label(text="Build Status", icon="CHECKMARK" if status.get("ready") else "INFO")
        if status.get("collection"):
            status_box.label(text=status["collection"], icon="OUTLINER_COLLECTION")
            status_box.label(text=f"Pieces: {status.get('exportable_pieces', 0)}", icon="MESH_CUBE")
            if status.get("hidden_objects", 0):
                status_box.label(text=f"Hidden on export: {status['hidden_objects']}", icon="HIDE_ON")
            if status.get("unknown_runtime_index", 0):
                status_box.label(text=f"Need attention: {status['unknown_runtime_index']}", icon="ERROR")
            elif status.get("exportable_pieces", 0):
                status_box.label(text="Ready to export", icon="CHECKMARK")
        else:
            status_box.label(text="No build collection active", icon="INFO")
        row = status_box.row(align=True)
        row.operator(RSDW_OT_FindProblems.bl_idname,
                     text="Find Problems", icon="VIEWZOOM")
        row.operator(RSDW_OT_PreflightBuild.bl_idname,
                     text="Check", icon="CHECKMARK")
        if _problem_cache and _problem_cache.get("collection") == status.get("collection"):
            level = _problem_cache.get("level")
            icon = "CHECKMARK" if level == "INFO" else "ERROR"
            status_box.label(text=str(_problem_cache.get("message") or ""), icon=icon)

        layout.separator()
        anchor_box = layout.box()
        anchor_box.label(text="Anchor", icon="PINNED")
        # Resolve the live build collection the same way Set/Clear/Select
        # operators do, so the label always agrees with what those buttons
        # would act on. Falling back to status["collection"] alone breaks
        # for fresh files / drag-dropped pieces where validate hasn't run.
        anchor_coll = _context_build_collection(context)
        if anchor_coll is None and status.get("collection"):
            anchor_coll = bpy.data.collections.get(status["collection"])
        anchor_pid, anchor_label = _resolve_anchor_summary(anchor_coll)
        if anchor_pid > 0:
            anchor_box.label(text=anchor_label, icon="PINNED")
            row = anchor_box.row(align=True)
            row.operator(RSDW_OT_SelectAnchor.bl_idname,
                         text="Select", icon="RESTRICT_SELECT_OFF")
            row.operator(RSDW_OT_ClearAnchor.bl_idname,
                         text="Clear", icon="X")
        else:
            anchor_box.label(text="No anchor set", icon="UNPINNED")
        anchor_box.operator(RSDW_OT_SetAnchor.bl_idname,
                            text="Set Selected as Anchor", icon="PINNED")

        layout.separator()
        scene_box = layout.box()
        scene_box.label(text="Scene", icon="OUTLINER_COLLECTION")
        scene_box.operator(RSDW_OT_MoveSelectedToNewCollection.bl_idname,
                           text="Move Selected to New Collection",
                           icon="OUTLINER_OB_GROUP_INSTANCE")

        layout.separator()
        snap_box = layout.box()
        snap_box.label(text="Build Assist", icon="SNAP_ON")
        snap_box.prop(s, "auto_snap")
        sub = snap_box.column(align=True)
        sub.active = s.auto_snap
        sub.prop(s, "auto_snap_max_distance")
        snap_box.operator(RSDW_OT_SnapToActive.bl_idname,
                          text="Snap Selected to Active", icon="SNAP_VERTEX")

        layout.separator()
        layout.label(text="Asset Library", icon="ASSET_MANAGER")
        layout.label(text=f"  {ASSET_LIBRARY_NAME}", icon="DOT")


class RSDW_PT_advanced(Panel):
    bl_idname = "RSDW_PT_advanced"
    bl_label = "Advanced"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s: RSDWSettings = context.scene.rsdw_settings

        box = layout.box()
        box.label(text="Import Options", icon="IMPORT")
        box.prop(s, "recenter")
        box.prop(s, "include_ghosted")
        box.prop(s, "scale")

        snap_box = layout.box()
        snap_box.label(text="Snap Diagnostics", icon="SNAP_GRID")
        snap_box.prop(s, "auto_snap_align_rotation")
        snap_box.prop(s, "surface_snap_inset")
        snap_box.operator(RSDW_OT_DiagnoseAutoSnap.bl_idname,
                          text="Diagnose Selected", icon="INFO")

        lint_box = layout.box()
        lint_box.label(text="Validation (heuristic)", icon="CHECKMARK")
        lint_box.prop(s, "lint_tolerance")
        lint_op = lint_box.operator(RSDW_OT_LintIsolated.bl_idname,
                                    text="Find Isolated Pieces",
                                    icon="ZOOM_SELECTED")
        lint_op.only_in_active_collection = False
        lint_box.label(text="  Selects pieces with NO snapped neighbor.",
                       icon="DOT")
        lint_box.label(text="  Does NOT verify full structural support.",
                       icon="ERROR")

        stab_box = layout.box()
        stab_box.label(text="Validation (structural)", icon="PHYSICS")
        stab_box.prop(s, "stability_fragile_hops")
        stab_op = stab_box.operator(RSDW_OT_ValidateStability.bl_idname,
                                    text="Validate Stability",
                                    icon="MOD_PHYSICS")
        stab_op.only_in_active_collection = False
        stab_op.select_fragile = False
        stab_box.label(text="  Selects pieces with no path to an anchor.",
                       icon="DOT")
        stab_box.label(text="  Anchors: foundation / prop / farm / tier-0.",
                       icon="DOT")


class RSDW_PT_plug_status(Panel):
    bl_idname = "RSDW_PT_plug_status"
    bl_label = "Plug Status (Active)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None:
            layout.label(text="No active object.", icon="INFO")
            return
        layout.label(text=obj.name, icon="OBJECT_DATA")
        layout.operator(RSDW_OT_InspectPlugs.bl_idname,
                        text="Inspect Active", icon="VIEWZOOM")

        rows = _plug_inspect_cache.get(obj.name)
        if not rows:
            layout.label(text="(click Inspect Active to compute)", icon="DOT")
            return

        col = layout.column(align=True)
        snapped = sum(1 for r in rows if r[2] == "snapped")
        col.label(text=f"Snapped: {snapped} / {len(rows)} plugs",
                  icon="LINKED" if snapped == len(rows) else "UNLINKED")
        for idx, tag, status, dist, neighbor in rows:
            row = col.row(align=True)
            if status == "snapped":
                row.label(text=f"#{idx} {tag}: -> {neighbor} @ {dist*100:.2f} cm",
                          icon="CHECKMARK")
            elif status == "free":
                row.label(text=f"#{idx} {tag}: free (nearest {dist*100:.1f} cm)",
                          icon="DOT")
            else:
                row.label(text=f"#{idx} {tag}: free (no compat in 1 m)",
                          icon="X")


# ---------- registration ----------

def _register_keymaps() -> None:
    _unregister_keymaps()
    try:
        keyconfig = bpy.context.window_manager.keyconfigs.addon
    except Exception:
        keyconfig = None
    if keyconfig is None:
        return

    keymap = keyconfig.keymaps.new(name="3D View", space_type="VIEW_3D")
    diagnose_item = keymap.keymap_items.new(
        RSDW_OT_DiagnoseAutoSnap.bl_idname,
        type="D",
        value="PRESS",
        ctrl=True,
        alt=True,
    )
    _addon_keymaps.append((keymap, diagnose_item))


def _unregister_keymaps() -> None:
    for keymap, item in list(_addon_keymaps):
        try:
            keymap.keymap_items.remove(item)
        except Exception:
            pass
    _addon_keymaps.clear()

_classes = (
    RSDWSettings,
    RSDW_OT_NewBuildCollection,
    RSDW_OT_ImportBuildingJson,
    RSDW_OT_ExportBuildingJson,
    RSDW_OT_PreflightBuild,
    RSDW_OT_SnapToActive,
    RSDW_OT_DiagnoseAutoSnap,
    RSDW_OT_LintIsolated,
    RSDW_OT_InspectPlugs,
    RSDW_OT_ValidateStability,
    RSDW_OT_FindProblems,
    RSDW_OT_SetAnchor,
    RSDW_OT_ClearAnchor,
    RSDW_OT_SelectAnchor,
    RSDW_OT_NewBasebuildingFile,
    RSDW_OT_MoveSelectedToNewCollection,
    RSDW_PT_main,
    RSDW_PT_advanced,
    RSDW_PT_plug_status,
)


def register() -> None:
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.rsdw_settings = bpy.props.PointerProperty(type=RSDWSettings)
    _register_keymaps()

    # Auto-snap-on-drop handler.
    if _rsdw_auto_snap_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_rsdw_auto_snap_handler)
    if _rsdw_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_rsdw_load_post)
    # With auto-snap defaulting to ON, seed the known-object snapshot now so
    # existing scene objects are not mistaken for fresh drops.
    _rsdw_load_post(None)

    first_err = None
    try:
        _register_asset_library()
    except Exception as e:
        first_err = e

        def _deferred():
            try:
                _register_asset_library()
            except Exception as e2:
                print(f"[RSDW Base Builder] asset library register failed (deferred): {e2}")
            return None

        try:
            bpy.app.timers.register(_deferred, first_interval=0.1)
        except Exception as e3:
            print(f"[RSDW Base Builder] asset library register failed: {first_err} / timer: {e3}")


def unregister() -> None:
    _unregister_keymaps()

    try:
        _unregister_asset_library()
    except Exception as e:
        print(f"[RSDW Base Builder] asset library unregister failed: {e}")

    if _rsdw_auto_snap_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_rsdw_auto_snap_handler)
    if _rsdw_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_rsdw_load_post)
    try:
        if bpy.app.timers.is_registered(_drain_pending_snaps):
            bpy.app.timers.unregister(_drain_pending_snaps)
    except Exception:
        pass
    _pending_snaps.clear()

    if hasattr(bpy.types.Scene, "rsdw_settings"):
        del bpy.types.Scene.rsdw_settings
    for c in reversed(_classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
