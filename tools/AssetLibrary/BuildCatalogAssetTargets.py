"""Create catalog-shaped asset-library build targets.

The runtime catalog is the master list because it is the only authoritative
source for piece_data_index. This script converts the 648-row reconciliation
report into concrete .blend build targets and a dry-run cut list for existing
non-catalog-shaped blends.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import categorize  # noqa: E402


REPO = Path(__file__).resolve().parents[2]
RECONCILIATION_FILE = REPO / "tools" / "AssetLibrary" / "catalog_reconciliation.json"
MODEL_DATA_FILES = [
    REPO / "tools" / "ModelData" / "SM_Data.json",
    REPO / "tools" / "ModelData" / "SK_Data.json",
]
DEFAULT_SOURCE_ROOT = Path(r"E:/Github/RSDWModel/0.11.2.2")
RSDWMODEL_SOURCE_ROOT = Path(r"E:/Github/RSDWModel/0.11.0.10")
FISHING_FMODEL_SOURCE_ROOT = Path(r"C:/Users/NZXT/Desktop/RSDW_Modding/FModel/Fishing")
LIBRARY_ROOT = REPO / "_build" / "extension"
OUT_FILE = REPO / "tools" / "AssetLibrary" / "catalog_asset_targets.json"
CUT_LIST_FILE = REPO / "tools" / "AssetLibrary" / "catalog_blends_to_cut.txt"
BPMAP_FILE = REPO / "data" / "BPMap.json"
ARCHIVE_JSON_ROOT = Path(r"E:/Github/RSDWArchive/0.11.2.2/json")
TEXTURE_EXTENSIONS = {".png", ".tga", ".dds", ".jpg", ".jpeg", ".exr", ".bmp", ".hdr", ".webp"}

SOURCE_STEM_ALIASES = {
    "BP_BaseBuilding_Chandelier_Blue_C": "BP_BaseBuilding_Chandelier_C",
    "BP_BaseBuilding_Chandelier_Green_C": "BP_BaseBuilding_Chandelier_C",
    "BP_BaseBuilding_Chandelier_Purple_C": "BP_BaseBuilding_Chandelier_C",
    "BP_BaseBuilding_Chandelier_Red_C": "BP_BaseBuilding_Chandelier_C",
    "BP_BaseBuilding_Torch_Blue_C": "BP_BaseBuilding_Torch_C",
    "BP_BaseBuilding_Torch_Green_C": "BP_BaseBuilding_Torch_C",
    "BP_BaseBuilding_Torch_Purple_C": "BP_BaseBuilding_Torch_C",
    "BP_BaseBuilding_Torch_Red_C": "BP_BaseBuilding_Torch_C",
    "BP_BaseBuilding_TorchStanding_Blue_C": "BP_BaseBuilding_TorchStanding_C",
    "BP_BaseBuilding_TorchStanding_Green_C": "BP_BaseBuilding_TorchStanding_C",
    "BP_BaseBuilding_TorchStanding_Purple_C": "BP_BaseBuilding_TorchStanding_C",
    "BP_BaseBuilding_TorchStanding_Red_C": "BP_BaseBuilding_TorchStanding_C",
    "BP_BaseBuilding_Torch_Type2_Blue_C": "BP_BaseBuilding_Torch_Type2_Natural_C",
    "BP_BaseBuilding_Torch_Type2_Green_C": "BP_BaseBuilding_Torch_Type2_Natural_C",
    "BP_BaseBuilding_Torch_Type2_Purple_C": "BP_BaseBuilding_Torch_Type2_Natural_C",
    "BP_BaseBuilding_Torch_Type2_Red_C": "BP_BaseBuilding_Torch_Type2_Natural_C",
    "BP_BaseBuilding_TorchStanding_Type2_Blue_C": "BP_BaseBuilding_TorchStanding_Type2_Natural_C",
    "BP_BaseBuilding_TorchStanding_Type2_Green_C": "BP_BaseBuilding_TorchStanding_Type2_Natural_C",
    "BP_BaseBuilding_TorchStanding_Type2_Purple_C": "BP_BaseBuilding_TorchStanding_Type2_Natural_C",
    "BP_BaseBuilding_TorchStanding_Type2_Red_C": "BP_BaseBuilding_TorchStanding_Type2_Natural_C",
    "BP_FarmPlot1x1_T1_C": "BP_FarmPlot1x1_Base_C",
}

SOURCE_STEM_BY_BP = {
    "PROXY_BP_BaseBuilding_Wall_Small_C": "SM_CollisionMesh_Wall_Small",
    "PROXY_BP_BaseBuilding_Floor_C": "SM_CollisionMesh_Floor",
    "PROXY_BP_BaseBuilding_Foundation_C": "SM_CollisionMesh_Foundation_Large",
    "PROXY_BP_BaseBuilding_Roof_26_C": "SM_CollisionMesh_Roof_Med_Shallow",
    "PROXY_BP_BaseBuilding_Roof_45_C": "SM_CollisionMesh_Roof_Med_Steep",
    "PROXY_BP_BaseBuilding_Wall_C": "SM_CollisionMesh_Wall_Large",
}

SOURCE_STEM_BY_ASSET = {
    "BUILDPIECE_Beam_Horizontal_Half_Thick": "SM_BB_T1_Beam_Thick_Med_Horizontal",
    "BUILDPIECE_Stairs_45": "SM_T1_Stairs_Shallow",
}

HELPER_SOURCE_MARKERS = (
    "SM_VFX_",
    "SM_Raw_",
    "SM_Placement",
    "SM_ProxyFlame",
    "SM_CandleFlame",
)

IGNORED_ASSET_STEMS = {
    "DA_BuildPiece_Default",
}

_ARCHIVE_JSON_BY_STEM: dict[str, Path] | None = None


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _archive_json_by_stem() -> dict[str, Path]:
    global _ARCHIVE_JSON_BY_STEM
    if _ARCHIVE_JSON_BY_STEM is None:
        _ARCHIVE_JSON_BY_STEM = {}
        if ARCHIVE_JSON_ROOT.is_dir():
            for path in ARCHIVE_JSON_ROOT.rglob("*.json"):
                _ARCHIVE_JSON_BY_STEM.setdefault(path.stem, path)
    return _ARCHIVE_JSON_BY_STEM


def _looks_like_material_json(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".json":
        return False
    try:
        data = _load_json(path)
    except Exception:
        return False
    return isinstance(data, dict) and "Textures" in data


def _nearby_support_paths(path: Path, root: Path) -> tuple[list[str], list[str]]:
    """Return material JSONs and textures near a fallback .uemodel.

    The worker can already resolve exact material JSON paths from UE slot paths;
    these lists are a fallback for FModel one-off exports where the model,
    materials, and textures were dropped into a small folder without compiling
    SM_Data/SK_Data first.
    """
    search_roots = [path.parent]
    for name in ("Materials", "Material", "Textures", "Texture"):
        candidate = path.parent / name
        if candidate.is_dir():
            search_roots.append(candidate)
    parent = path.parent.parent
    for name in ("Materials", "Material", "Textures", "Texture"):
        candidate = parent / name
        if candidate.is_dir():
            search_roots.append(candidate)

    material_jsons: set[str] = set()
    texture_paths: set[str] = set()
    for search_root in search_roots:
        for candidate in search_root.iterdir():
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(root).as_posix()
            suffix = candidate.suffix.lower()
            if suffix == ".json" and _looks_like_material_json(candidate):
                material_jsons.add(rel)
            elif suffix in TEXTURE_EXTENSIONS:
                texture_paths.add(rel)
    return sorted(material_jsons), sorted(texture_paths)


def _class_name(bp_asset_path: str) -> str:
    if not bp_asset_path:
        return ""
    if bp_asset_path.startswith("BlueprintGeneratedClass "):
        return bp_asset_path
    return f"BlueprintGeneratedClass {bp_asset_path}"


def _load_bpmap() -> dict[str, str]:
    if not BPMAP_FILE.is_file():
        return {}
    return _load_json(BPMAP_FILE).get("mapping", {})


def _extract_mesh_stem(ref: dict | str | None) -> str:
    if isinstance(ref, dict):
        text = ref.get("ObjectName") or ref.get("AssetPathName") or ref.get("ObjectPath") or ""
    else:
        text = ref or ""
    match = re.search(r"\b(?:SM|SK)_[A-Za-z0-9_]+", text)
    return match.group(0) if match else ""


@lru_cache(maxsize=None)
def _bp_component_mesh_stems(bp_class: str) -> tuple[str, ...]:
    if not bp_class or not ARCHIVE_JSON_ROOT.is_dir():
        return ()
    bp_asset_name = bp_class.removesuffix("_C")
    bp_file = _archive_json_by_stem().get(bp_asset_name)
    if bp_file is None:
        return ()
    try:
        data = _load_json(bp_file)
    except Exception:
        return ()
    out: list[str] = []
    for obj in data if isinstance(data, list) else [data]:
        if obj.get("Type") not in {"StaticMeshComponent", "SkeletalMeshComponent"}:
            continue
        props = obj.get("Properties") or {}
        stem = _extract_mesh_stem(props.get("StaticMesh") or props.get("SkeletalMesh"))
        if stem and stem not in out:
            out.append(stem)
    return tuple(out)


def _preferred_component_mesh_stem(bp_class: str, model_entries: dict[str, dict]) -> str:
    for stem in _bp_component_mesh_stems(bp_class):
        if stem not in model_entries:
            continue
        if stem.startswith(HELPER_SOURCE_MARKERS):
            continue
        return stem
    return ""


def _is_helper_source(stem: str) -> bool:
    return stem.startswith(HELPER_SOURCE_MARKERS)


def _alias_bp_from_resolution(source_resolution: str) -> str:
    prefix = "bpmap_alias:"
    if source_resolution.startswith(prefix):
        return source_resolution[len(prefix):]
    return ""


def _resolve_source_stem(row: dict, bpmap: dict[str, str]) -> tuple[str, str]:
    bp_class = row.get("bp_class") or ""
    asset_stem = row.get("asset_stem") or ""
    source_stem = row.get("bpmap_sm_stem") or ""
    if source_stem:
        return source_stem, "bpmap"

    if asset_stem in SOURCE_STEM_BY_ASSET:
        return SOURCE_STEM_BY_ASSET[asset_stem], "asset_alias"
    if bp_class in SOURCE_STEM_BY_BP:
        return SOURCE_STEM_BY_BP[bp_class], "bp_alias"

    alias_bp_class = SOURCE_STEM_ALIASES.get(bp_class)
    if alias_bp_class and bpmap.get(alias_bp_class):
        return bpmap[alias_bp_class], f"bpmap_alias:{alias_bp_class}"

    for stem in _bp_component_mesh_stems(bp_class):
        return stem, "bp_component_mesh"

    return "", ""


def _blend_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.blend")
        if path.name != "_Materials.blend"
        and not path.stem.startswith("_")
        and (not path.relative_to(root).parts or path.relative_to(root).parts[0] != "templates")
    )


def main(argv: list[str] | None = None) -> int:
    global ARCHIVE_JSON_ROOT, BPMAP_FILE, _ARCHIVE_JSON_BY_STEM

    parser = argparse.ArgumentParser(description="Build catalog-shaped asset targets.")
    parser.add_argument("--reconciliation", type=Path, default=RECONCILIATION_FILE)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT,
                        help="Source root for entries loaded from model inventory JSONs.")
    parser.add_argument("--model-data", type=Path, action="append", default=None,
                        help="Model inventory JSON. Defaults to SM_Data.json and SK_Data.json.")
    parser.add_argument("--fallback-model-root", type=Path, action="append", default=None,
                        help="Read-only .uemodel tree used to synthesize missing inventory entries.")
    parser.add_argument("--archive-json-root", type=Path, default=ARCHIVE_JSON_ROOT,
                        help="Archive json root used for BP component fallback scans.")
    parser.add_argument("--bpmap", type=Path, default=BPMAP_FILE,
                        help="BPMap.json used to resolve building-piece BP classes.")
    parser.add_argument("--library-root", type=Path, default=LIBRARY_ROOT)
    parser.add_argument("--out", type=Path, default=OUT_FILE)
    parser.add_argument("--cut-list", type=Path, default=CUT_LIST_FILE)
    args = parser.parse_args(argv)

    ARCHIVE_JSON_ROOT = args.archive_json_root
    BPMAP_FILE = args.bpmap
    _ARCHIVE_JSON_BY_STEM = None

    reconciliation = _load_json(args.reconciliation)
    bpmap = _load_bpmap()
    model_data_files = args.model_data or MODEL_DATA_FILES
    model_entries = {}
    for model_data_file in model_data_files:
        model_data = _load_json(model_data_file)
        for entry in model_data.get("entries", []):
            model_entries.setdefault(Path(entry["path"]).stem, {
                "entry": entry,
                "source_root": str(args.source_root.resolve()),
                "source": str(model_data_file),
            })

    fallback_roots = args.fallback_model_root
    if fallback_roots is None:
        fallback_roots = [
            root for root in (RSDWMODEL_SOURCE_ROOT, FISHING_FMODEL_SOURCE_ROOT)
            if root.is_dir()
        ]
    for fallback_root in fallback_roots:
        if not fallback_root.is_dir():
            continue
        for path in fallback_root.rglob("*.uemodel"):
            rel = path.relative_to(fallback_root).as_posix()
            material_json_paths, texture_image_paths = _nearby_support_paths(path, fallback_root)
            model_entries.setdefault(path.stem, {
                "entry": {
                    "name": path.name,
                    "path": rel,
                    "Materials": {"material_json_paths": material_json_paths, "items": []},
                    "MaterialsHybrid": {"texture_image_paths": texture_image_paths, "discovery": []},
                },
                "source_root": str(fallback_root.resolve()),
                "source": str(fallback_root),
            })

    targets = []
    unresolved = []
    ignored = []
    status_counts = Counter()
    target_stems = set()

    for row in reconciliation.get("pieces", []):
        piece_data_index = row.get("piece_data_index")
        asset_stem = row.get("asset_stem") or f"BUILDPIECE_{piece_data_index}"
        target_id = f"{int(piece_data_index):03d}_{asset_stem}" if piece_data_index is not None else asset_stem
        if asset_stem in IGNORED_ASSET_STEMS:
            status_counts["ignored"] += 1
            ignored.append({
                "target_id": target_id,
                "piece_data_index": piece_data_index,
                "piece_data_name": row.get("piece_data_name", ""),
                "asset_stem": asset_stem,
                "display_name": row.get("display_name", ""),
                "bp_class": row.get("bp_class", ""),
                "reason": "ignored default/no-actor catalog row",
            })
            continue
        source_stem, source_resolution = _resolve_source_stem(row, bpmap)
        component_bp_class = _alias_bp_from_resolution(source_resolution) or row.get("bp_class") or ""
        preferred_component_stem = _preferred_component_mesh_stem(component_bp_class, model_entries)
        if source_stem and _is_helper_source(source_stem) and preferred_component_stem:
            source_stem = preferred_component_stem
            source_resolution = f"visible_component_mesh:{component_bp_class}"
        source_model = model_entries.get(source_stem)
        source_entry = source_model["entry"] if source_model else None

        if row.get("status") == "missing_buildable_actor":
            reason = "catalog row has no BuildableActor"
        elif not row.get("bp_class"):
            reason = "catalog row has no BP class"
        elif not source_stem:
            reason = "catalog row has no source mesh"
        elif source_entry is None:
            reason = "source mesh is not in model inventory"
        else:
            reason = ""

        if reason:
            status_counts["unresolved"] += 1
            unresolved.append({
                "target_id": target_id,
                "piece_data_index": piece_data_index,
                "piece_data_name": row.get("piece_data_name", ""),
                "asset_stem": asset_stem,
                "display_name": row.get("display_name", ""),
                "bp_class": row.get("bp_class", ""),
                "source_sm_stem": source_stem,
                "source_resolution": source_resolution,
                "reason": reason,
            })
            continue

        catalog_path = categorize(source_entry["path"])
        target_stems.add(asset_stem)
        status_counts["buildable"] += 1
        targets.append({
            "target_id": target_id,
            "asset_stem": asset_stem,
            "display_name": row.get("display_name", ""),
            "catalog_path": catalog_path,
            "source_entry_path": source_entry["path"],
            "source_entry": source_entry,
            "source_root": source_model["source_root"],
            "source_inventory": source_model["source"],
            "source_sm_stem": source_stem,
            "source_resolution": source_resolution,
            "bp_class": row.get("bp_class", ""),
            "class_name": _class_name(row.get("bp_asset_path", "")),
            "piece_data_index": int(piece_data_index),
            "piece_data_name": row.get("piece_data_name", ""),
            "source_reconciliation_status": row.get("status", ""),
        })

    current_blends = _blend_files(args.library_root)
    cut_blends = [
        path.relative_to(args.library_root).as_posix()
        for path in current_blends
        if path.stem not in target_stems
    ]

    summary = {
        "catalog_entries": len(reconciliation.get("pieces", [])),
        "ignored_catalog_entries": len(ignored),
        "effective_catalog_entries": len(reconciliation.get("pieces", [])) - len(ignored),
        "model_inventory_entries": len(model_entries),
        "buildable_targets": len(targets),
        "unresolved_targets": len(unresolved),
        "current_blend_files": len(current_blends),
        "current_blends_not_in_catalog_targets": len(cut_blends),
        "source_status_counts": dict(sorted(Counter(t["source_reconciliation_status"] for t in targets).items())),
        "unresolved_reason_counts": dict(sorted(Counter(u["reason"] for u in unresolved).items())),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"summary": summary, "targets": targets, "unresolved": unresolved, "ignored": ignored}, indent=2),
        encoding="utf-8",
    )
    args.cut_list.write_text("\n".join(cut_blends) + ("\n" if cut_blends else ""), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nWrote targets -> {args.out}")
    print(f"Wrote dry-run cut list -> {args.cut_list}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
