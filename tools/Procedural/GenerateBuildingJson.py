from __future__ import annotations

import argparse
import json
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
        "shallow_stairs": "443_DA_T1_Stairs_Straight_Shallow",
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
        "shallow_stairs": "298_DA_T2_Stairs_Straight_Shallow",
    },
    3: {
        "foundation": "187_DA_T3_Foundation_Large",
        "floor": "203_DA_T3_Floor_Large",
        "wall": "122_DA_T3_Wall_Large",
        "doorframe": "118_DA_T3_Wall_Large_Doorframe",
        "stairs": "127_DA_T3_Stairs_Straight",
        "window_wall": "101_DA_T3_Wall_Large_Windowframe",
        "double_window_wall": "106_DA_T3_Wall_Large_Special_Windowed_1",
        "narrow_wall": "116_DA_T3_Wall_Large_Narrow",
        "small_wall": "091_DA_T3_Wall_Small",
        "medium_wall": "123_DA_T3_Wall_CurvedWindow_Medium",
        "floor_small": "190_DA_T3_Floor_Small",
        "floor_medium": "201_DA_T3_Floor_Medium",
        "shallow_stairs": "126_DA_T3_Stairs_Straight_Shallow",
    },
}

STRAIGHT_STAIR_YAW = 180
STRAIGHT_STAIR_ALIGNMENT_OFFSET_X = -64.749
STRAIGHT_STAIR_ALIGNMENT_OFFSET_Z = 77.135

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
        if self.anchor_piece_id == 0 and role == "foundation":
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
    parser.add_argument("--preset", choices=("maze", "platform", "elevation-demo", "room-maze"), default="maze")
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
    )
    layout_room_maze(build, rng)
    room_maze_to_pieces(generator, build)
    validate_room_maze_build(build)
    return RoomMazeReport(
        rooms=len(build.rooms),
        critical_path_length=build.critical_path_length,
        branches=build.branches,
        loops=build.loops,
        levels_used=build.levels_used,
    )


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
            room.width, room.height = 4, 4
        elif room.room_id == end_room_id:
            room.room_type = "overlook" if room.level > 0 else "gallery"
            room.width, room.height = 5, 3
        elif room.room_id in vertical_rooms:
            room.room_type = rng.choice(["stair_core", "tower", "atrium"])
            room.width, room.height = (5, 5) if room.room_type == "atrium" else (4, 4)
        elif degrees[room.room_id] >= 3:
            room.room_type = "crossroad"
            room.width, room.height = 4, 4
        elif degrees[room.room_id] == 1:
            room.room_type = "dead_end"
            room.width, room.height = rng.choice([(2, 3), (3, 2), (3, 3)])
        elif rng.random() < 0.35:
            room.room_type = "gallery"
            room.width, room.height = rng.choice([(6, 3), (3, 6), (5, 3)])
        else:
            room.room_type = "chamber"
            room.width, room.height = rng.choice([(3, 3), (4, 3), (4, 4), (5, 4)])
        apply_room_architecture_flags(room, rng, irregular_room_rate, tall_room_rate, balcony_rate, window_rate)


def apply_room_architecture_flags(
    room: RoomNode,
    rng: random.Random,
    irregular_room_rate: float,
    tall_room_rate: float,
    balcony_rate: float,
    window_rate: float,
) -> None:
    if room.room_type in {"stair_core", "tower", "atrium"}:
        room.mask_kind = "rect"
        room.wall_height = 2 if room.room_type == "stair_core" else rng.choice([2, 3])
        room.has_balcony = room.room_type == "atrium"
        room.has_divider = room.room_type == "tower"
        room.has_columns = room.room_type == "atrium"
        room.has_windows = rng.random() < window_rate
        return
    if room.room_type == "entry":
        room.mask_kind = "rect"
    elif room.room_type == "crossroad":
        room.mask_kind = "cross" if rng.random() < irregular_room_rate else "rect"
    elif room.room_type == "gallery":
        room.mask_kind = "split" if rng.random() < irregular_room_rate else "rect"
    elif room.room_type == "overlook":
        room.mask_kind = "u" if rng.random() < irregular_room_rate else "rect"
    elif room.room_type == "dead_end":
        room.mask_kind = "l" if rng.random() < irregular_room_rate else "rect"
    else:
        room.mask_kind = rng.choice(["l", "t", "u", "split"]) if rng.random() < irregular_room_rate else "rect"
    room.wall_height = rng.choice([2, 3]) if rng.random() < tall_room_rate else 1
    room.has_balcony = room.wall_height >= 2 and room.width >= 4 and room.height >= 4 and rng.random() < balcony_rate
    room.has_divider = room.width >= 4 and room.height >= 3 and rng.random() < 0.45
    room.has_columns = room.width >= 4 and room.height >= 4 and rng.random() < 0.35
    room.has_windows = rng.random() < window_rate


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
    x_options = [base_x + offset for offset in (0, 2, 4, 6, 8, 12)]
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


