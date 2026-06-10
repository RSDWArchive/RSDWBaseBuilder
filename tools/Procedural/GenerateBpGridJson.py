from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = ROOT / "website" / "basebuilder-index.json"
DEFAULT_OUTPUT = ROOT / "_build" / "procedural" / "all_bp_bounds_grid.json"
SCHEMA = "rsdwtools.buildings.v1"
UNIT_SCALE = 0.01


@dataclass(frozen=True)
class Bounds:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @property
    def width(self) -> float:
        return max(1.0, self.max_x - self.min_x)

    @property
    def depth(self) -> float:
        return max(1.0, self.max_y - self.min_y)


@dataclass(frozen=True)
class BpTarget:
    target_id: str
    display_name: str
    actor_class: str
    class_path: str
    bounds: Bounds
    catalog_path: str


@dataclass(frozen=True)
class PieceTarget:
    target_id: str
    piece_data_index: int
    piece_data_name: str
    class_name: str
    default_stability: int


class GridError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        index_doc = load_json(args.index)
        webassets_root = resolve_webassets_root(index_doc, args.webassets_root)
        targets = load_bp_targets(
            index_doc,
            webassets_root,
            args.limit,
            max_bound=args.max_bound,
            skip_over_max_bound=args.skip_over_max_bound,
            exclude_character=args.exclude_character,
            exclude_contains=args.exclude_contains,
        )
        anchor_piece = None if args.no_anchor else load_piece_target(index_doc, args.anchor_target)
        if args.split_by_folder:
            output_dir = args.output if not args.output.suffix else args.output.parent
            write_folder_splits(targets, args, output_dir, anchor_piece)
            return 0
        rows = pack_targets(
            targets,
            padding=args.padding,
            row_width=args.row_width,
            align_bottom=not args.no_align_bottom,
            x_offset=anchor_actor_x_offset(args, anchor_piece),
        )
        pieces = anchor_pieces(anchor_piece)
        data = {
            "schema": SCHEMA,
            "name": args.name or "All BP Bounds Grid",
            "generated_unix": generated_unix(args.generated_unix),
            "count": len(pieces),
            "skipped": 0,
            "item_count": 0,
            "item_skipped": 0,
            "hidden": 0,
            "pieces": pieces,
            "items": [],
            "actors": rows,
        }
        if anchor_piece:
            data["anchor_piece_id"] = 1
            data["anchor_piece_data_index"] = anchor_piece.piece_data_index
        validate_output(data)

        if args.dry_run:
            print_summary(data, args.output)
            return 0

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print_summary(data, args.output)
        return 0
    except (GridError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a bounds-packed JSON grid containing every BP actor.")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--webassets-root",
        type=Path,
        help="Optional RSDWModel WebAssets root. Defaults to ../RSDWModel/<index version>/WebAssets.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--split-by-folder", action="store_true", help="Write one grid JSON per BP catalog folder.")
    parser.add_argument(
        "--folder-depth",
        type=positive_int,
        default=3,
        help="Catalog path depth used for split files. Default groups BP/<pack>/<section>.",
    )
    parser.add_argument("--padding", type=positive_float, default=300.0, help="Gap between BP bounds in game centimeters.")
    parser.add_argument("--anchor-target", default="367_DA_T2_Foundation_Large_Triangle")
    parser.add_argument("--anchor-offset", type=positive_float, default=900.0, help="X offset between the anchor foundation and BP actor grid.")
    parser.add_argument("--no-anchor", action="store_true", help="Do not add a triangle foundation anchor piece.")
    parser.add_argument(
        "--row-width",
        type=positive_float,
        default=0.0,
        help="Optional shelf row width in game centimeters. Defaults to a near-square width derived from total bounds area.",
    )
    parser.add_argument("--limit", type=positive_int, default=0, help="Optional first-N target limit for smoke tests.")
    parser.add_argument("--max-bound", type=positive_float, default=0.0, help="Optional max width/depth/height in cm.")
    parser.add_argument("--exclude-character", action="store_true", help="Skip BP targets containing '_Character'.")
    parser.add_argument(
        "--exclude-contains",
        action="append",
        default=[],
        help="Skip BP targets whose target/display/export metadata contains this substring. May be repeated.",
    )
    parser.add_argument(
        "--skip-over-max-bound",
        action="store_true",
        help="Skip BP targets above --max-bound instead of failing.",
    )
    parser.add_argument("--name", default="")
    parser.add_argument(
        "--generated-unix",
        default="0",
        help="Unix timestamp metadata. Defaults to 0 for deterministic generated files; use 'now' for current UTC time.",
    )
    parser.add_argument("--no-align-bottom", action="store_true", help="Keep all actor roots at z=0 instead of resting visual bounds on z=0.")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def load_bp_targets(
    index_doc: dict[str, Any],
    webassets_root: Path,
    limit: int,
    *,
    max_bound: float = 0.0,
    skip_over_max_bound: bool = False,
    exclude_character: bool = False,
    exclude_contains: list[str] | None = None,
) -> list[BpTarget]:
    rows = index_doc.get("targets")
    if not isinstance(rows, list):
        raise GridError("basebuilder-index.json does not contain a targets list.")
    bp_rows = [row for row in rows if isinstance(row, dict) and row.get("asset_kind") == "bp"]
    if limit > 0:
        bp_rows = bp_rows[:limit]

    targets: list[BpTarget] = []
    skipped_missing = 0
    skipped_oversize = 0
    skipped_character = 0
    skipped_substring = 0
    excluded_substrings = [value for value in (exclude_contains or []) if value]
    for row in bp_rows:
        text = " ".join(str(row.get(key) or "") for key in ("target_id", "display_name", "class_name"))
        export_text = " ".join(str((row.get("export") or {}).get(key) or "") for key in ("actor_class", "class_path", "runtime_path"))
        if exclude_character and ("_Character" in text or "_Character" in export_text):
            skipped_character += 1
            continue
        combined_text = f"{text} {export_text}"
        if any(substring in combined_text for substring in excluded_substrings):
            skipped_substring += 1
            continue
        export = row.get("export") or {}
        actor_class = str(export.get("actor_class") or "")
        class_path = str(export.get("class_path") or export.get("runtime_path") or "")
        if not actor_class or not class_path:
            skipped_missing += 1
            continue
        bounds = bp_bounds(row, webassets_root)
        if bounds is None:
            skipped_missing += 1
            continue
        largest_bound = max(bounds.width, bounds.depth, bounds.max_z - bounds.min_z)
        if max_bound > 0 and largest_bound > max_bound:
            if skip_over_max_bound:
                skipped_oversize += 1
                continue
            raise GridError(
                f"{row.get('display_name') or row.get('target_id')} has bound {largest_bound:.1f}cm, "
                f"above --max-bound {max_bound:.1f}. Use --skip-over-max-bound to omit it."
            )
        targets.append(
            BpTarget(
                target_id=str(row.get("target_id") or ""),
                display_name=str(row.get("display_name") or row.get("target_id") or ""),
                actor_class=actor_class,
                class_path=class_path,
                bounds=bounds,
                catalog_path=str(row.get("catalog_path") or "BP/Uncategorized"),
            )
        )
    if not targets:
        raise GridError("No BP targets with usable bounds were found.")
    if skipped_missing:
        print(f"skipped BP targets without usable metadata/bounds: {skipped_missing}", file=sys.stderr)
    if skipped_oversize:
        print(f"skipped BP targets over --max-bound: {skipped_oversize}", file=sys.stderr)
    if skipped_character:
        print(f"skipped BP targets containing _Character: {skipped_character}", file=sys.stderr)
    if skipped_substring:
        print(f"skipped BP targets matching --exclude-contains: {skipped_substring}", file=sys.stderr)
    return sorted(targets, key=lambda target: natural_key(target.display_name or target.target_id))


