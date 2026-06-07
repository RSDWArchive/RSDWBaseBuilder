"""
Driver: build shared material .blend files for the asset library.

By default this writes one _build/extension/_Materials.blend. When --shard-size-mb is supplied,
it writes Git-safe shards named _Materials_0000.blend, _Materials_0001.blend,
etc, plus _Materials.manifest.json so asset builds can link materials from the
right shard.

Usage:
    python tools/AssetLibrary/BuildSharedMaterials.py
    python tools/AssetLibrary/BuildSharedMaterials.py --inventory tools/ModelData/MaterialInventory.json
    python tools/AssetLibrary/BuildSharedMaterials.py --shard-size-mb 95
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


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
    return _latest_version_root(Path(r"E:/Github/RSDWModel")) or (_repo_root() / "0.11.1.4")


def _default_material_data_roots() -> list[Path]:
    archive_root = _latest_version_root(Path(r"E:/Github/RSDWArchive")) or Path(r"E:/Github/RSDWArchive/0.11.1.4")
    return [archive_root / "json", archive_root / "textures"]


def _default_inventory() -> Path:
    return _repo_root() / "tools" / "ModelData" / "MaterialInventory.json"


def _default_out_blend() -> Path:
    return _repo_root() / "_build" / "extension" / "_Materials.blend"


def _default_web_assets_manifest(source_root: Path) -> Path | None:
    candidate = source_root / "WebAssets" / "WebAssetManifest.json"
    return candidate if candidate.is_file() else None


def _default_worker() -> Path:
    return Path(__file__).resolve().parent / "BuildSharedMaterialsWorker.py"


def _default_manifest(out_blend: Path) -> Path:
    return out_blend.with_name(f"{out_blend.stem}.manifest.json")


def _shard_path(out_blend: Path, index: int) -> Path:
    return out_blend.with_name(f"{out_blend.stem}_{index:04d}{out_blend.suffix}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_result(stdout: str) -> dict | None:
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


def _rel(path: Path, base: Path) -> str:
    return os.path.relpath(path, base).replace("\\", "/")


def _normalize_material(entry: dict) -> dict:
    key = str(entry.get("key") or "")
    stem = str(entry.get("stem") or Path(key).stem)
    out = {
        "key": key,
        "stem": stem,
    }
    if "ref_count" in entry:
        out["ref_count"] = entry.get("ref_count")
    if entry.get("sample_meshes"):
        out["sample_meshes"] = entry.get("sample_meshes")
    return out


def _manifest_material(entry: dict) -> dict:
    out = {"key": entry["key"], "stem": entry["stem"]}
    if "ref_count" in entry:
        out["ref_count"] = entry.get("ref_count")
    return out


def _stem_collisions(materials: list[dict]) -> list[dict]:
    counts = Counter(m["stem"] for m in materials)
    collisions: list[dict] = []
    for stem, count in sorted(counts.items()):
        if count <= 1:
            continue
        collisions.append({
            "stem": stem,
            "count": count,
            "keys": [m["key"] for m in materials if m["stem"] == stem],
        })
    return collisions


def _initial_batches(materials: list[dict], size: int) -> list[list[dict]]:
    batches: list[list[dict]] = []
    current: list[dict] = []
    stems: set[str] = set()
    for material in materials:
        stem = material["stem"]
        if current and (len(current) >= size or stem in stems):
            batches.append(current)
            current = []
            stems = set()
        current.append(material)
        stems.add(stem)
    if current:
        batches.append(current)
    return batches


def _split_batch(batch: list[dict]) -> tuple[list[dict], list[dict]]:
    mid = max(1, len(batch) // 2)
    return batch[:mid], batch[mid:]


def _clean_shard_outputs(out_blend: Path, manifest: Path) -> None:
    out_blend.parent.mkdir(parents=True, exist_ok=True)
    out_blend.unlink(missing_ok=True)
    out_blend.with_suffix(out_blend.suffix + "1").unlink(missing_ok=True)
    manifest.unlink(missing_ok=True)
    for path in out_blend.parent.glob(f"{out_blend.stem}_*{out_blend.suffix}"):
        if path.is_file():
            path.unlink()
        backup = path.with_suffix(path.suffix + "1")
        backup.unlink(missing_ok=True)


def _clean_default_texture_root(texture_root: Path, library_root: Path) -> None:
    resolved = texture_root.resolve()
    base = library_root.resolve()
    if resolved.name != "_MaterialTextures" or base not in resolved.parents:
        return
    if resolved.is_dir():
        shutil.rmtree(resolved)


def _run_worker(
    *,
    args: argparse.Namespace,
    materials: list[dict],
    material_data_roots: list[Path],
    out_blend: Path,
    pack_images: bool = True,
    external_texture_root: Path | None = None,
    texture_limit_mb: float | None = None,
    texture_transcode_min_mb: float | None = None,
) -> tuple[dict | None, float, int]:
    task = {
        "source_root": str(args.source_root.resolve()),
        "data_roots": [str(root.resolve()) for root in material_data_roots],
        "out_blend": str(out_blend.resolve()),
        "materials": [{"key": m["key"], "stem": m["stem"]} for m in materials],
        "pack_images": pack_images,
        "external_texture_root": str(external_texture_root.resolve()) if external_texture_root else None,
        "texture_limit_mb": texture_limit_mb,
        "texture_transcode_min_mb": texture_transcode_min_mb,
        "web_assets_manifest": str(args.web_assets_manifest.resolve()) if args.web_assets_manifest else None,
    }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="shared_mats_", delete=False, encoding="utf-8",
    ) as tf:
        tf.write(json.dumps(task))
        task_path = Path(tf.name)

    t0 = time.time()
    try:
        cmd = [
            str(args.blender),
            "--background",
            "--factory-startup",
            "--python", str(args.worker),
            "--",
            "--task-file", str(task_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout_s)
        except subprocess.TimeoutExpired as exc:
            elapsed = time.time() - t0
            return {
                "status": "failed",
                "error": f"worker timed out after {args.timeout_s}s",
                "stdout_tail": "\n".join((exc.stdout or "").splitlines()[-30:]),
                "stderr_tail": "\n".join((exc.stderr or "").splitlines()[-30:]),
            }, elapsed, 124
        elapsed = time.time() - t0
        result = _parse_result(proc.stdout or "")
        if result is None:
            result = {
                "status": "failed",
                "error": f"no RESULT line (exit {proc.returncode})",
                "stdout_tail": "\n".join((proc.stdout or "").splitlines()[-30:]),
                "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-30:]),
            }
        return result, elapsed, proc.returncode
    finally:
        try:
            task_path.unlink(missing_ok=True)
        except Exception:
            pass


def _save_jpeg_under_limit(source: Path, dest: Path, limit_bytes: int) -> dict:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to transcode oversized textures") from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        rgb = image.convert("RGB")
        last_quality = None
        for quality in (80, 75, 70, 65, 60, 55, 50):
            rgb.save(dest, format="JPEG", quality=quality, optimize=True, progressive=True)
            last_quality = quality
            if dest.stat().st_size <= limit_bytes:
                break
    return {
        "dest": str(dest),
        "bytes": dest.stat().st_size,
        "quality": last_quality,
    }


def _materialize_transcoded_textures(result: dict, *, limit_mb: float) -> None:
    limit_bytes = int(limit_mb * 1024 * 1024)
    over_limit: list[dict] = []
    for item in result.get("externalized_textures") or []:
        if not item.get("transcode"):
            continue
        source = Path(item["source"])
        dest = Path(item["dest"])
        info = _save_jpeg_under_limit(source, dest, limit_bytes)
        item.update({
            "bytes": info["bytes"],
            "transcode_quality": info["quality"],
            "transcode": True,
        })
        if info["bytes"] > limit_bytes:
            over_limit.append({
                "source": str(source),
                "dest": str(dest),
                "bytes": info["bytes"],
                "mb": round(info["bytes"] / (1024 * 1024), 3),
            })
    if over_limit:
        raise RuntimeError(
            "transcoded texture(s) still exceed limit: "
            + json.dumps(over_limit[:10], indent=2)
        )


def _write_manifest(
    *,
    manifest_path: Path,
    inventory_path: Path,
    source_root: Path,
    material_data_roots: list[Path],
    web_assets_manifest: Path | None,
    limit_mb: float | None,
    materials: list[dict],
    shards: list[dict],
    over_limit: list[dict],
) -> None:
    by_name: dict[str, list[dict]] = {}
    by_key: dict[str, dict] = {}
    manifest_dir = manifest_path.parent

    for shard in shards:
        rel_blend = _rel(Path(shard["blend"]), manifest_dir)
        for material in shard["materials"]:
            location = {
                "blend": rel_blend,
                "material_name": material["stem"],
                "key": material["key"],
            }
            by_name.setdefault(material["stem"], []).append(location)
            by_key[material["key"]] = location

    manifest = {
        "schema": "RSDWBaseBuilder.SharedMaterialsManifest.v1",
        "generated_at_utc": _now_iso(),
        "limit_mb": limit_mb,
        "inputs": {
            "inventory": str(inventory_path.resolve()),
            "source_root": str(source_root.resolve()),
            "material_data_roots": [str(root.resolve()) for root in material_data_roots],
            "web_assets_manifest": str(web_assets_manifest.resolve()) if web_assets_manifest else None,
        },
        "summary": {
            "requested_materials": len(materials),
            "linked_materials": sum(len(shard["materials"]) for shard in shards),
            "shards": len(shards),
            "built_materials": sum(int(shard.get("built") or 0) for shard in shards),
            "empty_materials": sum(int(shard.get("empty") or 0) for shard in shards),
            "errored_materials": sum(int(shard.get("errored") or 0) for shard in shards),
            "external_texture_count": sum(int(shard.get("external_texture_count") or 0) for shard in shards),
            "web_texture_hit_count": sum(int((shard.get("web_texture_stats") or {}).get("hit_count") or 0) for shard in shards),
            "web_texture_miss_count": sum(int((shard.get("web_texture_stats") or {}).get("miss_count") or 0) for shard in shards),
            "over_limit_shards": len(over_limit),
            "externalized_shards": sum(1 for shard in shards if not shard.get("pack_images", True)),
            "stem_collisions": len(_stem_collisions(materials)),
        },
        "shards": [
            {
                "index": shard["index"],
                "blend": _rel(Path(shard["blend"]), manifest_dir),
                "bytes": shard["bytes"],
                "mb": shard["mb"],
                "requested": shard["requested"],
                "saved_material_count": shard["saved_material_count"],
                "built": shard.get("built", 0),
                "errored": shard["errored"],
                "empty": shard["empty"],
                "pack_images": shard.get("pack_images", True),
                "external_texture_count": shard.get("external_texture_count", 0),
                "web_texture_stats": shard.get("web_texture_stats"),
                "external_textures": shard.get("external_textures", []),
                "materials": shard["materials"],
            }
            for shard in shards
        ],
        "by_name": by_name,
        "by_key": by_key,
        "collisions": _stem_collisions(materials),
        "over_limit": over_limit,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _build_single(args: argparse.Namespace, materials: list[dict], material_data_roots: list[Path]) -> int:
    print(f"Building {len(materials)} shared materials -> {args.out_blend}")
    if material_data_roots:
        print("Material data roots: " + ", ".join(str(root) for root in material_data_roots))
    external_texture_root = args.external_texture_root or (args.out_blend.parent / "_MaterialTextures")
    pack_images = not args.externalize_textures

    result, elapsed, returncode = _run_worker(
        args=args,
        materials=materials,
        material_data_roots=material_data_roots,
        out_blend=args.out_blend,
        pack_images=pack_images,
        external_texture_root=external_texture_root if not pack_images else None,
        texture_limit_mb=args.external_texture_limit_mb if not pack_images else None,
        texture_transcode_min_mb=args.external_texture_transcode_min_mb if not pack_images else None,
    )
    if result is None or result.get("status") != "success":
        print(f"FAIL ({elapsed:.1f}s): {(result or {}).get('error', 'unknown error')}", file=sys.stderr)
        print(json.dumps(result, indent=2), file=sys.stderr)
        return returncode or 1
    if not pack_images and args.external_texture_limit_mb:
        try:
            _materialize_transcoded_textures(result, limit_mb=args.external_texture_limit_mb)
        except RuntimeError as exc:
            print(f"FAIL external texture transcode: {exc}", file=sys.stderr)
            return 1

    print(f"OK ({elapsed:.1f}s)")
    print(json.dumps(result, indent=2))

    if args.manifest:
        saved = set(result.get("saved_materials") or [m["stem"] for m in materials])
        size = args.out_blend.stat().st_size if args.out_blend.exists() else 0
        shard = {
            "index": 0,
            "blend": str(args.out_blend.resolve()),
            "bytes": size,
            "mb": round(size / (1024 * 1024), 3),
            "requested": len(materials),
            "saved_material_count": len(saved),
            "built": int(result.get("built") or 0),
            "errored": int(result.get("errored") or 0),
            "empty": int(result.get("empty") or 0),
            "pack_images": bool(result.get("pack_images", True)),
            "external_texture_count": int(result.get("externalized_texture_count") or 0),
            "web_texture_stats": result.get("web_texture_stats") or {},
            "external_textures": result.get("externalized_textures") or [],
            "materials": [_manifest_material(m) for m in materials if m["stem"] in saved],
        }
        _write_manifest(
            manifest_path=args.manifest,
            inventory_path=args.inventory,
            source_root=args.source_root,
            material_data_roots=material_data_roots,
            web_assets_manifest=args.web_assets_manifest,
            limit_mb=None,
            materials=materials,
            shards=[shard],
            over_limit=[],
        )
        print(f"Manifest: {args.manifest}")
    return 0


def _build_sharded(args: argparse.Namespace, materials: list[dict], material_data_roots: list[Path]) -> int:
    if args.shard_size_mb is None or args.shard_size_mb <= 0:
        print("--shard-size-mb must be positive", file=sys.stderr)
        return 2

    manifest_path = args.manifest or _default_manifest(args.out_blend)
    external_texture_root = args.external_texture_root or (args.out_blend.parent / "_MaterialTextures")
    _clean_shard_outputs(args.out_blend, manifest_path)
    _clean_default_texture_root(external_texture_root, args.out_blend.parent)

    limit_bytes = int(args.shard_size_mb * 1024 * 1024)
    pending = _initial_batches(materials, max(1, args.shard_material_count))
    shards: list[dict] = []
    over_limit: list[dict] = []
    attempts = 0

    print(
        f"Building {len(materials)} shared materials into Git-safe shards "
        f"(limit {args.shard_size_mb:g} MiB)"
    )
    if material_data_roots:
        print("Material data roots: " + ", ".join(str(root) for root in material_data_roots))

    while pending:
        batch = pending.pop(0)
        shard_index = len(shards)
        out_blend = _shard_path(args.out_blend, shard_index)
        attempts += 1
        print(f"[{shard_index:04d}] building {len(batch)} materials -> {out_blend.name}")

        pack_images = not args.externalize_textures
        result, elapsed, returncode = _run_worker(
            args=args,
            materials=batch,
            material_data_roots=material_data_roots,
            out_blend=out_blend,
            pack_images=pack_images,
            external_texture_root=external_texture_root if not pack_images else None,
            texture_limit_mb=args.external_texture_limit_mb if not pack_images else None,
            texture_transcode_min_mb=args.external_texture_transcode_min_mb if not pack_images else None,
        )
        if result is None or result.get("status") != "success":
            print(f"FAIL shard {shard_index:04d} ({elapsed:.1f}s): {(result or {}).get('error', 'unknown error')}", file=sys.stderr)
            print(json.dumps(result, indent=2), file=sys.stderr)
            return returncode or 1
        if not pack_images and args.external_texture_limit_mb:
            try:
                _materialize_transcoded_textures(result, limit_mb=args.external_texture_limit_mb)
            except RuntimeError as exc:
                print(f"FAIL shard {shard_index:04d} external texture transcode: {exc}", file=sys.stderr)
                return 1

        size = out_blend.stat().st_size if out_blend.exists() else 0
        size_mb = size / (1024 * 1024)
        if size > limit_bytes and len(batch) > 1:
            left, right = _split_batch(batch)
            out_blend.unlink(missing_ok=True)
            out_blend.with_suffix(out_blend.suffix + "1").unlink(missing_ok=True)
            print(
                f"[{shard_index:04d}] {size_mb:.1f} MiB exceeds limit; "
                f"splitting into {len(left)} + {len(right)} materials"
            )
            pending.insert(0, right)
            pending.insert(0, left)
            continue
        if size > limit_bytes and len(batch) == 1 and pack_images:
            attempts += 1
            print(
                f"[{shard_index:04d}] {size_mb:.1f} MiB for one material; "
                "rebuilding with external copied textures"
            )
            result, elapsed, returncode = _run_worker(
                args=args,
                materials=batch,
                material_data_roots=material_data_roots,
                out_blend=out_blend,
                pack_images=False,
                external_texture_root=external_texture_root,
                texture_limit_mb=args.shard_size_mb,
                texture_transcode_min_mb=args.external_texture_transcode_min_mb,
            )
            if result is None or result.get("status") != "success":
                print(f"FAIL shard {shard_index:04d} externalized ({elapsed:.1f}s): {(result or {}).get('error', 'unknown error')}", file=sys.stderr)
                print(json.dumps(result, indent=2), file=sys.stderr)
                return returncode or 1
            try:
                _materialize_transcoded_textures(result, limit_mb=args.shard_size_mb)
            except RuntimeError as exc:
                print(f"FAIL shard {shard_index:04d} external texture transcode: {exc}", file=sys.stderr)
                return 1
            size = out_blend.stat().st_size if out_blend.exists() else 0
            size_mb = size / (1024 * 1024)

        saved = set(result.get("saved_materials") or [m["stem"] for m in batch])
        shard_materials = [_manifest_material(m) for m in batch if m["stem"] in saved]
        shard = {
            "index": shard_index,
            "blend": str(out_blend.resolve()),
            "bytes": size,
            "mb": round(size_mb, 3),
            "requested": len(batch),
            "saved_material_count": len(saved),
            "built": int(result.get("built") or 0),
            "errored": int(result.get("errored") or 0),
            "empty": int(result.get("empty") or 0),
            "pack_images": bool(result.get("pack_images", True)),
            "external_texture_count": int(result.get("externalized_texture_count") or 0),
            "web_texture_stats": result.get("web_texture_stats") or {},
            "external_textures": result.get("externalized_textures") or [],
            "materials": shard_materials,
        }
        shards.append(shard)
        print(
            f"[{shard_index:04d}] OK {size_mb:.1f} MiB, "
            f"{len(shard_materials)}/{len(batch)} linkable materials ({elapsed:.1f}s)"
        )

        if size > limit_bytes:
            over_limit.append({
                "index": shard_index,
                "blend": str(out_blend.resolve()),
                "bytes": size,
                "mb": round(size_mb, 3),
                "material_count": len(batch),
                "pack_images": bool(result.get("pack_images", True)),
                "external_texture_count": int(result.get("externalized_texture_count") or 0),
                "materials": shard_materials,
            })

    _write_manifest(
        manifest_path=manifest_path,
        inventory_path=args.inventory,
        source_root=args.source_root,
        material_data_roots=material_data_roots,
        web_assets_manifest=args.web_assets_manifest,
        limit_mb=args.shard_size_mb,
        materials=materials,
        shards=shards,
        over_limit=over_limit,
    )

    print(f"Manifest: {manifest_path}")
    print(f"Built {len(shards)} shards in {attempts} worker runs")
    if over_limit:
        print(f"FAIL: {len(over_limit)} shard(s) still exceed {args.shard_size_mb:g} MiB", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build a shared materials.blend for the asset library.")
    p.add_argument("--blender", type=Path, default=_default_blender())
    p.add_argument("--worker", type=Path, default=_default_worker())
    p.add_argument("--source-root", type=Path, default=_default_source_root())
    p.add_argument("--material-data-root", type=Path, action="append", default=None,
                   help="Supplemental root for material JSONs/textures; repeatable. Defaults to RSDWArchive json/textures roots when present.")
    p.add_argument("--inventory", type=Path, default=_default_inventory())
    p.add_argument("--out-blend", type=Path, default=_default_out_blend())
    p.add_argument("--manifest", type=Path, default=None,
                   help="Write a shared-material manifest. Defaults to _Materials.manifest.json in sharded mode.")
    p.add_argument("--shard-size-mb", type=float, default=None,
                   help="Write multiple shared-material blends, each no larger than this many MiB when possible.")
    p.add_argument("--shard-material-count", type=int, default=64,
                   help="Initial material count per shard before size-based splitting.")
    p.add_argument("--external-texture-root", type=Path, default=None,
                   help="Texture copy root for oversized single-material shards. Defaults to asset_library/_MaterialTextures.")
    p.add_argument("--externalize-textures", action="store_true",
                   help="Store shared material images under _MaterialTextures instead of packing them into .blend shards.")
    p.add_argument("--external-texture-limit-mb", type=float, default=None,
                   help="When externalizing textures, transcode supported images larger than this many MiB to JPEG under the limit.")
    p.add_argument("--external-texture-transcode-min-mb", type=float, default=None,
                   help="When externalizing textures, transcode supported images larger than this many MiB to JPEG even if they are under the hard limit.")
    p.add_argument("--web-assets-manifest", type=Path, default=None,
                   help="Optional RSDWModel WebAssets/WebAssetManifest.json used to load optimized WebP textures.")
    p.add_argument("--limit", type=int, default=None,
                   help="Build at most N materials (smoke testing)")
    p.add_argument("--timeout-s", type=int, default=900)
    args = p.parse_args(argv)

    if args.web_assets_manifest is None:
        args.web_assets_manifest = _default_web_assets_manifest(args.source_root)

    for path, label in [
        (args.blender, "blender.exe"),
        (args.worker, "worker script"),
        (args.source_root, "source root"),
        (args.inventory, "material inventory"),
        (args.web_assets_manifest, "web assets manifest"),
    ]:
        if path is not None and not path.exists():
            print(f"{label} not found: {path}", file=sys.stderr)
            return 2

    inv = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    materials = [_normalize_material(m) for m in inv.get("materials", []) if m.get("key")]
    if args.limit is not None:
        materials = materials[: args.limit]

    material_data_roots = [
        root for root in (args.material_data_root or _default_material_data_roots())
        if root.exists()
    ]

    args.out_blend.parent.mkdir(parents=True, exist_ok=True)
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)

    if args.shard_size_mb is not None:
        return _build_sharded(args, materials, material_data_roots)
    return _build_single(args, materials, material_data_roots)


if __name__ == "__main__":
    sys.exit(main())
