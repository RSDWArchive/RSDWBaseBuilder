from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = ROOT / "website" / "basebuilder-index.json"
DEFAULT_OUTPUT_DIR = ROOT / "_build" / "procedural"
SCHEMA = "rsdwtools.buildings.v1"

REQUIRED_ACTOR_FIELDS = (
    "actor_name",
    "actor_class",
    "class_path",
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
class ActorTarget:
    target_id: str
    display_name: str
    actor_class: str
    class_path: str
    bounds_min_y: float | None = None
    bounds_max_y: float | None = None


@dataclass(frozen=True)
class TerrainProfile:
    profile_id: str
    target_id: str
    scale: tuple[float, float, float]
    footprint_radius: float = 0.0
    fallback_bounds_y: tuple[float, float] | None = None
    z: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0


@dataclass(frozen=True)
class ActorSpec:
    profile_id: str
    x: float
    y: float
    z: float
    yaw: float
    scale: tuple[float, float, float]
    pitch: float = 0.0
    roll: float = 0.0


class TerrainError(RuntimeError):
    pass


PROFILES: dict[str, TerrainProfile] = {
    "limestone_ground": TerrainProfile(
        profile_id="limestone_ground",
        target_id="bp:BP_OreNode_Limestone_C",
        scale=(10.0, 10.0, 0.1),
        footprint_radius=760.0,
        fallback_bounds_y=(-0.03726499155163765, 1.570602297782898),
    ),
    "ash_grass": TerrainProfile(
        profile_id="ash_grass",
        target_id="bp:BP_BM_Tree_Ash_01_C",
        scale=(1.0, 1.0, 0.01),
        fallback_bounds_y=(-1.2850406169891357, 17.957128524780273),
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        targets = load_actor_targets(args.index, PROFILES.values(), args.webassets_root)

        if args.validate_only:
            if not args.input:
                raise TerrainError("--validate-only requires --input.")
            data = load_json(args.input)
            validate_terrain_json(data, targets)
            print(f"validated: {args.input}")
            return 0

        data = generate_terrain(args, targets)
        validate_terrain_json(data, targets)
        output = args.output or default_output_path(args)

        if args.dry_run:
            print_summary(data, output)
            return 0

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print_summary(data, output)
        return 0
    except (TerrainError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate actor-based procedural terrain JSON for RSDW Base Builder.",
    )
    parser.add_argument(
        "--preset",
        choices=("terrain-lab", "meadow-path", "forest-trail", "terrain-island"),
        default="terrain-lab",
    )
    parser.add_argument("--width", type=positive_float, default=12000.0, help="Terrain width in game centimeters.")
    parser.add_argument("--height", type=positive_float, default=9000.0, help="Terrain height in game centimeters.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--name", default="")
    parser.add_argument(
        "--ground-spacing",
        type=positive_float,
        default=1600.0,
        help="Maximum limestone center spacing. The generator may use tighter spacing to maintain overlap.",
    )
    parser.add_argument(
        "--ground-footprint-radius",
        type=positive_float,
        default=760.0,
        help="Approximate visible limestone footprint radius in game centimeters after scaling.",
    )
    parser.add_argument(
        "--ground-overlap",
        type=rate_float,
        default=0.4,
        help="Target overlap between neighboring limestone footprints.",
    )
    parser.add_argument("--grass-spacing", type=positive_float, default=420.0)
    parser.add_argument("--path-width", type=positive_float, default=1200.0)
    parser.add_argument("--density", type=rate_float, default=0.72)
    parser.add_argument("--edge-band-width", type=positive_float, default=1150.0)
    parser.add_argument("--edge-gap-width", type=positive_float, default=1700.0)
    parser.add_argument("--edge-scale-variation", type=rate_float, default=0.06)
    parser.add_argument(
        "--edge-uniform-scale",
        type=float,
        default=0.0,
        help="Optional override for selected edge limestone uniform scale. Defaults to each actor's existing XY scale.",
    )
    parser.add_argument("--no-edge-scaling", action="store_true", help="Skip converting outer limestone ground actors into border rocks.")
    parser.add_argument("--max-actors", type=positive_int, default=5000)
    parser.add_argument(
        "--generated-unix",
        default="0",
        help="Unix timestamp metadata. Defaults to 0 for deterministic generated files; use 'now' for current UTC time.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path, help="Existing JSON file to validate with --validate-only.")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--webassets-root",
        type=Path,
        help="Optional RSDWModel WebAssets root used to derive GLTF bounds for terrain surface placement.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate without writing a file.")
    parser.add_argument("--validate-only", action="store_true", help="Validate an existing generated terrain JSON.")
    return parser


def generate_terrain(args: argparse.Namespace, targets: dict[str, ActorTarget]) -> dict[str, Any]:
    rng = random.Random(args.seed)
    if args.preset == "terrain-lab":
        specs = terrain_lab(args, targets, rng)
    elif args.preset == "meadow-path":
        specs = meadow_path(args, targets, rng)
    elif args.preset == "forest-trail":
        specs = forest_trail(args, targets, rng)
    elif args.preset == "terrain-island":
        specs = terrain_island(args, targets, rng)
    else:
        raise TerrainError(f"Unknown preset: {args.preset}")

    if len(specs) > args.max_actors:
        raise TerrainError(f"Generated {len(specs)} actors, exceeding --max-actors {args.max_actors}.")

    actors = [actor_row(index + 1, spec, targets[PROFILES[spec.profile_id].target_id]) for index, spec in enumerate(specs)]
    return {
        "schema": SCHEMA,
        "name": args.name or default_build_name(args),
        "generated_unix": generated_unix(args.generated_unix),
        "count": 0,
        "skipped": 0,
        "item_count": 0,
        "item_skipped": 0,
        "hidden": 0,
        "pieces": [],
        "items": [],
        "actors": actors,
    }


def terrain_lab(args: argparse.Namespace, targets: dict[str, ActorTarget], rng: random.Random) -> list[ActorSpec]:
    specs: list[ActorSpec] = []
    ground_specs = add_ground_grid(specs, args, rng, width=5200.0, height=3600.0, origin=(-2600.0, -1800.0), spacing=1300.0)

    path = [(-2600.0, 0.0), (-900.0, -250.0), (900.0, 320.0), (2600.0, 0.0)]
    add_grass_field(
        specs,
        args,
        targets,
        rng,
        bounds=(-2600.0, -1800.0, 2600.0, 1800.0),
        path=path,
        ground_specs=ground_specs,
        spacing=360.0,
        path_width=700.0,
        density=0.82,
    )
    scale_edge_ground_specs(specs, args, targets, rng, bounds=(-2600.0, -1800.0, 2600.0, 1800.0), path=path, ground_specs=ground_specs)
    return specs


def meadow_path(args: argparse.Namespace, targets: dict[str, ActorTarget], rng: random.Random) -> list[ActorSpec]:
    specs: list[ActorSpec] = []
    bounds = centered_bounds(args.width, args.height)
    path = winding_path(args.width, args.height, rng, bends=7)
    ground_specs = add_ground_grid(specs, args, rng, width=args.width, height=args.height, origin=(bounds[0], bounds[1]), spacing=args.ground_spacing)
    add_grass_field(
        specs,
        args,
        targets,
        rng,
        bounds=bounds,
        path=path,
        ground_specs=ground_specs,
        spacing=args.grass_spacing,
        path_width=args.path_width,
        density=args.density,
    )
    scale_edge_ground_specs(specs, args, targets, rng, bounds=bounds, path=path, ground_specs=ground_specs)
    return specs


def forest_trail(args: argparse.Namespace, targets: dict[str, ActorTarget], rng: random.Random) -> list[ActorSpec]:
    specs: list[ActorSpec] = []
    bounds = centered_bounds(args.width, args.height)
    path = winding_path(args.width, args.height, rng, bends=8)
    ground_specs = add_ground_grid(specs, args, rng, width=args.width, height=args.height, origin=(bounds[0], bounds[1]), spacing=args.ground_spacing)
    add_grass_field(
        specs,
        args,
        targets,
        rng,
        bounds=bounds,
        path=path,
        ground_specs=ground_specs,
        spacing=args.grass_spacing * 0.85,
        path_width=args.path_width * 0.9,
        density=min(1.0, args.density + 0.12),
        edge_bias=True,
    )
    add_grass_clumps(
        specs,
        args,
        targets,
        rng,
        bounds=bounds,
        path=path,
        ground_specs=ground_specs,
        clumps=max(8, int((args.width * args.height) / 10_000_000)),
    )
    scale_edge_ground_specs(specs, args, targets, rng, bounds=bounds, path=path, ground_specs=ground_specs)
    return specs


def terrain_island(args: argparse.Namespace, targets: dict[str, ActorTarget], rng: random.Random) -> list[ActorSpec]:
    specs: list[ActorSpec] = []
    bounds = centered_bounds(args.width, args.height)
    ground_specs = add_ground_grid(
        specs,
        args,
        rng,
        width=args.width,
        height=args.height,
        origin=(bounds[0], bounds[1]),
        spacing=args.ground_spacing,
        mask=lambda x, y: island_mask(x, y, args.width, args.height),
    )

    ring_path = island_loop_path(args.width, args.height)
    add_grass_field(
        specs,
        args,
        targets,
        rng,
        bounds=bounds,
        path=ring_path,
        ground_specs=ground_specs,
        spacing=args.grass_spacing,
        path_width=args.path_width,
        density=args.density,
        mask=lambda x, y: island_mask(x, y, args.width, args.height),
        edge_bias=True,
    )
    scale_edge_ground_specs(
        specs,
        args,
        targets,
        rng,
        bounds=bounds,
        path=ring_path,
        ground_specs=ground_specs,
        island_size=(args.width, args.height),
    )
    return specs


def add_ground_grid(
    specs: list[ActorSpec],
    args: argparse.Namespace,
    rng: random.Random,
    *,
    width: float,
    height: float,
    origin: tuple[float, float],
    spacing: float,
    mask: Any | None = None,
) -> list[ActorSpec]:
    profile = PROFILES["limestone_ground"]
    ground_specs: list[ActorSpec] = []
    radius = float(args.ground_footprint_radius or profile.footprint_radius)
    center_spacing = min(spacing, radius * 2.0 * (1.0 - args.ground_overlap))
    row_spacing = center_spacing * math.sqrt(3.0) * 0.5
    x0, y0 = origin
    x1 = x0 + width
    y1 = y0 + height
    centers: list[tuple[float, float]] = []
    cols = int(math.ceil(width / center_spacing)) + 3
    rows = int(math.ceil(height / row_spacing)) + 3
    for row in range(rows):
        base_y = y0 + row * row_spacing
        row_offset = center_spacing * 0.5 if row % 2 else 0.0
        for col in range(cols):
            base_x = x0 + col * center_spacing + row_offset
            x = base_x + rng.uniform(-center_spacing * 0.06, center_spacing * 0.06)
            y = base_y + rng.uniform(-row_spacing * 0.06, row_spacing * 0.06)
            if x < x0 - radius or x > x1 + radius or y < y0 - radius or y > y1 + radius:
                continue
            if mask and not mask(x, y):
                continue
            spec = add_ground_actor(specs, profile, rng, x, y)
            ground_specs.append(spec)
            centers.append((x, y))

    repair_ground_holes(
        specs,
        ground_specs,
        profile,
        rng,
        bounds=(x0, y0, x1, y1),
        centers=centers,
        radius=radius,
        mask=mask,
    )
    return ground_specs


def add_ground_actor(
    specs: list[ActorSpec],
    profile: TerrainProfile,
    rng: random.Random,
    x: float,
    y: float,
) -> ActorSpec:
    scale = vary_scale(profile.scale, rng, xy=0.08, z=0.0)
    spec = ActorSpec(profile.profile_id, x, y, profile.z, rng.uniform(0.0, 360.0), scale)
    specs.append(spec)
    return spec


def repair_ground_holes(
    specs: list[ActorSpec],
    ground_specs: list[ActorSpec],
    profile: TerrainProfile,
    rng: random.Random,
    *,
    bounds: tuple[float, float, float, float],
    centers: list[tuple[float, float]],
    radius: float,
    mask: Any | None,
) -> None:
    x0, y0, x1, y1 = bounds
    sample_step = radius * 0.62
    covered_distance = radius * 0.68
    rows = int(math.ceil((y1 - y0) / sample_step)) + 1
    cols = int(math.ceil((x1 - x0) / sample_step)) + 1
    for row in range(rows):
        y = y0 + row * sample_step
        for col in range(cols):
            x = x0 + col * sample_step
            if mask and not mask(x, y):
                continue
            if nearest_distance_sq((x, y), centers) <= covered_distance * covered_distance:
                continue
            filler_x = x + rng.uniform(-sample_step * 0.12, sample_step * 0.12)
            filler_y = y + rng.uniform(-sample_step * 0.12, sample_step * 0.12)
            if mask and not mask(filler_x, filler_y):
                filler_x, filler_y = x, y
            spec = add_ground_actor(specs, profile, rng, filler_x, filler_y)
            ground_specs.append(spec)
            centers.append((filler_x, filler_y))


def nearest_distance_sq(point: tuple[float, float], centers: list[tuple[float, float]]) -> float:
    if not centers:
        return math.inf
    px, py = point
    return min((px - cx) * (px - cx) + (py - cy) * (py - cy) for cx, cy in centers)


def add_grass_field(
    specs: list[ActorSpec],
    args: argparse.Namespace,
    targets: dict[str, ActorTarget],
    rng: random.Random,
    *,
    bounds: tuple[float, float, float, float],
    path: list[tuple[float, float]],
    ground_specs: list[ActorSpec],
    spacing: float,
    path_width: float,
    density: float,
    mask: Any | None = None,
    edge_bias: bool = False,
) -> None:
    profile = PROFILES["ash_grass"]
    x0, y0, x1, y1 = bounds
    row_count = int(math.ceil((y1 - y0) / spacing)) + 1
    col_count = int(math.ceil((x1 - x0) / spacing)) + 1

    for row in range(row_count):
        for col in range(col_count):
            x = x0 + col * spacing + rng.uniform(-spacing * 0.45, spacing * 0.45)
            y = y0 + row * spacing + rng.uniform(-spacing * 0.45, spacing * 0.45)
            if x < x0 or x > x1 or y < y0 or y > y1:
                continue
            if mask and not mask(x, y):
                continue

            dist = distance_to_polyline((x, y), path)
            if dist < path_width * 0.5:
                continue

            falloff = clamp((dist - path_width * 0.5) / max(path_width * 1.8, 1.0), 0.0, 1.0)
            chance = density * (0.25 + 0.75 * falloff)
            if edge_bias:
                chance = min(1.0, chance + edge_density_bonus(x, y, bounds) * 0.25)
            if rng.random() > chance:
                continue

            scale = vary_scale(profile.scale, rng, xy=0.28, z=0.0)
            z = terrain_surface_z(x, y, ground_specs, targets) + visual_bottom_offset_cm(profile, targets, scale)
            specs.append(ActorSpec(profile.profile_id, x, y, z, rng.uniform(0.0, 360.0), scale))


def add_grass_clumps(
    specs: list[ActorSpec],
    args: argparse.Namespace,
    targets: dict[str, ActorTarget],
    rng: random.Random,
    *,
    bounds: tuple[float, float, float, float],
    path: list[tuple[float, float]],
    ground_specs: list[ActorSpec],
    clumps: int,
) -> None:
    profile = PROFILES["ash_grass"]
    x0, y0, x1, y1 = bounds
    for _ in range(clumps):
        for _attempt in range(50):
            cx = rng.uniform(x0, x1)
            cy = rng.uniform(y0, y1)
            if distance_to_polyline((cx, cy), path) > args.path_width:
                break
        else:
            continue
        count = rng.randint(8, 18)
        radius = rng.uniform(280.0, 760.0)
        for _ in range(count):
            angle = rng.uniform(0.0, math.tau)
            dist = radius * math.sqrt(rng.random())
            x = cx + math.cos(angle) * dist
            y = cy + math.sin(angle) * dist
            if x < x0 or x > x1 or y < y0 or y > y1:
                continue
            scale = vary_scale(profile.scale, rng, xy=0.35, z=0.0)
            z = terrain_surface_z(x, y, ground_specs, targets) + visual_bottom_offset_cm(profile, targets, scale)
            specs.append(ActorSpec(profile.profile_id, x, y, z, rng.uniform(0.0, 360.0), scale))


def scale_edge_ground_specs(
    specs: list[ActorSpec],
    args: argparse.Namespace,
    targets: dict[str, ActorTarget],
    rng: random.Random,
    *,
    bounds: tuple[float, float, float, float],
    path: list[tuple[float, float]],
    ground_specs: list[ActorSpec],
    island_size: tuple[float, float] | None = None,
) -> None:
    if args.no_edge_scaling:
        return
    profile = PROFILES["limestone_ground"]
    entrances = terrain_entrance_exit_points(bounds, path, island_size)
    spec_indexes = {id(spec): index for index, spec in enumerate(specs)}
    for ground_index, spec in enumerate(list(ground_specs)):
        if point_in_any_gap(spec.x, spec.y, entrances, args.edge_gap_width):
            continue
        is_edge = (
            island_ground_is_edge(spec, island_size, args.edge_band_width)
            if island_size
            else rectangle_ground_is_edge(spec, bounds, args.edge_band_width)
        )
        if not is_edge:
            continue
        base_scale = args.edge_uniform_scale if args.edge_uniform_scale > 0 else ((spec.scale[0] + spec.scale[1]) * 0.5)
        edge_scale = base_scale * rng.uniform(1.0 - args.edge_scale_variation, 1.0 + args.edge_scale_variation)
        scale = (edge_scale, edge_scale, edge_scale)
        replacement = ActorSpec(
            spec.profile_id,
            spec.x,
            spec.y,
            spec.z,
            spec.yaw,
            scale,
            spec.pitch,
            spec.roll,
        )
        ground_specs[ground_index] = replacement
        spec_index = spec_indexes.get(id(spec))
        if spec_index is not None:
            specs[spec_index] = replacement


def rectangle_ground_is_edge(
    spec: ActorSpec,
    bounds: tuple[float, float, float, float],
    edge_band_width: float,
) -> bool:
    x0, y0, x1, y1 = bounds
    distance = min(abs(spec.x - x0), abs(spec.x - x1), abs(spec.y - y0), abs(spec.y - y1))
    outside = spec.x < x0 or spec.x > x1 or spec.y < y0 or spec.y > y1
    return outside or distance <= edge_band_width


def island_ground_is_edge(
    spec: ActorSpec,
    island_size: tuple[float, float] | None,
    edge_band_width: float,
) -> bool:
    if not island_size:
        return False
    width, height = island_size
    angle = math.atan2(spec.y, spec.x)
    boundary_x, boundary_y = island_boundary_point(angle, width, height)
    boundary_radius = math.hypot(boundary_x, boundary_y)
    spec_radius = math.hypot(spec.x, spec.y)
    return boundary_radius - spec_radius <= edge_band_width


def terrain_entrance_exit_points(
    bounds: tuple[float, float, float, float],
    path: list[tuple[float, float]],
    island_size: tuple[float, float] | None,
) -> list[tuple[float, float]]:
    if island_size:
        width, height = island_size
        return [
            island_boundary_point(0.0, width, height),
            island_boundary_point(math.pi, width, height),
        ]
    if len(path) >= 2:
        return [project_point_to_bounds(path[0], bounds), project_point_to_bounds(path[-1], bounds)]
    x0, y0, x1, y1 = bounds
    return [(x0, (y0 + y1) * 0.5), (x1, (y0 + y1) * 0.5)]


def project_point_to_bounds(
    point: tuple[float, float],
    bounds: tuple[float, float, float, float],
) -> tuple[float, float]:
    x, y = point
    x0, y0, x1, y1 = bounds
    distances = [
        (abs(x - x0), (x0, clamp(y, y0, y1))),
        (abs(x - x1), (x1, clamp(y, y0, y1))),
        (abs(y - y0), (clamp(x, x0, x1), y0)),
        (abs(y - y1), (clamp(x, x0, x1), y1)),
    ]
    return min(distances, key=lambda row: row[0])[1]


def point_in_any_gap(
    x: float,
    y: float,
    gap_centers: list[tuple[float, float]],
    gap_width: float,
) -> bool:
    radius_sq = (gap_width * 0.5) * (gap_width * 0.5)
    return any((x - gx) * (x - gx) + (y - gy) * (y - gy) <= radius_sq for gx, gy in gap_centers)


def island_boundary_point(angle: float, width: float, height: float) -> tuple[float, float]:
    low = 0.0
    high = max(width, height)
    direction_x = math.cos(angle)
    direction_y = math.sin(angle)
    for _ in range(24):
        mid = (low + high) * 0.5
        x = direction_x * mid
        y = direction_y * mid
        if island_mask(x, y, width, height):
            low = mid
        else:
            high = mid
    return direction_x * low, direction_y * low


def terrain_surface_z(
    x: float,
    y: float,
    ground_specs: list[ActorSpec],
    targets: dict[str, ActorTarget],
) -> float:
    if not ground_specs:
        return 0.0
    best_covering = -math.inf
    best_nearest = None
    best_nearest_distance_sq = math.inf
    for spec in ground_specs:
        profile = PROFILES[spec.profile_id]
        radius = effective_footprint_radius(profile, spec.scale)
        distance_sq = (x - spec.x) * (x - spec.x) + (y - spec.y) * (y - spec.y)
        surface_z = spec.z + visual_top_offset_cm(profile, targets, spec.scale)
        if distance_sq <= radius * radius:
            best_covering = max(best_covering, surface_z)
        if distance_sq < best_nearest_distance_sq:
            best_nearest_distance_sq = distance_sq
            best_nearest = surface_z
    if math.isfinite(best_covering):
        return best_covering
    return best_nearest if best_nearest is not None else 0.0


def effective_footprint_radius(profile: TerrainProfile, scale: tuple[float, float, float]) -> float:
    if profile.footprint_radius <= 0:
        return 0.0
    base_x = profile.scale[0] or 1.0
    base_y = profile.scale[1] or 1.0
    scale_factor = ((scale[0] / base_x) + (scale[1] / base_y)) * 0.5
    return profile.footprint_radius * scale_factor


def visual_top_offset_cm(
    profile: TerrainProfile,
    targets: dict[str, ActorTarget],
    scale: tuple[float, float, float],
) -> float:
    target = targets.get(profile.target_id)
    max_y = target.bounds_max_y if target and target.bounds_max_y is not None else fallback_bounds_y(profile)[1]
    return max(0.0, float(max_y) * 100.0 * scale[2])


def visual_bottom_offset_cm(
    profile: TerrainProfile,
    targets: dict[str, ActorTarget],
    scale: tuple[float, float, float],
) -> float:
    target = targets.get(profile.target_id)
    min_y = target.bounds_min_y if target and target.bounds_min_y is not None else fallback_bounds_y(profile)[0]
    return max(0.0, -float(min_y) * 100.0 * scale[2])


def fallback_bounds_y(profile: TerrainProfile) -> tuple[float, float]:
    if profile.fallback_bounds_y is None:
        return (0.0, 0.0)
    return profile.fallback_bounds_y


def actor_row(index: int, spec: ActorSpec, target: ActorTarget) -> dict[str, Any]:
    sx, sy, sz = spec.scale
    return {
        "actor_name": f"{spec.profile_id}_{index:05d}",
        "actor_class": target.actor_class,
        "class_path": target.class_path,
        "x": rounded(spec.x),
        "y": rounded(spec.y),
        "z": rounded(spec.z),
        "pitch": rounded(spec.pitch),
        "yaw": rounded(spec.yaw),
        "roll": rounded(spec.roll),
        "scale_x": rounded(sx),
        "scale_y": rounded(sy),
        "scale_z": rounded(sz),
    }


def winding_path(width: float, height: float, rng: random.Random, *, bends: int) -> list[tuple[float, float]]:
    x0 = -width / 2.0
    x1 = width / 2.0
    usable_y = height * 0.32
    points: list[tuple[float, float]] = []
    for index in range(bends):
        t = index / max(bends - 1, 1)
        x = x0 + width * t
        wave = math.sin(t * math.tau * 1.35 + rng.uniform(-0.35, 0.35))
        y = wave * usable_y + rng.uniform(-height * 0.08, height * 0.08)
        if index == 0 or index == bends - 1:
            y *= 0.25
        points.append((x, y))
    return points


def island_loop_path(width: float, height: float) -> list[tuple[float, float]]:
    rx = width * 0.27
    ry = height * 0.22
    points = []
    for index in range(17):
        a = (index / 16.0) * math.tau
        points.append((math.cos(a) * rx, math.sin(a) * ry))
    return points


def island_mask(x: float, y: float, width: float, height: float) -> bool:
    rx = width * 0.48
    ry = height * 0.46
    wobble = 1.0 + 0.08 * math.sin(x / 900.0) + 0.06 * math.cos(y / 700.0)
    return ((x / rx) ** 2 + (y / ry) ** 2) <= wobble


def centered_bounds(width: float, height: float) -> tuple[float, float, float, float]:
    return (-width / 2.0, -height / 2.0, width / 2.0, height / 2.0)


def distance_to_polyline(point: tuple[float, float], polyline: list[tuple[float, float]]) -> float:
    if len(polyline) < 2:
        return math.inf
    return min(distance_to_segment(point, a, b) for a, b in zip(polyline, polyline[1:]))


def distance_to_segment(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    px, py = point
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = clamp(((px - ax) * dx + (py - ay) * dy) / length_sq, 0.0, 1.0)
    cx = ax + t * dx
    cy = ay + t * dy
    return math.hypot(px - cx, py - cy)


def edge_density_bonus(x: float, y: float, bounds: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = bounds
    edge_dist = min(abs(x - x0), abs(x - x1), abs(y - y0), abs(y - y1))
    max_dist = min(x1 - x0, y1 - y0) * 0.5
    return 1.0 - clamp(edge_dist / max(max_dist, 1.0), 0.0, 1.0)


def vary_scale(
    scale: tuple[float, float, float],
    rng: random.Random,
    *,
    xy: float,
    z: float,
) -> tuple[float, float, float]:
    sx, sy, sz = scale
    xy_factor = rng.uniform(1.0 - xy, 1.0 + xy)
    z_factor = rng.uniform(1.0 - z, 1.0 + z) if z else 1.0
    return sx * xy_factor, sy * xy_factor, sz * z_factor


def load_actor_targets(
    index_path: Path,
    profiles: Iterable[TerrainProfile],
    webassets_root: Path | None = None,
) -> dict[str, ActorTarget]:
    index_doc = load_json(index_path)
    rows = index_doc.get("targets")
    if not isinstance(rows, list):
        raise TerrainError(f"{index_path} does not contain a targets list.")

    by_id = {str(row.get("target_id")): row for row in rows if isinstance(row, dict)}
    resolved_webassets_root = resolve_webassets_root(index_doc, webassets_root)
    targets: dict[str, ActorTarget] = {}
    for profile in profiles:
        row = by_id.get(profile.target_id)
        if not row:
            raise TerrainError(f"Target {profile.target_id!r} is missing from {index_path}.")
        if row.get("asset_kind") != "bp":
            raise TerrainError(f"Target {profile.target_id!r} is not a BP actor target.")
        export = row.get("export") or {}
        actor_class = str(export.get("actor_class") or "")
        class_path = str(export.get("class_path") or export.get("runtime_path") or "")
        if not actor_class or not class_path:
            raise TerrainError(f"Target {profile.target_id!r} is missing actor export metadata.")
        bounds_min_y, bounds_max_y = actor_bounds_y_from_components(row, resolved_webassets_root)
        if bounds_min_y is None or bounds_max_y is None:
            bounds_min_y, bounds_max_y = fallback_bounds_y(profile)
        targets[profile.target_id] = ActorTarget(
            target_id=profile.target_id,
            display_name=str(row.get("display_name") or profile.target_id),
            actor_class=actor_class,
            class_path=class_path,
            bounds_min_y=bounds_min_y,
            bounds_max_y=bounds_max_y,
        )
    return targets


def resolve_webassets_root(index_doc: dict[str, Any], explicit_root: Path | None) -> Path | None:
    if explicit_root:
        return explicit_root if explicit_root.exists() else None
    version = str(index_doc.get("version") or "")
    if not version:
        return None
    candidate = ROOT.parent / "RSDWModel" / version / "WebAssets"
    return candidate if candidate.exists() else None


def actor_bounds_y_from_components(row: dict[str, Any], webassets_root: Path | None) -> tuple[float | None, float | None]:
    if not webassets_root:
        return None, None
    components = row.get("components")
    if not isinstance(components, list):
        return None, None
    mins: list[float] = []
    maxs: list[float] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        gltf_path = str(component.get("gltf_path") or "")
        if not gltf_path:
            continue
        min_y, max_y = gltf_bounds_y(webassets_root / gltf_path)
        if min_y is not None and max_y is not None:
            mins.append(min_y)
            maxs.append(max_y)
    if not mins or not maxs:
        return None, None
    return min(mins), max(maxs)


def gltf_bounds_y(path: Path) -> tuple[float | None, float | None]:
    if not path.exists():
        return None, None
    doc = load_json(path)
    accessors = doc.get("accessors")
    meshes = doc.get("meshes")
    if not isinstance(accessors, list) or not isinstance(meshes, list):
        return None, None
    mins: list[float] = []
    maxs: list[float] = []
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
            min_values = accessor.get("min")
            max_values = accessor.get("max")
            if (
                isinstance(min_values, list)
                and isinstance(max_values, list)
                and len(min_values) >= 2
                and len(max_values) >= 2
            ):
                mins.append(float(min_values[1]))
                maxs.append(float(max_values[1]))
    if not mins or not maxs:
        return None, None
    return min(mins), max(maxs)


def validate_terrain_json(data: dict[str, Any], targets: dict[str, ActorTarget]) -> None:
    if data.get("schema") != SCHEMA:
        raise TerrainError(f"Unexpected schema {data.get('schema')!r}; expected {SCHEMA!r}.")
    if data.get("pieces") not in ([], None):
        raise TerrainError("Terrain generator output should not contain building pieces.")
    if data.get("items") not in ([], None):
        raise TerrainError("Terrain generator output should not contain items.")
    if int(data.get("count") or 0) != 0:
        raise TerrainError("Terrain generator count should remain 0 because no building pieces are emitted.")

    actors = data.get("actors")
    if not isinstance(actors, list) or not actors:
        raise TerrainError("Generated terrain JSON must contain at least one actor.")

    valid_classes = {target.actor_class for target in targets.values()}
    names: set[str] = set()
    for index, actor in enumerate(actors):
        if not isinstance(actor, dict):
            raise TerrainError(f"Actor at index {index} is not an object.")
        missing = [field for field in REQUIRED_ACTOR_FIELDS if field not in actor]
        if missing:
            raise TerrainError(f"Actor at index {index} is missing fields: {missing}")
        actor_name = str(actor.get("actor_name") or "")
        if not actor_name:
            raise TerrainError(f"Actor at index {index} has an empty actor_name.")
        if actor_name in names:
            raise TerrainError(f"Duplicate actor_name: {actor_name}")
        names.add(actor_name)
        if actor.get("actor_class") not in valid_classes:
            raise TerrainError(f"Actor {actor_name} uses an actor_class outside the terrain profile whitelist.")
        for field in ("x", "y", "z", "pitch", "yaw", "roll", "scale_x", "scale_y", "scale_z"):
            value = float(actor[field])
            if not math.isfinite(value):
                raise TerrainError(f"Actor {actor_name} has non-finite {field}.")
        if float(actor["scale_x"]) <= 0 or float(actor["scale_y"]) <= 0 or float(actor["scale_z"]) <= 0:
            raise TerrainError(f"Actor {actor_name} has a non-positive scale.")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def generated_unix(value: str) -> int:
    if str(value).lower() == "now":
        return int(datetime.now(timezone.utc).timestamp())
    return int(value)


def default_build_name(args: argparse.Namespace) -> str:
    return f"Procedural Terrain {args.preset} seed {args.seed}"


def default_output_path(args: argparse.Namespace) -> Path:
    stem = args.preset.replace("-", "_")
    return DEFAULT_OUTPUT_DIR / f"{stem}_{int(args.width)}x{int(args.height)}_seed{args.seed}.json"


def print_summary(data: dict[str, Any], output: Path) -> None:
    print(f"name: {data['name']}")
    print(f"actors: {len(data['actors'])}")
    print(f"pieces: {len(data['pieces'])}")
    print(f"items: {len(data['items'])}")
    print(f"output: {output}")


def rounded(value: float) -> int | float:
    rounded_value = round(float(value), 3)
    if rounded_value.is_integer():
        return int(rounded_value)
    return rounded_value


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive number")
    return parsed


def rate_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0.0 or parsed > 1.0:
        raise argparse.ArgumentTypeError("expected a value from 0 to 1")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