def load_piece_target(index_doc: dict[str, Any], target_id: str) -> PieceTarget:
    rows = index_doc.get("targets")
    if not isinstance(rows, list):
        raise GridError("basebuilder-index.json does not contain a targets list.")
    row = next((candidate for candidate in rows if isinstance(candidate, dict) and candidate.get("target_id") == target_id), None)
    if not row:
        raise GridError(f"Anchor target not found: {target_id}")
    if row.get("asset_kind") != "building_piece":
        raise GridError(f"Anchor target is not a building piece: {target_id}")
    export = row.get("export") or {}
    piece_data_index = export.get("piece_data_index")
    piece_data_name = str(export.get("piece_data_name") or "")
    class_name = str(export.get("class_name") or "")
    if piece_data_index in (None, "") or not piece_data_name or not class_name:
        raise GridError(f"Anchor target missing export metadata: {target_id}")
    return PieceTarget(
        target_id=target_id,
        piece_data_index=int(piece_data_index),
        piece_data_name=piece_data_name,
        class_name=class_name,
        default_stability=int(export.get("default_stability") or 3000),
    )


def anchor_pieces(anchor_piece: PieceTarget | None) -> list[dict[str, Any]]:
    if not anchor_piece:
        return []
    return [
        {
            "piece_id": 1,
            "piece_data_index": anchor_piece.piece_data_index,
            "piece_data_name": anchor_piece.piece_data_name,
            "class_name": anchor_piece.class_name,
            "x": 0,
            "y": 0,
            "z": 0,
            "pitch": 0,
            "yaw": 0,
            "roll": 0,
            "scale_x": 1,
            "scale_y": 1,
            "scale_z": 1,
            "stability": anchor_piece.default_stability,
            "is_ghosted": False,
        }
    ]