def room_maze_to_pieces(generator: BuildingGenerator, build: RoomMazeBuild) -> None:
    occupied: dict[int, set[tuple[int, int]]] = {}
    room_cells: dict[int, set[tuple[int, int]]] = {}
    corridor_cells: dict[int, set[tuple[int, int]]] = {}
    stair_bay_cells: dict[int, set[tuple[int, int]]] = {}
    wall_roles: dict[tuple[int, tuple[str, int, int]], str] = {}
    connection_records: dict[tuple[int, int], list[tuple[int, tuple[str, int, int]]]] = {}
    stair_specs: list[tuple[RoomNode, RoomNode, int]] = []

    for room in build.rooms:
        cells = set(cells_for_room(room))
        room_cells[room.room_id] = cells
        occupied.setdefault(room.level, set()).update(cells)

    for edge in build.edges:
        if edge.vertical:
            lower, upper = vertical_edge_rooms(build.rooms, edge)
            door_edges, stair_row, lower_path = vertical_door_edges(lower, upper)
            bay_cells = lower_stair_bay_cells(upper, stair_row, generator)
            occupied.setdefault(lower.level, set()).update(lower_path)
            corridor_cells.setdefault(lower.level, set()).update(lower_path)
            stair_bay_cells.setdefault(lower.level, set()).update(bay_cells)
            occupied.setdefault(lower.level, set()).update(bay_cells)
            for door in door_edges:
                wall_roles[(door[0], door[1])] = "doorframe"
            stair_specs.append((lower, upper, stair_row))
            connection_records[normalized_edge(edge.a, edge.b)] = door_edges
            continue

        room_a = build.rooms[edge.a]
        room_b = build.rooms[edge.b]
        path, door_edges = horizontal_corridor(room_a, room_b)
        occupied.setdefault(room_a.level, set()).update(path)
        corridor_cells.setdefault(room_a.level, set()).update(path)
        for door in door_edges:
            wall_roles[(door[0], door[1])] = "doorframe"
        connection_records[normalized_edge(edge.a, edge.b)] = door_edges

    validate_room_connections(build, connection_records)
    validate_doorframes_open_to_floor(connection_records, occupied)

    for level in sorted(occupied):
        for col, row in sorted(occupied[level]):
            generator.add_cell_surface(col, row, level=level)

    for room in build.rooms:
        for height_index in range(room.wall_height):
            for edge in room_perimeter_edges(room):
                key = (room.level + height_index, edge)
                wall_roles.setdefault(key, room_wall_role(room, edge, height_index))

    for level, cells in stair_bay_cells.items():
        for edge in perimeter_edges_for_cells(cells):
            wall_roles.setdefault((level, edge), "wall")

    for level, cells in corridor_cells.items():
        for col, row in cells:
            for edge in cell_edges(col, row):
                neighbor = cell_neighbor_across_edge(edge, col, row)
                if neighbor not in occupied.get(level, set()):
                    wall_roles.setdefault((level, edge), "wall")

    for level, edge in sorted(wall_roles):
        generator.add_wall_edge(edge, role=wall_roles[(level, edge)], level=level)

    emit_room_architecture_features(generator, build)

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
) -> tuple[list[tuple[int, tuple[str, int, int]]], int, set[tuple[int, int]]]:
    if upper.level != lower.level + 1:
        raise GeneratorError("Vertical room-maze connections currently require exactly one level of rise.")
    stair_row = vertical_connection_row(lower, upper)
    _inside_lower, outside_lower, lower_edge = doorway_for_side(lower, "east", row_offset=stair_row - lower.y_value)
    lower_path = manhattan_path(outside_lower, (upper.x_value, stair_row))
    upper_internal_edge = ("v", upper.x_value + min(2, upper.width - 1), stair_row)
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


def vertical_connection_row(lower: RoomNode, upper: RoomNode) -> int:
    lower_rows = {row for _col, row in cells_for_room(lower)}
    upper_rows = {row for _col, row in cells_for_room(upper)}
    overlap = sorted(lower_rows & upper_rows)
    if not overlap:
        raise GeneratorError(f"Vertical rooms {lower.room_id}-{upper.room_id} do not overlap in Y for stairs.")
    preferred = lower.y_value + min(1, lower.height - 1)
    return min(overlap, key=lambda row: abs(row - preferred))


def lower_stair_bay_cells(upper: RoomNode, stair_row: int, generator: BuildingGenerator) -> set[tuple[int, int]]:
    stairs_needed = max(1, round(generator.cell_size / generator.stair_rise))
    width = min(upper.width, stairs_needed + 1)
    cells = {(upper.x_value + offset, stair_row) for offset in range(width)}
    room_cells = set(cells_for_room(upper))
    cells &= room_cells
    if len(cells) < stairs_needed:
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


def emit_room_architecture_features(generator: BuildingGenerator, build: RoomMazeBuild) -> None:
    for room in build.rooms:
        if room.has_balcony:
            emit_room_balcony(generator, room)
        if room.has_divider:
            emit_room_divider(generator, room)
        if room.has_columns:
            emit_room_columns(generator, room)


def emit_room_balcony(generator: BuildingGenerator, room: RoomNode) -> None:
    cells = balcony_cells(room)
    if not cells:
        return
    for col, row in cells:
        generator.add_cell_surface(col, row, level=room.level + 1, role="floor_medium")
    for edge in perimeter_edges_for_cells(cells):
        a, b = cells_across_edge(edge)
        if a in cells and b in cells:
            continue
        generator.add_wall_edge(edge, role="narrow_wall", level=room.level + 1)


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


def emit_room_divider(generator: BuildingGenerator, room: RoomNode) -> None:
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
            generator.add_wall_edge(("v", col, row), role="narrow_wall", level=room.level)
    else:
        row = room.y_value + room.height // 2
        cols = [col for col in range(room.x_value + 1, room.x_value + room.width - 1) if (col, row - 1) in cells and (col, row) in cells]
        gap = cols[len(cols) // 2] if cols else None
        for col in cols:
            if col == gap:
                continue
            generator.add_wall_edge(("h", col, row), role="narrow_wall", level=room.level)


def emit_room_columns(generator: BuildingGenerator, room: RoomNode) -> None:
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
        generator.add_wall_edge(edge, role="small_wall", level=room.level)


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
        return f"procedural_{args.preset}_t{args.tier}_{args.rooms}_rooms_s{args.seed}"
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
