"""
Blender-side worker: import one .uemodel, build materials from nearby material
JSONs (MI_*, MT_*, M_*, ... — any JSON with a top-level `Textures` dict; matched
via the Unreal `material_path` baked into the .uemodel), with a filename-heuristic
hybrid fallback. Saves a .blend next to the source, exports a .glb next to the
source, and emits a single RESULT: JSON line to stdout.

Launched by tools/ModelData/BuildGLB.py via:

    blender.exe --background --factory-startup --python BuildGLBWorker.py -- \
        --task-file <path to a small JSON task descriptor>

Task file shape:
{
    "source_root": "<absolute path to data root (e.g. 0.11.1.4)>",
    "save_blend": true,
    "entry": {
        "name": "SM_Foo.uemodel",
        "path": "RSDragonwilds/.../SM_Foo.uemodel",
        "Materials": { "material_json_paths": [...], "items": [...] },
        "MaterialsHybrid": { "texture_image_paths": [...], "discovery": {...} }
    }
}

On success prints: RESULT:{"status":"success", ...}
On failure prints: RESULT:{"status":"failed","error":"..."} and exits non-zero.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import traceback
from pathlib import Path

import bpy
import addon_utils


TEXTURE_EXTENSIONS = (".png", ".tga", ".dds", ".jpg", ".jpeg", ".exr", ".bmp", ".hdr", ".webp")

# MI JSON slot name -> logical shader role.
MI_SLOT_ROLES = {
    "basecolor": "BaseColor",
    "basecolor map": "BaseColor",
    "base color": "BaseColor",
    "base color map": "BaseColor",
    "base colour": "BaseColor",
    "base colour map": "BaseColor",
    "pm_diffuse": "BaseColor",
    "diffuse": "BaseColor",
    "albedo": "BaseColor",
    "normal": "Normal",
    "normal map": "Normal",
    "pm_normals": "Normal",
    "normalmap": "Normal",
    "orm": "ORM",
    "orm map": "ORM",
    "occlusionroughnessmetal": "ORM",
    "occlusionroughnessmetallic": "ORM",
    "ambientocclusionroughnessmetallic": "ORM",
    "metallic": "Metallic",
    "pm_metallic": "Metallic",
    "roughness": "Roughness",
    "pm_roughness": "Roughness",
    "emissive": "Emission",
    "emission": "Emission",
    "pm_emissive": "Emission",
    "ao": "AO",
    "ambientocclusion": "AO",
}

# Filename suffix (lowercased, leading underscore) -> role. Order matters: longer first.
HYBRID_SUFFIX_ROLES: list[tuple[str, str]] = [
    ("_basecolor", "BaseColor"),
    ("_albedo", "BaseColor"),
    ("_bcc", "BaseColor"),
    ("_bc", "BaseColor"),
    ("_diffuse", "BaseColor"),
    ("_d", "BaseColor"),
    ("_normal", "Normal"),
    ("_nrm", "Normal"),
    ("_n", "Normal"),
    ("_metallic", "Metallic"),
    ("_metal", "Metallic"),
    ("_roughness", "Roughness"),
    ("_rough", "Roughness"),
    ("_emissive", "Emission"),
    ("_emission", "Emission"),
    ("_e", "Emission"),
    ("_ao", "AO"),
    ("_orm", "ORM"),
    ("_arm", "ORM"),
    ("_mra", "ORM"),
]

NON_COLOR_ROLES = {"Normal", "Metallic", "Roughness", "AO", "ORM"}


# ---------------------------------------------------------------------------
# argv parsing (Blender puts our args after "--")
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    p = argparse.ArgumentParser()
    p.add_argument("--task-file", required=True)
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# RESULT emission
# ---------------------------------------------------------------------------

def _emit_result(obj: dict) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    # Prefix so the driver can pick this line out of Blender's noisy stdout.
    sys.stdout.write("RESULT:" + json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# .uemodel lightweight header/material-list re-read (path + name per slot)
# ---------------------------------------------------------------------------

def _read_uemodel_materials(uemodel_abs: Path) -> list[dict]:
    """
    Return [{"name": str, "path": str}, ...] for LOD0's material slots.

    Re-parses the file using the bundled UEFormat reader so we can recover
    `material_path` (the Unreal Package.Asset reference), which the in-scene
    Blender material only exposes as a name.
    """
    from io_scene_ueformat.importer.classes import (
        EUEFormatVersion,
        MAGIC,
        MODEL_IDENTIFIER,
        UEModel,
    )
    from io_scene_ueformat.importer.reader import FArchiveReader

    raw = uemodel_abs.read_bytes()
    with FArchiveReader(raw) as ar:
        magic = ar.read_string(len(MAGIC))
        if magic != MAGIC:
            raise ValueError(f"Bad magic in {uemodel_abs}")
        identifier = ar.read_fstring()
        file_version = EUEFormatVersion(int.from_bytes(ar.read_byte(), byteorder="big"))
        _object_name = ar.read_fstring()

        read_archive = ar
        is_compressed = ar.read_bool()
        if is_compressed:
            compression_type = ar.read_fstring()
            uncompressed_size = ar.read_int()
            _compressed_size = ar.read_int()

            if compression_type == "GZIP":
                read_archive = FArchiveReader(gzip.decompress(ar.read_to_end()))
            elif compression_type == "ZSTD":
                import io_scene_ueformat as ueformat_pkg
                read_archive = FArchiveReader(
                    ueformat_pkg.zstd_decompressor.decompress(
                        ar.read_to_end(), uncompressed_size
                    )
                )
            else:
                raise ValueError(f"Unknown compression: {compression_type}")

        read_archive.file_version = file_version
        read_archive.metadata["scale"] = 1.0

        if identifier != MODEL_IDENTIFIER:
            return []

        if file_version >= EUEFormatVersion.LevelOfDetailFormatRestructure:
            model = UEModel.from_archive(read_archive)
        else:
            model = UEModel.from_archive_legacy(read_archive)

    if not model.lods:
        return []
    lod0 = model.lods[0]
    return [{"name": m.material_name, "path": m.material_path} for m in lod0.materials]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _strip_trailing_asset_suffix(package_path: str) -> str:
    """
    Turn "<pkg>/Foo.Foo" into "<pkg>/Foo". UE package refs are "Package.Asset"
    where the asset name repeats the final segment.

    Note: does NOT re-root any mount-point prefixes (/Game/, /<PluginName>/)
    — that is handled by `_package_path_to_disk_relative` so callers can
    distinguish mount points from concrete on-disk paths.
    """
    s = package_path.replace("\\", "/").strip()
    if not s:
        return s
    if "." in s:
        head, tail = s.rsplit(".", 1)
        if head.rsplit("/", 1)[-1] == tail:
            return head
    return s


# Plugin mount-points Unreal uses to address content outside /Game/. In this
# project they live under RSDragonwilds/Plugins/GameFeatures/<Plugin>/Content/.
# Example: "/DowdunReach/Art/.../MI_Foo.MI_Foo" -> resolves under
# RSDragonwilds/Plugins/GameFeatures/DowdunReach/Content/Art/.../MI_Foo(.json).
_PLUGIN_ROOT_REL = "RSDragonwilds/Plugins/GameFeatures"
# /Game/ is the default project mount = RSDragonwilds/Content/.
_GAME_ROOT_REL = "RSDragonwilds/Content"


def _package_path_to_disk_relatives(package_path: str) -> list[str]:
    """Translate an Unreal package reference into a list of repo-relative
    on-disk paths (without file extension) to try in priority order.

    Handles three input shapes:
        "/Game/Foo/Bar"                      -> ["RSDragonwilds/Content/Foo/Bar"]
        "/<Plugin>/Foo/Bar"                  -> ["RSDragonwilds/Plugins/GameFeatures/<Plugin>/Content/Foo/Bar",
                                                  "<Plugin>/Foo/Bar"]  # fallback if unexpected layout
        "RSDragonwilds/Content/Foo/Bar"      -> ["RSDragonwilds/Content/Foo/Bar"]  (already repo-relative)
        "RSDragonwilds/Plugins/.../Foo/Bar"  -> ["RSDragonwilds/Plugins/.../Foo/Bar"]

    The Package.Asset dotted tail is expected to already be stripped.
    """
    s = (package_path or "").replace("\\", "/").strip()
    if not s:
        return []
    # Pre-normalized repo-relative refs: pass through unchanged.
    if s.startswith(("RSDragonwilds/", "RSDragonwilds\\")):
        return [s]
    if s.startswith("/Game/"):
        return [f"{_GAME_ROOT_REL}/{s[len('/Game/'):]}"]
    if s.startswith("/"):
        # Plugin-style mount: "/<PluginName>/<rest>".
        without_lead = s[1:]
        if "/" in without_lead:
            plugin, rest = without_lead.split("/", 1)
            return [
                f"{_PLUGIN_ROOT_REL}/{plugin}/Content/{rest}",
                without_lead,
            ]
        return [without_lead]
    return [s]


def _iter_data_roots(source_root: Path, data_roots: list[Path] | None = None) -> list[Path]:
    roots: list[Path] = [source_root]
    if data_roots:
        roots.extend(Path(root) for root in data_roots)
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _normalize_material_json_data(data: object) -> dict | None:
    if isinstance(data, dict) and ("Textures" in data or "Parameters" in data):
        return {
            "Textures": data.get("Textures") or {},
            "Parameters": data.get("Parameters") or {},
        }

    exports = data if isinstance(data, list) else [data]
    for export in exports:
        if not isinstance(export, dict):
            continue
        props = export.get("Properties")
        if not isinstance(props, dict):
            continue
        if not (
            "TextureParameterValues" in props
            or "ScalarParameterValues" in props
            or "VectorParameterValues" in props
        ):
            continue

        textures: dict[str, str] = {}
        for item in props.get("TextureParameterValues") or []:
            if not isinstance(item, dict):
                continue
            info = item.get("ParameterInfo") or {}
            value = item.get("ParameterValue") or {}
            if not isinstance(info, dict) or not isinstance(value, dict):
                continue
            name = info.get("Name")
            path = value.get("ObjectPath")
            if isinstance(name, str) and isinstance(path, str) and path.strip():
                textures[name] = path

        scalars: dict[str, float] = {}
        for item in props.get("ScalarParameterValues") or []:
            if not isinstance(item, dict):
                continue
            info = item.get("ParameterInfo") or {}
            name = info.get("Name") if isinstance(info, dict) else None
            value = item.get("ParameterValue")
            if not isinstance(name, str):
                continue
            try:
                scalars[name] = float(value)
            except (TypeError, ValueError):
                pass

        colors: dict[str, dict] = {}
        for item in props.get("VectorParameterValues") or []:
            if not isinstance(item, dict):
                continue
            info = item.get("ParameterInfo") or {}
            name = info.get("Name") if isinstance(info, dict) else None
            value = item.get("ParameterValue")
            if isinstance(name, str) and isinstance(value, dict):
                colors[name] = value

        return {"Textures": textures, "Parameters": {"Scalars": scalars, "Colors": colors}}
    return None


def _load_material_json_data(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _normalize_material_json_data(data)


def _resolve_texture_on_disk(
    source_root: Path,
    package_path: str,
    data_roots: list[Path] | None = None,
) -> Path | None:
    """Look up T_Foo on disk under source_root trying each texture extension."""
    pkg = _strip_trailing_asset_suffix(package_path)
    if not pkg:
        return None
    # Try each candidate repo-relative path (handles /Game/ and /<Plugin>/ mounts).
    for root in _iter_data_roots(source_root, data_roots):
        for rel in _package_path_to_disk_relatives(pkg):
            base = root / rel
            for ext in TEXTURE_EXTENSIONS:
                for candidate in (
                    base.with_suffix(ext),
                    base.parent / f"{base.name}{ext}",
                    base.parent / f"{base.name}_0{ext}",
                ):
                    if candidate.is_file():
                        return candidate
    return None


def _looks_like_material_json(path: Path) -> bool:
    """True if `path` is a JSON file whose top level has a `Textures` key.
    Mirrors the content-sniff rule in CompileModelData.py."""
    if not path.is_file() or path.suffix.lower() != ".json":
        return False
    try:
        data = _load_material_json_data(path)
    except OSError:
        return False
    return data is not None


def _resolve_material_json_for_slot(
    slot_name: str,
    slot_path: str,
    mi_paths_rel: list[str],
    source_root: Path,
    data_roots: list[Path] | None = None,
) -> Path | None:
    """Pick the material JSON for a slot. Priority:
    1. Direct on-disk lookup from the Unreal `material_path` — the authoritative answer.
       (Works regardless of whether CompileModelData happened to collect the file.)
    2. Exact path suffix match against the pre-collected list.
    3. Stem match (case-insensitive) against the pre-collected list.

    No "one-file fallback" — if we can't confidently match, return None so the
    caller falls through to hybrid or leaves the slot empty."""

    # 1) Authoritative lookup: material_path -> <source_root>/<stripped>.json.
    #    Uses `_package_path_to_disk_relatives` so Unreal mount points like
    #    "/Game/..." (-> RSDragonwilds/Content/...) and plugin mounts
    #    "/DowdunReach/..." (-> RSDragonwilds/Plugins/GameFeatures/.../Content/...)
    #    all resolve correctly. Plain "RSDragonwilds/..." refs pass through.
    if slot_path:
        stripped = _strip_trailing_asset_suffix(slot_path)
        if stripped:
            for root in _iter_data_roots(source_root, data_roots):
                for rel in _package_path_to_disk_relatives(stripped):
                    candidate = root / f"{rel}.json"
                    if _looks_like_material_json(candidate):
                        return candidate

    if not mi_paths_rel:
        return None

    mi_abs = [root / p for root in _iter_data_roots(source_root, data_roots) for p in mi_paths_rel]

    # 2) Exact path suffix match against the pre-collected list.
    if slot_path:
        target = _strip_trailing_asset_suffix(slot_path).lower()
        if target:
            for abs_p in mi_abs:
                try:
                    rel = abs_p.resolve().relative_to(source_root.resolve()).as_posix().lower()
                except ValueError:
                    rel = abs_p.as_posix().lower()
                rel_no_ext = rel[:-5] if rel.endswith(".json") else rel
                if rel_no_ext == target or rel_no_ext.endswith("/" + target):
                    return abs_p
                if target.endswith("/" + rel_no_ext) or rel_no_ext.endswith(target):
                    return abs_p

    # 3) Stem match (case-insensitive): material stem == slot_name or "MI_<slot_name>".
    slot_lower = (slot_name or "").lower()
    if not slot_lower:
        return None
    candidates: list[tuple[int, Path]] = []
    for abs_p in mi_abs:
        stem = abs_p.stem.lower()
        if stem == slot_lower:
            candidates.append((0, abs_p))
        elif stem == f"mi_{slot_lower}":
            candidates.append((1, abs_p))
        elif slot_lower in stem:
            candidates.append((2, abs_p))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    return None


# ---------------------------------------------------------------------------
# Shader graph construction
# ---------------------------------------------------------------------------

def _ensure_use_nodes(mat: bpy.types.Material) -> None:
    mat.use_nodes = True
    # Start from a clean slate: keep Output + Principled only.
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])


def _load_image(abs_path: Path, non_color: bool) -> bpy.types.Image | None:
    try:
        img = bpy.data.images.load(str(abs_path), check_existing=True)
    except RuntimeError:
        return None
    try:
        if non_color:
            img.colorspace_settings.name = "Non-Color"
        else:
            img.colorspace_settings.name = "sRGB"
    except Exception:
        pass
    return img


def _get_bsdf(mat: bpy.types.Material) -> bpy.types.Node | None:
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None


def _connect_role(
    mat: bpy.types.Material,
    role: str,
    image: bpy.types.Image,
    y_offset: int,
) -> None:
    """Attach a loaded Image to the Principled BSDF input matching `role`."""
    nt = mat.node_tree
    bsdf = _get_bsdf(mat)
    if bsdf is None:
        return

    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.location = (-600, y_offset)
    if role in NON_COLOR_ROLES:
        try:
            tex.image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass

    if role == "BaseColor":
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    elif role == "Normal":
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.location = (-300, y_offset)
        nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    elif role == "Metallic":
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Metallic"])
    elif role == "Roughness":
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Roughness"])
    elif role == "Emission":
        # Blender 5 Principled uses "Emission Color" + "Emission Strength".
        if "Emission Color" in bsdf.inputs:
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        elif "Emission" in bsdf.inputs:
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission"])
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 1.0
    elif role == "ORM":
        # Red=AO, Green=Roughness, Blue=Metallic (UE convention in packed textures).
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        sep.location = (-300, y_offset)
        nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    elif role == "AO":
        # Pure AO has no direct Principled input; leave the node floating so data is present.
        pass


def _apply_mi_parameters(
    mat: bpy.types.Material,
    parameters: dict,
    wired_texture_roles: set[str],
) -> list[str]:
    """Translate MI `Parameters` (scalars + colors) onto the Principled BSDF.

    Textures always win: a scalar/color is only applied if the corresponding
    role has no texture wired already. Only standard PBR inputs are honoured —
    artist-specific parameters (e.g. "Moss - height smoothstep width") are
    deliberately ignored to avoid guessing semantics.

    Returns the list of input names we set (for reporting).
    """
    if not isinstance(parameters, dict):
        return []
    bsdf = _get_bsdf(mat)
    if bsdf is None:
        return []

    colors = parameters.get("Colors") or {}
    scalars = parameters.get("Scalars") or {}
    applied: list[str] = []

    def _rgba_from(entry: object) -> tuple[float, float, float, float] | None:
        if not isinstance(entry, dict):
            return None
        try:
            r = float(entry.get("R", 0.0))
            g = float(entry.get("G", 0.0))
            b = float(entry.get("B", 0.0))
            a = float(entry.get("A", 1.0))
        except (TypeError, ValueError):
            return None
        return (r, g, b, a)

    def _set_input(name: str, value) -> bool:
        if name not in bsdf.inputs:
            return False
        # Skip if something is already linked to this input (texture took precedence).
        socket = bsdf.inputs[name]
        if socket.is_linked:
            return False
        try:
            socket.default_value = value
        except Exception:
            return False
        return True

    # --- Colors ---
    # Accept either "BaseColor" or generic "Color" as the albedo tint.
    base_color_entry = colors.get("BaseColor") or colors.get("Color")
    if "BaseColor" not in wired_texture_roles and "ORM" not in wired_texture_roles:
        rgba = _rgba_from(base_color_entry)
        if rgba is not None and _set_input("Base Color", rgba):
            applied.append("BaseColor(color)")

    # Emissive color (some MIs define just the color; others pair with intensity).
    emissive_entry = colors.get("EmissiveColor") or colors.get("Emissive")
    if "Emission" not in wired_texture_roles:
        rgba = _rgba_from(emissive_entry)
        if rgba is not None:
            target_input = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
            if _set_input(target_input, rgba):
                applied.append("EmissiveColor(color)")
                # Strength: prefer explicit scalar, else infer from color luma so
                # glTF viewers don't render jet-black emissives.
                intensity = scalars.get("EmissiveIntensity")
                try:
                    intensity = float(intensity) if intensity is not None else None
                except (TypeError, ValueError):
                    intensity = None
                if intensity is None:
                    intensity = 1.0 if max(rgba[:3]) > 0 else 0.0
                _set_input("Emission Strength", intensity)

    # --- Scalars ---
    # Straightforward 1:1 mappings to Principled BSDF defaults. ORM-packed
    # textures already drive Metallic + Roughness via SeparateColor, so skip
    # overriding those when ORM is present.
    orm_present = "ORM" in wired_texture_roles

    if "Metallic" not in wired_texture_roles and not orm_present:
        if "Metallic" in scalars:
            try:
                val = float(scalars["Metallic"])
                if _set_input("Metallic", val):
                    applied.append("Metallic(scalar)")
            except (TypeError, ValueError):
                pass

    if "Roughness" not in wired_texture_roles and not orm_present:
        if "Roughness" in scalars:
            try:
                val = float(scalars["Roughness"])
                if _set_input("Roughness", val):
                    applied.append("Roughness(scalar)")
            except (TypeError, ValueError):
                pass

    if "Specular" in scalars:
        try:
            val = float(scalars["Specular"])
            # Blender 4+ renamed "Specular" -> "Specular IOR Level" (default 0.5).
            target_input = (
                "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs
                else ("Specular" if "Specular" in bsdf.inputs else None)
            )
            if target_input and _set_input(target_input, val):
                applied.append("Specular(scalar)")
        except (TypeError, ValueError):
            pass

    if "Opacity" in scalars:
        try:
            val = float(scalars["Opacity"])
            if _set_input("Alpha", val):
                applied.append("Opacity(scalar)")
                mat.blend_method = "BLEND" if val < 1.0 else mat.blend_method
        except (TypeError, ValueError):
            pass

    return applied


def _build_material_from_mi(
    mat: bpy.types.Material,
    mi_json_abs: Path,
    source_root: Path,
    data_roots: list[Path] | None = None,
) -> dict:
    """Return a small report dict describing what was wired."""
    data = _load_material_json_data(mi_json_abs)
    if data is None:
        return {"source": "mi_error", "mi": str(mi_json_abs), "error": "unsupported material JSON", "roles": []}

    textures = data.get("Textures") or {}
    parameters = data.get("Parameters") or {}
    _ensure_use_nodes(mat)

    wired_roles: set[str] = set()
    y = 400
    for slot_name, pkg_value in textures.items():
        if not isinstance(pkg_value, str) or not pkg_value.strip():
            continue
        role = MI_SLOT_ROLES.get(slot_name.lower())
        if role is None:
            continue
        if role in wired_roles:
            continue
        tex_path = _resolve_texture_on_disk(source_root, pkg_value, data_roots)
        if tex_path is None:
            continue
        img = _load_image(tex_path, non_color=(role in NON_COLOR_ROLES))
        if img is None:
            continue
        _connect_role(mat, role, img, y)
        wired_roles.add(role)
        y -= 300

    # Apply scalar/color parameters on top (textures always win per-role).
    # Catches "tint-and-scalar" materials like MI_Steel/MI_Wood/MI_Rag where
    # Textures{} is empty but Parameters define the full look.
    applied_params = _apply_mi_parameters(mat, parameters, wired_roles)

    # Report "mi" whenever either textures OR params contributed. If neither
    # did, fall back to "mi_empty" so callers can route to hybrid.
    source = "mi" if (wired_roles or applied_params) else "mi_empty"
    return {
        "source": source,
        "mi": mi_json_abs.name,
        "roles": sorted(wired_roles),
        "params": applied_params,
    }


def _classify_hybrid_path(rel_path: str) -> tuple[str | None, str]:
    """Return (role, base_stem) for a texture path using suffix heuristics."""
    stem = Path(rel_path).stem
    lower = stem.lower()
    for suffix, role in HYBRID_SUFFIX_ROLES:
        if lower.endswith(suffix):
            base = stem[: -len(suffix)]
            return role, base
    return None, stem


def _build_material_from_hybrid(
    mat: bpy.types.Material,
    slot_name: str,
    hybrid_paths_rel: list[str],
    source_root: Path,
    *,
    strict_slot_match: bool,
    data_roots: list[Path] | None = None,
) -> dict:
    """Wire hybrid textures to the slot.

    When `strict_slot_match` is True (multi-slot mesh), candidates MUST have a
    base that relates to the slot name (exact, contains, or contained-by).
    This stops unrelated textures from being smeared across every slot of a
    multi-material mesh. Single-slot meshes keep the liberal behavior since the
    association is unambiguous."""
    _ensure_use_nodes(mat)

    slot_lower = (slot_name or "").lower()
    slot_clean = slot_lower.replace("mi_", "").replace("mt_", "").lstrip("m_") or slot_lower

    classified: list[tuple[str, str, str, int]] = []  # (role, base, rel_path, score)
    for rel in hybrid_paths_rel:
        role, base = _classify_hybrid_path(rel)
        if role is None:
            continue
        b = base.lower()
        if b.startswith("t_"):
            b = b[2:]
        if not slot_clean:
            score = 1
        elif b == slot_clean:
            score = 0
        elif slot_clean in b or b in slot_clean:
            score = 1
        else:
            score = 2
        classified.append((role, base, rel, score))

    if strict_slot_match:
        related = [c for c in classified if c[3] <= 1]
        candidates = related
    else:
        candidates = classified

    candidates.sort(key=lambda x: (x[3], x[0]))

    wired_roles: set[str] = set()
    wired_files: list[str] = []
    y = 400
    for role, _base, rel, _score in candidates:
        if role in wired_roles:
            continue
        abs_p = None
        for root in _iter_data_roots(source_root, data_roots):
            candidate = root / rel
            if candidate.is_file():
                abs_p = candidate
                break
        if abs_p is None:
            continue
        if not abs_p.is_file():
            continue
        img = _load_image(abs_p, non_color=(role in NON_COLOR_ROLES))
        if img is None:
            continue
        _connect_role(mat, role, img, y)
        wired_roles.add(role)
        wired_files.append(rel)
        y -= 300

    return {
        "source": "hybrid" if wired_roles else "none",
        "roles": sorted(wired_roles),
        "files": wired_files,
    }


# ---------------------------------------------------------------------------
# Scene setup / cleanup
# ---------------------------------------------------------------------------

def _clear_scene() -> None:
    # Factory-startup gives us one scene with a default cube, camera, light.
    # Remove the objects but keep the master collection so UEFormat's
    # bpy.context.collection.objects.link(...) still has somewhere to land.
    for obj in list(bpy.data.objects):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass
    for db in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.armatures):
        for item in list(db):
            if item.users == 0:
                try:
                    db.remove(item)
                except Exception:
                    pass


def _enable_required_addons() -> None:
    # io_scene_gltf2 is a factory add-on but we enable it explicitly because
    # --factory-startup may not leave it active.
    for mod_name in ("io_scene_ueformat", "io_scene_gltf2"):
        try:
            addon_utils.enable(mod_name, default_set=False, persistent=True)
        except Exception:
            # If it's already enabled (via factory-startup defaults) enable raises; ignore.
            pass


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _import_uemodel(uemodel_abs: Path) -> None:
    from io_scene_ueformat.importer.logic import UEFormatImport
    from io_scene_ueformat.options import UEModelOptions

    options = UEModelOptions(
        scale_factor=0.01,
        link=True,
        bone_length=4.0,
        reorient_bones=False,
        import_collision=False,
        import_sockets=False,
        import_morph_targets=False,
        import_virtual_bones=False,
        target_lod=0,
    )
    UEFormatImport(options).import_file(uemodel_abs)


def _build_materials(
    mat_slots: list[dict],
    mi_paths_rel: list[str],
    hybrid_paths_rel: list[str],
    source_root: Path,
    data_roots: list[Path] | None = None,
) -> tuple[str, list[dict]]:
    """Return (overall_source, per-slot reports)."""
    reports: list[dict] = []
    mi_count = 0
    hybrid_count = 0
    none_count = 0

    strict_hybrid = len(mat_slots) > 1

    for slot in mat_slots:
        slot_name = slot.get("name") or ""
        slot_path = slot.get("path") or ""
        mat = bpy.data.materials.get(slot_name) if slot_name else None
        if mat is None:
            continue

        mi_abs = _resolve_material_json_for_slot(slot_name, slot_path, mi_paths_rel, source_root, data_roots)
        report = {"slot": slot_name, "material_path": slot_path}
        if mi_abs is not None:
            rep = _build_material_from_mi(mat, mi_abs, source_root, data_roots)
            report.update(rep)
            # MI counts as a real assignment when it produced either a texture
            # role OR a scalar/color parameter binding. Pure "mi_empty" (JSON
            # found but nothing applicable) falls through to hybrid.
            mi_wired = rep.get("source") == "mi" and (rep.get("roles") or rep.get("params"))
            if mi_wired:
                mi_count += 1
            else:
                hr = _build_material_from_hybrid(
                    mat, slot_name, hybrid_paths_rel, source_root,
                    strict_slot_match=strict_hybrid,
                    data_roots=data_roots,
                )
                report["hybrid_fallback"] = hr
                if hr.get("source") == "hybrid":
                    hybrid_count += 1
                else:
                    none_count += 1
        else:
            hr = _build_material_from_hybrid(
                mat, slot_name, hybrid_paths_rel, source_root,
                strict_slot_match=strict_hybrid,
                data_roots=data_roots,
            )
            report.update(hr)
            if hr.get("source") == "hybrid":
                hybrid_count += 1
            else:
                none_count += 1
        reports.append(report)

    if mi_count and not hybrid_count and not none_count:
        overall = "mi"
    elif hybrid_count and not mi_count and not none_count:
        overall = "hybrid"
    elif mi_count or hybrid_count:
        overall = "mixed"
    else:
        overall = "none"
    return overall, reports


def _save_blend(blend_path: Path) -> None:
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True, copy=False)


def _export_glb(glb_path: Path) -> None:
    glb_path.parent.mkdir(parents=True, exist_ok=True)
    # Select everything so Blender's default "selected" exports don't miss objects
    # (use_selection defaults to False, but being explicit is cheap).
    try:
        bpy.ops.object.select_all(action="SELECT")
    except RuntimeError:
        pass
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        export_apply=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_yup=True,
        use_selection=False,
    )


def main() -> int:
    t0 = time.time()
    try:
        args = _parse_args()
        task_file = Path(args.task_file)
        task = json.loads(task_file.read_text(encoding="utf-8"))

        source_root = Path(task["source_root"]).resolve()
        entry = task["entry"]
        save_blend = bool(task.get("save_blend", True))
        output_dir_raw = task.get("output_dir")
        output_dir = Path(output_dir_raw).resolve() if output_dir_raw else None

        model_rel = entry["path"]
        uemodel_abs = (source_root / model_rel).resolve()
        if not uemodel_abs.is_file():
            raise FileNotFoundError(f".uemodel not found: {uemodel_abs}")

        materials_block = entry.get("Materials", {}) or {}
        mi_paths_rel = list(
            materials_block.get("material_json_paths")
            or materials_block.get("material_instance_json_paths")
            or []
        )
        hybrid_paths_rel = list(entry.get("MaterialsHybrid", {}).get("texture_image_paths", []))

        _enable_required_addons()
        _clear_scene()

        mat_slots = _read_uemodel_materials(uemodel_abs)

        _import_uemodel(uemodel_abs)

        overall, reports = _build_materials(mat_slots, mi_paths_rel, hybrid_paths_rel, source_root)

        stem = uemodel_abs.stem
        if output_dir is not None:
            # Mirror source-relative directory structure beneath output_dir so
            # `RSDragonwilds/.../Tier1/SM_X.uemodel` becomes
            # `<output_dir>/RSDragonwilds/.../Tier1/SM_X.glb`.
            rel_parent = Path(model_rel).parent
            out_dir = (output_dir / rel_parent).resolve()
            anchor = output_dir
        else:
            out_dir = uemodel_abs.parent
            anchor = source_root
        glb_abs = out_dir / f"{stem}.glb"
        blend_abs = out_dir / f"{stem}.blend"

        if save_blend:
            _save_blend(blend_abs)
        _export_glb(glb_abs)

        def _rel(p: Path) -> str:
            try:
                return p.resolve().relative_to(anchor).as_posix()
            except ValueError:
                return p.resolve().as_posix()

        _emit_result(
            {
                "status": "success",
                "model_rel": model_rel,
                "glb_path": _rel(glb_abs),
                "blend_path": _rel(blend_abs) if save_blend else None,
                "materials_source": overall,
                "slot_count": len(mat_slots),
                "slots": reports,
                "duration_s": round(time.time() - t0, 3),
            }
        )
        return 0
    except Exception as e:
        _emit_result(
            {
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
                "duration_s": round(time.time() - t0, 3),
            }
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