def anchor_actor_x_offset(args: argparse.Namespace, anchor_piece: PieceTarget | None) -> float:
    return args.anchor_offset if anchor_piece else 0.0


def bp_bounds(row: dict[str, Any], webassets_root: Path) -> Bounds | None:
    components = row.get("components")
    if not isinstance(components, list) or not components:
        return None
    union: Bounds | None = None
    for component in components:
        if not isinstance(component, dict):
            continue
        gltf_path = str(component.get("gltf_path") or "")
        if not gltf_path:
            continue
        mesh_bounds = gltf_bounds(webassets_root / gltf_path)
        if mesh_bounds is None:
            continue
        matrix = component_transform_to_three_matrix(component.get("transform") or {})
        transformed = transform_bounds(mesh_bounds, matrix)
        union = transformed if union is None else union_bounds(union, transformed)
    return union


def pack_targets(
    targets: list[BpTarget],
    *,
    padding: float,
    row_width: float,
    align_bottom: bool,
    x_offset: float = 0.0,
) -> list[dict[str, Any]]:
    if row_width <= 0:
        row_width = choose_square_row_width(targets, padding)

    packed, _layout_width, _layout_depth, _row_count = pack_targets_with_width(
        targets,
        padding=padding,
        row_width=row_width,
        align_bottom=align_bottom,
        x_offset=x_offset,
    )
    return packed


def write_folder_splits(
    targets: list[BpTarget],
    args: argparse.Namespace,
    output_dir: Path,
    anchor_piece: PieceTarget | None,
) -> None:
    groups: dict[str, list[BpTarget]] = {}
    for target in targets:
        key = folder_key(target.catalog_path, args.folder_depth)
        groups.setdefault(key, []).append(target)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "RSDWBaseBuilder.BpGridSplitManifest.v1",
        "group_count": len(groups),
        "actor_count": sum(len(group) for group in groups.values()),
        "groups": [],
    }
    for key in sorted(groups, key=natural_key):
        group_targets = sorted(groups[key], key=lambda target: natural_key(target.display_name or target.target_id))
        rows = pack_targets(
            group_targets,
            padding=args.padding,
            row_width=args.row_width,
            align_bottom=not args.no_align_bottom,
            x_offset=anchor_actor_x_offset(args, anchor_piece),
        )
        pieces = anchor_pieces(anchor_piece)
        data = {
            "schema": SCHEMA,
            "name": args.name or f"BP Grid - {key}",
            "generated_unix": generated_unix(args.generated_unix),
            "count": len(pieces),
            "skipped": 0,
            "item_count": 0,
            "item_skipped": 0,
            "hidden": 0,
            "pieces": pieces,
            "items": [],
            "actors": rows,
        }
        if anchor_piece:
            data["anchor_piece_id"] = 1
            data["anchor_piece_data_index"] = anchor_piece.piece_data_index
        validate_output(data)
        filename = f"{safe_filename(key)}.json"
        path = output_dir / filename
        if not args.dry_run:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        manifest["groups"].append(
            {
                "folder": key,
                "actor_count": len(rows),
                "file": filename,
            }
        )

    manifest_path = output_dir / "manifest.json"
    if not args.dry_run:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"groups: {manifest['group_count']}")
    print(f"actors: {manifest['actor_count']}")
    print(f"output_dir: {output_dir}")
    print(f"manifest: {manifest_path}")


