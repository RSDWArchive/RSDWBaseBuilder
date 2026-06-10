from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = ROOT / "website" / "basebuilder-index.json"
DEFAULT_SNAPS = ROOT / "addon" / "data" / "Snaps.json"
DEFAULT_OUTPUT_DIR = ROOT / "_build" / "procedural"
SCHEMA = "rsdwtools.buildings.v1"

TIER_TARGETS = {
    1: {
        "foundation": "526_DA_T1_Foundation_Large",
        "floor": "531_DA_T1_Floor_Large",
        "wall": "441_DA_T1_Wall_Large",
        "doorframe": "438_DA_T1_Wall_Large_Doorframe",
        "stairs": "444_DA_T1_Stairs_Straight",
        "window_wall": "431_DA_T1_Wall_Large_Windowframe",
        "double_window_wall": "430_DA_T1_Wall_Large_Windowframe_Double",
        "narrow_wall": "436_DA_T1_Wall_Large_Narrow",
        "small_wall": "409_DA_T1_Wall_Small",
        "medium_wall": "429_DA_T1_Wall_Medium",
        "floor_small": "527_DA_T1_Floor_Small",
        "floor_medium": "529_DA_T1_Floor_Medium",
        "foundation_triangle": "525_DA_T1_Foundation_Large_Triangle",
        "foundation_medium_triangle": "523_DA_T1_Foundation_Medium_Triangle",
        "floor_triangle": "530_DA_T1_Floor_Large_Triangle",
        "floor_medium_triangle": "528_DA_T1_Floor_Medium_Triangle",
        "shallow_stairs": "443_DA_T1_Stairs_Straight_Shallow",
        "outer_corner_stairs": "445_DA_T1_Stairs_OuterCorner",
        "inner_corner_stairs": "446_DA_T1_Stairs_InnerCorner",
        "narrow_doorframe": "435_DA_T1_Wall_Large_Narrow_Doorframe",
        "narrow_window_wall": "434_DA_T1_Wall_Large_Narrow_Windowframe",
        "wall_large_diagonal": "440_DA_T1_Wall_Large_Diagonal",
        "wall_large_diagonal_inverted": "439_DA_T1_Wall_Large_Diagonal_Inverted",
        "wall_large_shallow": "433_DA_T1_Wall_Large_Shallow",
        "wall_large_shallow_inverted": "432_DA_T1_Wall_Large_Shallow_Inverted",
        "wall_medium_diagonal": "428_DA_T1_Wall_Medium_Diagonal",
        "wall_medium_diagonal_inverted": "427_DA_T1_Wall_Medium_Diagonal_Inverted",
        "pillar": "550_DA_T1_Beam_Thick_Large_Vertical",
    },
    2: {
        "foundation": "368_DA_T2_Foundation_Large",
        "floor": "388_DA_T2_Floor_Large",
        "wall": "296_DA_T2_Wall_Large",
        "doorframe": "293_DA_T2_Wall_Large_Doorframe",
        "stairs": "299_DA_T2_Stairs_Straight",
        "window_wall": "284_DA_T2_Wall_Large_Windowframe",
        "double_window_wall": "283_DA_T2_Wall_Large_Windowframe_Double",
        "narrow_wall": "291_DA_T2_Wall_Large_Narrow",
        "small_wall": "265_DA_T2_Wall_Small",
        "medium_wall": "282_DA_T2_Wall_Medium",
        "floor_small": "369_DA_T2_Floor_Small",
        "floor_medium": "386_DA_T2_Floor_Medium",
        "foundation_triangle": "367_DA_T2_Foundation_Large_Triangle",
        "foundation_medium_triangle": "365_DA_T2_Foundation_Medium_Triangle",
        "floor_triangle": "387_DA_T2_Floor_Large_Triangle",
        "floor_medium_triangle": "385_DA_T2_Floor_Medium_Triangle",
        "shallow_stairs": "298_DA_T2_Stairs_Straight_Shallow",
        "outer_corner_stairs": "300_DA_T2_Stairs_OuterCorner",
        "inner_corner_stairs": "301_DA_T2_Stairs_InnerCorner",
        "narrow_doorframe": "290_DA_T2_Wall_Large_Narrow_Doorframe",
        "narrow_window_wall": "289_DA_T2_Wall_Large_Narrow_Windowframe",
        "wall_large_diagonal": "295_DA_T2_Wall_Large_Diagonal",
        "wall_large_diagonal_inverted": "294_DA_T2_Wall_Large_Diagonal_Inverted",
        "wall_large_shallow": "288_DA_T2_Wall_Large_Shallow",
        "wall_large_shallow_inverted": "287_DA_T2_Wall_Large_Shallow_Inverted",
        "wall_medium_diagonal": "272_DA_T2_Wall_Medium_Diagonal",
        "wall_medium_diagonal_inverted": "271_DA_T2_Wall_Medium_Diagonal_Inverted",
        "pillar": "404_DA_T2_Beam_Thick_Large_Vertical",
    },
    3: {
        "foundation": "187_DA_T3_Foundation_Large",
        "floor": "203_DA_T3_Floor_Large",
        "wall": "122_DA_T3_Wall_Large",
        "doorframe": "118_DA_T3_Wall_Large_Doorframe",
        "double_doorframe": "117_DA_T3_Wall_Large_Doorframe_Double",
        "stairs": "127_DA_T3_Stairs_Straight",
        "window_wall": "101_DA_T3_Wall_Large_Windowframe",
        "double_window_wall": "106_DA_T3_Wall_Large_Special_Windowed_1",
        "stained_glass_wall": "090_DA_T3_Wall_StainedGlass_6",
        "cross_slit_wall": "102_DA_T3_Wall_Large_Special_Windowed_5",
        "dual_tall_slit_wall": "103_DA_T3_Wall_Large_Special_Windowed_4",
        "tall_slit_wall": "104_DA_T3_Wall_Large_Special_Windowed_3",
        "stone_inset_wall": "105_DA_T3_Wall_Large_Special_Windowed_2",
        "arched_window_wall": "106_DA_T3_Wall_Large_Special_Windowed_1",
        "narrow_wall": "116_DA_T3_Wall_Large_Narrow",
        "small_wall": "091_DA_T3_Wall_Small",
        "medium_wall": "123_DA_T3_Wall_CurvedWindow_Medium",
        "floor_small": "190_DA_T3_Floor_Small",
        "floor_medium": "201_DA_T3_Floor_Medium",
        "foundation_triangle": "186_DA_T3_Foundation_Large_Triangle",
        "foundation_medium_triangle": "184_DA_T3_Foundation_Medium_Triangle",
        "floor_triangle": "202_DA_T3_Floor_Large_Triangle",
        "floor_medium_triangle": "191_DA_T3_Floor_Medium_Triangle",
        "shallow_stairs": "126_DA_T3_Stairs_Straight_Shallow",
        "outer_corner_stairs": "128_DA_T3_Stairs_OuterCorner",
        "inner_corner_stairs": "145_DA_T3_Stairs_InnerCorner",
        "narrow_doorframe": "115_DA_T3_Wall_Large_Narrow_Doorframe",
        "narrow_window_wall": "109_DA_T3_Wall_Large_Narrow_Windowframe",
        "wall_large_diagonal": "120_DA_T3_Wall_Large_Diagonal",
        "wall_large_diagonal_inverted": "119_DA_T3_Wall_Large_Diagonal_Inverted",
        "wall_large_shallow": "108_DA_T3_Wall_Large_Shallow",
        "wall_large_shallow_inverted": "107_DA_T3_Wall_Large_Shallow_Inverted",
        "wall_medium_diagonal": "098_DA_T3_Wall_Medium_Diagonal",
        "wall_medium_diagonal_inverted": "096_DA_T3_Wall_Medium_Diagonal_Inverted",
        "pillar": "260_DA_T3_Beam_Thick_Large_Vertical",
    },
}

STRAIGHT_STAIR_YAW = 180
STRAIGHT_STAIR_ALIGNMENT_OFFSET_X = -64.749
STRAIGHT_STAIR_ALIGNMENT_OFFSET_Z = 77.135
TRIANGLE_SIDE = 300.0
TRIANGLE_HEIGHT = 259.80762
TRIANGLE_BASE_OFFSET = 86.60254
TRIANGLE_APEX_OFFSET = TRIANGLE_HEIGHT - TRIANGLE_BASE_OFFSET
TRIANGLE_CENTER_EDGE_OFFSET = 236.60254

REQUIRED_EXPORT_FIELDS = ("piece_data_index", "piece_data_name", "class_name")
REQUIRED_TRANSFORM_FIELDS = (
    "x",
    "y",
    "z",
    "pitch",
    "yaw",
    "roll",
    "scale_x",
    "scale_y",
    "scale_z",
)

ROOM_TYPES = (
    "entry",
    "chamber",
    "gallery",
    "crossroad",
    "dead_end",
    "overlook",
    "stair_core",
    "tower",
    "atrium",
    "jumping_puzzle",
)
DETAIL_BUDGETS = ("balanced", "low-piece-count", "max-variety")
JUMPING_PUZZLE_VARIANTS = ("stepping_stones", "ledge_climb", "spiral_ascent", "gap_crossing")
SHAPE_LAB_STYLES = (
    "chamfered-hall",
    "diamond-hall",
    "split-gallery",
    "hex-cluster",
    "faceted-room",
    "obtuse-hex-room",
)
SHAPE_LAB_WALL_PATTERN = (
    "wall",
    "cross_slit_wall",
    "wall",
    "dual_tall_slit_wall",
    "wall",
    "arched_window_wall",
    "wall",
    "stained_glass_wall",
    "wall",
    "stone_inset_wall",
    "wall",
    "tall_slit_wall",
)


@dataclass(frozen=True)
class PieceTarget:
    target_id: str
    display_name: str
    asset_stem: str
    snap_class: str
    piece_data_index: int
    piece_data_name: str
    class_name: str
    default_stability: int


@dataclass
class RoomNode:
    room_id: int
    room_type: str
    level: int
    width: int
    height: int
    x: int | None = None
    y: int | None = None
    mask_kind: str = "rect"
    wall_height: int = 1
    has_balcony: bool = False
    has_divider: bool = False
    has_columns: bool = False
    has_windows: bool = False
    detail_budget: str = "balanced"
    jumping_variant: str = "stepping_stones"
    blueprint_id: str = ""
    features: tuple[str, ...] = ()

    @property
    def x_value(self) -> int:
        if self.x is None:
            raise GeneratorError(f"Room {self.room_id} has no x placement.")
        return self.x

    @property
    def y_value(self) -> int:
        if self.y is None:
            raise GeneratorError(f"Room {self.room_id} has no y placement.")
        return self.y


@dataclass(frozen=True)
class RoomGraphEdge:
    a: int
    b: int
    vertical: bool = False
    loop: bool = False
    critical: bool = False


@dataclass(frozen=True)
class RoomMazeReport:
    rooms: int
    critical_path_length: int
    branches: int
    loops: int
    levels_used: int


@dataclass(frozen=True)
class RoomBlueprint:
    blueprint_id: str
    room_type: str
    width: int
    height: int
    mask_kind: str
    wall_height: int
    features: tuple[str, ...]
    window_bias: float = 0.4


ROOM_BLUEPRINTS: tuple[RoomBlueprint, ...] = (
    RoomBlueprint("entry_clear_5x4", "entry", 5, 4, "rect", 1, ("corner_pillars",), 0.2),
    RoomBlueprint("entry_chamfered_gate_6x4", "entry", 6, 4, "chamfered", 2, ("corner_pillars",), 0.35),
    RoomBlueprint("chamber_loft_8x6", "chamber", 8, 6, "rect", 2, ("loft", "corner_pillars"), 0.5),
    RoomBlueprint("chamber_stage_7x5", "chamber", 7, 5, "rect", 2, ("back_stage",), 0.35),
    RoomBlueprint("chamber_nested_suite_7x6", "chamber", 7, 6, "chamfered", 2, ("inner_room", "back_stage", "corner_pillars"), 0.45),
    RoomBlueprint("chamber_split_6x5", "chamber", 6, 5, "split", 2, ("side_walkway",), 0.35),
    RoomBlueprint("gallery_side_walkway_8x4", "gallery", 8, 4, "rect", 2, ("side_walkway",), 0.65),
    RoomBlueprint("gallery_chamfered_8x5", "gallery", 8, 5, "chamfered", 2, ("side_walkway",), 0.65),
    RoomBlueprint("crossroad_open_hub_6x6", "crossroad", 6, 6, "cross", 2, ("corner_pillars",), 0.35),
    RoomBlueprint("crossroad_chamfered_hub_7x7", "crossroad", 7, 7, "chamfered", 2, ("corner_pillars",), 0.4),
    RoomBlueprint("dead_end_stage_5x4", "dead_end", 5, 4, "rect", 2, ("back_stage",), 0.5),
    RoomBlueprint("dead_end_alcove_5x5", "dead_end", 5, 5, "l", 2, ("back_stage",), 0.45),
    RoomBlueprint("overlook_balcony_6x4", "overlook", 6, 4, "u", 2, ("balcony",), 0.7),
    RoomBlueprint("overlook_chamfered_6x5", "overlook", 6, 5, "chamfered", 2, ("balcony",), 0.65),
    RoomBlueprint("stair_core_landing_6x5", "stair_core", 6, 5, "rect", 2, (), 0.45),
    RoomBlueprint("tower_stacked_6x5", "tower", 6, 5, "rect", 3, ("corner_pillars", "divider"), 0.55),
    RoomBlueprint("atrium_upper_ring_7x6", "atrium", 7, 6, "rect", 3, ("upper_ring", "corner_pillars"), 0.7),
    RoomBlueprint("atrium_chamfered_ring_8x7", "atrium", 8, 7, "chamfered", 3, ("upper_ring", "corner_pillars"), 0.75),
    RoomBlueprint("jumping_puzzle_supported_8x8", "jumping_puzzle", 8, 8, "rect", 3, ("jumping_platforms",), 0.7),
)

BLUEPRINTS_BY_ROOM_TYPE: dict[str, tuple[RoomBlueprint, ...]] = {
    room_type: tuple(blueprint for blueprint in ROOM_BLUEPRINTS if blueprint.room_type == room_type)
    for room_type in ROOM_TYPES
}


@dataclass
class RoomMazeBuild:
    rooms: list[RoomNode]
    edges: list[RoomGraphEdge]
    critical_path_length: int
    branches: int
    loops: int
    levels_used: int


class GeneratorError(RuntimeError):
    pass


