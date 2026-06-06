"""Build a catalog-first reconciliation report for the 648 BuildingPieceData rows.

The catalog is the master list. PieceDataMap, BPMap, and .blend files are joins
against that master and do not have to be 648 rows themselves.
"""

from __future__ import annotations

import json
import argparse
from collections import Counter, defaultdict
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CATALOG_FILE = REPO / "CatalogData" / "_catalog.json"
DISK_CATALOG_FILE = REPO / "CatalogData" / "_catalog_disk.json"
PIECE_DATA_MAP_FILE = REPO / "data" / "PieceDataMap.json"
BPMAP_FILE = REPO / "tools" / "ModelData" / "BPMap.json"
BLEND_ROOT = REPO / "_build" / "extension"
OUT_FILE = REPO / "tools" / "AssetLibrary" / "catalog_reconciliation.json"
ARCHIVE_JSON_ROOT = Path(r"E:/Github/RSDWArchive/0.11.2.2/json")


def _archive_roots(archive_json_root: Path) -> list[tuple[Path, str]]:
    return [
        (
            archive_json_root / "RSDragonwilds" / "Content" / "Gameplay" / "BaseBuilding_New" / "BuildingPieces",
            "BuildingPieceData /Game/Gameplay/BaseBuilding_New/BuildingPieces",
        ),
        (
            archive_json_root / "RSDragonwilds" / "Content" / "Gameplay" / "BaseBuilding" / "Data" / "BuildingPieces",
            "BuildingPieceData /Game/Gameplay/BaseBuilding/Data/BuildingPieces",
        ),
        (
            archive_json_root / "RSDragonwilds" / "Plugins" / "GameFeatures" / "Fishing" / "Content" / "Gameplay" / "BaseBuilding" / "BuildingPieces",
            "BuildingPieceData /Fishing/Gameplay/BaseBuilding/BuildingPieces",
        ),
    ]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _bp_short(asset_path: str) -> str:
    if not asset_path:
        return ""
    leaf = asset_path.rsplit("/", 1)[-1]
    return leaf.rsplit(".", 1)[-1] if "." in leaf else leaf


def _piece_data_name_for_file(path: Path, root: Path, mount_prefix: str) -> str:
    rel = path.relative_to(root).with_suffix("").as_posix()
    return f"{mount_prefix}/{rel}.{path.stem}"


def _display_name(props: dict) -> str:
    display = props.get("DisplayName") or {}
    if not isinstance(display, dict):
        return ""
    return display.get("LocalizedString") or display.get("SourceString") or display.get("Key") or ""