def folder_key(catalog_path: str, depth: int) -> str:
    parts = [part for part in catalog_path.replace("\\", "/").split("/") if part]
    if not parts:
        return "BP/Uncategorized"
    return "/".join(parts[: max(1, depth)])


def safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "folder"


def choose_square_row_width(targets: list[BpTarget], padding: float) -> float:
    dimensions = [(target.bounds.width + padding, target.bounds.depth + padding) for target in targets]
    total_area = sum(width * depth for width, depth in dimensions)
    total_width = sum(width for width, _depth in dimensions)
    min_width = max(width for width, _depth in dimensions)
    base_width = max(min_width, math.sqrt(total_area))
    max_width = min(total_width, max(min_width, base_width * 10.0))

    candidates = {min_width, base_width, max_width}
    for factor in (0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0):
        candidates.add(min(total_width, max(min_width, base_width * factor)))
    for index in range(121):
        t = index / 120.0
        candidates.add(min_width + (max_width - min_width) * t)

    best_width = base_width
    best_score = math.inf
    for candidate in sorted(candidates):
        layout_width, layout_depth, row_count = layout_dimensions(targets, padding, candidate)
        if layout_width <= 0 or layout_depth <= 0:
            continue
        aspect_score = abs(math.log(layout_width / layout_depth))
        compactness_score = (layout_width * layout_depth) / max(total_area, 1.0)
        row_score = 1.0 / max(row_count, 1)
        score = aspect_score + compactness_score * 0.02 + row_score * 0.01
        if score < best_score:
            best_score = score
            best_width = candidate
    return best_width


def layout_dimensions(targets: list[BpTarget], padding: float, row_width: float) -> tuple[float, float, int]:
    x_cursor = 0.0
    y_cursor = 0.0
    row_depth = 0.0
    layout_width = 0.0
    row_count = 1 if targets else 0
    for target in targets:
        width = target.bounds.width
        depth = target.bounds.depth
        if x_cursor > 0 and x_cursor + width > row_width:
            layout_width = max(layout_width, x_cursor - padding)
            x_cursor = 0.0
            y_cursor += row_depth + padding
            row_depth = 0.0
            row_count += 1
        x_cursor += width + padding
        row_depth = max(row_depth, depth)
    layout_width = max(layout_width, x_cursor - padding)
    layout_depth = y_cursor + row_depth
    return layout_width, layout_depth, row_count


def pack_targets_with_width(
    targets: list[BpTarget],
    *,
    padding: float,
    row_width: float,
    align_bottom: bool,
    x_offset: float = 0.0,
) -> tuple[list[dict[str, Any]], float, float, int]:
    x_cursor = 0.0
    y_cursor = 0.0
    row_depth = 0.0
    layout_width = 0.0
    row_count = 1 if targets else 0
    packed: list[dict[str, Any]] = []

    for index, target in enumerate(targets, start=1):
        width = target.bounds.width
        depth = target.bounds.depth
        if x_cursor > 0 and x_cursor + width > row_width:
            layout_width = max(layout_width, x_cursor - padding)
            x_cursor = 0.0
            y_cursor += row_depth + padding
            row_depth = 0.0
            row_count += 1

        x = x_cursor - target.bounds.min_x + x_offset
        y = y_cursor - target.bounds.min_y
        z = -target.bounds.min_z if align_bottom else 0.0
        packed.append(
            {
                "actor_name": safe_actor_name(target, index),
                "actor_class": target.actor_class,
                "class_path": target.class_path,
                "x": rounded(x),
                "y": rounded(y),
                "z": rounded(z),
                "pitch": 0,
                "yaw": 0,
                "roll": 0,
                "scale_x": 1,
                "scale_y": 1,
                "scale_z": 1,
            }
        )
        x_cursor += width + padding
        row_depth = max(row_depth, depth)
    layout_width = max(layout_width, x_cursor - padding)
    layout_depth = y_cursor + row_depth
    return packed, layout_width, layout_depth, row_count