class BuildingGenerator:
    def __init__(
        self,
        targets: dict[str, PieceTarget],
        cell_size: float,
        stair_run: float,
        stair_rise: float,
    ) -> None:
        self.targets = targets
        self.cell_size = cell_size
        self.half_cell = cell_size / 2
        self.stair_run = stair_run
        self.stair_rise = stair_rise
        self.pieces: list[dict[str, Any]] = []
        self.next_piece_id = 1
        self.anchor_piece_id = 0
        self.anchor_piece_data_index = 0

    def add_piece(
        self,
        role: str,
        x: float,
        y: float,
        z: float = 0,
        yaw: float = 0,
        pitch: float = 0,
        roll: float = 0,
    ) -> dict[str, Any]:
        target = self.targets[role]
        piece_id = self.next_piece_id
        self.next_piece_id += 1
        row = {
            "piece_id": piece_id,
            "piece_data_index": target.piece_data_index,
            "piece_data_name": target.piece_data_name,
            "class_name": target.class_name,
            "x": round_number(x),
            "y": round_number(y),
            "z": round_number(z),
            "pitch": round_number(pitch),
            "yaw": round_number(yaw),
            "roll": round_number(roll),
            "scale_x": 1,
            "scale_y": 1,
            "scale_z": 1,
            "stability": target.default_stability,
            "is_ghosted": False,
        }
        if self.anchor_piece_id == 0 and role.startswith("foundation"):
            self.anchor_piece_id = piece_id
            self.anchor_piece_data_index = target.piece_data_index
        self.pieces.append(row)
        return row

    def add_cell_surface(self, col: int, row: int, level: int = 0, role: str | None = None) -> dict[str, Any]:
        surface_role = role or ("foundation" if level == 0 else "floor")
        return self.add_piece(
            surface_role,
            x=col * self.cell_size,
            y=row * self.cell_size,
            z=level * self.cell_size,
        )

    def add_cell_triangle_surface(
        self,
        col: int,
        row: int,
        level: int = 0,
        role: str | None = None,
        yaw: float = 0,
    ) -> dict[str, Any]:
        surface_role = role or ("foundation_triangle" if level == 0 else "floor_triangle")
        return self.add_piece(
            surface_role,
            x=col * self.cell_size,
            y=row * self.cell_size,
            z=level * self.cell_size,
            yaw=yaw,
        )

    def add_wall_edge(self, edge: tuple[str, int, int], role: str = "wall", level: int = 0) -> dict[str, Any]:
        axis, a, b = edge
        if axis == "h":
            return self.add_piece(
                role,
                x=a * self.cell_size,
                y=(b * self.cell_size) - self.half_cell,
                z=level * self.cell_size,
                yaw=0,
            )
        if axis == "v":
            return self.add_piece(
                role,
                x=(a * self.cell_size) - self.half_cell,
                y=b * self.cell_size,
                z=level * self.cell_size,
                yaw=90,
            )
        raise GeneratorError(f"Unknown wall edge axis: {axis!r}")

    def add_wall_segment(
        self,
        role: str,
        p1: tuple[float, float],
        p2: tuple[float, float],
        level: int = 0,
    ) -> dict[str, Any]:
        x1, y1 = p1
        x2, y2 = p2
        yaw = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 360
        return self.add_piece(
            role,
            x=(x1 + x2) / 2,
            y=(y1 + y2) / 2,
            z=level * self.cell_size,
            yaw=yaw,
        )

    def document(self, name: str, generated_unix: int = 0) -> dict[str, Any]:
        if not self.anchor_piece_id:
            raise GeneratorError("Generated build has no foundation anchor.")
        return {
            "schema": SCHEMA,
            "name": name,
            "generated_unix": int(generated_unix),
            "count": len(self.pieces),
            "skipped": 0,
            "item_count": 0,
            "item_skipped": 0,
            "hidden": 0,
            "pieces": self.pieces,
            "items": [],
            "actors": [],
            "anchor_piece_id": self.anchor_piece_id,
            "anchor_piece_data_index": self.anchor_piece_data_index,
        }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.preset == "shape-lab":
        args.tier = 3

    try:
        if args.validate_only and args.input:
            data = load_json(args.input)
            validate_building_json(data)
            validate_against_index(data, load_json(args.index))
            print_summary(data, args.input)
            return 0

        targets, index_doc = load_targets(args.index, args.tier)
        snaps = load_json(args.snaps)
        cell_size = derive_cell_size(snaps, targets["foundation"])
        stair_run, stair_rise = derive_stair_extents(snaps, targets["stairs"])
        data, report = generate_build(args, targets, cell_size, stair_run, stair_rise)
        validate_building_json(data)
        validate_against_index(data, index_doc)

        if args.validate_only:
            print_summary(data, None, report)
            return 0

        output = args.output or default_output_path(args)
        if args.dry_run:
            print_summary(data, output, report)
            return 0

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print_summary(data, output, report)
        return 0
    except (GeneratorError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate procedural RSDW Base Builder JSON files from math-based presets.",
    )
    parser.add_argument(
        "--preset",
        choices=("maze", "platform", "elevation-demo", "room-maze", "jumping-puzzle", "room-lab", "shape-lab"),
        default="maze",
    )
    parser.add_argument("--width", type=positive_int, default=16)
    parser.add_argument("--height", type=positive_int, default=16)
    parser.add_argument("--levels", type=positive_int, default=2)
    parser.add_argument("--rooms", type=positive_int, default=24)
    parser.add_argument("--branch-rate", type=rate_float, default=0.35)
    parser.add_argument("--loop-rate", type=rate_float, default=0.15)
    parser.add_argument("--elevation-rate", type=rate_float, default=0.25)
    parser.add_argument("--max-levels", type=positive_int, default=3)
    parser.add_argument("--irregular-room-rate", type=rate_float, default=0.55)
    parser.add_argument("--tall-room-rate", type=rate_float, default=0.35)
    parser.add_argument("--balcony-rate", type=rate_float, default=0.25)
    parser.add_argument("--window-rate", type=rate_float, default=0.4)
    parser.add_argument("--room-type", choices=ROOM_TYPES, default="chamber")
    parser.add_argument("--detail-budget", choices=DETAIL_BUDGETS, default="balanced")
    parser.add_argument("--jumping-variant", choices=JUMPING_PUZZLE_VARIANTS, default="stepping_stones")
    parser.add_argument("--shape-style", choices=SHAPE_LAB_STYLES, default="chamfered-hall")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tier", type=int, choices=sorted(TIER_TARGETS), default=2)
    parser.add_argument("--name", default="")
    parser.add_argument(
        "--generated-unix",
        default="0",
        help="Unix timestamp metadata. Defaults to 0 for deterministic generated files; use 'now' for current UTC time.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path, help="Existing JSON file to validate with --validate-only.")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--snaps", type=Path, default=DEFAULT_SNAPS)
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate without writing a file.")
    parser.add_argument("--validate-only", action="store_true", help="Validate generated output, or --input if provided.")
    return parser


def generate_build(
    args: argparse.Namespace,
    targets: dict[str, PieceTarget],
    cell_size: float,
    stair_run: float,
    stair_rise: float,
) -> tuple[dict[str, Any], RoomMazeReport | None]:
    generator = BuildingGenerator(targets, cell_size, stair_run, stair_rise)
    report = None
    if args.preset == "maze":
        generate_maze(generator, width=args.width, height=args.height, seed=args.seed)
    elif args.preset == "platform":
        generate_platform(generator, width=args.width, height=args.height)
    elif args.preset == "elevation-demo":
        generate_elevation_demo(generator, width=args.width, height=args.height, levels=args.levels)
    elif args.preset == "jumping-puzzle":
        generate_jumping_puzzle(
            generator,
            width=args.width,
            height=args.height,
            seed=args.seed,
            variant=args.jumping_variant,
            detail_budget=args.detail_budget,
        )
    elif args.preset == "room-lab":
        report = generate_room_lab(
            generator,
            room_type=args.room_type,
            width=args.width,
            height=args.height,
            seed=args.seed,
            detail_budget=args.detail_budget,
            jumping_variant=args.jumping_variant,
        )
    elif args.preset == "shape-lab":
        generate_shape_lab(generator, style=args.shape_style)
    elif args.preset == "room-maze":
        report = generate_room_maze(
            generator,
            room_count=args.rooms,
            branch_rate=args.branch_rate,
            loop_rate=args.loop_rate,
            elevation_rate=args.elevation_rate,
            max_levels=args.max_levels,
            irregular_room_rate=args.irregular_room_rate,
            tall_room_rate=args.tall_room_rate,
            balcony_rate=args.balcony_rate,
            window_rate=args.window_rate,
            detail_budget=args.detail_budget,
            seed=args.seed,
        )
    else:
        raise GeneratorError(f"Unsupported preset: {args.preset}")
    name = args.name or default_build_name(args)
    return generator.document(name, generated_unix=parse_generated_unix(args.generated_unix)), report


def generate_platform(generator: BuildingGenerator, width: int, height: int) -> None:
    for row in range(height):
        for col in range(width):
            generator.add_cell_surface(col, row)
    for edge in perimeter_edges(width, height):
        generator.add_wall_edge(edge)


def generate_maze(generator: BuildingGenerator, width: int, height: int, seed: int) -> None:
    for row in range(height):
        for col in range(width):
            generator.add_cell_surface(col, row)

    walls = set(all_grid_edges(width, height))
    visited = {(0, 0)}
    stack = [(0, 0)]
    rng = random.Random(seed)

    while stack:
        col, row = stack[-1]
        candidates = [
            (ncol, nrow, edge_between(col, row, ncol, nrow))
            for ncol, nrow in neighbors(col, row, width, height)
            if (ncol, nrow) not in visited
        ]
        if not candidates:
            stack.pop()
            continue
        ncol, nrow, edge = rng.choice(candidates)
        walls.discard(edge)
        visited.add((ncol, nrow))
        stack.append((ncol, nrow))

    for edge in sorted(walls):
        role = "doorframe" if edge in {("h", 0, 0), ("h", width - 1, height)} else "wall"
        generator.add_wall_edge(edge, role=role)


def generate_elevation_demo(generator: BuildingGenerator, width: int, height: int, levels: int) -> None:
    platform_width = max(2, min(width, 4))
    platform_height = max(2, min(height, 4))
    offset_step = max(platform_width + 1, 5)

    for level in range(levels):
        x_offset = level * offset_step
        for row in range(platform_height):
            for col in range(platform_width):
                generator.add_cell_surface(x_offset + col, row, level=level)
        for edge in perimeter_edges(platform_width, platform_height):
            shifted = shift_edge(edge, x_offset, 0)
            if edge[0] == "h" and edge[2] == 0 and level > 0:
                continue
            if is_elevation_stair_connector_edge(edge, level, levels, platform_width):
                continue
            generator.add_wall_edge(shifted, level=level)
        if level > 0:
            stairs_needed = max(1, round(generator.cell_size / generator.stair_rise))
            start_x = (x_offset * generator.cell_size) - (stairs_needed * generator.stair_run)
            for stair_index in range(stairs_needed):
                stair_x = start_x + (stair_index * generator.stair_run) + STRAIGHT_STAIR_ALIGNMENT_OFFSET_X
                stair_y = 0
                stair_z = (
                    ((level - 1) * generator.cell_size)
                    + (stair_index * generator.stair_rise)
                    + STRAIGHT_STAIR_ALIGNMENT_OFFSET_Z
                )
                generator.add_piece("stairs", stair_x, stair_y, stair_z, yaw=STRAIGHT_STAIR_YAW)


def is_elevation_stair_connector_edge(
    edge: tuple[str, int, int],
    level: int,
    levels: int,
    platform_width: int,
) -> bool:
    axis, a, b = edge
    if axis != "v" or b != 0:
        return False
    incoming_opening = level > 0 and a == 0
    outgoing_opening = level + 1 < levels and a == platform_width
    return incoming_opening or outgoing_opening


