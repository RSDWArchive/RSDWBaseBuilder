"""Verify the generated RSDW Base Builder browser index."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCHEMA = "RSDWBaseBuilder.WebIndex.v1"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_absolute_local_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value)) or value.startswith("\\\\")


def find_absolute_strings(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(find_absolute_strings(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_absolute_strings(child, f"{path}[{index}]"))
    elif isinstance(value, str) and is_absolute_local_path(value):
        found.append(f"{path}: {value}")
    return found


def parse_args() -> argparse.Namespace:
    root = repo_root()
    parser = argparse.ArgumentParser(description="Verify the RSDWBaseBuilder browser web index.")
    parser.add_argument("--index", type=Path, default=root / "website" / "basebuilder-index.json")
    parser.add_argument("--expected-targets", type=int, default=None)
    parser.add_argument("--expected-model-refs", type=int, default=None)
    parser.add_argument("--require-bp-web-previews", action="store_true")
    parser.add_argument("--allow-missing-required-icons", action="store_true",
                        help="Allow item/building-piece browser rows without icons for tolerant release validation.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = load_json(args.index)
    failures: list[str] = []
    if data.get("schema") != SCHEMA:
        failures.append(f"schema mismatch: {data.get('schema')!r}")
    targets = data.get("targets")
    if not isinstance(targets, list):
        failures.append("targets is not a list")
        targets = []
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    if args.expected_targets is not None and len(targets) != args.expected_targets:
        failures.append(f"target count {len(targets)} != expected {args.expected_targets}")
    if args.expected_model_refs is not None and int(summary.get("unique_model_refs") or 0) != args.expected_model_refs:
        failures.append(
            f"unique_model_refs {summary.get('unique_model_refs')} != expected {args.expected_model_refs}"
        )
    if find_absolute_strings(data):
        failures.append("index contains local absolute paths")

    seen_ids: set[str] = set()
    icon_count = 0
    web_preview_count = 0
    bp_count = 0
    for target in targets:
        target_id = str(target.get("target_id") or "")
        if not target_id:
            failures.append("target without target_id")
            continue
        if target_id in seen_ids:
            failures.append(f"duplicate target_id: {target_id}")
        seen_ids.add(target_id)
        kind = target.get("asset_kind")
        if kind not in {"building_piece", "item", "bp"}:
            failures.append(f"{target_id}: invalid asset_kind {kind!r}")
        icon_path = str(target.get("icon_path") or "")
        if icon_path:
            icon_count += 1
        if kind in {"building_piece", "item"} and not icon_path and not args.allow_missing_required_icons:
            failures.append(f"{target_id}: missing browser icon_path")
        if kind == "bp" and icon_path:
            failures.append(f"{target_id}: BP target should not carry a custom icon_path")
        web_preview_path = str(target.get("web_preview_path") or "")
        if web_preview_path:
            web_preview_count += 1
        if kind == "bp":
            bp_count += 1
            if args.require_bp_web_previews and not web_preview_path:
                failures.append(f"{target_id}: missing BP web_preview_path")
        elif web_preview_path:
            failures.append(f"{target_id}: only BP targets should carry web_preview_path")
        components = target.get("components")
        if not isinstance(components, list) or not components:
            failures.append(f"{target_id}: missing components")
            continue
        for component in components:
            if not component.get("model_ref"):
                failures.append(f"{target_id}: component missing model_ref")
            if not component.get("gltf_path"):
                failures.append(f"{target_id}: component missing gltf_path")

    report = {
        "index": str(args.index),
        "targets": len(targets),
        "unique_model_refs": summary.get("unique_model_refs"),
        "unique_component_model_refs": summary.get("unique_component_model_refs"),
        "snap_class_count": summary.get("snap_class_count"),
        "icon_count": icon_count,
        "allow_missing_required_icons": args.allow_missing_required_icons,
        "web_preview_count": web_preview_count,
        "bp_count": bp_count,
        "failed": len(failures),
        "failure_examples": failures[:20],
    }
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