def gltf_bounds(path: Path) -> Bounds | None:
    if not path.exists():
        return None
    doc = load_json(path)
    accessors = doc.get("accessors")
    meshes = doc.get("meshes")
    if not isinstance(accessors, list) or not isinstance(meshes, list):
        return None
    union: Bounds | None = None
    for mesh in meshes:
        primitives = mesh.get("primitives") if isinstance(mesh, dict) else None
        if not isinstance(primitives, list):
            continue
        for primitive in primitives:
            attributes = primitive.get("attributes") if isinstance(primitive, dict) else None
            if not isinstance(attributes, dict):
                continue
            accessor_index = attributes.get("POSITION")
            if not isinstance(accessor_index, int) or accessor_index < 0 or accessor_index >= len(accessors):
                continue
            accessor = accessors[accessor_index]
            if not isinstance(accessor, dict):
                continue
            mins = accessor.get("min")
            maxs = accessor.get("max")
            if not (isinstance(mins, list) and isinstance(maxs, list) and len(mins) >= 3 and len(maxs) >= 3):
                continue
            bounds = Bounds(float(mins[0]), float(mins[1]), float(mins[2]), float(maxs[0]), float(maxs[1]), float(maxs[2]))
            union = bounds if union is None else union_bounds(union, bounds)
    return union


def component_transform_to_three_matrix(transform: dict[str, Any]) -> list[list[float]]:
    if isinstance(transform.get("matrix"), list):
        return ue_matrix_rows_to_three_matrix(transform["matrix"])
    loc = transform.get("location") or {}
    rot = transform.get("rotation") or {}
    scale = transform.get("scale") or {}
    rot3 = ue_rotator_matrix3(rot)
    sx = float(scale.get("X", 1.0))
    sy = float(scale.get("Y", 1.0))
    sz = float(scale.get("Z", 1.0))
    rows = [
        [rot3[0][0] * sx, rot3[0][1] * sy, rot3[0][2] * sz, float(loc.get("X", 0.0))],
        [rot3[1][0] * sx, rot3[1][1] * sy, rot3[1][2] * sz, float(loc.get("Y", 0.0))],
        [rot3[2][0] * sx, rot3[2][1] * sy, rot3[2][2] * sz, float(loc.get("Z", 0.0))],
        [0.0, 0.0, 0.0, 1.0],
    ]
    return ue_matrix_rows_to_three_matrix(rows)


def ue_rotator_matrix3(rot: dict[str, Any]) -> list[list[float]]:
    pitch = math.radians(float(rot.get("Pitch", rot.get("pitch", 0.0)) or 0.0))
    yaw = math.radians(float(rot.get("Yaw", rot.get("yaw", 0.0)) or 0.0))
    roll = math.radians(float(rot.get("Roll", rot.get("roll", 0.0)) or 0.0))
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cr, sr = math.cos(roll), math.sin(roll)
    rz = [[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]]
    ry = [[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]]
    rx = [[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]]
    return mat3_mul(mat3_mul(rz, ry), rx)


def mat3_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [
            a[row][0] * b[0][col] + a[row][1] * b[1][col] + a[row][2] * b[2][col]
            for col in range(3)
        ]
        for row in range(3)
    ]


def ue_matrix_rows_to_three_matrix(rows: list[list[float]]) -> list[list[float]]:
    m = normalized_rows(rows)
    tx = m[0][3] * UNIT_SCALE
    ty = m[2][3] * UNIT_SCALE
    tz = m[1][3] * UNIT_SCALE
    return [
        [m[0][0], m[0][2], m[0][1], tx],
        [m[2][0], m[2][2], m[2][1], ty],
        [m[1][0], m[1][2], m[1][1], tz],
        [0.0, 0.0, 0.0, 1.0],
    ]


def normalized_rows(rows: list[list[float]]) -> list[list[float]]:
    if len(rows) != 4 or any(not isinstance(row, list) or len(row) != 4 for row in rows):
        raise GridError("Component matrix must be a 4x4 list.")
    return [[float(value) for value in row] for row in rows]


def transform_bounds(bounds: Bounds, matrix: list[list[float]]) -> Bounds:
    points = [
        transform_point((x, y, z), matrix)
        for x in (bounds.min_x, bounds.max_x)
        for y in (bounds.min_y, bounds.max_y)
        for z in (bounds.min_z, bounds.max_z)
    ]
    min_x = min(point[0] for point in points) / UNIT_SCALE
    max_x = max(point[0] for point in points) / UNIT_SCALE
    min_y = min(point[1] for point in points) / UNIT_SCALE
    max_y = max(point[1] for point in points) / UNIT_SCALE
    min_z = min(point[2] for point in points) / UNIT_SCALE
    max_z = max(point[2] for point in points) / UNIT_SCALE
    return Bounds(min_x, min_y, min_z, max_x, max_y, max_z)