def _archive_index_by_piece_data_name(archive_roots: list[tuple[Path, str]]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for root, mount_prefix in archive_roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.json")):
            try:
                data = _load_json(path)
            except Exception:
                continue
            for entry in data if isinstance(data, list) else [data]:
                if entry.get("Type") != "BuildingPieceData":
                    continue
                props = entry.get("Properties") or {}
                buildable = props.get("BuildableActor") or {}
                piece_data_name = _piece_data_name_for_file(path, root, mount_prefix)
                out[piece_data_name] = {
                    "asset_stem": path.stem,
                    "display_name": _display_name(props),
                    "bp_class": _bp_short(buildable.get("AssetPathName", "")),
                    "bp_asset_path": buildable.get("AssetPathName", ""),
                    "archive_file": str(path).replace("\\", "/"),
                }
                break
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build catalog-first building-piece reconciliation.")
    parser.add_argument("--catalog-file", type=Path, default=CATALOG_FILE)
    parser.add_argument("--disk-catalog-file", type=Path, default=DISK_CATALOG_FILE)
    parser.add_argument("--piece-data-map", type=Path, default=PIECE_DATA_MAP_FILE)
    parser.add_argument("--bpmap", type=Path, default=BPMAP_FILE)
    parser.add_argument("--archive-json-root", type=Path, default=ARCHIVE_JSON_ROOT)
    parser.add_argument("--blend-root", type=Path, default=BLEND_ROOT)
    parser.add_argument("--out", type=Path, default=OUT_FILE)
    args = parser.parse_args(argv)

    for path, label in (
        (args.catalog_file, "catalog file"),
        (args.disk_catalog_file, "disk catalog file"),
        (args.piece_data_map, "PieceDataMap.json"),
        (args.bpmap, "BPMap.json"),
        (args.archive_json_root, "archive json root"),
    ):
        if not path.exists():
            raise SystemExit(f"{label} not found: {path}")

    catalog = _load_json(args.catalog_file)
    disk_catalog = _load_json(args.disk_catalog_file)
    piece_data_map = _load_json(args.piece_data_map).get("mapping", {})
    bpmap = _load_json(args.bpmap).get("mapping", {})

    archive_by_pdn = _archive_index_by_piece_data_name(_archive_roots(args.archive_json_root))
    disk_paths = {piece.get("object_path", "") for piece in disk_catalog.get("pieces", [])}

    pdm_by_pdn: dict[str, list[dict]] = defaultdict(list)
    for bp_class, value in piece_data_map.items():
        piece_data_name = value.get("piece_data_name")
        if not piece_data_name:
            continue
        pdm_by_pdn[piece_data_name].append({
            "bp_class": bp_class,
            "piece_data_index": value.get("piece_data_index"),
            "piece_data_name": piece_data_name,
        })

    blend_by_stem: dict[str, list[str]] = defaultdict(list)
    blend_files = sorted(args.blend_root.rglob("*.blend")) if args.blend_root.is_dir() else []
    for path in blend_files:
        if path.stem.startswith("_"):
            continue
        rel = path.relative_to(args.blend_root)
        if rel.parts and rel.parts[0] == "templates":
            continue
        blend_by_stem[path.stem].append(str(rel).replace("\\", "/"))

    catalog_bp_counts = Counter(
        archive_by_pdn.get(piece.get("piece_data_name", ""), {}).get("bp_class", "")
        for piece in catalog.get("pieces", [])
    )

    rows = []
    status_counts = Counter()
    for piece in sorted(catalog.get("pieces", []), key=lambda item: item.get("piece_data_index", -1)):
        piece_data_name = piece.get("piece_data_name", "")
        archive = archive_by_pdn.get(piece_data_name, {})
        bp_class = archive.get("bp_class", "")
        pdm_matches = pdm_by_pdn.get(piece_data_name, [])
        expected_pdm_match = next((m for m in pdm_matches if m["bp_class"] == bp_class), None)
        if expected_pdm_match is None and pdm_matches:
            expected_pdm_match = pdm_matches[0]

        sm_stem = bpmap.get(bp_class, "") if bp_class else ""
        blend_files = blend_by_stem.get(sm_stem, []) if sm_stem else []
        bp_class_piece = piece_data_map.get(bp_class, {}) if bp_class else {}
        shared_bp_count = catalog_bp_counts[bp_class] if bp_class else 0

        if not archive:
            status = "missing_archive_metadata"
        elif not bp_class:
            status = "missing_buildable_actor"
        elif not pdm_matches:
            status = "missing_piece_data_map_entry"
        elif bp_class_piece.get("piece_data_name") != piece_data_name:
            status = "shared_bp_class_or_variant"
        elif not sm_stem:
            status = "missing_bpmap_entry"
        elif not blend_files:
            status = "missing_blend_file"
        else:
            status = "covered"
        status_counts[status] += 1

        rows.append({
            "status": status,
            "piece_data_index": piece.get("piece_data_index"),
            "piece_data_name": piece_data_name,
            "asset_stem": archive.get("asset_stem") or piece_data_name.rsplit("/", 1)[-1].split(".", 1)[0],
            "display_name": archive.get("display_name", ""),
            "disk_catalog_match": piece_data_name.removeprefix("BuildingPieceData ") in disk_paths,
            "bp_class": bp_class,
            "bp_asset_path": archive.get("bp_asset_path", ""),
            "catalog_entries_for_bp_class": shared_bp_count,
            "piece_data_map_matches": pdm_matches,
            "bp_class_current_piece_data_name": bp_class_piece.get("piece_data_name", ""),
            "bpmap_sm_stem": sm_stem,
            "blend_files": blend_files,
            "archive_file": archive.get("archive_file", ""),
        })

    bpmap_stems = set(bpmap.values())
    blend_stems = set(blend_by_stem)
    summary = {
        "catalog_entries": len(catalog.get("pieces", [])),
        "disk_catalog_entries": len(disk_catalog.get("pieces", [])),
        "catalog_disk_missing": sum(1 for row in rows if not row["disk_catalog_match"]),
        "piece_data_map_bp_classes": len(piece_data_map),
        "piece_data_map_unique_piece_data_names": len(pdm_by_pdn),
        "bpmap_entries": len(bpmap),
        "bpmap_unique_sm_stems": len(bpmap_stems),
        "blend_files": sum(len(paths) for paths in blend_by_stem.values()),
        "blend_unique_sm_stems": len(blend_stems),
        "status_counts": dict(sorted(status_counts.items())),
        "shared_bp_classes": sum(1 for bp, count in catalog_bp_counts.items() if bp and count > 1),
        "catalog_entries_using_shared_bp_classes": sum(
            1 for row in rows if row["catalog_entries_for_bp_class"] > 1
        ),
        "bpmap_stems_without_blend": len(bpmap_stems - blend_stems),
        "blend_stems_without_bpmap": len(blend_stems - bpmap_stems),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, "pieces": rows}, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nWritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
