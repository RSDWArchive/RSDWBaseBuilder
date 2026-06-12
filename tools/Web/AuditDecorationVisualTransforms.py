"""Audit decoration building-piece visual transforms in the browser index."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "RSDWBaseBuilder.DecorationVisualTransformAudit.v1"
WEB_INDEX_SCHEMA = "RSDWBaseBuilder.WebIndex.v1"
ANGLE_EPSILON = 0.001
VALUE_EPSILON = 0.0001


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def number_or(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isfinite(number):
        return number
    return default


def normalize_number(value: float) -> int | float:
    if abs(value) < VALUE_EPSILON:
        return 0
    rounded = round(value, 6)
    if abs(rounded - round(rounded)) < VALUE_EPSILON:
        return int(round(rounded))
    return rounded


def normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [normalize_value(child) for child in value]
    if isinstance(value, (int, float)):
        return normalize_number(float(value))
    return value


def transforms_match(left: Any, right: Any) -> bool:
    return normalize_value(left or {}) == normalize_value(right or {})


def angle_value(rotation: dict[str, Any], key: str) -> float:
    return number_or(rotation.get(key) if key in rotation else rotation.get(key.lower()))


def has_pitch_or_roll(transform: dict[str, Any]) -> bool:
    rotation = transform.get("rotation") if isinstance(transform.get("rotation"), dict) else {}
    return (
        abs(angle_value(rotation, "Pitch")) > ANGLE_EPSILON
        or abs(angle_value(rotation, "Roll")) > ANGLE_EPSILON
    )


def is_identity_transform(transform: dict[str, Any]) -> bool:
    return normalize_value(transform or {}) == {}


def rounded_rotation_key(transform: dict[str, Any]) -> str:
    rotation = transform.get("rotation") if isinstance(transform.get("rotation"), dict) else {}
    pitch = round(angle_value(rotation, "Pitch"))
    yaw = round(angle_value(rotation, "Yaw"))
    roll = round(angle_value(rotation, "Roll"))
    return f"{pitch}/{yaw}/{roll}"


def target_text(target: dict[str, Any]) -> str:
    export = target.get("export") if isinstance(target.get("export"), dict) else {}
    fields = [
        target.get("catalog_path"),
        target.get("target_id"),
        target.get("asset_stem"),
        target.get("display_name"),
        export.get("bp_class"),
        export.get("class_name"),
        export.get("piece_data_name"),
    ]
    return " ".join(str(field or "") for field in fields).casefold()


def is_decoration_like(target: dict[str, Any], include_misc: bool) -> bool:
    if target.get("asset_kind") != "building_piece":
        return False
    catalog_path = str(target.get("catalog_path") or "").replace("\\", "/")
    text = target_text(target)
    if "building pieces/decorations" in catalog_path.casefold():
        return True
    if "decoration" in text:
        return True
    if include_misc and "building pieces/misc" in catalog_path.casefold():
        return True
    return False


def bp_class_for(target: dict[str, Any]) -> str:
    export = target.get("export") if isinstance(target.get("export"), dict) else {}
    return str(export.get("bp_class") or "")


def bp_class_keys(target: dict[str, Any]) -> set[str]:
    export = target.get("export") if isinstance(target.get("export"), dict) else {}
    keys = {
        str(target.get("target_id") or "").removeprefix("bp:"),
        str(export.get("bp_class") or ""),
    }
    return {key for key in keys if key}


def component_key(component: dict[str, Any]) -> str:
    return str(component.get("model_ref") or component.get("gltf_path") or component.get("name") or "")


def brief_target(target: dict[str, Any]) -> dict[str, Any]:
    export = target.get("export") if isinstance(target.get("export"), dict) else {}
    return {
        "target_id": str(target.get("target_id") or ""),
        "display_name": str(target.get("display_name") or ""),
        "catalog_path": str(target.get("catalog_path") or ""),
        "bp_class": str(export.get("bp_class") or ""),
        "piece_data_index": export.get("piece_data_index"),
    }


def parse_args() -> argparse.Namespace:
    root = repo_root()
    parser = argparse.ArgumentParser(
        description="Audit decoration building-piece component transforms against their BP source visuals."
    )
    parser.add_argument("--index", type=Path, default=root / "website" / "basebuilder-index.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--include-misc",
        action="store_true",
        help="Also scan every Building Pieces/Misc target, even if it is not explicitly decoration-like.",
    )
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Return a non-zero exit code when pitch/roll review candidates are present.",
    )
    parser.add_argument("--max-examples", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = load_json(args.index)
    failures: list[str] = []
    if data.get("schema") != WEB_INDEX_SCHEMA:
        failures.append(f"schema mismatch: {data.get('schema')!r}")
    targets = data.get("targets")
    if not isinstance(targets, list):
        failures.append("targets is not a list")
        targets = []

    bp_by_class: dict[str, dict[str, Any]] = {}
    for target in targets:
        if isinstance(target, dict) and target.get("asset_kind") == "bp":
            for key in bp_class_keys(target):
                bp_by_class[key] = target

    scanned = [target for target in targets if isinstance(target, dict) and is_decoration_like(target, args.include_misc)]
    issues: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    rotation_bins: Counter[str] = Counter()
    counts: Counter[str] = Counter()

    for target in scanned:
        counts["targets_scanned"] += 1
        bp_class = bp_class_for(target)
        bp_target = bp_by_class.get(bp_class)
        if bp_target is None:
            counts["missing_bp_target"] += 1
            issues.append({
                "severity": "error",
                "reason": "missing_bp_target",
                **brief_target(target),
            })
            continue

        bp_components = [
            component
            for component in bp_target.get("components", [])
            if isinstance(component, dict)
        ]
        bp_components_by_key = {component_key(component): component for component in bp_components if component_key(component)}
        components = [
            component
            for component in target.get("components", [])
            if isinstance(component, dict)
        ]
        if not components:
            counts["missing_piece_components"] += 1
            issues.append({
                "severity": "error",
                "reason": "missing_piece_components",
                **brief_target(target),
            })
            continue

        for component in components:
            counts["components_scanned"] += 1
            key = component_key(component)
            source_component = bp_components_by_key.get(key)
            if source_component is None:
                counts["missing_matching_bp_component"] += 1
                issues.append({
                    "severity": "error",
                    "reason": "missing_matching_bp_component",
                    "component": str(component.get("name") or ""),
                    "model_ref": str(component.get("model_ref") or ""),
                    **brief_target(target),
                })
                continue

            transform = component.get("transform") if isinstance(component.get("transform"), dict) else {}
            source_transform = (
                source_component.get("transform")
                if isinstance(source_component.get("transform"), dict)
                else {}
            )
            rotation_bins[rounded_rotation_key(transform)] += 1
            if is_identity_transform(transform):
                counts["identity_components"] += 1
            elif has_pitch_or_roll(transform):
                counts["pitch_roll_components"] += 1
                if len(review) < args.max_examples:
                    review.append({
                        "reason": "component_pitch_or_roll_transform",
                        "component": str(component.get("name") or ""),
                        "model_ref": str(component.get("model_ref") or ""),
                        "rotation": transform.get("rotation") or {},
                        **brief_target(target),
                    })
            else:
                counts["yaw_or_offset_components"] += 1

            if transforms_match(transform, source_transform):
                counts["matching_component_transforms"] += 1
            else:
                counts["mismatched_component_transforms"] += 1
                issues.append({
                    "severity": "error",
                    "reason": "mismatched_component_transform",
                    "component": str(component.get("name") or ""),
                    "model_ref": str(component.get("model_ref") or ""),
                    "piece_transform": normalize_value(transform),
                    "bp_transform": normalize_value(source_transform),
                    **brief_target(target),
                })

    hard_failures = [issue for issue in issues if issue.get("severity") == "error"]
    if args.fail_on_review and counts["pitch_roll_components"]:
        failures.append(f"{counts['pitch_roll_components']} pitch/roll review candidates present")
    if hard_failures:
        failures.append(f"{len(hard_failures)} decoration visual transform audit errors")

    report = {
        "schema": SCHEMA,
        "generated_at_utc": now_iso(),
        "index": str(args.index),
        "include_misc": bool(args.include_misc),
        "summary": {
            "targets_scanned": counts["targets_scanned"],
            "components_scanned": counts["components_scanned"],
            "matching_component_transforms": counts["matching_component_transforms"],
            "mismatched_component_transforms": counts["mismatched_component_transforms"],
            "missing_bp_target": counts["missing_bp_target"],
            "missing_piece_components": counts["missing_piece_components"],
            "missing_matching_bp_component": counts["missing_matching_bp_component"],
            "identity_components": counts["identity_components"],
            "yaw_or_offset_components": counts["yaw_or_offset_components"],
            "pitch_roll_components": counts["pitch_roll_components"],
            "hard_errors": len(hard_failures),
            "failed": bool(failures),
        },
        "rotation_bins": dict(sorted(rotation_bins.items())),
        "issue_examples": issues[: args.max_examples],
        "pitch_roll_review_examples": review,
        "failures": failures,
    }

    if args.out is not None:
        write_json(args.out, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