def generate_shape_lab(generator: BuildingGenerator, style: str) -> None:
    if style == "chamfered-hall":
        square_cells = {
            (col, row)
            for row in range(6)
            for col in range(8)
        }
        triangle_attachments = [
            (1, 0, "s"),
            (6, 0, "s"),
            (1, 5, "n"),
            (6, 5, "n"),
            (0, 1, "w"),
            (0, 4, "w"),
            (7, 1, "e"),
            (7, 4, "e"),
        ]
        entry_edges = {("h", 3, 0): "double_doorframe", ("h", 4, 6): "double_doorframe"}
    elif style == "diamond-hall":
        square_cells = {
            (3, 0),
            (2, 1), (3, 1), (4, 1),
            (1, 2), (2, 2), (3, 2), (4, 2), (5, 2),
            (0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (6, 3),
            (1, 4), (2, 4), (3, 4), (4, 4), (5, 4),
            (2, 5), (3, 5), (4, 5),
            (3, 6),
        }
        triangle_attachments = [
            (2, 1, "s"),
            (4, 1, "s"),
            (1, 2, "w"),
            (5, 2, "e"),
            (1, 4, "w"),
            (5, 4, "e"),
            (2, 5, "n"),
            (4, 5, "n"),
        ]
        entry_edges = {("h", 3, 0): "doorframe", ("h", 3, 7): "doorframe"}
    elif style == "split-gallery":
        square_cells = {
            (col, row)
            for row in range(5)
            for col in range(9)
            if col in {0, 1, 2, 3, 5, 6, 7, 8} or row in {1, 2, 3}
        }
        triangle_attachments = [
            (0, 0, "w"),
            (8, 0, "e"),
            (0, 4, "w"),
            (8, 4, "e"),
            (4, 1, "s"),
            (4, 3, "n"),
        ]
        entry_edges = {("v", 0, 2): "double_doorframe", ("v", 9, 2): "double_doorframe"}
    elif style == "hex-cluster":
        emit_hex_cluster_shape_lab(generator)
        return
    elif style == "faceted-room":
        emit_faceted_room_shape_lab(generator)
        return
    elif style == "obtuse-hex-room":
        emit_obtuse_hex_room_shape_lab(generator)
        return
    else:
        raise GeneratorError(f"Unsupported shape-lab style: {style}")

    emit_shape_lab_room(generator, square_cells, triangle_attachments, entry_edges)


def emit_hex_cluster_shape_lab(generator: BuildingGenerator) -> None:
    triangle_tiles = triangle_hex_tiles(0, 0)
    by_yaw = {round(yaw): (x, y, yaw) for x, y, yaw in triangle_tiles}

    entry_square = square_tile_attached_to_triangle_base(by_yaw[0])
    exit_square = square_tile_attached_to_triangle_base(by_yaw[180])
    square_tiles = [
        (entry_square[0], entry_square[1], entry_square[2]),
        (exit_square[0], exit_square[1], exit_square[2]),
    ]
    entry_edge_roles = {
        square_outer_edge_key(entry_square): "double_doorframe",
        square_outer_edge_key(exit_square): "double_doorframe",
    }
    emit_polygon_shape_lab_room(generator, square_tiles, triangle_tiles, entry_edge_roles)


def emit_faceted_room_shape_lab(generator: BuildingGenerator) -> None:
    square_tiles: list[tuple[float, float, float]] = []
    for col in range(4):
        for row in range(4):
            square_tiles.append(((col - 1.5) * generator.cell_size, (row - 1.5) * generator.cell_size, 0.0))

    triangle_tiles: list[tuple[float, float, float]] = []
    triangle_keys: set[tuple[float, float, float]] = set()
    square_by_grid = {
        (col, row): ((col - 1.5) * generator.cell_size, (row - 1.5) * generator.cell_size, 0.0)
        for col in range(4)
        for row in range(4)
    }
    bay_specs = [
        ((1, 3), "n"),
        ((2, 0), "s"),
        ((0, 1), "w"),
        ((3, 2), "e"),
    ]
    for grid_key, side in bay_specs:
        add_triangle_bay_from_square_edge(
            square_by_grid[grid_key],
            side,
            triangle_tiles,
            triangle_keys,
            include_wings=True,
        )

    entry_edge_roles = {
        square_edge_key_by_side(square_by_grid[(1, 0)], "s"): "double_doorframe",
        square_edge_key_by_side(square_by_grid[(2, 3)], "n"): "double_doorframe",
    }
    emit_polygon_shape_lab_room(generator, square_tiles, triangle_tiles, entry_edge_roles)


def emit_obtuse_hex_room_shape_lab(generator: BuildingGenerator) -> None:
    hex_centers = triangle_hex_room_centers()
    triangle_tiles: list[tuple[float, float, float]] = []
    triangle_keys: set[tuple[float, float, float]] = set()
    for center_x, center_y in hex_centers:
        for tile in triangle_hex_tiles(center_x, center_y):
            append_triangle_tile(triangle_tiles, triangle_keys, tile)

    boundary_edges = polygon_boundary_edges([], triangle_tiles)
    entry_edge = boundary_edge_by_direction(boundary_edges, 240)
    exit_edge = boundary_edge_by_direction(boundary_edges, 60)
    entry_edge_roles = {
        entry_edge[0]: "double_doorframe",
        exit_edge[0]: "double_doorframe",
    }
    emit_polygon_shape_lab_room(generator, [], triangle_tiles, entry_edge_roles)


def triangle_hex_room_centers() -> list[tuple[float, float]]:
    centers: list[tuple[float, float]] = [(0.0, 0.0)]
    center_keys: set[tuple[float, float]] = {(0.0, 0.0)}

    for angle in (0, 60, 120, 180, 240, 300):
        append_hex_center(centers, center_keys, hex_neighbor_center(0.0, 0.0, angle))

    east = hex_neighbor_center(0.0, 0.0, 0)
    northeast = hex_neighbor_center(0.0, 0.0, 60)
    southwest = hex_neighbor_center(0.0, 0.0, 240)
    for source, angle in (
        (east, 0),
        (east, 60),
        (northeast, 60),
        (southwest, 240),
    ):
        append_hex_center(centers, center_keys, hex_neighbor_center(source[0], source[1], angle))

    return centers


def append_hex_center(
    centers: list[tuple[float, float]],
    center_keys: set[tuple[float, float]],
    center: tuple[float, float],
) -> None:
    key = (round(center[0], 3), round(center[1], 3))
    if key in center_keys:
        return
    center_keys.add(key)
    centers.append(center)


def hex_neighbor_center(center_x: float, center_y: float, angle: float) -> tuple[float, float]:
    edge_key, p1, p2 = boundary_edge_by_direction(hex_boundary_edges(center_x, center_y), angle)
    return reflect_point_across_line((center_x, center_y), p1, p2)


def hex_boundary_edges(center_x: float, center_y: float) -> list[
    tuple[
        tuple[tuple[float, float], tuple[float, float]],
        tuple[float, float],
        tuple[float, float],
    ]
]:
    return polygon_boundary_edges([], triangle_hex_tiles(center_x, center_y))


def add_triangle_bay_from_square_edge(
    square_tile: tuple[float, float, float],
    side: str,
    triangle_tiles: list[tuple[float, float, float]],
    triangle_keys: set[tuple[float, float, float]],
    include_wings: bool = True,
) -> None:
    center_x, center_y, _yaw = square_tile
    _label, p1, p2 = square_edge_by_side(square_tile, side)
    root = triangle_tile_outside_edge(p1, p2, (center_x, center_y))
    append_triangle_tile(triangle_tiles, triangle_keys, root)
    if not include_wings:
        return
    for label, wing_p1, wing_p2 in triangle_edge_segments(root[0], root[1], root[2]):
        if label == "base":
            continue
        append_triangle_tile(
            triangle_tiles,
            triangle_keys,
            triangle_tile_outside_edge(wing_p1, wing_p2, (root[0], root[1])),
        )


def emit_polygon_shape_lab_room(
    generator: BuildingGenerator,
    square_tiles: list[tuple[float, float, float]],
    triangle_tiles: list[tuple[float, float, float]],
    entry_edge_roles: dict[tuple[tuple[float, float], tuple[float, float]], str],
) -> None:
    for x, y, yaw in square_tiles:
        generator.add_piece("foundation", x=x, y=y, z=0, yaw=yaw)
    for x, y, yaw in triangle_tiles:
        generator.add_piece("foundation_triangle", x=x, y=y, z=0, yaw=yaw)

    edge_records = polygon_edge_records(square_tiles, triangle_tiles)

    wall_index = 0
    for key in sorted(edge_records):
        records = edge_records[key]
        if len(records) > 2:
            raise GeneratorError(f"Too many surfaces share edge {key}.")
        if len(records) == 2:
            continue
        role = entry_edge_roles.get(key)
        if role is None:
            role = shape_wall_role(wall_index)
            wall_index += 1
        p1, p2 = records[0]
        generator.add_wall_segment(role, p1, p2, level=0)


def polygon_edge_records(
    square_tiles: list[tuple[float, float, float]],
    triangle_tiles: list[tuple[float, float, float]],
) -> dict[
    tuple[tuple[float, float], tuple[float, float]],
    list[tuple[tuple[float, float], tuple[float, float]]],
]:
    edge_records: dict[
        tuple[tuple[float, float], tuple[float, float]],
        list[tuple[tuple[float, float], tuple[float, float]]],
    ] = {}

    for x, y, yaw in square_tiles:
        for _label, p1, p2 in square_edge_segments(x, y, yaw):
            edge_records.setdefault(surface_edge_key(p1, p2), []).append((p1, p2))

    for x, y, yaw in triangle_tiles:
        for _label, p1, p2 in triangle_edge_segments(x, y, yaw):
            edge_records.setdefault(surface_edge_key(p1, p2), []).append((p1, p2))

    return edge_records


def polygon_boundary_edges(
    square_tiles: list[tuple[float, float, float]],
    triangle_tiles: list[tuple[float, float, float]],
) -> list[
    tuple[
        tuple[tuple[float, float], tuple[float, float]],
        tuple[float, float],
        tuple[float, float],
    ]
]:
    boundary = []
    for key, records in polygon_edge_records(square_tiles, triangle_tiles).items():
        if len(records) > 2:
            raise GeneratorError(f"Too many surfaces share edge {key}.")
        if len(records) == 1:
            p1, p2 = records[0]
            boundary.append((key, p1, p2))
    return boundary


def boundary_edge_by_direction(
    boundary_edges: list[
        tuple[
            tuple[tuple[float, float], tuple[float, float]],
            tuple[float, float],
            tuple[float, float],
        ]
    ],
    angle: float,
) -> tuple[tuple[tuple[float, float], tuple[float, float]], tuple[float, float], tuple[float, float]]:
    if not boundary_edges:
        raise GeneratorError("Cannot pick a boundary edge from an empty polygon.")
    direction_x, direction_y = rotate_vector(1.0, 0.0, angle)
    return max(
        boundary_edges,
        key=lambda edge: (((edge[1][0] + edge[2][0]) / 2) * direction_x)
        + (((edge[1][1] + edge[2][1]) / 2) * direction_y),
    )


def triangle_hex_tiles(center_x: float, center_y: float) -> list[tuple[float, float, float]]:
    tiles = []
    for yaw in (0, 60, 120, 180, 240, 300):
        apex_x, apex_y = rotate_vector(0, TRIANGLE_APEX_OFFSET, yaw)
        tiles.append((center_x - apex_x, center_y - apex_y, float(yaw)))
    return tiles


def square_tile_attached_to_triangle_base(
    triangle_tile: tuple[float, float, float],
) -> tuple[float, float, float, tuple[float, float]]:
    center_x, center_y, yaw = triangle_tile
    _label, p1, p2 = triangle_edge_segments(center_x, center_y, yaw)[0]
    mid_x = (p1[0] + p2[0]) / 2
    mid_y = (p1[1] + p2[1]) / 2
    normal_x = mid_x - center_x
    normal_y = mid_y - center_y
    length = math.hypot(normal_x, normal_y)
    if length == 0:
        raise GeneratorError("Cannot attach square tile to zero-length triangle base normal.")
    normal_x /= length
    normal_y /= length
    edge_yaw = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0])) % 360
    return (
        mid_x + normal_x * (TRIANGLE_SIDE / 2),
        mid_y + normal_y * (TRIANGLE_SIDE / 2),
        edge_yaw,
        (normal_x, normal_y),
    )


def triangle_tile_outside_edge(
    p1: tuple[float, float],
    p2: tuple[float, float],
    occupied_point: tuple[float, float],
) -> tuple[float, float, float]:
    edge_x = p2[0] - p1[0]
    edge_y = p2[1] - p1[1]
    edge_length = math.hypot(edge_x, edge_y)
    if abs(edge_length - TRIANGLE_SIDE) > 0.01:
        raise GeneratorError(f"Triangle edge length must be {TRIANGLE_SIDE}, got {edge_length:.3f}.")

    occupied_side = edge_x * (occupied_point[1] - p1[1]) - edge_y * (occupied_point[0] - p1[0])
    if abs(occupied_side) < 0.001:
        raise GeneratorError("Cannot attach triangle because occupied point is on the source edge.")

    base_start, base_end = (p2, p1) if occupied_side > 0 else (p1, p2)
    base_x = base_end[0] - base_start[0]
    base_y = base_end[1] - base_start[1]
    yaw = math.degrees(math.atan2(base_y, base_x)) % 360
    normal_x = -base_y / edge_length
    normal_y = base_x / edge_length
    mid_x = (base_start[0] + base_end[0]) / 2
    mid_y = (base_start[1] + base_end[1]) / 2
    return (
        mid_x + normal_x * TRIANGLE_BASE_OFFSET,
        mid_y + normal_y * TRIANGLE_BASE_OFFSET,
        yaw,
    )


def append_triangle_tile(
    triangle_tiles: list[tuple[float, float, float]],
    triangle_keys: set[tuple[float, float, float]],
    tile: tuple[float, float, float],
) -> None:
    key = (round(tile[0], 3), round(tile[1], 3), round(tile[2] % 360, 3))
    if key in triangle_keys:
        return
    triangle_keys.add(key)
    triangle_tiles.append(tile)


def square_edge_by_side(
    square_tile: tuple[float, float, float],
    side: str,
) -> tuple[str, tuple[float, float], tuple[float, float]]:
    for edge in square_edge_segments(square_tile[0], square_tile[1], square_tile[2]):
        if edge[0] == side:
            return edge
    raise GeneratorError(f"Unknown square edge side: {side}")


def square_edge_key_by_side(
    square_tile: tuple[float, float, float],
    side: str,
) -> tuple[tuple[float, float], tuple[float, float]]:
    _label, p1, p2 = square_edge_by_side(square_tile, side)
    return surface_edge_key(p1, p2)


def square_outer_edge_key(
    square_tile: tuple[float, float, float, tuple[float, float]],
) -> tuple[tuple[float, float], tuple[float, float]]:
    center_x, center_y, yaw, normal = square_tile
    normal_x, normal_y = normal
    best_edge = max(
        square_edge_segments(center_x, center_y, yaw),
        key=lambda edge: ((((edge[1][0] + edge[2][0]) / 2) - center_x) * normal_x)
        + ((((edge[1][1] + edge[2][1]) / 2) - center_y) * normal_y),
    )
    return surface_edge_key(best_edge[1], best_edge[2])


def square_edge_segments(
    center_x: float,
    center_y: float,
    yaw: float,
) -> list[tuple[str, tuple[float, float], tuple[float, float]]]:
    local_vertices = (
        (-TRIANGLE_SIDE / 2, -TRIANGLE_SIDE / 2),
        (TRIANGLE_SIDE / 2, -TRIANGLE_SIDE / 2),
        (TRIANGLE_SIDE / 2, TRIANGLE_SIDE / 2),
        (-TRIANGLE_SIDE / 2, TRIANGLE_SIDE / 2),
    )
    vertices = [
        (
            center_x + rotate_vector(local_x, local_y, yaw)[0],
            center_y + rotate_vector(local_x, local_y, yaw)[1],
        )
        for local_x, local_y in local_vertices
    ]
    return [
        ("s", vertices[0], vertices[1]),
        ("e", vertices[1], vertices[2]),
        ("n", vertices[3], vertices[2]),
        ("w", vertices[0], vertices[3]),
    ]


def triangle_edge_segments(
    center_x: float,
    center_y: float,
    yaw: float,
) -> list[tuple[str, tuple[float, float], tuple[float, float]]]:
    base_left, base_right, apex = triangle_world_vertices(center_x, center_y, yaw)
    return [
        ("base", base_left, base_right),
        ("left", base_left, apex),
        ("right", apex, base_right),
    ]