def transform_point(point: tuple[float, float, float], matrix: list[list[float]]) -> tuple[float, float, float]:
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def union_bounds(a: Bounds, b: Bounds) -> Bounds:
    return Bounds(
        min(a.min_x, b.min_x),
        min(a.min_y, b.min_y),
        min(a.min_z, b.min_z),
        max(a.max_x, b.max_x),
        max(a.max_y, b.max_y),
        max(a.max_z, b.max_z),
    )


def resolve_webassets_root(index_doc: dict[str, Any], explicit_root: Path | None) -> Path:
    if explicit_root:
        if not explicit_root.exists():
            raise GridError(f"WebAssets root does not exist: {explicit_root}")
        return explicit_root
    version = str(index_doc.get("version") or "")
    candidate = ROOT.parent / "RSDWModel" / version / "WebAssets"
    if not candidate.exists():
        raise GridError(f"Could not resolve RSDWModel WebAssets root: {candidate}")
    return candidate


def validate_output(data: dict[str, Any]) -> None:
    if data.get("schema") != SCHEMA:
        raise GridError("Unexpected output schema.")
    pieces = data.get("pieces") or []
    if not isinstance(pieces, list):
        raise GridError("pieces must be a list.")
    if int(data.get("count") or 0) != len(pieces):
        raise GridError("count must match pieces length.")
    if pieces:
        piece_ids = {int(piece.get("piece_id") or 0) for piece in pieces if isinstance(piece, dict)}
        anchor_piece_id = int(data.get("anchor_piece_id") or 0)
        if anchor_piece_id not in piece_ids:
            raise GridError("anchor_piece_id must refer to the generated anchor piece.")
        anchor_piece = next(piece for piece in pieces if int(piece.get("piece_id") or 0) == anchor_piece_id)
        if int(data.get("anchor_piece_data_index") or 0) != int(anchor_piece.get("piece_data_index") or 0):
            raise GridError("anchor_piece_data_index must match the anchor piece.")
    actors = data.get("actors")
    if not isinstance(actors, list) or not actors:
        raise GridError("Output must contain actors.")
    names: set[str] = set()
    for actor in actors:
        name = str(actor.get("actor_name") or "")
        if not name or name in names:
            raise GridError(f"Invalid or duplicate actor_name: {name!r}")
        names.add(name)
        for field in ("actor_class", "class_path", "x", "y", "z", "pitch", "yaw", "roll", "scale_x", "scale_y", "scale_z"):
            if field not in actor:
                raise GridError(f"Actor {name} missing {field}.")
        for field in ("x", "y", "z", "pitch", "yaw", "roll", "scale_x", "scale_y", "scale_z"):
            if not math.isfinite(float(actor[field])):
                raise GridError(f"Actor {name} has non-finite {field}.")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def generated_unix(value: str) -> int:
    if str(value).lower() == "now":
        return int(datetime.now(timezone.utc).timestamp())
    return int(value)


def print_summary(data: dict[str, Any], output: Path) -> None:
    actors = data["actors"]
    min_x = min(float(actor["x"]) for actor in actors)
    max_x = max(float(actor["x"]) for actor in actors)
    min_y = min(float(actor["y"]) for actor in actors)
    max_y = max(float(actor["y"]) for actor in actors)
    print(f"name: {data['name']}")
    print(f"pieces: {len(data.get('pieces') or [])}")
    print(f"actors: {len(actors)}")
    print(f"layout: {round(max_x - min_x, 3)}cm x {round(max_y - min_y, 3)}cm")
    print(f"output: {output}")


def safe_actor_name(target: BpTarget, index: int) -> str:
    base = target.target_id.removeprefix("bp:") or target.display_name or f"BP_{index}"
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base)
    return f"{index:04d}_{safe[:80]}"


def natural_key(value: str) -> list[Any]:
    parts: list[Any] = []
    buffer = ""
    numeric = False
    for char in value:
        is_digit = char.isdigit()
        if buffer and is_digit != numeric:
            parts.append(int(buffer) if numeric else buffer.lower())
            buffer = ""
        buffer += char
        numeric = is_digit
    if buffer:
        parts.append(int(buffer) if numeric else buffer.lower())
    return parts


def rounded(value: float) -> int | float:
    rounded_value = round(float(value), 3)
    if rounded_value.is_integer():
        return int(rounded_value)
    return rounded_value


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative number")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
