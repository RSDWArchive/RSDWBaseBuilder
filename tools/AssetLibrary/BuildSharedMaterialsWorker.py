"""
Blender-side worker: build a shared materials.blend containing one Material
per MI JSON in the task list. All materials are flagged with use_fake_user=True
so they survive Blender's "purge orphans on save" pass.

Reuses _build_material_from_mi from tools/ModelData/BuildGLBWorker.py so we
have one source of truth for the MI -> Principled BSDF translation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

import bpy


# Make tools/ModelData importable inside Blender so we can reuse the existing
# material builder. This worker runs via `blender --python` so sys.path doesn't
# include the repo by default.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tools" / "ModelData"))
sys.path.insert(0, str(_REPO_ROOT / "tools" / "AssetLibrary"))

import BuildGLBWorker as base  # noqa: E402
from BuildGLBWorker import (  # noqa: E402  (sys.path manipulated above)
    _build_material_from_mi,
    _clear_scene,
    _enable_required_addons,
)
from OptimizedTextures import compact_web_texture_stats, install_web_texture_loader  # noqa: E402


def _parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    p = argparse.ArgumentParser()
    p.add_argument("--task-file", required=True)
    return p.parse_args(argv)


def _emit_result(obj: dict) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    sys.stdout.write("RESULT:" + json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _save_blend(blend_path: Path, *, pack_images: bool) -> None:
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    if pack_images:
        # Embed image data into the .blend so the shipped file is self-contained.
        # Without this the .blend just stores absolute paths into 0.11.1.4/.
        try:
            bpy.ops.file.pack_all()
        except RuntimeError as e:
            # pack_all errors if there are no images; ignore that specific case.
            sys.stderr.write(f"[warn] pack_all: {e}\n")
    # Suppress .blend1 backup writes -- they double our shipped payload.
    try:
        bpy.context.preferences.filepaths.save_version = 0
    except Exception:
        pass
    bpy.ops.wm.save_as_mainfile(
        filepath=str(blend_path), compress=True, copy=False,
    )


def _copy_external_images(
    texture_root: Path,
    blend_path: Path,
    *,
    texture_limit_bytes: int | None,
    texture_transcode_min_bytes: int | None,
) -> list[dict]:
    texture_root.mkdir(parents=True, exist_ok=True)
    copied: list[dict] = []
    seen: dict[Path, Path] = {}

    for image in bpy.data.images:
        raw = image.filepath or ""
        if not raw:
            continue
        try:
            src = Path(bpy.path.abspath(raw)).resolve()
        except Exception:
            continue
        if not src.is_file():
            continue

        dest = seen.get(src)
        if dest is None:
            digest = hashlib.sha1(str(src).encode("utf-8", errors="ignore")).hexdigest()[:12]
            source_bytes = src.stat().st_size
            transcode = (
                src.suffix.lower() in {".png", ".tga", ".tif", ".tiff", ".bmp"}
                and (
                    (
                        texture_transcode_min_bytes is not None
                        and source_bytes > texture_transcode_min_bytes
                    )
                    or (
                        texture_limit_bytes is not None
                        and source_bytes > texture_limit_bytes
                    )
                )
            )
            suffix = ".jpg" if transcode else (src.suffix or ".img")
            dest = texture_root / digest[:2] / f"{src.stem}_{digest}{suffix}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if transcode:
                # The Python driver owns the actual transcode because Blender's
                # bundled Python does not ship Pillow in our portable runtime.
                dest.unlink(missing_ok=True)
            elif not dest.exists() or dest.stat().st_size != source_bytes:
                shutil.copy2(src, dest)
            seen[src] = dest

        rel = os.path.relpath(dest, blend_path.parent).replace("\\", "/")
        image.filepath = f"//{rel}"
        try:
            image.filepath_raw = image.filepath
        except Exception:
            pass
        copied.append({
            "image": image.name,
            "source": str(src),
            "dest": str(dest),
            "source_bytes": src.stat().st_size,
            "bytes": dest.stat().st_size if dest.exists() else None,
            "transcode": not dest.exists(),
            "transcode_format": "jpeg" if not dest.exists() else None,
        })

    return copied


def main() -> int:
    t0 = time.time()
    try:
        args = _parse_args()
        task = json.loads(Path(args.task_file).read_text(encoding="utf-8"))

        source_root = Path(task["source_root"]).resolve()
        data_roots = [Path(root).resolve() for root in task.get("data_roots", [])]
        out_blend = Path(task["out_blend"]).resolve()
        mat_entries = task["materials"]
        pack_images = bool(task.get("pack_images", True))
        texture_limit_mb = task.get("texture_limit_mb")
        texture_limit_bytes = (
            int(float(texture_limit_mb) * 1024 * 1024)
            if texture_limit_mb is not None else None
        )
        texture_transcode_min_mb = task.get("texture_transcode_min_mb")
        texture_transcode_min_bytes = (
            int(float(texture_transcode_min_mb) * 1024 * 1024)
            if texture_transcode_min_mb is not None else None
        )
        external_texture_root_raw = task.get("external_texture_root")
        external_texture_root = (
            Path(external_texture_root_raw).resolve()
            if external_texture_root_raw else None
        )
        web_assets_manifest_raw = task.get("web_assets_manifest")
        web_assets_manifest = (
            Path(web_assets_manifest_raw).resolve()
            if web_assets_manifest_raw else None
        )

        if not source_root.is_dir():
            raise FileNotFoundError(f"source_root not found: {source_root}")

        _enable_required_addons()
        _clear_scene()
        web_texture_stats = install_web_texture_loader(
            base,
            source_root=source_root,
            data_roots=data_roots,
            manifest_path=web_assets_manifest,
        )

        built: list[dict] = []
        empty: list[dict] = []
        errored: list[dict] = []

        for entry in mat_entries:
            stem = entry["stem"]
            mi_rel = entry["key"]
            mi_abs = source_root / mi_rel
            if not mi_abs.is_file():
                for root in data_roots:
                    candidate = root / mi_rel
                    if candidate.is_file():
                        mi_abs = candidate
                        break
            if not mi_abs.is_file():
                errored.append({"stem": stem, "error": f"missing MI JSON: {mi_rel}"})
                continue
            # Each material must end up unique in this .blend. If two MIs have
            # the same stem (collision across folders), Blender will append a
            # .001 suffix automatically, which would break linking by name.
            # Detect and report.
            existing = bpy.data.materials.get(stem)
            if existing is not None:
                errored.append({"stem": stem, "error": "stem collision (already exists in this .blend)"})
                continue

            mat = bpy.data.materials.new(name=stem)
            # Without fake user, Blender drops orphan materials on save.
            mat.use_fake_user = True
            try:
                report = _build_material_from_mi(mat, mi_abs, source_root, data_roots)
            except Exception as e:
                errored.append({"stem": stem, "error": f"{type(e).__name__}: {e}"})
                continue

            src = report.get("source", "?")
            if src == "mi":
                built.append({"stem": stem, "roles": report.get("roles", []), "params": report.get("params", [])})
            else:
                # mi_empty / mi_error -> still keep the material (so linking by name works)
                # but flag for the report so we can review which materials need a hybrid pass.
                empty.append({"stem": stem, "source": src, "error": report.get("error")})

        externalized_textures: list[dict] = []
        if not pack_images and external_texture_root is not None:
            externalized_textures = _copy_external_images(
            external_texture_root,
            out_blend,
            texture_limit_bytes=texture_limit_bytes,
            texture_transcode_min_bytes=texture_transcode_min_bytes,
        )

        _save_blend(out_blend, pack_images=pack_images)

        # Count packed images so we can report the embedded asset count.
        packed_images = sum(1 for img in bpy.data.images if img.packed_file is not None)
        total_images = len(bpy.data.images)

        _emit_result({
            "status": "success",
            "out_blend": str(out_blend),
            "requested": len(mat_entries),
            "built": len(built),
            "empty": len(empty),
            "errored": len(errored),
            "saved_materials": sorted(mat.name for mat in bpy.data.materials),
            "pack_images": pack_images,
            "external_texture_root": str(external_texture_root) if external_texture_root else None,
            "externalized_texture_count": len(externalized_textures),
            "externalized_textures": externalized_textures,
            "web_texture_stats": compact_web_texture_stats(web_texture_stats),
            "packed_images": packed_images,
            "total_images": total_images,
            "empty_list": empty[:20],
            "error_list": errored[:20],
            "duration_s": round(time.time() - t0, 3),
        })
        return 0
    except Exception as e:
        _emit_result({
            "status": "failed",
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "duration_s": round(time.time() - t0, 3),
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