def surface_edge_key(
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    a = canonical_surface_point(p1)
    b = canonical_surface_point(p2)
    return (a, b) if a <= b else (b, a)


def canonical_surface_point(point: tuple[float, float]) -> tuple[float, float]:
    return round(point[0], 3), round(point[1], 3)


def rotate_vector(x: float, y: float, yaw: float) -> tuple[float, float]:
    angle = math.radians(yaw)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return (x * cos_a) - (y * sin_a), (x * sin_a) + (y * cos_a)


def reflect_point_across_line(
    point: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> tuple[float, float]:
    point_x, point_y = point
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    length_sq = (dx * dx) + (dy * dy)
    if length_sq == 0:
        raise GeneratorError("Cannot reflect across a zero-length edge.")
    t = (((point_x - x1) * dx) + ((point_y - y1) * dy)) / length_sq
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return (2 * proj_x) - point_x, (2 * proj_y) - point_y


def emit_shape_lab_room(
    generator: BuildingGenerator,
    square_cells: set[tuple[int, int]],
    triangle_attachments: list[tuple[int, int, str]],
    entry_edges: dict[tuple[str, int, int], str],
) -> None:
    perimeter_edges = set(perimeter_edges_for_cells(square_cells))
    triangle_base_edges: set[tuple[str, int, int]] = set()

    for col, row, side in triangle_attachments:
        if (col, row) not in square_cells:
            raise GeneratorError(f"Triangle attachment {(col, row, side)} has no square floor to attach to.")
        base_edge = triangle_attachment_base_edge(col, row, side)
        if base_edge not in perimeter_edges:
            raise GeneratorError(f"Triangle attachment {(col, row, side)} is not on an exposed room edge.")
        if base_edge in entry_edges:
            raise GeneratorError(f"Triangle attachment {(col, row, side)} overlaps a room entry edge.")
        triangle_base_edges.add(base_edge)

    for col, row in sorted(square_cells):
        generator.add_cell_surface(col, row, level=0, role="foundation")
    for col, row, side in triangle_attachments:
        x, y, yaw = triangle_attachment_transform(generator, col, row, side)
        generator.add_piece("foundation_triangle", x=x, y=y, z=0, yaw=yaw)

    wall_index = 0
    for edge in sorted(perimeter_edges):
        if edge in triangle_base_edges:
            continue
        role = entry_edges.get(edge)
        if role is None:
            role = shape_wall_role(wall_index)
            wall_index += 1
        generator.add_wall_edge(edge, role=role, level=0)

    for col, row, side in triangle_attachments:
        x, y, yaw = triangle_attachment_transform(generator, col, row, side)
        for p1, p2 in triangle_exposed_wall_segments(x, y, yaw):
            generator.add_wall_segment(shape_wall_role(wall_index), p1, p2, level=0)
            wall_index += 1


def triangle_attachment_base_edge(col: int, row: int, side: str) -> tuple[str, int, int]:
    if side == "n":
        return "h", col, row + 1
    if side == "s":
        return "h", col, row
    if side == "e":
        return "v", col + 1, row
    if side == "w":
        return "v", col, row
    raise GeneratorError(f"Unknown triangle attachment side: {side}")


def triangle_attachment_transform(
    generator: BuildingGenerator,
    col: int,
    row: int,
    side: str,
) -> tuple[float, float, float]:
    center_x = col * generator.cell_size
    center_y = row * generator.cell_size
    if side == "n":
        return center_x, center_y + TRIANGLE_CENTER_EDGE_OFFSET, 0
    if side == "s":
        return center_x, center_y - TRIANGLE_CENTER_EDGE_OFFSET, 180
    if side == "e":
        return center_x + TRIANGLE_CENTER_EDGE_OFFSET, center_y, 270
    if side == "w":
        return center_x - TRIANGLE_CENTER_EDGE_OFFSET, center_y, 90
    raise GeneratorError(f"Unknown triangle attachment side: {side}")


def triangle_exposed_wall_segments(
    center_x: float,
    center_y: float,
    yaw: float,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    base_left, base_right, apex = triangle_world_vertices(center_x, center_y, yaw)
    return [(base_left, apex), (apex, base_right)]


def triangle_world_vertices(center_x: float, center_y: float, yaw: float) -> tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]:
    angle = math.radians(yaw)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    local_vertices = (
        (-TRIANGLE_SIDE / 2, -TRIANGLE_BASE_OFFSET),
        (TRIANGLE_SIDE / 2, -TRIANGLE_BASE_OFFSET),
        (0.0, TRIANGLE_HEIGHT - TRIANGLE_BASE_OFFSET),
    )
    world_vertices = []
    for local_x, local_y in local_vertices:
        world_vertices.append((
            center_x + (local_x * cos_a) - (local_y * sin_a),
            center_y + (local_x * sin_a) + (local_y * cos_a),
        ))
    return world_vertices[0], world_vertices[1], world_vertices[2]


def shape_wall_role(index: int) -> str:
    return SHAPE_LAB_WALL_PATTERN[index % len(SHAPE_LAB_WALL_PATTERN)]


def generate_jumping_puzzle(
    generator: BuildingGenerator,
    width: int,
    height: int,
    seed: int,
    variant: str,
    detail_budget: str,
) -> None:
    rng = random.Random(seed)
    width = max(5, width)
    height = max(5, height)
    wall_height = 3
    entry_col = width // 2
    exit_col = width // 2

    for row in range(height):
        for col in range(width):
            generator.add_cell_surface(col, row)

    platform_cells = jumping_puzzle_platform_cells(width, height, rng, variant)
    blocked_support_edges = {
        (level, edge)
        for level in range(wall_height)
        for edge in perimeter_edges(width, height)
    }
    for col, row, level, role in platform_cells:
        generator.add_cell_surface(col, row, level=level, role=role)
        add_platform_supports(
            generator,
            col,
            row,
            level,
            role,
            blocked_edges=blocked_support_edges,
            detail_budget=detail_budget,
        )

    blocked_rail_edges: set[tuple[int, tuple[str, int, int]]] = set()
    for col, row, level, _role in platform_cells:
        for edge in cell_edges(col, row):
            blocked_rail_edges.add((level, edge))

    for level in range(wall_height):
        for edge in perimeter_edges(width, height):
            if edge == ("h", entry_col, 0) and level == 0:
                generator.add_wall_edge(edge, role="doorframe", level=level)
                continue
            if edge == ("h", exit_col, height) and level == 2:
                generator.add_wall_edge(edge, role="doorframe", level=level)
                continue
            generator.add_wall_edge(edge, role=jumping_puzzle_wall_role(edge, level), level=level)

    rail_edges = {
        (1, ("h", 1, 1)),
        (1, ("h", width - 2, 1)),
        (2, ("v", width // 2, height // 2)),
        (2, ("h", 1, height - 2)),
        (2, ("h", width - 2, height - 2)),
    }
    for level, edge in sorted(rail_edges):
        if (level, edge) in blocked_rail_edges:
            continue
        generator.add_wall_edge(edge, role="narrow_wall", level=level)


def jumping_puzzle_platform_cells(
    width: int,
    height: int,
    rng: random.Random,
    variant: str,
) -> list[tuple[int, int, int, str]]:
    if variant == "ledge_climb":
        candidates = [
            (1, 1, 1, "floor_medium"),
            (1, max(2, height // 2), 1, "floor_medium"),
            (2, height - 2, 2, "floor_small"),
            (width // 2, height - 1, 2, "floor_medium"),
            (width - 2, height - 2, 2, "floor_small"),
        ]
        return unique_platform_cells(candidates)
    if variant == "spiral_ascent":
        candidates = [
            (1, 1, 1, "floor_medium"),
            (width - 2, 1, 1, "floor_small"),
            (width - 2, height // 2, 2, "floor_medium"),
            (width - 2, height - 2, 2, "floor_small"),
            (1, height - 2, 2, "floor_medium"),
            (width // 2, height - 1, 2, "floor_medium"),
        ]
        return unique_platform_cells(candidates)
    if variant == "gap_crossing":
        candidates = [
            (1, height // 2, 1, "floor_medium"),
            (width // 2, height // 2, 1, "floor_small"),
            (width - 2, height // 2, 2, "floor_medium"),
            (width // 2, height - 1, 2, "floor_medium"),
        ]
        return unique_platform_cells(candidates)
    left_first = rng.random() < 0.5
    low_a = (1, 1) if left_first else (width - 2, 1)
    low_b = (width - 2, 1) if left_first else (1, 1)
    mid = (width // 2, height // 2)
    high_a = (1, height - 2) if left_first else (width - 2, height - 2)
    high_b = (width - 2, height - 2) if left_first else (1, height - 2)
    exit_landing = (width // 2, height - 1)
    candidates = [
        (*low_a, 1, "floor_medium"),
        (*low_b, 1, "floor_small"),
        (*mid, 2, "floor_small"),
        (*high_a, 2, "floor_medium"),
        (*high_b, 2, "floor_small"),
        (*exit_landing, 2, "floor_medium"),
    ]
    return unique_platform_cells(candidates)


def unique_platform_cells(candidates: list[tuple[int, int, int, str]]) -> list[tuple[int, int, int, str]]:
    seen: set[tuple[int, int, int]] = set()
    out = []
    for col, row, level, role in candidates:
        key = (col, row, level)
        if key in seen:
            continue
        seen.add(key)
        out.append((col, row, level, role))
    return out


def add_platform_supports(
    generator: BuildingGenerator,
    col: int,
    row: int,
    platform_level: int,
    floor_role: str,
    base_level: int = 0,
    blocked_edges: set[tuple[int, tuple[str, int, int]]] | None = None,
    detail_budget: str = "balanced",
) -> None:
    blocked_edges = blocked_edges or set()
    support_role, half_size, support_height, support_faces = platform_support_spec(generator, floor_role, detail_budget)
    center_x = col * generator.cell_size
    center_y = row * generator.cell_size
    z = base_level * generator.cell_size
    top_z = platform_level * generator.cell_size
    while z < top_z:
        if support_role == "pillar":
            generator.add_piece(support_role, x=center_x, y=center_y, z=z)
            z += support_height
            continue
        faces = (
            (center_x, center_y - half_size, 0),
            (center_x, center_y + half_size, 0),
            (center_x - half_size, center_y, 90),
            (center_x + half_size, center_y, 90),
        )
        for x, y, yaw in faces[:support_faces]:
            generator.add_piece(support_role, x=x, y=y, z=z, yaw=yaw)
        z += support_height


def platform_support_spec(generator: BuildingGenerator, floor_role: str, detail_budget: str) -> tuple[str, float, float, int]:
    if floor_role == "floor_small":
        faces = 1 if detail_budget == "low-piece-count" else 4 if detail_budget == "max-variety" else 2
        return "small_wall", generator.cell_size / 8, generator.cell_size / 4, faces
    if floor_role in {"floor_medium", "floor_medium_triangle"}:
        faces = 1 if detail_budget == "low-piece-count" else 4 if detail_budget == "max-variety" else 2
        return "narrow_wall", generator.cell_size / 4, generator.cell_size, faces
    return "pillar", 0, generator.cell_size, 1


def jumping_puzzle_wall_role(edge: tuple[str, int, int], level: int) -> str:
    return "window_wall" if level > 0 and deterministic_jump_wall_pick(edge, level) == 0 else "wall"


def deterministic_jump_wall_pick(edge: tuple[str, int, int], level: int) -> int:
    axis, a, b = edge
    axis_value = 1 if axis == "v" else 2
    return abs((level + 1) * 79 + a * 17 + b * 31 + axis_value) % 4


def generate_room_maze(
    generator: BuildingGenerator,
    room_count: int,
    branch_rate: float,
    loop_rate: float,
    elevation_rate: float,
    max_levels: int,
    irregular_room_rate: float,
    tall_room_rate: float,
    balcony_rate: float,
    window_rate: float,
    detail_budget: str,
    seed: int,
) -> RoomMazeReport:
    rng = random.Random(seed)
    build = build_room_maze_graph(
        room_count=room_count,
        branch_rate=branch_rate,
        loop_rate=loop_rate,
        elevation_rate=elevation_rate,
        max_levels=max_levels,
        rng=rng,
    )
    assign_room_templates(
        build,
        rng,
        irregular_room_rate=irregular_room_rate,
        tall_room_rate=tall_room_rate,
        balcony_rate=balcony_rate,
        window_rate=window_rate,
        detail_budget=detail_budget,
    )
    layout_room_maze(build, rng)
    room_maze_to_pieces(generator, build, detail_budget=detail_budget)
    validate_room_maze_build(build)
    return RoomMazeReport(
        rooms=len(build.rooms),
        critical_path_length=build.critical_path_length,
        branches=build.branches,
        loops=build.loops,
        levels_used=build.levels_used,
    )


def generate_room_lab(
    generator: BuildingGenerator,
    room_type: str,
    width: int,
    height: int,
    seed: int,
    detail_budget: str,
    jumping_variant: str,
) -> RoomMazeReport:
    rng = random.Random(seed)
    build = build_room_lab(room_type, width, height, rng, detail_budget, jumping_variant)
    room_maze_to_pieces(generator, build, detail_budget=detail_budget)
    validate_room_maze_build(build)
    return RoomMazeReport(
        rooms=len(build.rooms),
        critical_path_length=build.critical_path_length,
        branches=build.branches,
        loops=build.loops,
        levels_used=build.levels_used,
    )


def build_room_lab(
    room_type: str,
    width: int,
    height: int,
    rng: random.Random,
    detail_budget: str,
    jumping_variant: str,
) -> RoomMazeBuild:
    if room_type in {"stair_core", "atrium"}:
        lower = lab_room_node(0, "entry", 0, 0, 0, 4, 4, rng, detail_budget, jumping_variant)
        upper_w, upper_h = room_lab_dimensions(room_type, width, height)
        upper = lab_room_node(1, room_type, 1, lower.x_value + lower.width, lower.y_value, upper_w, upper_h, rng, detail_budget, jumping_variant)
        return RoomMazeBuild(
            rooms=[lower, upper],
            edges=[RoomGraphEdge(0, 1, vertical=True, critical=True)],
            critical_path_length=2,
            branches=0,
            loops=0,
            levels_used=2,
        )

    if room_type == "tower":
        lower = lab_room_node(0, "entry", 0, 0, 0, 4, 4, rng, detail_budget, jumping_variant)
        tower_w, tower_h = room_lab_dimensions(room_type, width, height)
        tower = lab_room_node(1, "tower", 1, lower.x_value + lower.width, lower.y_value, tower_w, tower_h, rng, detail_budget, jumping_variant)
        top = lab_room_node(2, "chamber", 2, tower.x_value + tower.width, tower.y_value, 4, 4, rng, detail_budget, jumping_variant)
        top.mask_kind = "rect"
        return RoomMazeBuild(
            rooms=[lower, tower, top],
            edges=[
                RoomGraphEdge(0, 1, vertical=True, critical=True),
                RoomGraphEdge(1, 2, vertical=True, critical=True),
            ],
            critical_path_length=3,
            branches=0,
            loops=0,
            levels_used=3,
        )

    room_w, room_h = room_lab_dimensions(room_type, width, height)
    primary = lab_room_node(0, room_type, 0, 4, 4, room_w, room_h, rng, detail_budget, jumping_variant)
    rooms = [primary]
    edges: list[RoomGraphEdge] = []
    if room_type == "crossroad":
        connector_specs = [
            (1, primary.x_value + primary.width // 2 - 1, primary.y_value + primary.height + 2),
            (2, primary.x_value + primary.width // 2 - 1, primary.y_value - 4),
            (3, primary.x_value + primary.width + 2, primary.y_value + primary.height // 2 - 1),
            (4, primary.x_value - 4, primary.y_value + primary.height // 2 - 1),
        ]
    else:
        connector_specs = [(1, primary.x_value + primary.width // 2 - 1, primary.y_value + primary.height + 2)]
    for room_id, x, y in connector_specs:
        connector = RoomNode(
            room_id=room_id,
            room_type="chamber",
            level=0,
            width=2,
            height=2,
            x=x,
            y=y,
            mask_kind="rect",
            wall_height=1,
            detail_budget=detail_budget,
            blueprint_id="lab_connector_2x2",
        )
        rooms.append(connector)
        edges.append(RoomGraphEdge(0, room_id, critical=True))
    return RoomMazeBuild(
        rooms=rooms,
        edges=edges,
        critical_path_length=max(2, len(rooms)),
        branches=max(0, len(rooms) - 2),
        loops=0,
        levels_used=1,
    )


def lab_room_node(
    room_id: int,
    room_type: str,
    level: int,
    x: int,
    y: int,
    width: int,
    height: int,
    rng: random.Random,
    detail_budget: str,
    jumping_variant: str,
) -> RoomNode:
    room = RoomNode(room_id=room_id, room_type=room_type, level=level, width=width, height=height, x=x, y=y)
    apply_room_architecture_flags(
        room,
        rng,
        irregular_room_rate=1.0,
        tall_room_rate=0.7,
        balcony_rate=0.6,
        window_rate=0.7,
        detail_budget=detail_budget,
        jumping_variant=jumping_variant,
    )
    return room


def room_lab_dimensions(room_type: str, width: int, height: int) -> tuple[int, int]:
    default_w, default_h = default_room_blueprint(room_type).width, default_room_blueprint(room_type).height
    if width == 16 and height == 16:
        return default_w, default_h
    return max(default_w, min(width, 10)), max(default_h, min(height, 10))


def default_room_blueprint(room_type: str) -> RoomBlueprint:
    blueprints = BLUEPRINTS_BY_ROOM_TYPE.get(room_type) or ()
    if not blueprints:
        raise GeneratorError(f"No room blueprints registered for room type {room_type!r}.")
    return blueprints[0]


def build_room_maze_graph(
    room_count: int,
    branch_rate: float,
    loop_rate: float,
    elevation_rate: float,
    max_levels: int,
    rng: random.Random,
) -> RoomMazeBuild:
    room_count = max(2, room_count)
    max_levels = max(1, max_levels)
    branch_count = min(room_count - 2, round(room_count * branch_rate))
    critical_path_length = max(2, room_count - branch_count)

    levels = [0 for _ in range(room_count)]
    edges: list[RoomGraphEdge] = []
    for room_id in range(1, critical_path_length):
        parent = room_id - 1
        levels[room_id] = next_room_level(levels[parent], max_levels, elevation_rate, rng)
        edges.append(RoomGraphEdge(parent, room_id, vertical=levels[room_id] != levels[parent], critical=True))

    for room_id in range(critical_path_length, room_count):
        if rng.random() < 0.75:
            parent = rng.randrange(0, critical_path_length)
        else:
            parent = rng.randrange(0, room_id)
        levels[room_id] = next_room_level(levels[parent], max_levels, elevation_rate * 0.75, rng)
        edges.append(RoomGraphEdge(parent, room_id, vertical=levels[room_id] != levels[parent]))

    existing = {normalized_edge(edge.a, edge.b) for edge in edges}
    loop_target = round(room_count * loop_rate)
    attempts = 0
    loops_added = 0
    while loops_added < loop_target and attempts < room_count * room_count:
        attempts += 1
        a, b = rng.sample(range(room_count), 2)
        if a == b or levels[a] != levels[b]:
            continue
        key = normalized_edge(a, b)
        if key in existing:
            continue
        existing.add(key)
        edges.append(RoomGraphEdge(a, b, loop=True))
        loops_added += 1

    rooms = [
        RoomNode(room_id=room_id, room_type="", level=levels[room_id], width=0, height=0)
        for room_id in range(room_count)
    ]
    return RoomMazeBuild(
        rooms=rooms,
        edges=edges,
        critical_path_length=critical_path_length,
        branches=room_count - critical_path_length,
        loops=loops_added,
        levels_used=len(set(levels)),
    )


def next_room_level(parent_level: int, max_levels: int, elevation_rate: float, rng: random.Random) -> int:
    if max_levels <= 1 or rng.random() >= elevation_rate:
        return parent_level
    if parent_level + 1 < max_levels:
        return parent_level + 1
    return parent_level


def assign_room_templates(
    build: RoomMazeBuild,
    rng: random.Random,
    irregular_room_rate: float,
    tall_room_rate: float,
    balcony_rate: float,
    window_rate: float,
    detail_budget: str,
) -> None:
    degrees = room_degrees(build.edges, len(build.rooms))
    vertical_rooms = {
        room_id
        for edge in build.edges
        if edge.vertical
        for room_id in (edge.a, edge.b)
    }
    end_room_id = build.critical_path_length - 1
    for room in build.rooms:
        if room.room_id == 0:
            room.room_type = "entry"
        elif room.room_id == end_room_id:
            room.room_type = "overlook" if room.level > 0 else "gallery"
        elif room.room_id in vertical_rooms:
            room.room_type = rng.choice(["stair_core", "tower", "atrium"])
        elif degrees[room.room_id] >= 3:
            room.room_type = "crossroad"
        elif degrees[room.room_id] == 1:
            if rng.random() < 0.3:
                room.room_type = "jumping_puzzle"
            else:
                room.room_type = "dead_end"
        elif rng.random() < 0.35:
            room.room_type = "gallery"
        elif rng.random() < 0.15:
            room.room_type = "jumping_puzzle"
        else:
            room.room_type = "chamber"
        if room.room_type == "jumping_puzzle":
            room.jumping_variant = JUMPING_PUZZLE_VARIANTS[room.room_id % len(JUMPING_PUZZLE_VARIANTS)]
        apply_room_architecture_flags(
            room,
            rng,
            irregular_room_rate,
            tall_room_rate,
            balcony_rate,
            window_rate,
            detail_budget,
            room.jumping_variant,
        )


def apply_room_architecture_flags(
    room: RoomNode,
    rng: random.Random,
    irregular_room_rate: float,
    tall_room_rate: float,
    balcony_rate: float,
    window_rate: float,
    detail_budget: str,
    jumping_variant: str,
) -> None:
    room.detail_budget = detail_budget
    room.jumping_variant = jumping_variant
    blueprint = choose_room_blueprint(room.room_type, rng, irregular_room_rate, detail_budget)
    apply_room_blueprint(room, blueprint, detail_budget, tall_room_rate, balcony_rate, window_rate, rng)


def choose_room_blueprint(
    room_type: str,
    rng: random.Random,
    irregular_room_rate: float,
    detail_budget: str,
) -> RoomBlueprint:
    choices = list(BLUEPRINTS_BY_ROOM_TYPE.get(room_type) or ())
    if not choices:
        raise GeneratorError(f"No room blueprints registered for room type {room_type!r}.")
    if detail_budget == "low-piece-count":
        choices.sort(key=lambda blueprint: (len(blueprint.features), blueprint.width * blueprint.height))
        return choices[0]
    if rng.random() > irregular_room_rate:
        simple = [
            blueprint
            for blueprint in choices
            if blueprint.mask_kind in {"rect", "cross", "u"} and "inner_room" not in blueprint.features
        ]
        if simple:
            choices = simple
    return rng.choice(choices)


def apply_room_blueprint(
    room: RoomNode,
    blueprint: RoomBlueprint,
    detail_budget: str,
    tall_room_rate: float,
    balcony_rate: float,
    window_rate: float,
    rng: random.Random,
) -> None:
    room.blueprint_id = blueprint.blueprint_id
    room.width = blueprint.width
    room.height = blueprint.height
    room.mask_kind = blueprint.mask_kind
    room.features = budgeted_blueprint_features(blueprint.features, detail_budget)
    if detail_budget == "low-piece-count":
        room.wall_height = min(blueprint.wall_height, 2)
    elif detail_budget == "max-variety":
        room.wall_height = max(blueprint.wall_height, 3 if room.room_type not in {"entry", "dead_end"} else blueprint.wall_height)
    else:
        room.wall_height = blueprint.wall_height if rng.random() < tall_room_rate or blueprint.wall_height > 1 else 1
    room.has_balcony = "balcony" in room.features or ("upper_ring" in room.features and rng.random() < balcony_rate)
    room.has_divider = "divider" in room.features
    room.has_columns = "corner_pillars" in room.features
    room.has_windows = rng.random() < max(window_rate, blueprint.window_bias)


def budgeted_blueprint_features(features: tuple[str, ...], detail_budget: str) -> tuple[str, ...]:
    if detail_budget == "max-variety":
        return features
    if detail_budget == "low-piece-count":
        expensive = {"inner_room", "corner_triangles", "diagonal_braces"}
        return tuple(feature for feature in features if feature not in expensive)
    return features


def layout_room_maze(build: RoomMazeBuild, rng: random.Random) -> None:
    build.rooms[0].x = 0
    build.rooms[0].y = 0
    tree_edges = [edge for edge in build.edges if not edge.loop]
    for edge in tree_edges:
        parent = build.rooms[edge.a]
        child = build.rooms[edge.b]
        if parent.x is None or parent.y is None:
            raise GeneratorError(f"Parent room {parent.room_id} is not placed before child {child.room_id}.")
        if child.x is not None and child.y is not None:
            continue
        place_child_room(build.rooms, parent, child, edge.vertical, rng)

    for room in build.rooms:
        if room.x is None or room.y is None:
            raise GeneratorError(f"Room {room.room_id} was not placed.")


def place_child_room(
    rooms: list[RoomNode],
    parent: RoomNode,
    child: RoomNode,
    vertical: bool,
    rng: random.Random,
) -> None:
    if vertical:
        candidates = vertical_room_candidates(parent, child)
    else:
        directions = ["east", "west", "north", "south"]
        rng.shuffle(directions)
        candidates = []
        for direction in directions:
            for distance in rng.sample([2, 3, 4, 5], 4):
                candidates.extend(room_candidates_for_direction(parent, child, direction, distance))

    for x, y in candidates:
        child.x = x
        child.y = y
        if not room_overlaps_any(child, rooms):
            return

    if vertical:
        for _x, y in vertical_room_candidates(parent, child):
            child.x = _x
            child.y = y
            if not room_overlaps_any(child, rooms):
                return
        raise GeneratorError(f"Could not place vertical room {child.room_id} next to room {parent.room_id}.")

    fallback_x = max((room.x or 0) + room.width for room in rooms if room.x is not None) + 3
    child.x = fallback_x
    child.y = parent.y
    while room_overlaps_any(child, rooms):
        child.x += child.width + 3


def vertical_room_candidates(parent: RoomNode, child: RoomNode) -> list[tuple[int, int]]:
    assert parent.x is not None and parent.y is not None
    base_x = parent.x + parent.width
    x_options = [base_x + offset for offset in range(0, 42, 2)]
    parent_rows = sorted({row for _col, row in cells_for_room(parent)}, key=lambda row: abs(row - parent.y_value))
    y_options = []
    for row in parent_rows:
        y_options.extend([
            row,
            row - 1,
            row - (child.height // 2),
            row - child.height + 1,
        ])
    valid_y = list(dict.fromkeys(y for y in y_options if y <= parent_rows[-1] and y + child.height > parent_rows[0]))
    return [(x, y) for x in x_options for y in valid_y]


def lower_stair_bay_overlaps_any(child: RoomNode, parent: RoomNode, rooms: list[RoomNode]) -> bool:
    child_rect = room_rect(child)
    lower_level = parent.level
    for other in rooms:
        if other.room_id in {child.room_id, parent.room_id} or other.x is None or other.y is None:
            continue
        if other.level != lower_level:
            continue
        if rectangles_overlap(child_rect, room_rect(other), padding=0):
            return True
    return False


def room_candidates_for_direction(
    parent: RoomNode,
    child: RoomNode,
    direction: str,
    distance: int,
) -> list[tuple[int, int]]:
    assert parent.x is not None and parent.y is not None
    y_alignments = [
        parent.y,
        parent.y + (parent.height // 2) - (child.height // 2),
        parent.y + parent.height - child.height,
    ]
    x_alignments = [
        parent.x,
        parent.x + (parent.width // 2) - (child.width // 2),
        parent.x + parent.width - child.width,
    ]
    if direction == "east":
        x = parent.x + parent.width + distance
        return [(x, y) for y in dict.fromkeys(y_alignments)]
    if direction == "west":
        x = parent.x - child.width - distance
        return [(x, y) for y in dict.fromkeys(y_alignments)]
    if direction == "north":
        y = parent.y + parent.height + distance
        return [(x, y) for x in dict.fromkeys(x_alignments)]
    if direction == "south":
        y = parent.y - child.height - distance
        return [(x, y) for x in dict.fromkeys(x_alignments)]
    raise GeneratorError(f"Unknown room placement direction: {direction}")


def room_overlaps_any(room: RoomNode, rooms: list[RoomNode]) -> bool:
    for other in rooms:
        if other.room_id == room.room_id or other.x is None or other.y is None:
            continue
        if other.level != room.level:
            continue
        if rectangles_overlap(room_rect(room), room_rect(other), padding=1):
            return True
    return False


def room_maze_to_pieces(generator: BuildingGenerator, build: RoomMazeBuild, detail_budget: str = "balanced") -> None:
    occupied: dict[int, set[tuple[int, int]]] = {}
    room_cells: dict[int, set[tuple[int, int]]] = {}
    corridor_cells: dict[int, set[tuple[int, int]]] = {}
    stair_bay_cells: dict[int, set[tuple[int, int]]] = {}
    protected_cells: dict[int, set[tuple[int, int]]] = {}
    wall_roles: dict[tuple[int, tuple[str, int, int]], str] = {}
    open_wall_edges: set[tuple[int, tuple[str, int, int]]] = set()
    connection_records: dict[tuple[int, int], list[tuple[int, tuple[str, int, int]]]] = {}
    stair_specs: list[tuple[RoomNode, RoomNode, int]] = []
    upper_stair_shaft_cells: dict[int, set[tuple[int, int]]] = {}

    for edge in build.edges:
        if not edge.vertical:
            continue
        lower, upper = vertical_edge_rooms(build.rooms, edge)
        stair_row = vertical_connection_row(lower, upper)
        upper_stair_shaft_cells.setdefault(upper.room_id, set()).update(
            vertical_stair_shaft_cells(upper, stair_row, generator)
        )
        open_wall_edges.add((upper.level, vertical_stair_top_edge(upper, stair_row, generator)))

    for room in build.rooms:
        cells = set(cells_for_room(room))
        cells -= upper_stair_shaft_cells.get(room.room_id, set())
        if not cells:
            raise GeneratorError(f"Room {room.room_id} has no floor cells after stair shaft reservation.")
        room_cells[room.room_id] = cells
        occupied.setdefault(room.level, set()).update(cells)

    for edge in build.edges:
        if edge.vertical:
            lower, upper = vertical_edge_rooms(build.rooms, edge)
            door_edges, stair_row, lower_path = vertical_door_edges(lower, upper, generator)
            bay_cells = lower_stair_bay_cells(upper, stair_row, generator)
            occupied.setdefault(lower.level, set()).update(lower_path)
            corridor_cells.setdefault(lower.level, set()).update(lower_path)
            protect_cells(protected_cells, lower.level, lower_path)
            stair_bay_cells.setdefault(lower.level, set()).update(bay_cells)
            occupied.setdefault(lower.level, set()).update(bay_cells)
            protect_cells(protected_cells, lower.level, bay_cells)
            for door in door_edges:
                if door[0] == upper.level:
                    open_wall_edges.add(door)
                else:
                    wall_roles[(door[0], door[1])] = "doorframe"
                protect_cells(protected_cells, door[0], cells_across_edge(door[1]))
            stair_specs.append((lower, upper, stair_row))
            connection_records[normalized_edge(edge.a, edge.b)] = door_edges
            continue

        room_a = build.rooms[edge.a]
        room_b = build.rooms[edge.b]
        path, door_edges = horizontal_corridor(room_a, room_b)
        occupied.setdefault(room_a.level, set()).update(path)
        corridor_cells.setdefault(room_a.level, set()).update(path)
        protect_cells(protected_cells, room_a.level, path)
        for door in door_edges:
            wall_roles[(door[0], door[1])] = "doorframe"
            protect_cells(protected_cells, door[0], cells_across_edge(door[1]))
        connection_records[normalized_edge(edge.a, edge.b)] = door_edges

    validate_room_connections(build, connection_records)
    validate_doorframes_open_to_floor(connection_records, occupied)

    for level in sorted(occupied):
        for col, row in sorted(occupied[level]):
            generator.add_cell_surface(col, row, level=level)

    for room in build.rooms:
        for height_index in range(room.wall_height):
            for edge in perimeter_edges_for_cells(room_cells[room.room_id]):
                key = (room.level + height_index, edge)
                if key in open_wall_edges:
                    continue
                wall_roles.setdefault(key, room_wall_role(room, edge, height_index))

    for level, cells in stair_bay_cells.items():
        for col, row in cells:
            for edge in cell_edges(col, row):
                neighbor = cell_neighbor_across_edge(edge, col, row)
                if neighbor not in occupied.get(level, set()):
                    wall_roles.setdefault((level, edge), "wall")

    for level, cells in corridor_cells.items():
        for col, row in cells:
            for edge in cell_edges(col, row):
                neighbor = cell_neighbor_across_edge(edge, col, row)
                if neighbor not in occupied.get(level, set()):
                    wall_roles.setdefault((level, edge), "wall")

    for level, edge in sorted(wall_roles):
        if (level, edge) in open_wall_edges:
            continue
        generator.add_wall_edge(edge, role=wall_roles[(level, edge)], level=level)

    blocked_feature_edges = set(wall_roles) | open_wall_edges
    emit_room_architecture_features(generator, build, blocked_feature_edges, protected_cells, detail_budget)

    for lower, upper, stair_row in stair_specs:
        add_vertical_stairs(generator, lower, upper, stair_row)


def horizontal_corridor(room_a: RoomNode, room_b: RoomNode) -> tuple[set[tuple[int, int]], list[tuple[int, tuple[str, int, int]]]]:
    if room_a.level != room_b.level:
        raise GeneratorError("Horizontal corridor requested for rooms on different levels.")
    side_a, side_b = connection_sides(room_a, room_b)
    inside_a, outside_a, edge_a = doorway_for_side(room_a, side_a)
    inside_b, outside_b, edge_b = doorway_for_side(room_b, side_b)
    path = manhattan_path(outside_a, outside_b)
    path.discard(inside_a)
    path.discard(inside_b)
    return path, [(room_a.level, edge_a), (room_b.level, edge_b)]


def vertical_door_edges(
    lower: RoomNode,
    upper: RoomNode,
    generator: BuildingGenerator,
) -> tuple[list[tuple[int, tuple[str, int, int]]], int, set[tuple[int, int]]]:
    if upper.level != lower.level + 1:
        raise GeneratorError("Vertical room-maze connections currently require exactly one level of rise.")
    stair_row = vertical_connection_row(lower, upper)
    _inside_lower, outside_lower, lower_edge = doorway_for_side(lower, "east", row_offset=stair_row - lower.y_value)
    lower_path = manhattan_path(outside_lower, (upper.x_value, stair_row))
    upper_internal_edge = vertical_upper_landing_edge(upper, stair_row, generator)
    return [(lower.level, lower_edge), (upper.level, upper_internal_edge)], stair_row, lower_path


def add_vertical_stairs(generator: BuildingGenerator, lower: RoomNode, upper: RoomNode, stair_row: int) -> None:
    if upper.x is None or upper.y is None:
        raise GeneratorError("Upper room is missing placement for stairs.")
    stairs_needed = max(1, round(generator.cell_size / generator.stair_rise))
    start_x = upper.x * generator.cell_size
    stair_y = stair_row * generator.cell_size
    for stair_index in range(stairs_needed):
        stair_x = start_x + (stair_index * generator.stair_run) + STRAIGHT_STAIR_ALIGNMENT_OFFSET_X
        stair_z = (
            (lower.level * generator.cell_size)
            + (stair_index * generator.stair_rise)
            + STRAIGHT_STAIR_ALIGNMENT_OFFSET_Z
        )
        validate_stair_root_inside_room(stair_x, stair_y, upper, generator)
        generator.add_piece("stairs", stair_x, stair_y, stair_z, yaw=STRAIGHT_STAIR_YAW)


def vertical_stair_segment_count(generator: BuildingGenerator) -> int:
    return max(1, round(generator.cell_size / generator.stair_rise))


def vertical_stair_shaft_cells(upper: RoomNode, stair_row: int, generator: BuildingGenerator) -> set[tuple[int, int]]:
    stairs_needed = vertical_stair_segment_count(generator)
    room_cells = set(cells_for_room(upper))
    shaft = {(upper.x_value + offset, stair_row) for offset in range(max(0, stairs_needed - 1))}
    if not shaft <= room_cells:
        raise GeneratorError(f"Room {upper.room_id} cannot fit an internal stair shaft.")
    landing = vertical_stair_landing_cell(upper, stair_row, generator)
    if landing not in room_cells:
        raise GeneratorError(f"Room {upper.room_id} cannot fit an upper stair landing.")
    return shaft


def vertical_stair_landing_cell(upper: RoomNode, stair_row: int, generator: BuildingGenerator) -> tuple[int, int]:
    return upper.x_value + max(0, vertical_stair_segment_count(generator) - 1), stair_row


def vertical_stair_top_edge(upper: RoomNode, stair_row: int, generator: BuildingGenerator) -> tuple[str, int, int]:
    landing_col, landing_row = vertical_stair_landing_cell(upper, stair_row, generator)
    return ("v", landing_col, landing_row)


def vertical_upper_landing_edge(
    upper: RoomNode,
    stair_row: int,
    generator: BuildingGenerator,
) -> tuple[str, int, int]:
    landing_col, landing_row = vertical_stair_landing_cell(upper, stair_row, generator)
    interior_cell = (landing_col + 1, landing_row)
    if interior_cell not in set(cells_for_room(upper)):
        raise GeneratorError(f"Room {upper.room_id} needs one interior cell beyond the upper stair landing.")
    return ("v", landing_col + 1, landing_row)


def vertical_connection_row(lower: RoomNode, upper: RoomNode) -> int:
    lower_rows = {row for _col, row in cells_for_room(lower)}
    upper_rows = {row for _col, row in cells_for_room(upper)}
    overlap = sorted(lower_rows & upper_rows)
    if not overlap:
        raise GeneratorError(f"Vertical rooms {lower.room_id}-{upper.room_id} do not overlap in Y for stairs.")
    preferred = lower.y_value + min(1, lower.height - 1)
    return min(overlap, key=lambda row: abs(row - preferred))


def lower_stair_bay_cells(upper: RoomNode, stair_row: int, generator: BuildingGenerator) -> set[tuple[int, int]]:
    stairs_needed = vertical_stair_segment_count(generator)
    width = min(upper.width, stairs_needed + 2)
    rows = [stair_row]
    if stair_row + 1 < upper.y_value + upper.height:
        rows.append(stair_row + 1)
    elif stair_row - 1 >= upper.y_value:
        rows.append(stair_row - 1)
    cells = {
        (upper.x_value + offset, row)
        for offset in range(width)
        for row in rows
    }
    room_cells = set(cells_for_room(upper))
    cells &= room_cells
    if len({cell for cell in cells if cell[1] == stair_row}) < stairs_needed + 1:
        raise GeneratorError(f"Upper room {upper.room_id} has no internal space for a stair bay.")
    return cells


def validate_stair_root_inside_room(stair_x: float, stair_y: float, room: RoomNode, generator: BuildingGenerator) -> None:
    adjusted_x = (stair_x - STRAIGHT_STAIR_ALIGNMENT_OFFSET_X) / generator.cell_size
    adjusted_y = stair_y / generator.cell_size
    cell = (int(adjusted_x), int(adjusted_y))
    if cell not in set(cells_for_room(room)):
        raise GeneratorError(f"Generated stair root for room {room.room_id} is outside the room footprint.")


def connection_sides(room_a: RoomNode, room_b: RoomNode) -> tuple[str, str]:
    ax, ay = room_center(room_a)
    bx, by = room_center(room_b)
    dx = bx - ax
    dy = by - ay
    if abs(dx) >= abs(dy):
        return ("east", "west") if dx >= 0 else ("west", "east")
    return ("north", "south") if dy >= 0 else ("south", "north")


def doorway_for_side(
    room: RoomNode,
    side: str,
    row_offset: int | None = None,
) -> tuple[tuple[int, int], tuple[int, int], tuple[str, int, int]]:
    cells = set(cells_for_room(room))
    if not cells:
        raise GeneratorError(f"Room {room.room_id} has no floor cells.")
    min_x = min(col for col, _row in cells)
    max_x = max(col for col, _row in cells)
    min_y = min(row for _col, row in cells)
    max_y = max(row for _col, row in cells)
    preferred_row = room.y_value + (row_offset if row_offset is not None else room.height // 2)
    preferred_col = room.x_value + room.width // 2
    if side == "east":
        candidates = sorted(
            (cell for cell in cells if cell[0] == max_x or (cell[0] + 1, cell[1]) not in cells),
            key=lambda cell: (abs(cell[1] - preferred_row), -cell[0]),
        )
        inside = candidates[0]
        outside = (inside[0] + 1, inside[1])
        return inside, outside, ("v", inside[0] + 1, inside[1])
    if side == "west":
        candidates = sorted(
            (cell for cell in cells if cell[0] == min_x or (cell[0] - 1, cell[1]) not in cells),
            key=lambda cell: (abs(cell[1] - preferred_row), cell[0]),
        )
        inside = candidates[0]
        outside = (inside[0] - 1, inside[1])
        return inside, outside, ("v", inside[0], inside[1])
    if side == "north":
        candidates = sorted(
            (cell for cell in cells if cell[1] == max_y or (cell[0], cell[1] + 1) not in cells),
            key=lambda cell: (abs(cell[0] - preferred_col), -cell[1]),
        )
        inside = candidates[0]
        outside = (inside[0], inside[1] + 1)
        return inside, outside, ("h", inside[0], inside[1] + 1)
    if side == "south":
        candidates = sorted(
            (cell for cell in cells if cell[1] == min_y or (cell[0], cell[1] - 1) not in cells),
            key=lambda cell: (abs(cell[0] - preferred_col), cell[1]),
        )
        inside = candidates[0]
        outside = (inside[0], inside[1] - 1)
        return inside, outside, ("h", inside[0], inside[1])
    raise GeneratorError(f"Unknown doorway side: {side}")


def manhattan_path(start: tuple[int, int], end: tuple[int, int]) -> set[tuple[int, int]]:
    x, y = start
    out = {(x, y)}
    step_x = 1 if end[0] >= x else -1
    while x != end[0]:
        x += step_x
        out.add((x, y))
    step_y = 1 if end[1] >= y else -1
    while y != end[1]:
        y += step_y
        out.add((x, y))
    return out


def validate_room_maze_build(build: RoomMazeBuild) -> None:
    validate_graph_connected(build)
    validate_room_footprints(build.rooms)


def validate_graph_connected(build: RoomMazeBuild) -> None:
    adjacency = {room.room_id: set() for room in build.rooms}
    for edge in build.edges:
        adjacency[edge.a].add(edge.b)
        adjacency[edge.b].add(edge.a)
    seen = {0}
    stack = [0]
    while stack:
        current = stack.pop()
        for neighbor in adjacency[current]:
            if neighbor in seen:
                continue
            seen.add(neighbor)
            stack.append(neighbor)
    if len(seen) != len(build.rooms):
        raise GeneratorError("Room graph is not fully connected.")
    end_room = build.critical_path_length - 1
    if end_room not in seen:
        raise GeneratorError("Critical path end is not reachable from the entry room.")


def validate_room_footprints(rooms: list[RoomNode]) -> None:
    for index, room in enumerate(rooms):
        for other in rooms[index + 1:]:
            if room.level == other.level and rectangles_overlap(room_rect(room), room_rect(other), padding=0):
                raise GeneratorError(f"Room footprints overlap: {room.room_id} and {other.room_id}.")


def validate_room_connections(
    build: RoomMazeBuild,
    connection_records: dict[tuple[int, int], list[tuple[int, tuple[str, int, int]]]],
) -> None:
    for edge in build.edges:
        key = normalized_edge(edge.a, edge.b)
        records = connection_records.get(key) or []
        if len(records) < 2:
            raise GeneratorError(f"Graph edge {edge.a}-{edge.b} has no physical connection.")
        if edge.vertical and {level for level, _edge in records} != {build.rooms[edge.a].level, build.rooms[edge.b].level}:
            raise GeneratorError(f"Vertical edge {edge.a}-{edge.b} does not reserve openings on both levels.")


def validate_doorframes_open_to_floor(
    connection_records: dict[tuple[int, int], list[tuple[int, tuple[str, int, int]]]],
    occupied: dict[int, set[tuple[int, int]]],
) -> None:
    for records in connection_records.values():
        for level, edge in records:
            a, b = cells_across_edge(edge)
            if a not in occupied.get(level, set()) or b not in occupied.get(level, set()):
                raise GeneratorError(f"Doorframe at level {level}, edge {edge} opens into empty space.")


def cells_for_room(room: RoomNode) -> list[tuple[int, int]]:
    cells = set(rectangle_cells(room.x_value, room.y_value, room.width, room.height))
    if room.mask_kind == "rect" or room.width < 4 or room.height < 4:
        return sorted(cells)

    corner_width = max(1, room.width // 2)
    corner_height = max(1, room.height // 2)
    orientation = room.room_id % 4
    if room.mask_kind == "l":
        cells -= corner_cells(room, orientation, corner_width, corner_height)
    elif room.mask_kind == "t":
        cells -= corner_cells(room, 0, corner_width, corner_height)
        cells -= corner_cells(room, 1, corner_width, corner_height)
    elif room.mask_kind == "u":
        notch_width = max(1, room.width // 3)
        notch_x = room.x_value + (room.width - notch_width) // 2
        notch_height = max(1, room.height // 2)
        for col in range(notch_x, notch_x + notch_width):
            for row in range(room.y_value + room.height - notch_height, room.y_value + room.height):
                cells.discard((col, row))
    elif room.mask_kind == "cross":
        center_col = room.x_value + room.width // 2
        center_row = room.y_value + room.height // 2
        cells = {
            (col, row)
            for col, row in cells
            if abs(col - center_col) <= 1 or abs(row - center_row) <= 1
        }
    elif room.mask_kind == "chamfered":
        if room.width >= 5 and room.height >= 5:
            cells -= {
                (room.x_value, room.y_value),
                (room.x_value + room.width - 1, room.y_value),
                (room.x_value, room.y_value + room.height - 1),
                (room.x_value + room.width - 1, room.y_value + room.height - 1),
            }
    elif room.mask_kind == "split":
        return sorted(cells)
    if not cells:
        return rectangle_cells(room.x_value, room.y_value, room.width, room.height)
    return sorted(cells)


def rectangle_cells(x: int, y: int, width: int, height: int) -> list[tuple[int, int]]:
    return [(col, row) for row in range(y, y + height) for col in range(x, x + width)]


def corner_cells(room: RoomNode, orientation: int, width: int, height: int) -> set[tuple[int, int]]:
    west = range(room.x_value, room.x_value + width)
    east = range(room.x_value + room.width - width, room.x_value + room.width)
    south = range(room.y_value, room.y_value + height)
    north = range(room.y_value + room.height - height, room.y_value + room.height)
    if orientation == 0:
        return {(col, row) for col in east for row in north}
    if orientation == 1:
        return {(col, row) for col in west for row in north}
    if orientation == 2:
        return {(col, row) for col in east for row in south}
    return {(col, row) for col in west for row in south}


def room_perimeter_edges(room: RoomNode) -> list[tuple[str, int, int]]:
    edges = []
    cells = set(cells_for_room(room))
    for col, row in cells:
        if (col - 1, row) not in cells:
            edges.append(("v", col, row))
        if (col + 1, row) not in cells:
            edges.append(("v", col + 1, row))
        if (col, row - 1) not in cells:
            edges.append(("h", col, row))
        if (col, row + 1) not in cells:
            edges.append(("h", col, row + 1))
    return edges


def perimeter_edges_for_cells(cells: set[tuple[int, int]]) -> list[tuple[str, int, int]]:
    edges = []
    for col, row in cells:
        if (col - 1, row) not in cells:
            edges.append(("v", col, row))
        if (col + 1, row) not in cells:
            edges.append(("v", col + 1, row))
        if (col, row - 1) not in cells:
            edges.append(("h", col, row))
        if (col, row + 1) not in cells:
            edges.append(("h", col, row + 1))
    return edges


def room_wall_role(room: RoomNode, edge: tuple[str, int, int], height_index: int) -> str:
    if height_index > 0:
        return "window_wall" if room.has_windows and height_index == 1 and deterministic_edge_pick(room, edge, 5) == 0 else "wall"
    if room.has_windows and room_edge_is_outer(room, edge) and deterministic_edge_pick(room, edge, 3) == 0:
        return "double_window_wall" if deterministic_edge_pick(room, edge, 2) == 0 else "window_wall"
    return "wall"


def room_edge_is_outer(room: RoomNode, edge: tuple[str, int, int]) -> bool:
    axis, a, b = edge
    if axis == "v":
        return a in {room.x_value, room.x_value + room.width}
    return b in {room.y_value, room.y_value + room.height}


def deterministic_edge_pick(room: RoomNode, edge: tuple[str, int, int], modulo: int) -> int:
    axis, a, b = edge
    axis_value = 1 if axis == "v" else 2
    return abs((room.room_id + 1) * 131 + a * 17 + b * 31 + axis_value) % modulo


def room_cell_bounds(room: RoomNode) -> tuple[int, int, int, int]:
    cells = set(cells_for_room(room))
    if not cells:
        raise GeneratorError(f"Room {room.room_id} has no floor cells.")
    return (
        min(col for col, _row in cells),
        min(row for _col, row in cells),
        max(col for col, _row in cells),
        max(row for _col, row in cells),
    )


def protect_cells(
    protected_cells: dict[int, set[tuple[int, int]]],
    level: int,
    cells: set[tuple[int, int]] | tuple[tuple[int, int], ...],
) -> None:
    protected_cells.setdefault(level, set()).update(cells)


def room_protected_cells(
    room: RoomNode,
    protected_cells: dict[int, set[tuple[int, int]]],
    feature_level: int | None = None,
) -> set[tuple[int, int]]:
    out = set(protected_cells.get(room.level, set()))
    if feature_level is not None:
        out.update(protected_cells.get(feature_level, set()))
    return out


def cell_is_protected(
    room: RoomNode,
    protected_cells: dict[int, set[tuple[int, int]]],
    col: int,
    row: int,
    feature_level: int | None = None,
) -> bool:
    return (col, row) in room_protected_cells(room, protected_cells, feature_level)


def emit_room_architecture_features(
    generator: BuildingGenerator,
    build: RoomMazeBuild,
    blocked_edges: set[tuple[int, tuple[str, int, int]]] | None = None,
    protected_cells: dict[int, set[tuple[int, int]]] | None = None,
    detail_budget: str = "balanced",
) -> None:
    blocked_edges = blocked_edges or set()
    protected_cells = protected_cells or {}
    for room in build.rooms:
        room.detail_budget = room.detail_budget or detail_budget
        if room.room_type == "entry":
            emit_entry_room(generator, room, blocked_edges, protected_cells)
        elif room.room_type == "chamber":
            emit_chamber_room(generator, room, blocked_edges, protected_cells)
        elif room.room_type == "gallery":
            emit_gallery_room(generator, room, blocked_edges, protected_cells)
        elif room.room_type == "crossroad":
            emit_crossroad_room(generator, room, blocked_edges, protected_cells)
        elif room.room_type == "dead_end":
            emit_dead_end_room(generator, room, blocked_edges, protected_cells)
        elif room.room_type == "overlook":
            emit_overlook_room(generator, room, blocked_edges, protected_cells)
        elif room.room_type == "stair_core":
            emit_stair_core_room(generator, room, blocked_edges, protected_cells)
        elif room.room_type == "tower":
            emit_tower_room(generator, room, blocked_edges, protected_cells)
        elif room.room_type == "atrium":
            emit_atrium_room(generator, room, blocked_edges, protected_cells)
        elif room.room_type == "jumping_puzzle":
            emit_jumping_puzzle_room(generator, room, blocked_edges, protected_cells)


def emit_entry_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    if room_has_feature(room, "corner_pillars"):
        emit_corner_pillars(generator, room, blocked_edges, protected_cells, max_count=2)
    if room_has_feature(room, "diagonal_braces"):
        emit_diagonal_corner_braces(generator, room, blocked_edges, max_count=2)


def emit_chamber_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    if room_has_feature(room, "diagonal_braces"):
        emit_diagonal_corner_braces(generator, room, blocked_edges)
    if room_has_feature(room, "back_stage"):
        emit_back_stage(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "loft"):
        emit_loft_room(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "inner_room"):
        emit_inner_partition_room(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "side_walkway"):
        emit_side_walkway(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "balcony"):
        emit_room_balcony(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "divider"):
        emit_room_divider(generator, room, blocked_edges, protected_cells)


def emit_gallery_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    if room_has_feature(room, "side_walkway"):
        emit_side_walkway(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "corner_triangles"):
        emit_corner_triangle_platforms(generator, room, blocked_edges, max_count=2)
    if room_has_feature(room, "diagonal_braces"):
        emit_diagonal_corner_braces(generator, room, blocked_edges, max_count=2)


def emit_crossroad_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    if room_has_feature(room, "corner_pillars"):
        emit_corner_pillars(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "corner_triangles"):
        emit_corner_triangle_platforms(generator, room, blocked_edges, max_count=2)
    if room_has_feature(room, "diagonal_braces"):
        emit_diagonal_corner_braces(generator, room, blocked_edges)


def emit_dead_end_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    if room_has_feature(room, "back_stage"):
        emit_back_stage(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "diagonal_braces"):
        emit_diagonal_corner_braces(generator, room, blocked_edges, max_count=2)


def emit_overlook_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    if room_has_feature(room, "balcony"):
        emit_room_balcony(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "corner_triangles"):
        emit_corner_triangle_platforms(generator, room, blocked_edges, max_count=2)
    if room_has_feature(room, "diagonal_braces"):
        emit_diagonal_corner_braces(generator, room, blocked_edges, max_count=2)


def emit_stair_core_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    if room_has_feature(room, "diagonal_braces"):
        emit_diagonal_corner_braces(generator, room, blocked_edges, max_count=2)


def emit_tower_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    if room_has_feature(room, "corner_pillars"):
        emit_corner_pillars(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "corner_triangles"):
        emit_corner_triangle_platforms(generator, room, blocked_edges, max_count=2)
    if room_has_feature(room, "divider"):
        emit_room_divider(generator, room, blocked_edges, protected_cells)


def emit_atrium_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    if room_has_feature(room, "upper_ring"):
        emit_upper_ring(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "corner_pillars"):
        emit_corner_pillars(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "inner_room"):
        emit_inner_partition_room(generator, room, blocked_edges, protected_cells)
    if room_has_feature(room, "diagonal_braces"):
        emit_diagonal_corner_braces(generator, room, blocked_edges)


def room_has_feature(room: RoomNode, feature: str) -> bool:
    return feature in room.features


def emit_back_stage(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
    include_triangles: bool = False,
) -> None:
    cells = set(cells_for_room(room))
    min_x, min_y, max_x, max_y = room_cell_bounds(room)
    stage_rows = [max_y]
    if room.height >= 6:
        stage_rows.insert(0, max_y - 1)
    stage_cells = {
        (col, row)
        for row in stage_rows
        for col in range(min_x + 1, max_x)
        if (col, row) in cells
    }
    emit_room_platform_cells(
        generator,
        room,
        stage_cells,
        room.level + 1,
        "floor",
        blocked_edges,
        protected_cells,
        rail_role="narrow_wall",
    )


def emit_loft_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    cells = set(cells_for_room(room))
    min_x, min_y, max_x, max_y = room_cell_bounds(room)
    loft_rows = {max_y - 1, max_y}
    loft_cells = {
        (col, row)
        for row in loft_rows
        for col in range(min_x + 1, max_x)
        if (col, row) in cells
    }
    emit_room_platform_cells(
        generator,
        room,
        loft_cells,
        room.level + 1,
        "floor",
        blocked_edges,
        protected_cells,
        rail_role="narrow_wall",
    )
    stair_col = min_x + 1
    stair_row = max_y - 2
    if (stair_col, stair_row) in cells and not cell_is_protected(room, protected_cells, stair_col, stair_row):
        generator.add_piece(
            "stairs",
            x=(stair_col * generator.cell_size) + STRAIGHT_STAIR_ALIGNMENT_OFFSET_X,
            y=stair_row * generator.cell_size,
            z=(room.level * generator.cell_size) + STRAIGHT_STAIR_ALIGNMENT_OFFSET_Z,
            yaw=STRAIGHT_STAIR_YAW,
        )


def emit_side_walkway(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    cells = set(cells_for_room(room))
    min_x, min_y, max_x, max_y = room_cell_bounds(room)
    if (max_x - min_x) >= (max_y - min_y):
        row = min_y + 1
        walkway = {(col, row) for col in range(min_x + 1, max_x) if (col, row) in cells}
    else:
        col = min_x + 1
        walkway = {(col, row) for row in range(min_y + 1, max_y) if (col, row) in cells}
    emit_room_platform_cells(
        generator,
        room,
        walkway,
        room.level + 1,
        "floor",
        blocked_edges,
        protected_cells,
        rail_role="narrow_wall",
    )


def emit_upper_ring(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    cells = set(cells_for_room(room))
    min_x, min_y, max_x, max_y = room_cell_bounds(room)
    if max_x - min_x < 4 or max_y - min_y < 4:
        emit_room_balcony(generator, room, blocked_edges, protected_cells)
        return
    ring = {
        (col, row)
        for col, row in cells
        if col in {min_x + 1, max_x - 1} or row in {min_y + 1, max_y - 1}
    }
    center_clear = {
        (col, row)
        for col in range(min_x + 2, max_x - 1)
        for row in range(min_y + 2, max_y - 1)
    }
    ring -= center_clear
    emit_room_platform_cells(
        generator,
        room,
        ring,
        room.level + 1,
        "floor",
        blocked_edges,
        protected_cells,
        rail_role="narrow_wall",
    )


def emit_inner_partition_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
) -> None:
    if room.width < 6 or room.height < 5:
        return
    cells = set(cells_for_room(room))
    min_x, min_y, max_x, max_y = room_cell_bounds(room)
    inner_width = 3 if room.width >= 7 else 2
    inner_height = 2
    inner_x = min_x + 1
    inner_y = min_y + 1
    if room.room_id % 2:
        inner_x = max_x - inner_width
    inner_cells = {
        (col, row)
        for col in range(inner_x, inner_x + inner_width)
        for row in range(inner_y, inner_y + inner_height)
    }
    if not inner_cells <= cells:
        return
    if inner_cells & room_protected_cells(room, protected_cells):
        return
    door_edge = ("h", inner_x + inner_width // 2, inner_y + inner_height)
    for edge in perimeter_edges_for_cells(inner_cells):
        if feature_edge_blocked(edge, room.level, blocked_edges):
            continue
        role = "narrow_doorframe" if edge == door_edge else "narrow_wall"
        generator.add_wall_edge(edge, role=role, level=room.level)


def emit_corner_triangle_platforms(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    max_count: int = 4,
) -> None:
    return
    cells = set(cells_for_room(room))
    min_x, min_y, max_x, max_y = room_cell_bounds(room)
    candidates = [
        (min_x + 1, min_y + 1, 0),
        (max_x - 1, min_y + 1, 90),
        (max_x - 1, max_y - 1, 180),
        (min_x + 1, max_y - 1, 270),
    ]
    added = 0
    for col, row, yaw in candidates:
        if added >= max_count:
            break
        if (col, row) not in cells:
            continue
        add_room_feature_platform(generator, room, col, row, room.level + 1, "floor_triangle", blocked_edges, yaw=yaw)
        added += 1


def emit_diagonal_corner_braces(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    max_count: int = 4,
) -> None:
    cells = set(cells_for_room(room))
    min_x, min_y, max_x, max_y = room_cell_bounds(room)
    candidates = [
        (min_x, min_y, 45),
        (max_x, min_y, 135),
        (max_x, max_y, 225),
        (min_x, max_y, 315),
    ]
    role = "wall_large_diagonal" if room.width >= 6 or room.height >= 6 else "wall_medium_diagonal"
    z = room.level * generator.cell_size
    added = 0
    for col, row, yaw in candidates:
        if added >= max_count:
            break
        adjacent = (
            (col, row) in cells
            or (col + (1 if col == min_x else -1), row) in cells
            or (col, row + (1 if row == min_y else -1)) in cells
        )
        if not adjacent:
            continue
        x = col * generator.cell_size
        y = row * generator.cell_size
        generator.add_piece(role, x=x, y=y, z=z, yaw=yaw)
        if room.wall_height >= 3 and room.detail_budget == "max-variety":
            generator.add_piece("wall_large_diagonal_inverted", x=x, y=y, z=z + generator.cell_size, yaw=yaw)
        added += 1


def emit_corner_pillars(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]] | None = None,
    max_count: int = 4,
) -> None:
    protected_cells = protected_cells or {}
    cells = set(cells_for_room(room))
    min_x, min_y, max_x, max_y = room_cell_bounds(room)
    candidates = [
        (min_x + 1, min_y + 1),
        (max_x - 1, min_y + 1),
        (max_x - 1, max_y - 1),
        (min_x + 1, max_y - 1),
    ]
    added = 0
    for col, row in candidates:
        if added >= max_count:
            break
        if (col, row) not in cells:
            continue
        if cell_is_protected(room, protected_cells, col, row):
            continue
        if any(feature_edge_blocked(edge, room.level, blocked_edges) for edge in cell_edges(col, row)):
            continue
        generator.add_piece("pillar", col * generator.cell_size, row * generator.cell_size, room.level * generator.cell_size)
        added += 1


def add_room_feature_platform(
    generator: BuildingGenerator,
    room: RoomNode,
    col: int,
    row: int,
    level: int,
    role: str,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]] | None = None,
    yaw: float = 0,
) -> None:
    protected_cells = protected_cells or {}
    if (col, row) not in set(cells_for_room(room)):
        return
    if cell_is_protected(room, protected_cells, col, row, level):
        return
    if "triangle" in role:
        generator.add_cell_triangle_surface(col, row, level=level, role=role, yaw=yaw)
    else:
        generator.add_cell_surface(col, row, level=level, role=role)
    add_platform_supports(
        generator,
        col,
        row,
        level,
        role,
        base_level=room.level,
        blocked_edges=blocked_edges,
        detail_budget=room.detail_budget,
    )


def emit_room_platform_cells(
    generator: BuildingGenerator,
    room: RoomNode,
    cells: set[tuple[int, int]],
    level: int,
    role: str,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
    rail_role: str | None = None,
) -> None:
    room_cells = set(cells_for_room(room))
    valid = sorted((cells & room_cells) - room_protected_cells(room, protected_cells, level))
    if not valid:
        return
    for col, row in valid:
        generator.add_cell_surface(col, row, level=level, role=role)
    support_stride = 4 if room.detail_budget == "low-piece-count" else 2 if room.detail_budget == "max-variety" else 3
    for index, (col, row) in enumerate(valid):
        if index not in {0, len(valid) - 1} and index % support_stride:
            continue
        add_platform_supports(
            generator,
            col,
            row,
            level,
            role,
            base_level=room.level,
            blocked_edges=blocked_edges,
            detail_budget=room.detail_budget,
        )
    if rail_role:
        emit_platform_rails(generator, valid, level, blocked_edges, protected_cells, rail_role)


def emit_platform_rails(
    generator: BuildingGenerator,
    cells: list[tuple[int, int]],
    level: int,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
    protected_cells: dict[int, set[tuple[int, int]]],
    role: str,
) -> None:
    cell_set = set(cells)
    for edge in perimeter_edges_for_cells(cell_set):
        a, b = cells_across_edge(edge)
        if a in cell_set and b in cell_set:
            continue
        if a in protected_cells.get(level, set()) or b in protected_cells.get(level, set()):
            continue
        if feature_edge_blocked(edge, level, blocked_edges):
            continue
        generator.add_wall_edge(edge, role=role, level=level)


def emit_jumping_puzzle_room(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]] | None = None,
    protected_cells: dict[int, set[tuple[int, int]]] | None = None,
) -> None:
    blocked_edges = blocked_edges or set()
    protected_cells = protected_cells or {}
    cells = set(cells_for_room(room))
    if room.width < 5 or room.height < 5:
        return
    rng = random.Random((room.room_id + 1) * 1009 + len(room.jumping_variant) * 37)
    candidates = [
        (room.x_value + col, room.y_value + row, room.level + level, role)
        for col, row, level, role in jumping_puzzle_platform_cells(room.width, room.height, rng, room.jumping_variant)
    ]
    used: set[tuple[int, int, int]] = set()
    for col, row, level, role in candidates:
        if (col, row) not in cells or (col, row, level) in used:
            continue
        used.add((col, row, level))
        generator.add_cell_surface(col, row, level=level, role=role)
        add_platform_supports(
            generator,
            col,
            row,
            level,
            role,
            base_level=room.level,
            blocked_edges=blocked_edges,
            detail_budget=room.detail_budget,
        )

    rail_edges = [
        ("h", room.x_value + 1, room.y_value + 1),
        ("v", room.x_value + room.width - 1, room.y_value + 1),
        ("h", room.x_value + room.width - 2, room.y_value + room.height - 1),
    ]
    for edge in rail_edges:
        a, b = cells_across_edge(edge)
        if a in protected_cells.get(room.level + 1, set()) or b in protected_cells.get(room.level + 1, set()):
            continue
        if feature_edge_blocked(edge, room.level + 1, blocked_edges):
            continue
        generator.add_wall_edge(edge, role="narrow_wall", level=room.level + 1)


def emit_room_balcony(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]] | None = None,
    protected_cells: dict[int, set[tuple[int, int]]] | None = None,
) -> None:
    blocked_edges = blocked_edges or set()
    protected_cells = protected_cells or {}
    cells = balcony_cells(room)
    if not cells:
        return
    emit_room_platform_cells(
        generator,
        room,
        cells,
        room.level + 1,
        "floor",
        blocked_edges,
        protected_cells,
        rail_role="narrow_wall",
    )


def balcony_cells(room: RoomNode) -> set[tuple[int, int]]:
    base = set(cells_for_room(room))
    if room.width < 4 or room.height < 4:
        return set()
    row = room.y_value + room.height - 1
    cells = {(col, row) for col in range(room.x_value + 1, room.x_value + room.width - 1)}
    cells &= base
    if len(cells) < 2:
        return set()
    return cells


def emit_room_divider(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]] | None = None,
    protected_cells: dict[int, set[tuple[int, int]]] | None = None,
) -> None:
    blocked_edges = blocked_edges or set()
    protected_cells = protected_cells or {}
    cells = set(cells_for_room(room))
    if room.width < 4 or room.height < 3:
        return
    if room.width >= room.height:
        col = room.x_value + room.width // 2
        rows = [row for row in range(room.y_value + 1, room.y_value + room.height - 1) if (col - 1, row) in cells and (col, row) in cells]
        gap = rows[len(rows) // 2] if rows else None
        for row in rows:
            if row == gap:
                continue
            if cell_is_protected(room, protected_cells, col - 1, row) or cell_is_protected(room, protected_cells, col, row):
                continue
            edge = ("v", col, row)
            if feature_edge_blocked(edge, room.level, blocked_edges):
                continue
            generator.add_wall_edge(edge, role="narrow_wall", level=room.level)
    else:
        row = room.y_value + room.height // 2
        cols = [col for col in range(room.x_value + 1, room.x_value + room.width - 1) if (col, row - 1) in cells and (col, row) in cells]
        gap = cols[len(cols) // 2] if cols else None
        for col in cols:
            if col == gap:
                continue
            if cell_is_protected(room, protected_cells, col, row - 1) or cell_is_protected(room, protected_cells, col, row):
                continue
            edge = ("h", col, row)
            if feature_edge_blocked(edge, room.level, blocked_edges):
                continue
            generator.add_wall_edge(edge, role="narrow_wall", level=room.level)


def emit_room_columns(
    generator: BuildingGenerator,
    room: RoomNode,
    blocked_edges: set[tuple[int, tuple[str, int, int]]] | None = None,
) -> None:
    blocked_edges = blocked_edges or set()
    cells = set(cells_for_room(room))
    candidates = [
        (room.x_value + 1, room.y_value + 1),
        (room.x_value + room.width - 2, room.y_value + 1),
        (room.x_value + 1, room.y_value + room.height - 2),
        (room.x_value + room.width - 2, room.y_value + room.height - 2),
    ]
    for index, (col, row) in enumerate(candidates):
        if (col, row) not in cells:
            continue
        axis = "h" if index % 2 else "v"
        edge = (axis, col, row)
        if feature_edge_blocked(edge, room.level, blocked_edges):
            continue
        generator.add_wall_edge(edge, role="small_wall", level=room.level)


def feature_edge_blocked(
    edge: tuple[str, int, int],
    level: int,
    blocked_edges: set[tuple[int, tuple[str, int, int]]],
) -> bool:
    if (level, edge) in blocked_edges:
        return True
    a, b = cells_across_edge(edge)
    for cell in (a, b):
        for candidate in cell_edges(cell[0], cell[1]):
            if (level, candidate) in blocked_edges:
                return True
    return False


def cells_across_edge(edge: tuple[str, int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    axis, a, b = edge
    if axis == "v":
        return (a - 1, b), (a, b)
    if axis == "h":
        return (a, b - 1), (a, b)
    raise GeneratorError(f"Unknown edge axis: {axis}")


def cell_edges(col: int, row: int) -> list[tuple[str, int, int]]:
    return [
        ("v", col, row),
        ("v", col + 1, row),
        ("h", col, row),
        ("h", col, row + 1),
    ]


def cell_neighbor_across_edge(edge: tuple[str, int, int], col: int, row: int) -> tuple[int, int]:
    axis, a, b = edge
    if axis == "v":
        return (col - 1, row) if a == col else (col + 1, row)
    if axis == "h":
        return (col, row - 1) if b == row else (col, row + 1)
    raise GeneratorError(f"Unknown edge axis: {axis}")


def room_center(room: RoomNode) -> tuple[float, float]:
    return room.x_value + ((room.width - 1) / 2), room.y_value + ((room.height - 1) / 2)


def room_rect(room: RoomNode) -> tuple[int, int, int, int]:
    return room.x_value, room.y_value, room.x_value + room.width - 1, room.y_value + room.height - 1


def rectangles_overlap(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
    padding: int,
) -> bool:
    return not (
        a[2] + padding < b[0]
        or b[2] + padding < a[0]
        or a[3] + padding < b[1]
        or b[3] + padding < a[1]
    )


def room_degrees(edges: list[RoomGraphEdge], room_count: int) -> list[int]:
    degrees = [0 for _ in range(room_count)]
    for edge in edges:
        degrees[edge.a] += 1
        degrees[edge.b] += 1
    return degrees


def vertical_edge_rooms(rooms: list[RoomNode], edge: RoomGraphEdge) -> tuple[RoomNode, RoomNode]:
    room_a = rooms[edge.a]
    room_b = rooms[edge.b]
    if room_a.level < room_b.level:
        return room_a, room_b
    if room_b.level < room_a.level:
        return room_b, room_a
    raise GeneratorError(f"Edge {edge.a}-{edge.b} was marked vertical but both rooms are on level {room_a.level}.")


def normalized_edge(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def load_targets(index_path: Path, tier: int) -> tuple[dict[str, PieceTarget], dict[str, Any]]:
    index_doc = load_json(index_path)
    rows = index_doc.get("targets")
    if not isinstance(rows, list):
        raise GeneratorError(f"{index_path} does not contain a targets list.")
    by_id = {str(row.get("target_id")): row for row in rows if isinstance(row, dict)}
    targets = {}
    for role, target_id in TIER_TARGETS[tier].items():
        row = by_id.get(target_id)
        if not row:
            raise GeneratorError(f"Target {target_id!r} for {role} is missing from {index_path}.")
        targets[role] = parse_target(row, role)
    return targets, index_doc


def parse_target(row: dict[str, Any], role: str) -> PieceTarget:
    if row.get("asset_kind") != "building_piece":
        raise GeneratorError(f"Target {row.get('target_id')} for {role} is not a building piece.")
    export = row.get("export") or {}
    missing = [field for field in REQUIRED_EXPORT_FIELDS if missing_value(export, field)]
    if missing:
        raise GeneratorError(f"Target {row.get('target_id')} for {role} is missing export fields: {missing}")
    return PieceTarget(
        target_id=str(row["target_id"]),
        display_name=str(row.get("display_name") or row["target_id"]),
        asset_stem=str(row.get("asset_stem") or row["target_id"]),
        snap_class=str(row.get("snap_class") or export.get("bp_class") or ""),
        piece_data_index=int(export["piece_data_index"]),
        piece_data_name=str(export["piece_data_name"]),
        class_name=str(export["class_name"]),
        default_stability=int(export.get("default_stability") or 3000),
    )


def derive_cell_size(snaps_doc: dict[str, Any], foundation: PieceTarget) -> float:
    snaps = snaps_doc.get("pieces") if isinstance(snaps_doc, dict) else {}
    data = snaps.get(foundation.snap_class) if isinstance(snaps, dict) else None
    plugs = data.get("plugs") if isinstance(data, dict) else None
    if not isinstance(plugs, list) or not plugs:
        raise GeneratorError(f"No snap plugs found for foundation snap class {foundation.snap_class!r}.")
    xs = []
    ys = []
    for plug in plugs:
        pos = plug.get("pos") if isinstance(plug, dict) else None
        if isinstance(pos, list) and len(pos) >= 2:
            xs.append(float(pos[0]))
            ys.append(float(pos[1]))
    if not xs or not ys:
        raise GeneratorError(f"Foundation snap class {foundation.snap_class!r} has no usable plug positions.")
    cell_size = max(max(xs) - min(xs), max(ys) - min(ys))
    if cell_size <= 0:
        raise GeneratorError(f"Could not derive positive cell size from {foundation.snap_class!r}.")
    return cell_size


def derive_stair_extents(snaps_doc: dict[str, Any], stairs: PieceTarget) -> tuple[float, float]:
    snaps = snaps_doc.get("pieces") if isinstance(snaps_doc, dict) else {}
    data = snaps.get(stairs.snap_class) if isinstance(snaps, dict) else None
    plugs = data.get("plugs") if isinstance(data, dict) else None
    if not isinstance(plugs, list) or not plugs:
        raise GeneratorError(f"No snap plugs found for stairs snap class {stairs.snap_class!r}.")
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for plug in plugs:
        pos = plug.get("pos") if isinstance(plug, dict) else None
        if isinstance(pos, list) and len(pos) >= 3:
            xs.append(float(pos[0]))
            ys.append(float(pos[1]))
            zs.append(float(pos[2]))
    if not xs or not ys or not zs:
        raise GeneratorError(f"Stairs snap class {stairs.snap_class!r} has no usable plug positions.")
    run = max(max(xs) - min(xs), max(ys) - min(ys))
    rise = max(zs) - min(zs)
    if run <= 0 or rise <= 0:
        raise GeneratorError(f"Could not derive positive stair extents from {stairs.snap_class!r}.")
    return run, rise


def validate_building_json(data: dict[str, Any]) -> None:
    if data.get("schema") != SCHEMA:
        raise GeneratorError(f"Unexpected schema {data.get('schema')!r}; expected {SCHEMA!r}.")
    pieces = data.get("pieces")
    if not isinstance(pieces, list) or not pieces:
        raise GeneratorError("Generated JSON must contain at least one piece.")
    seen_ids: set[int] = set()
    for index, row in enumerate(pieces):
        if not isinstance(row, dict):
            raise GeneratorError(f"Piece at index {index} is not an object.")
        piece_id = int(row.get("piece_id") or 0)
        if piece_id <= 0:
            raise GeneratorError(f"Piece at index {index} has no positive piece_id.")
        if piece_id in seen_ids:
            raise GeneratorError(f"Duplicate piece_id: {piece_id}")
        seen_ids.add(piece_id)
        missing_export = [field for field in REQUIRED_EXPORT_FIELDS if missing_value(row, field)]
        if missing_export:
            raise GeneratorError(f"Piece {piece_id} is missing fields: {missing_export}")
        missing_transform = [field for field in REQUIRED_TRANSFORM_FIELDS if field not in row]
        if missing_transform:
            raise GeneratorError(f"Piece {piece_id} is missing transform fields: {missing_transform}")
        if "stability" not in row or "is_ghosted" not in row:
            raise GeneratorError(f"Piece {piece_id} is missing stability/is_ghosted metadata.")
    anchor_piece_id = int(data.get("anchor_piece_id") or 0)
    if anchor_piece_id not in seen_ids:
        raise GeneratorError(f"anchor_piece_id {anchor_piece_id} does not refer to a generated piece.")
    anchor_piece = next(row for row in pieces if int(row["piece_id"]) == anchor_piece_id)
    if int(data.get("anchor_piece_data_index") or 0) != int(anchor_piece["piece_data_index"]):
        raise GeneratorError("anchor_piece_data_index does not match the anchor piece.")
    if int(data.get("count") or 0) != len(pieces):
        raise GeneratorError("count does not match pieces length.")


def validate_against_index(data: dict[str, Any], index_doc: dict[str, Any]) -> None:
    rows = index_doc.get("targets")
    if not isinstance(rows, list):
        raise GeneratorError("Index targets are unavailable for validation.")
    by_piece_data_index = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("asset_kind") != "building_piece":
            continue
        export = row.get("export") or {}
        if export.get("piece_data_index") is None:
            continue
        by_piece_data_index[int(export["piece_data_index"])] = export
    for row in data["pieces"]:
        piece_data_index = int(row["piece_data_index"])
        export = by_piece_data_index.get(piece_data_index)
        if not export:
            raise GeneratorError(f"Piece {row['piece_id']} has unknown piece_data_index {piece_data_index}.")
        if row["piece_data_name"] != export.get("piece_data_name"):
            raise GeneratorError(f"Piece {row['piece_id']} piece_data_name does not match index metadata.")
        if row["class_name"] != export.get("class_name"):
            raise GeneratorError(f"Piece {row['piece_id']} class_name does not match index metadata.")


def all_grid_edges(width: int, height: int) -> set[tuple[str, int, int]]:
    edges: set[tuple[str, int, int]] = set()
    for row in range(height):
        for col in range(width + 1):
            edges.add(("v", col, row))
    for row in range(height + 1):
        for col in range(width):
            edges.add(("h", col, row))
    return edges


def perimeter_edges(width: int, height: int) -> list[tuple[str, int, int]]:
    edges: list[tuple[str, int, int]] = []
    for row in range(height):
        edges.append(("v", 0, row))
        edges.append(("v", width, row))
    for col in range(width):
        edges.append(("h", col, 0))
        edges.append(("h", col, height))
    return edges


def shift_edge(edge: tuple[str, int, int], col_offset: int, row_offset: int) -> tuple[str, int, int]:
    axis, a, b = edge
    return axis, a + col_offset, b + row_offset


def neighbors(col: int, row: int, width: int, height: int) -> list[tuple[int, int]]:
    out = []
    if col > 0:
        out.append((col - 1, row))
    if col + 1 < width:
        out.append((col + 1, row))
    if row > 0:
        out.append((col, row - 1))
    if row + 1 < height:
        out.append((col, row + 1))
    return out


def edge_between(col: int, row: int, ncol: int, nrow: int) -> tuple[str, int, int]:
    if ncol == col + 1 and nrow == row:
        return "v", col + 1, row
    if ncol == col - 1 and nrow == row:
        return "v", col, row
    if nrow == row + 1 and ncol == col:
        return "h", col, row + 1
    if nrow == row - 1 and ncol == col:
        return "h", col, row
    raise GeneratorError(f"Cells are not adjacent: {(col, row)} -> {(ncol, nrow)}")


def default_output_path(args: argparse.Namespace) -> Path:
    name = args.name or default_build_name(args)
    stem = safe_stem(name)
    return DEFAULT_OUTPUT_DIR / f"{stem}.json"


def default_build_name(args: argparse.Namespace) -> str:
    if args.preset == "elevation-demo":
        return f"procedural_{args.preset}_t{args.tier}_{args.width}x{args.height}x{args.levels}"
    if args.preset == "room-maze":
        return f"procedural_{args.preset}_t{args.tier}_{args.detail_budget}_{args.rooms}_rooms_s{args.seed}"
    if args.preset == "room-lab":
        if args.room_type == "jumping_puzzle":
            return f"procedural_{args.preset}_{args.room_type}_{args.jumping_variant}_t{args.tier}_{args.detail_budget}_s{args.seed}"
        return f"procedural_{args.preset}_{args.room_type}_t{args.tier}_{args.detail_budget}_s{args.seed}"
    if args.preset == "shape-lab":
        return f"procedural_{args.preset}_{args.shape_style}_t{args.tier}"
    if args.preset == "jumping-puzzle":
        return f"procedural_{args.preset}_{args.jumping_variant}_t{args.tier}_{args.detail_budget}_{args.width}x{args.height}_s{args.seed}"
    return f"procedural_{args.preset}_t{args.tier}_{args.width}x{args.height}_s{args.seed}"


def print_summary(data: dict[str, Any], output: Path | None, report: RoomMazeReport | None = None) -> None:
    target = str(output) if output else "(not written)"
    print(f"schema: {data['schema']}")
    print(f"name: {data['name']}")
    print(f"pieces: {len(data['pieces'])}")
    print(f"anchor_piece_id: {data['anchor_piece_id']}")
    if report:
        print(f"rooms: {report.rooms}")
        print(f"critical_path_length: {report.critical_path_length}")
        print(f"branches: {report.branches}")
        print(f"loops: {report.loops}")
        print(f"levels_used: {report.levels_used}")
    print(f"output: {target}")


def parse_generated_unix(value: str) -> int:
    if str(value).lower() == "now":
        return int(datetime.now(timezone.utc).timestamp())
    parsed = int(value)
    if parsed < 0:
        raise GeneratorError("--generated-unix must be 0, a positive integer, or 'now'.")
    return parsed


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise GeneratorError(f"{path} did not contain a JSON object.")
    return data


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def rate_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def round_number(value: float) -> int | float:
    rounded = round(float(value), 3)
    return int(rounded) if rounded.is_integer() else rounded


def missing_value(row: dict[str, Any], field: str) -> bool:
    return field not in row or row[field] is None or row[field] == ""


def safe_stem(value: str) -> str:
    out = []
    for char in value.lower():
        if char.isalnum():
            out.append(char)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_") or "procedural_build"


if __name__ == "__main__":
    raise SystemExit(main())
