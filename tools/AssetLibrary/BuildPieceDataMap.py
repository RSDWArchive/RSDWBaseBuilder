"""Build the Blender add-on fallback PieceDataMap from the runtime catalog."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from BuildCatalogReconciliation import _archive_index_by_piece_data_name, _archive_roots  # noqa: E402


REPO = Path(__file__).resolve().parents[2]
CATALOG_FILE = REPO / "CatalogData" / "_catalog.json"
OUT_FILE = REPO / "addon" / "data" / "PieceDataMap.json"
ARCHIVE_JSON_ROOT = Path(r"E:/Github/RSDWArchive/0.12.0.0/json")


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build addon/data/PieceDataMap.json from the runtime building-piece catalog."
    )
    parser.add_argument("--catalog-file", type=Path, default=CATALOG_FILE)
    parser.add_argument("--archive-json-root", type=Path, default=ARCHIVE_JSON_ROOT)
    parser.add_argument("--out", type=Path, default=OUT_FILE)
    args = parser.parse_args(argv)

    for path, label in (
        (args.catalog_file, "catalog file"),
        (args.archive_json_root, "archive json root"),
    ):
        if not path.exists():
            raise SystemExit(f"{label} not found: {path}")

    catalog = _load_json(args.catalog_file)
    archive_by_pdn = _archive_index_by_piece_data_name(_archive_roots(args.archive_json_root))

    mapping: dict[str, dict] = {}
    variants: dict[str, list[dict]] = defaultdict(list)
    missing_archive_metadata = 0
    missing_buildable_actor = 0

    for piece in sorted(catalog.get("pieces", []), key=lambda item: item.get("piece_data_index", -1)):
        piece_data_name = piece.get("piece_data_name", "")
        archive = archive_by_pdn.get(piece_data_name)
        if not archive:
            missing_archive_metadata += 1
            continue
        bp_class = archive.get("bp_class", "")
        if not bp_class:
            missing_buildable_actor += 1
            continue
        entry = {
            "piece_data_index": piece.get("piece_data_index"),
            "piece_data_name": piece_data_name,
        }
        variants[bp_class].append(entry)
        mapping.setdefault(bp_class, entry)

    shared_variants = {
        bp_class: rows
        for bp_class, rows in sorted(variants.items())
        if len(rows) > 1
    }
    out = {
        "schema": "RSDWBaseBuilder.PieceDataMap.v1",
        "count": len(mapping),
        "catalog_entries": len(catalog.get("pieces", [])),
        "missing_archive_metadata": missing_archive_metadata,
        "missing_buildable_actor": missing_buildable_actor,
        "shared_bp_class_count": len(shared_variants),
        "shared_bp_classes": shared_variants,
        "mapping": dict(sorted(mapping.items())),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(json.dumps({
        "catalog_entries": out["catalog_entries"],
        "mapping_count": out["count"],
        "missing_archive_metadata": missing_archive_metadata,
        "missing_buildable_actor": missing_buildable_actor,
        "shared_bp_class_count": len(shared_variants),
    }, indent=2))
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
