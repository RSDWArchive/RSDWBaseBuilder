"""
Driver: batch-build per-piece asset .blend files for every SM_*.uemodel listed
in SM_Data.json. Writes one .blend per piece under the asset library tree,
with each piece's materials linked from the shared _Materials.blend.

Reuses the parallel/progress-manifest infrastructure pattern from
BuildGLB.py and adds asset-library specific bits:
  - per-entry catalog UUID (via tools/AssetLibrary/catalog.py)
  - per-entry preview policy (target icons or generated Blender previews)
  - shared _Materials.blend reference handed to each worker

Example:
    python tools/AssetLibrary/BuildAssetLibrary.py
    python tools/AssetLibrary/BuildAssetLibrary.py --limit 5 --only T1_Door
    python tools/AssetLibrary/BuildAssetLibrary.py --workers 8 --force
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Local import (tools/AssetLibrary/catalog.py)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import categorize, catalog_uuid  # noqa: E402


PROGRESS_SCHEMA = "RSDWModel.AssetLibraryProgress.v1"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _default_blender() -> Path:
    env_path = os.environ.get("BLENDER_EXE")
    root = _repo_root()
    candidates = [
        root / "_local" / "blender-5.0.0-windows-x64" / "blender.exe",
    ]
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend([
        Path(r"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe"),
        Path(r"C:/Program Files/Blender Foundation/Blender 4.5/blender.exe"),
    ])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0] if candidates else root / "blender.exe"


def _latest_version_root(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    versions: list[Path] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        parts = child.name.split(".")
        if parts and all(part.isdigit() for part in parts):
            versions.append(child)
    if not versions:
        return None
    versions.sort(key=lambda path: tuple(int(part) for part in path.name.split(".")))
    return versions[-1]


def _default_source_root() -> Path:
    model_root = Path(r"E:/Github/RSDWModel")
    latest = _latest_version_root(model_root)
    return latest or (_repo_root() / "0.11.1.4")


def _default_web_assets_manifest(source_root: Path) -> Path | None:
    candidate = source_root / "WebAssets" / "WebAssetManifest.json"
    return candidate if candidate.is_file() else None


def _default_material_data_roots() -> list[Path]:
    archive_root = _latest_version_root(Path(r"E:/Github/RSDWArchive")) or Path(r"E:/Github/RSDWArchive/0.11.1.4")
    return [archive_root / "json", archive_root / "textures"]


def _default_sm_data() -> Path:
    return _repo_root() / "tools" / "ModelData" / "SM_Data.json"


def _default_icon_map() -> Path:
    # Prefer V3 (DA-driven authoritative map) when present; fall back to V2.
    v3 = _repo_root() / "tools" / "Icons" / "IconMap.v3.json"
    if v3.is_file():
        return v3
    return _repo_root() / "tools" / "Icons" / "IconMap.json"


def _default_materials_blend() -> Path:
    return _default_library_root() / "_Materials.blend"


def _default_library_root() -> Path:
    return _repo_root() / "_build" / "extension"


def _default_progress_file() -> Path:
    return Path(__file__).resolve().parent / "AssetLibraryProgress.json"


def _default_worker() -> Path:
    return Path(__file__).resolve().parent / "BuildAssetLibraryWorker.py"


def _default_category_icon_root() -> Path:
    # Category fallback icons live under the archive's UI/Building/Icons/Categories folder.
    archive_root = _latest_version_root(Path(r"E:/Github/RSDWArchive")) or Path(r"E:/Github/RSDWArchive/0.11.1.4")
    return archive_root / "textures" / "RSDragonwilds" / "Content" / "Art" / "UI" / "Building" / "Icons" / "Categories"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel_to_repo(p: Path) -> str:
    try:
        return p.resolve().relative_to(_repo_root().resolve()).as_posix()
    except ValueError:
        return p.resolve().as_posix()


# ---------------------------------------------------------------------------
# Category icon fallback
# ---------------------------------------------------------------------------

# Keyword -> category icon stem. First match wins.
_CATEGORY_ICON_RULES: list[tuple[str, str]] = [
    ("door", "T_Build_Category_IconWalls"),
    ("window", "T_Build_Category_IconWalls"),
    ("wall", "T_Build_Category_IconWalls"),
    ("floor", "T_Build_Category_IconFloorsStairs"),
    ("stair", "T_Build_Category_IconFloorsStairs"),
    ("ramp", "T_Build_Category_IconFloorsStairs"),
    ("roof", "T_Build_Category_IconRoofs"),
    ("beam", "T_Build_Category_IconBeams"),
    ("post", "T_Build_Category_IconBeams"),
    ("pillar", "T_Build_Category_IconBeams"),
    ("column", "T_Build_Category_IconBeams"),
    ("strut", "T_Build_Category_IconBeams"),
    ("brace", "T_Build_Category_IconBeams"),
    ("bracket", "T_Build_Category_IconBeams"),
    ("rail", "T_Build_Category_IconBeams"),
    ("fence", "T_Build_Category_IconBeams"),
    ("alter", "T_Build_Category_IconPrayer"),
    ("altar", "T_Build_Category_IconPrayer"),
    ("shrine", "T_Build_Category_IconPrayer"),
]


def _resolve_category_icon(stem: str, catalog_path: str, category_icon_root: Path) -> Path | None:
    name = stem.lower()
    chosen: str | None = None
    for kw, icon_stem in _CATEGORY_ICON_RULES:
        if kw in name:
            chosen = icon_stem
            break
    if chosen is None:
        # Catalog-based fallback. There's no dedicated Crafting icon in the
        # archive; Crafting Stations and Farming both fall back to IconGeneral.
        cat = catalog_path.lower()
        if "furniture" in cat:
            chosen = "T_Build_Category_IconFurniture"
        else:
            chosen = "T_Build_Category_IconGeneral"
    icon = category_icon_root / f"{chosen}.png"
    return icon if icon.is_file() else None


def _resolve_icon_map_path(raw_path: str, search_roots: list[Path]) -> Path | None:
    """Resolve an IconMap path against the current Archive texture root.

    Older generated icon maps store absolute paths into a specific archive
    version. When that version is not present, keep the useful
    RSDragonwilds/... suffix and try the current texture root supplied by the
    pipeline.
    """
    if not raw_path:
        return None
    direct = Path(raw_path)
    if direct.is_file():
        return direct

    normalized = raw_path.replace("\\", "/")
    suffixes: list[str] = []
    for marker in ("RSDragonwilds/", "Engine/"):
        if marker in normalized:
            suffixes.append(normalized[normalized.index(marker):])
    if not suffixes and not direct.is_absolute():
        suffixes.append(normalized)

    for root in search_roots:
        if not root.is_dir():
            continue
        for suffix in suffixes:
            candidate = root / suffix
            if candidate.is_file():
                return candidate
    return None


# ---------------------------------------------------------------------------
# Progress manifest (mirrors BuildGLB pattern)
# ---------------------------------------------------------------------------

class ProgressManifest:
    def __init__(self, path: Path, source_root: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data: dict = {
            "manifest_schema": PROGRESS_SCHEMA,
            "started_utc": _now_utc(),
            "updated_utc": _now_utc(),
            "source_root": _rel_to_repo(source_root),
            "totals": {"success": 0, "failed": 0, "pending": 0},
            "entries": {},
        }
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded.get("manifest_schema") == PROGRESS_SCHEMA:
                    self.data = loaded
                    self.data["started_utc"] = self.data.get("started_utc") or _now_utc()
            except Exception:
                pass
        self._recount()

    def _recount(self) -> None:
        totals = {"success": 0, "failed": 0, "pending": 0}
        for e in self.data.get("entries", {}).values():
            s = e.get("status", "pending")
            totals[s if s in totals else "pending"] += 1
        self.data["totals"] = totals

    def get(self, key: str) -> dict | None:
        return self.data["entries"].get(key)

    def update(self, key: str, record: dict) -> None:
        with self.lock:
            self.data["entries"][key] = record
            self.data["updated_utc"] = _now_utc()
            self._recount()
            self._write_atomic()

    def totals(self) -> dict:
        return dict(self.data["totals"])

    def _write_atomic(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        last_err: Exception | None = None
        for attempt in range(10):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError as e:
                last_err = e
                time.sleep(0.1 * (attempt + 1))
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        sys.stderr.write(
            f"[progress] could not update {self.path.name} ({last_err})\n"
        )


# ---------------------------------------------------------------------------
# Worker invocation
# ---------------------------------------------------------------------------

def _parse_result_line(stdout: str) -> dict | None:
    last = None
    for line in stdout.splitlines():
        if line.startswith("RESULT:"):
            last = line[len("RESULT:"):].strip()
    if last is None:
        return None
    try:
        return json.loads(last)
    except Exception:
        return None


def _run_one(
    *,
    blender_exe: Path,
    worker_script: Path,
    source_root: Path,
    data_roots: list[Path],
    materials_blend: Path,
    materials_manifest: Path | None,
    out_blend: Path,
    entry: dict,
    catalog_path: str,
    catalog_id: str,
    icon_path: Path | None,
    preview_mode: str,
    icon_source: str,
    tags: list[str],
    description: str,
    asset_stem: str | None,
    asset_metadata: dict | None,
    material_mode: str,
    web_assets_manifest: Path | None,
    timeout_s: int,
) -> dict:
    task = {
        "source_root": str(source_root.resolve()),
        "data_roots": [str(root.resolve()) for root in data_roots],
        "materials_blend": str(materials_blend.resolve()),
        "materials_manifest": str(materials_manifest.resolve()) if materials_manifest else None,
        "out_blend": str(out_blend.resolve()),
        "entry": entry,
        "catalog_id": catalog_id,
        "catalog_path": catalog_path,
        "icon_path": str(icon_path.resolve()) if icon_path else None,
        "preview_mode": preview_mode,
        "icon_source": icon_source,
        "tags": tags,
        "description": description,
        "asset_stem": asset_stem,
        "asset_metadata": asset_metadata or {},
        "material_mode": material_mode,
        "pack_unmatched_textures": material_mode in {"fallback", "optimized-pbr"},
        "web_assets_manifest": str(web_assets_manifest.resolve()) if web_assets_manifest else None,
    }
    t0 = time.time()
    tf = None
    try:
        fd, task_path = tempfile.mkstemp(prefix="al_task_", suffix=".json")
        os.close(fd)
        tf = Path(task_path)
        tf.write_text(json.dumps(task), encoding="utf-8")
        cmd = [
            str(blender_exe),
            "--background",
            "--factory-startup",
            "--python", str(worker_script),
            "--",
            "--task-file", str(tf),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        elapsed = round(time.time() - t0, 3)
        result = _parse_result_line(proc.stdout or "")
        if result is None:
            tail = "\n".join((proc.stderr or "").splitlines()[-20:])
            return {
                "status": "failed",
                "error": f"no RESULT line (exit {proc.returncode})",
                "stderr_tail": tail,
                "duration_s": elapsed,
            }
        if proc.returncode != 0 and result.get("status") == "success":
            result = dict(result)
            result["status"] = "failed"
            result["error"] = f"{result.get('error', '')} (exit {proc.returncode})".strip()
        return result
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": f"timeout after {timeout_s}s",
                "duration_s": round(time.time() - t0, 3)}
    except Exception as e:
        return {"status": "failed", "error": f"{type(e).__name__}: {e}",
                "duration_s": round(time.time() - t0, 3)}
    finally:
        if tf is not None:
            try:
                tf.unlink(missing_ok=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Entry planning
# ---------------------------------------------------------------------------

def _select_entries(
    all_entries: list[dict], *,
    only_substr: str | None, only_paths: set[str] | None, limit: int | None,
) -> list[dict]:
    out = all_entries
    if only_substr:
        low = only_substr.lower()
        out = [e for e in out if low in e.get("name", "").lower() or low in e.get("path", "").lower()]
    if only_paths is not None:
        out = [e for e in out if e.get("path", "") in only_paths]
    if limit is not None and limit >= 0:
        out = out[:limit]
    return out


def _category_to_subdir(catalog_path: str) -> Path:
    """Map 'Building/Tier 1' -> Path('Building/Tier_1') for on-disk layout.
    Spaces are converted to underscores; slashes become directory separators."""
    parts = catalog_path.split("/")
    safe = ["_".join(p.split()) for p in parts]
    return Path(*safe)


def _plan_out_blend(library_root: Path, catalog_path: str, stem: str) -> Path:
    return library_root / _category_to_subdir(catalog_path) / f"{stem}.blend"


def _should_skip(
    key: str,
    progress: ProgressManifest,
    out_blend: Path,
    force: bool,
    *,
    preview_mode: str,
    material_mode: str,
    asset_kind: str = "",
) -> dict | None:
    if force:
        return None
    rec = progress.get(key)
    if not rec or rec.get("status") != "success":
        return None
    if rec.get("preview_mode") != preview_mode:
        return None
    if rec.get("material_mode") != material_mode:
        return None
    if asset_kind == "bp":
        if rec.get("bp_root_normalized") is not True:
            return None
        bp_audit = rec.get("bp_root_audit") or {}
        if bp_audit and bp_audit.get("root_identity_ok") is not True:
            return None
    if material_mode in {"fallback", "optimized-pbr", "base-color"} and not rec.get("material_quality"):
        return None
    if material_mode == "optimized-pbr" and not rec.get("web_texture_stats"):
        return None
    if material_mode in {"fallback", "optimized-pbr", "base-color"}:
        quality = rec.get("material_quality") or {}
        try:
            slot_count = int(quality.get("slot_count") or 0)
            materialized_slot_count = int(quality.get("materialized_slot_count") or 0)
            base_color_slot_count = int(quality.get("base_color_slot_count") or 0)
        except (TypeError, ValueError):
            slot_count = 0
            materialized_slot_count = 0
            base_color_slot_count = 0
        if slot_count > 0 and materialized_slot_count <= 0:
            return None
        if material_mode == "base-color" and slot_count > 0 and base_color_slot_count <= 0:
            return None
    if preview_mode == "custom_icon" and rec.get("preview_source") != "custom_icon":
        return None
    if preview_mode == "generated" and rec.get("preview_source") not in {"generated", "blender_default"}:
        return None
    out_blend_rel = rec.get("out_blend_rel")
    if out_blend_rel and out_blend.is_file():
        return rec
    if out_blend.is_file():
        return rec
    return None


def _load_catalog_targets(target_file: Path, entries_by_path: dict[str, dict]) -> list[dict]:
    doc = json.loads(target_file.read_text(encoding="utf-8"))
    out: list[dict] = []
    for target in doc.get("targets", []):
        source_path = target.get("source_entry_path", "")
        entry = target.get("source_entry") or entries_by_path.get(source_path)
        if entry is None:
            continue
        out.append({"target": target, "entry": entry})
    return out


def _log(msg: str) -> None:
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Batch build per-piece asset .blend files.")
    p.add_argument("--data-file", type=Path, default=_default_sm_data())
    p.add_argument("--extra-data-file", type=Path, action="append", default=[],
                   help="Additional model inventory JSONs, e.g. SK_Data.json for catalog targets.")
    p.add_argument("--source-root", type=Path, default=_default_source_root())
    p.add_argument("--material-data-root", type=Path, action="append", default=None,
                   help="Supplemental root for material JSONs/textures; repeatable. Defaults to RSDWArchive json/textures roots when present.")
    p.add_argument("--library-root", type=Path, default=_default_library_root(),
                   help="Where per-piece .blend files are written (asset library root).")
    p.add_argument("--materials-blend", type=Path, default=_default_materials_blend(),
                   help="Path to the shared _Materials.blend that pieces link to.")
    p.add_argument("--materials-manifest", type=Path, default=None,
                   help="Optional sharded shared-material manifest.")
    p.add_argument("--material-mode", choices=("optimized-pbr", "fallback", "base-color", "light", "none"), default="optimized-pbr",
                   help="optimized-pbr links real PBR materials using the RSDWModel WebP cache; fallback builds textured materials from source textures; base-color writes flat local colors; light links existing shared materials; none skips material work.")
    p.add_argument("--web-assets-manifest", type=Path, default=None,
                   help="Optional RSDWModel WebAssets/WebAssetManifest.json used by optimized-pbr material builds.")
    p.add_argument("--icon-map", type=Path, default=_default_icon_map())
    p.add_argument("--category-icon-root", type=Path, default=_default_category_icon_root())
    p.add_argument("--blender", type=Path, default=_default_blender())
    p.add_argument("--worker", type=Path, default=_default_worker())
    p.add_argument("--progress-file", type=Path, default=_default_progress_file())
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    p.add_argument("--timeout-s", type=int, default=300)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--only", type=str, default=None)
    p.add_argument("--only-list", type=Path, default=None)
    p.add_argument("--target-file", type=Path, default=None,
                   help="Catalog-shaped targets from BuildCatalogAssetTargets.py.")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if args.web_assets_manifest is None:
        args.web_assets_manifest = _default_web_assets_manifest(args.source_root)

    material_data_roots = [
        root for root in (args.material_data_root or _default_material_data_roots())
        if root.exists()
    ]

    for path, label in [
        (args.blender, "blender.exe"),
        (args.worker, "worker script"),
        (args.source_root, "source root"),
        (args.data_file, "data inventory"),
        (args.web_assets_manifest, "web assets manifest"),
    ]:
        if path is not None and not path.exists():
            _log(f"{label} not found: {path}")
            return 2
    if args.material_mode in {"optimized-pbr", "fallback", "light"} and args.materials_manifest is None:
        default_manifest = args.library_root / "_Materials.manifest.json"
        args.materials_manifest = default_manifest if default_manifest.is_file() else None
    if (
        args.material_mode in {"optimized-pbr", "fallback", "light"}
        and not args.materials_blend.exists()
        and not (args.materials_manifest and args.materials_manifest.exists())
    ):
        _log(f"shared materials.blend not found; workers will build local fallback materials: {args.materials_blend}")

    # icon_map_by_path: keyed by uemodel entry path (V2 schema)
    # icon_map_by_stem: keyed by SM stem            (V3 schema)
    icon_map_by_path: dict[str, str] = {}
    icon_map_by_stem: dict[str, str] = {}
    if args.icon_map.is_file():
        try:
            d = json.loads(args.icon_map.read_text(encoding="utf-8"))
            if "by_sm_stem" in d:
                icon_map_by_stem = dict(d.get("by_sm_stem") or {})
                _log(f"IconMap V3 loaded: {len(icon_map_by_stem)} per-stem icons")
            else:
                icon_map_by_path = dict(d.get("matches") or {})
                _log(f"IconMap V2 loaded: {len(icon_map_by_path)} per-piece icons")
        except Exception as e:
            _log(f"WARNING: could not load icon map: {e}")

    inventory = json.loads(args.data_file.read_text(encoding="utf-8"))
    entries: list[dict] = list(inventory.get("entries", []))
    for extra_data_file in args.extra_data_file:
        if not extra_data_file.is_file():
            _log(f"--extra-data-file not found: {extra_data_file}")
            return 2
        extra_inventory = json.loads(extra_data_file.read_text(encoding="utf-8"))
        entries.extend(extra_inventory.get("entries", []))
    if not entries:
        _log("No entries to process.")
        return 0
    _log(f"Inventory: {args.data_file.name} ({len(entries)} entries)")
    if material_data_roots:
        _log("Material data roots: " + ", ".join(str(root) for root in material_data_roots))

    only_paths: set[str] | None = None
    if args.only_list is not None:
        if not args.only_list.is_file():
            _log(f"--only-list not found: {args.only_list}")
            return 2
        only_paths = set()
        for line in args.only_list.read_text(encoding="utf-8").splitlines():
            cleaned = line.strip().lstrip("\ufeff")
            if cleaned and not cleaned.startswith("#"):
                only_paths.add(cleaned)

    entries_by_path = {entry.get("path", ""): entry for entry in entries}
    target_items: list[dict] | None = None
    if args.target_file is not None:
        if not args.target_file.is_file():
            _log(f"--target-file not found: {args.target_file}")
            return 2
        target_items = _load_catalog_targets(args.target_file, entries_by_path)
        if args.only:
            low = args.only.lower()
            target_items = [
                item for item in target_items
                if low in item["target"].get("target_id", "").lower()
                or low in item["target"].get("asset_stem", "").lower()
                or low in item["target"].get("source_sm_stem", "").lower()
                or low in item["target"].get("piece_data_name", "").lower()
            ]
        if only_paths is not None:
            target_items = [
                item for item in target_items
                if item["target"].get("target_id") in only_paths
                or item["target"].get("source_entry_path") in only_paths
            ]
        if args.limit is not None and args.limit >= 0:
            target_items = target_items[:args.limit]
        selected = [item["entry"] for item in target_items]
    else:
        selected = _select_entries(entries, only_substr=args.only, only_paths=only_paths, limit=args.limit)
    progress = ProgressManifest(args.progress_file, args.source_root)

    args.library_root.mkdir(parents=True, exist_ok=True)

    # Pre-plan per-entry: catalog path / UUID / icon / out path.
    plans: list[dict] = []
    pre_skipped = 0
    plan_inputs = target_items if target_items is not None else [{"entry": e, "target": None} for e in selected]
    for item in plan_inputs:
        e = item["entry"]
        target = item.get("target")
        cat = target.get("catalog_path") if target else categorize(e["path"])
        cuid = str(catalog_uuid(cat))
        stem = target.get("asset_stem") if target else Path(e["path"]).stem
        source_stem = target.get("source_sm_stem") if target else stem
        out_blend = _plan_out_blend(args.library_root, cat, stem)
        icon: Path | None = None
        icon_source = ""
        preview_mode = "generated"
        if target:
            asset_kind = str(target.get("asset_kind") or "")
            icon_source = str(target.get("icon_source") or "")
            if asset_kind == "bp":
                # Blueprint assets intentionally rely on Blender's asset browser
                # object previews. Only item/building-piece targets should carry
                # custom icon image previews.
                preview_mode = "generated"
                icon = None
            else:
                preview_mode = str(target.get("preview_mode") or "generated")
            if asset_kind != "bp" and preview_mode == "custom_icon":
                target_icon = target.get("icon_path")
                if target_icon:
                    cand = Path(target_icon)
                    if cand.is_file():
                        icon = cand
        else:
            # Legacy direct-script mode keeps the old IconMap/category fallback.
            m = icon_map_by_stem.get(stem) or icon_map_by_stem.get(source_stem) or icon_map_by_path.get(e["path"])
            if m:
                icon = _resolve_icon_map_path(m, material_data_roots)
                icon_source = "icon_map"
            if icon is None:
                icon = _resolve_category_icon(stem, cat, args.category_icon_root)
                icon_source = "category_fallback" if icon else ""
            preview_mode = "custom_icon" if icon else "generated"

        plan = {
            "entry": e,
            "target": target,
            "key": target.get("target_id") if target else e["path"],
            "stem": stem,
            "source_stem": source_stem,
            "source_root": Path(target.get("source_root")) if target and target.get("source_root") else args.source_root,
            "catalog_path": cat,
            "catalog_id": cuid,
            "icon_path": icon,
            "preview_mode": preview_mode,
            "icon_source": icon_source,
            "out_blend": out_blend,
        }
        if _should_skip(
            plan["key"],
            progress,
            out_blend,
            args.force,
            preview_mode=preview_mode,
            material_mode=args.material_mode,
            asset_kind=str((target or {}).get("asset_kind") or ""),
        ):
            pre_skipped += 1
            continue
        plans.append(plan)

    _log(f"Selected {len(selected)} (skipped already-built: {pre_skipped}), "
         f"running {len(plans)} with {args.workers} workers")
    if args.dry_run:
        for pl in plans[:50]:
            _log(f"  {pl['stem']:42s}  catalog={pl['catalog_path']}  "
                 f"preview={pl['preview_mode']}  icon={'yes' if pl['icon_path'] else 'NO'}")
        if len(plans) > 50:
            _log(f"  ... ({len(plans) - 50} more)")
        return 0
    if not plans:
        _log("Nothing to do.")
        return 0

    total = len(plans)
    done = 0
    ok = 0
    fail = 0
    start = time.time()

    in_flight: dict[str, float] = {}
    in_flight_lock = threading.Lock()
    stop_heartbeat = threading.Event()

    def _task(pl: dict) -> tuple[dict, dict]:
        e = pl["entry"]
        key = e["path"]
        with in_flight_lock:
            in_flight[key] = time.time()
        try:
            res = _run_one(
                blender_exe=args.blender,
                worker_script=args.worker,
                source_root=pl["source_root"],
                data_roots=material_data_roots,
                materials_blend=args.materials_blend,
                materials_manifest=args.materials_manifest,
                out_blend=pl["out_blend"],
                entry=e,
                catalog_path=pl["catalog_path"],
                catalog_id=pl["catalog_id"],
                icon_path=pl["icon_path"],
                preview_mode=pl["preview_mode"],
                icon_source=pl["icon_source"],
                tags=[pl["catalog_path"].split("/")[0]],
                description=(pl.get("target") or {}).get("display_name", ""),
                asset_stem=pl["stem"] if pl.get("target") else None,
                asset_metadata=pl.get("target"),
                material_mode=args.material_mode,
                web_assets_manifest=args.web_assets_manifest,
                timeout_s=args.timeout_s,
            )
        finally:
            with in_flight_lock:
                in_flight.pop(key, None)
        return pl, res

    def _heartbeat() -> None:
        interval = 10.0
        while not stop_heartbeat.wait(interval):
            with in_flight_lock:
                snap = list(in_flight.items())
            now = time.time()
            elapsed = now - start
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (total - done) / rate if rate > 0 else 0
            oldest_name = "-"
            oldest_age = 0.0
            if snap:
                oldest_key, oldest_t0 = max(snap, key=lambda kv: now - kv[1])
                oldest_age = now - oldest_t0
                oldest_name = Path(oldest_key).name
            _log(f"[heartbeat] {done}/{total}  active={len(snap)}  "
                 f"elapsed={elapsed:.0f}s  eta={eta:.0f}s  "
                 f"oldest={oldest_name} ({oldest_age:.0f}s)")

    hb = threading.Thread(target=_heartbeat, daemon=True)
    hb.start()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_task, pl) for pl in plans]
        for fut in as_completed(futures):
            pl, res = fut.result()
            done += 1
            e = pl["entry"]
            key = pl["key"]
            status = res.get("status", "failed")
            try:
                out_blend_rel = pl["out_blend"].resolve().relative_to(args.library_root.resolve()).as_posix()
            except ValueError:
                out_blend_rel = str(pl["out_blend"])
            record = {
                "name": e.get("name"),
                "path": key,
                "source_path": e.get("path"),
                "target_id": (pl.get("target") or {}).get("target_id"),
                "asset_kind": (pl.get("target") or {}).get("asset_kind"),
                "status": status,
                "catalog_path": pl["catalog_path"],
                "catalog_id": pl["catalog_id"],
                "out_blend_rel": out_blend_rel,
                "preview_attached": res.get("preview_attached"),
                "preview_mode": pl["preview_mode"],
                "preview_source": res.get("preview_source"),
                "preview_generated": res.get("preview_generated"),
                "preview_error": res.get("preview_error"),
                "icon_source": pl["icon_source"],
                "icon_path": str(pl["icon_path"]) if pl["icon_path"] else None,
                "bp_root_normalized": res.get("bp_root_normalized"),
                "bp_root_audit": res.get("bp_root_audit"),
                "material_mode": args.material_mode,
                "web_assets_manifest": str(args.web_assets_manifest) if args.web_assets_manifest else None,
                "linked_materials": res.get("linked_materials"),
                "swapped_slots": res.get("swapped_slots"),
                "unmatched_slots": res.get("unmatched_slots"),
                "unmatched_built": res.get("unmatched_built"),
                "base_color_built": res.get("base_color_built"),
                "material_quality": res.get("material_quality"),
                "web_texture_stats": res.get("web_texture_stats"),
                "duration_s": res.get("duration_s"),
                "finished_utc": _now_utc(),
                "error": res.get("error"),
            }
            progress.update(key, record)
            if status == "success":
                ok += 1
                tag = res.get("preview_source") or ("custom_icon" if res.get("preview_attached") else "no-preview")
                _log(f"[{done}/{total}] OK   {pl['stem']}  ({tag}, {res.get('duration_s')}s)")
            else:
                fail += 1
                _log(f"[{done}/{total}] FAIL {pl['stem']}  -> {res.get('error') or 'unknown'}")

    stop_heartbeat.set()
    hb.join(timeout=2.0)

    elapsed = time.time() - start
    _log(f"Done: {ok} ok, {fail} failed, {pre_skipped} pre-skipped in {elapsed:.1f}s. "
         f"Manifest totals: {progress.totals()}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
