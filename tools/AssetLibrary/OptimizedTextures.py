"""Helpers for reusing RSDWModel's optimized WebP texture cache."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _norm_rel(value: str) -> str:
    return str(value or "").replace("\\", "/").strip().lstrip("/")


def is_unreal_helper_texture(rel_path: str) -> bool:
    rel = _norm_rel(rel_path).lower()
    if Path(rel).suffix != ".hdr":
        return False
    return (
        "/curveatlases/" in rel
        or "/engine_materialfunctions02/" in rel
        or "/haircolourcurves/" in rel
        or "/pivpaintertextures/" in rel
        or "/pivotpainter2/" in rel
    )


def is_web_texture_candidate(rel_path: str) -> bool:
    return bool(_norm_rel(rel_path)) and not is_unreal_helper_texture(rel_path)


def load_web_asset_texture_map(manifest_path: Path) -> tuple[dict[str, Path], dict[str, Any]]:
    """Return {source-relative texture path -> optimized WebP path} from RSDWModel."""
    manifest_path = manifest_path.resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    web_assets_root = manifest_path.parent
    texture_map: dict[str, Path] = {}
    for source_rel, row in (data.get("textures") or {}).items():
        if not isinstance(source_rel, str) or source_rel.startswith("generated:"):
            continue
        if not is_web_texture_candidate(source_rel):
            continue
        if not isinstance(row, dict):
            continue
        optimized = row.get("optimized")
        if not isinstance(optimized, str) or not optimized:
            continue
        if row.get("status") == "failed":
            continue
        optimized_abs = (web_assets_root / optimized).resolve()
        if optimized_abs.is_file():
            texture_map[_norm_rel(source_rel).lower()] = optimized_abs
    return texture_map, dict(data.get("texture_profile") or {})


def candidate_source_rels(path: Path, roots: list[Path]) -> list[str]:
    """Return possible RSDWModel manifest keys for an absolute texture path."""
    path = path.resolve()
    out: list[str] = []

    def add(value: str) -> None:
        value = _norm_rel(value)
        if value and value not in out:
            out.append(value)

    for root in roots:
        try:
            rel = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        add(rel)
        parts = Path(rel).parts
        if parts and parts[0].lower() in {"json", "textures"} and len(parts) > 1:
            add("/".join(parts[1:]))

    parts = path.parts
    lowered = [part.lower() for part in parts]
    for anchor in ("rsdragonwilds", "engine"):
        if anchor in lowered:
            idx = lowered.index(anchor)
            add("/".join(parts[idx:]))

    return out


def install_web_texture_loader(
    base_module: Any,
    *,
    source_root: Path,
    data_roots: list[Path],
    manifest_path: Path | None,
) -> dict[str, Any]:
    """Patch BuildGLBWorker._load_image so it loads optimized WebPs when possible."""
    stats: dict[str, Any] = {
        "enabled": False,
        "manifest": str(manifest_path.resolve()) if manifest_path else None,
        "texture_profile": {},
        "texture_map_count": 0,
        "hits": [],
        "misses": [],
    }
    if manifest_path is None:
        return stats
    if not manifest_path.is_file():
        stats["misses"].append({"reason": "manifest_missing", "path": str(manifest_path)})
        return stats

    texture_map, texture_profile = load_web_asset_texture_map(manifest_path)
    stats["enabled"] = True
    stats["texture_profile"] = texture_profile
    stats["texture_map_count"] = len(texture_map)

    original_load_image = base_module._load_image
    roots = [source_root.resolve(), *[root.resolve() for root in data_roots]]

    def _load_optimized_image(abs_path: Path, non_color: bool):
        abs_path = Path(abs_path)
        rels = candidate_source_rels(abs_path, roots)
        if rels and not is_web_texture_candidate(rels[0]):
            return None
        for rel in rels:
            optimized = texture_map.get(rel.lower())
            if optimized is None:
                continue
            image = original_load_image(optimized, non_color)
            if image is not None:
                stats["hits"].append({"source": rel, "optimized": str(optimized)})
                return image
        if rels:
            stats["misses"].append({"source": rels[0], "path": str(abs_path)})
        return original_load_image(abs_path, non_color)

    base_module._load_image = _load_optimized_image
    return stats


def compact_web_texture_stats(stats: dict[str, Any], *, sample_count: int = 25) -> dict[str, Any]:
    def unique_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        out: list[dict[str, Any]] = []
        for row in rows:
            key = (str(row.get("source") or row.get("reason") or ""), str(row.get("optimized") or row.get("path") or ""))
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    hits = unique_rows(list(stats.get("hits") or []))
    misses = unique_rows(list(stats.get("misses") or []))
    return {
        "enabled": bool(stats.get("enabled")),
        "manifest": stats.get("manifest"),
        "texture_profile": stats.get("texture_profile") or {},
        "texture_map_count": int(stats.get("texture_map_count") or 0),
        "hit_count": len(hits),
        "miss_count": len(misses),
        "hit_examples": hits[:sample_count],
        "miss_examples": misses[:sample_count],
    }
