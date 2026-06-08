"""Blender-side worker for baking generated asset previews into .blend files.

This worker is intentionally separate from BuildAssetLibraryWorker. On some
Windows/GPU combinations Blender can save generated previews successfully, then
crash while shutting down. The host script treats per-file saved result rows as
authoritative so that crash-on-exit does not poison the whole asset build.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
import traceback
from pathlib import Path

import bpy
from mathutils import Vector


def _emit(results_path: Path, row: dict) -> None:
    with results_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()


def _asset_object() -> bpy.types.Object | None:
    for obj in bpy.data.objects:
        if obj.asset_data:
            return obj
    return None


def _preview_metrics(obj: bpy.types.Object | None) -> dict:
    if obj is None:
        return {
            "size": [0, 0],
            "pixel_count": 0,
            "alpha_pixels": 0,
            "bright_pixels": 0,
            "avg_alpha": 0.0,
            "avg_rgb": 0.0,
            "max_rgb": 0.0,
            "nonblank": False,
        }
    preview = getattr(obj, "preview", None)
    size = getattr(preview, "image_size", None) if preview else None
    if not size:
        size_out = [0, 0]
    else:
        try:
            size_out = [int(size[0]), int(size[1])]
        except Exception:
            size_out = [0, 0]

    pixels = list(getattr(preview, "image_pixels_float", []) or []) if preview else []
    pixel_count = len(pixels) // 4
    alpha_pixels = 0
    bright_pixels = 0
    total_alpha = 0.0
    total_rgb = 0.0
    max_rgb = 0.0
    for index in range(0, len(pixels) - 3, 4):
        rgb = (float(pixels[index]) + float(pixels[index + 1]) + float(pixels[index + 2])) / 3.0
        alpha = float(pixels[index + 3])
        total_rgb += rgb
        total_alpha += alpha
        max_rgb = max(max_rgb, rgb)
        if alpha > 0.01:
            alpha_pixels += 1
        if rgb > 0.01:
            bright_pixels += 1

    min_pixels = max(8, int(pixel_count * 0.001))
    nonblank = size_out[0] > 0 and size_out[1] > 0 and alpha_pixels >= min_pixels
    return {
        "size": size_out,
        "pixel_count": pixel_count,
        "alpha_pixels": alpha_pixels,
        "bright_pixels": bright_pixels,
        "avg_alpha": round(total_alpha / pixel_count, 6) if pixel_count else 0.0,
        "avg_rgb": round(total_rgb / pixel_count, 6) if pixel_count else 0.0,
        "max_rgb": round(max_rgb, 6),
        "nonblank": nonblank,
    }


def _preview_size(obj: bpy.types.Object | None) -> list[int]:
    return list(_preview_metrics(obj)["size"])


def _has_preview(obj: bpy.types.Object | None) -> bool:
    return bool(_preview_metrics(obj)["nonblank"])


def _is_useful_preview(obj: bpy.types.Object | None) -> bool:
    metrics = _preview_metrics(obj)
    pixel_count = int(metrics.get("pixel_count") or 0)
    alpha_pixels = int(metrics.get("alpha_pixels") or 0)
    useful_pixels = max(512, int(pixel_count * 0.008))
    return bool(metrics.get("nonblank")) and alpha_pixels >= useful_pixels


def _save_preview_to_webp(obj: bpy.types.Object | None, web_preview_path: Path | None) -> tuple[bool, int | None, str | None]:
    if web_preview_path is None:
        return False, None, None
    if obj is None:
        return False, None, "no asset object"
    preview = getattr(obj, "preview", None)
    size = getattr(preview, "image_size", None) if preview else None
    pixels = list(getattr(preview, "image_pixels_float", []) or []) if preview else []
    if not size or not pixels:
        return False, None, "asset preview has no pixels"
    width = int(size[0])
    height = int(size[1])
    if width <= 0 or height <= 0 or len(pixels) < width * height * 4:
        return False, None, "asset preview pixel buffer is invalid"

    web_preview_path.parent.mkdir(parents=True, exist_ok=True)
    image = bpy.data.images.new(web_preview_path.stem, width=width, height=height, alpha=True, float_buffer=False)
    try:
        image.pixels.foreach_set(pixels[:width * height * 4])
        image.filepath_raw = str(web_preview_path)
        image.file_format = "WEBP"
        image.save()
    finally:
        bpy.data.images.remove(image)
    try:
        size_on_disk = web_preview_path.stat().st_size
    except FileNotFoundError:
        return False, None, "WebP file was not written"
    if size_on_disk <= 0:
        return False, size_on_disk, "WebP file is empty"
    return True, size_on_disk, None


def _render_objects() -> list[bpy.types.Object]:
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    asset = _asset_object()
    if asset is not None and asset.type == "MESH" and asset not in meshes:
        meshes.append(asset)
    return meshes


def _objects_bounds(objs: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points: list[Vector] = []
    for obj in objs:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))
    if not points:
        return Vector((0.0, 0.0, 0.0)), Vector((1.0, 1.0, 1.0))
    min_v = Vector((
        min(point.x for point in points),
        min(point.y for point in points),
        min(point.z for point in points),
    ))
    max_v = Vector((
        max(point.x for point in points),
        max(point.y for point in points),
        max(point.z for point in points),
    ))
    return (min_v + max_v) * 0.5, max_v - min_v


def _look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _configure_render_scene(thumbnail_path: Path, mode: str) -> None:
    scene = bpy.context.scene
    if mode == "workbench":
        scene.render.engine = "BLENDER_WORKBENCH"
        try:
            scene.display.shading.light = "STUDIO"
            scene.display.shading.color_type = "SINGLE"
            scene.display.shading.single_color = (0.72, 0.72, 0.72)
            scene.display.shading.show_backface_culling = False
            scene.display.shading.show_xray = False
        except Exception:
            pass
    else:
        for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"):
            try:
                scene.render.engine = engine
                break
            except TypeError:
                continue
    scene.render.resolution_x = 256
    scene.render.resolution_y = 256
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(thumbnail_path)
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "Medium High Contrast"
        scene.view_settings.exposure = 0
        scene.view_settings.gamma = 1
    except Exception:
        pass


def _crop_thumbnail_to_alpha(thumbnail_path: Path) -> Path:
    image = bpy.data.images.load(str(thumbnail_path), check_existing=False)
    try:
        width, height = int(image.size[0]), int(image.size[1])
        pixels = list(image.pixels)
    finally:
        bpy.data.images.remove(image)

    if width <= 0 or height <= 0 or not pixels:
        return thumbnail_path

    mask: set[tuple[int, int]] = set()
    for y in range(height):
        row = y * width * 4
        for x in range(width):
            index = row + x * 4
            alpha = float(pixels[index + 3])
            rgb = (
                float(pixels[index])
                + float(pixels[index + 1])
                + float(pixels[index + 2])
            ) / 3.0
            if alpha > 0.01 and rgb > 0.005:
                mask.add((x, y))

    if not mask:
        return thumbnail_path

    # Large world-room meshes often have a few faraway visible pixels that
    # ruin a simple alpha bbox. Crop to the largest connected component instead.
    remaining = set(mask)
    best_component: list[tuple[int, int]] = []
    neighbors = [
        (-1, -1), (0, -1), (1, -1),
        (-1, 0),           (1, 0),
        (-1, 1),  (0, 1),  (1, 1),
    ]
    while remaining:
        seed = remaining.pop()
        component = [seed]
        stack = [seed]
        while stack:
            cx, cy = stack.pop()
            for dx, dy in neighbors:
                candidate = (cx + dx, cy + dy)
                if candidate in remaining:
                    remaining.remove(candidate)
                    stack.append(candidate)
                    component.append(candidate)
        if len(component) > len(best_component):
            best_component = component

    if not best_component:
        return thumbnail_path

    xs = [point[0] for point in best_component]
    ys = [point[1] for point in best_component]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    crop_w = max_x - min_x + 1
    crop_h = max_y - min_y + 1
    if crop_w <= 0 or crop_h <= 0:
        return thumbnail_path

    out_w = 256
    out_h = 256
    padding = 18
    scale = min((out_w - padding * 2) / crop_w, (out_h - padding * 2) / crop_h)
    if scale <= 0:
        return thumbnail_path

    dst_w = max(1, int(round(crop_w * scale)))
    dst_h = max(1, int(round(crop_h * scale)))
    dst_x0 = (out_w - dst_w) // 2
    dst_y0 = (out_h - dst_h) // 2
    out_pixels = [0.0] * (out_w * out_h * 4)
    for y in range(dst_h):
        src_y = min_y + min(crop_h - 1, int(y / scale))
        for x in range(dst_w):
            src_x = min_x + min(crop_w - 1, int(x / scale))
            src_index = (src_y * width + src_x) * 4
            dst_index = ((dst_y0 + y) * out_w + (dst_x0 + x)) * 4
            out_pixels[dst_index:dst_index + 4] = pixels[src_index:src_index + 4]

    cropped_path = thumbnail_path.with_name(f"{thumbnail_path.stem}.cropped.png")
    out_image = bpy.data.images.new(cropped_path.stem, width=out_w, height=out_h, alpha=True, float_buffer=False)
    try:
        out_image.pixels.foreach_set(out_pixels)
        out_image.filepath_raw = str(cropped_path)
        out_image.file_format = "PNG"
        out_image.save()
    finally:
        bpy.data.images.remove(out_image)
    return cropped_path


def _render_thumbnail(obj: bpy.types.Object, thumbnail_path: Path) -> str:
    render_objs = _render_objects()
    if not render_objs:
        raise RuntimeError("no mesh objects to render for preview")

    visibility_state = []
    for candidate in bpy.data.objects:
        visibility_state.append((
            candidate,
            bool(candidate.hide_viewport),
            bool(candidate.hide_render),
        ))
        candidate.hide_viewport = False
        candidate.hide_render = False
        try:
            candidate.hide_set(False)
        except Exception:
            pass

    camera_data = None
    camera = None
    light_data = None
    light = None
    try:
        center, dims = _objects_bounds(render_objs)
        max_dim = max(float(dims.x), float(dims.y), float(dims.z), 0.1)

        camera_data = bpy.data.cameras.new("RSDW_PreviewCamera")
        camera = bpy.data.objects.new("RSDW_PreviewCamera", camera_data)
        bpy.context.scene.collection.objects.link(camera)
        camera_direction = Vector((1.6, -2.2, 1.15)).normalized()
        camera.location = center + camera_direction * max_dim * 3.0
        _look_at(camera, center)
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = max_dim * 1.35
        camera_data.clip_start = max(0.001, max_dim / 100000.0)
        camera_data.clip_end = max(1000.0, max_dim * 10.0)
        bpy.context.scene.camera = camera

        light_data = bpy.data.lights.new("RSDW_PreviewKey", "AREA")
        light = bpy.data.objects.new("RSDW_PreviewKey", light_data)
        bpy.context.scene.collection.objects.link(light)
        light.location = center + Vector((-1.5, -2.0, 3.0)).normalized() * max_dim * 3.0
        light_data.energy = max(500.0, max_dim * 120.0)
        light_data.size = max(max_dim, 1.0)

        attempts = [
            ("eevee_outside", "eevee", False),
            ("workbench_outside", "workbench", False),
            ("workbench_inside", "workbench", True),
        ]
        last_strategy = "none"
        best_strategy = "none"
        best_path: Path | None = None
        best_alpha_pixels = 0
        for strategy, mode, inside_camera in attempts:
            last_strategy = strategy
            if inside_camera:
                camera_data.type = "PERSP"
                camera_data.angle = math.radians(50.0)
                camera_data.clip_start = 0.001
                camera_data.clip_end = max(1000.0, max_dim * 10.0)
                camera.location = center
                _look_at(camera, center + Vector((1.0, -1.0, 0.25)).normalized() * max_dim)
            else:
                attempt_direction = (
                    Vector((1.0, -1.0, 2.4)).normalized()
                    if mode == "workbench"
                    else camera_direction
                )
                camera_data.type = "ORTHO"
                camera_data.ortho_scale = max_dim * (1.15 if mode == "workbench" else 1.35)
                camera_data.clip_start = max(0.001, max_dim / 100000.0)
                camera_data.clip_end = max(1000.0, max_dim * 10.0)
                camera.location = center + attempt_direction * max_dim * 3.0
                _look_at(camera, center)

            attempt_path = thumbnail_path.with_name(f"{thumbnail_path.stem}.{strategy}.png")
            _configure_render_scene(attempt_path, mode)
            bpy.ops.render.render(write_still=True)
            if not attempt_path.is_file() or attempt_path.stat().st_size <= 0:
                continue
            preview_path = _crop_thumbnail_to_alpha(attempt_path)

            with bpy.context.temp_override(id=obj):
                bpy.ops.ed.lib_id_load_custom_preview(filepath=str(preview_path))
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass
            metrics = _preview_metrics(obj)
            alpha_pixels = int(metrics.get("alpha_pixels") or 0)
            if bool(metrics.get("nonblank")) and alpha_pixels >= best_alpha_pixels:
                best_strategy = strategy
                best_path = preview_path
                best_alpha_pixels = alpha_pixels
            if _is_useful_preview(obj):
                return strategy
        if best_path is not None:
            with bpy.context.temp_override(id=obj):
                bpy.ops.ed.lib_id_load_custom_preview(filepath=str(best_path))
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass
            return best_strategy
        return last_strategy
    finally:
        if camera is not None:
            bpy.data.objects.remove(camera, do_unlink=True)
        if camera_data is not None:
            bpy.data.cameras.remove(camera_data, do_unlink=True)
        if light is not None:
            bpy.data.objects.remove(light, do_unlink=True)
        if light_data is not None:
            bpy.data.lights.remove(light_data, do_unlink=True)
        for candidate, hide_viewport, hide_render in visibility_state:
            if candidate.name not in bpy.data.objects:
                continue
            candidate.hide_viewport = hide_viewport
            candidate.hide_render = hide_render


def _save_current_file(path: Path) -> None:
    try:
        bpy.context.preferences.filepaths.save_version = 0
    except Exception:
        pass
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True, copy=False)


def _process_one(
    path: Path,
    *,
    force: bool,
    verify_only: bool,
    results_path: Path,
    web_preview_path: Path | None = None,
) -> bool:
    t0 = time.time()
    row = {
        "blend_file": str(path),
        "status": "failed",
        "action": "failed",
        "duration_s": None,
        "web_preview_path": str(web_preview_path) if web_preview_path else "",
        "web_preview_written": False,
        "web_preview_size": None,
        "web_preview_error": None,
    }
    try:
        if not path.is_file():
            row.update({"action": "missing_file", "error": "blend file missing"})
            return False

        bpy.ops.wm.open_mainfile(filepath=str(path))
        obj = _asset_object()
        before_metrics = _preview_metrics(obj)
        before_has_preview = bool(before_metrics["nonblank"])
        row.update({
            "asset_object": obj.name if obj else "",
            "preview_before": before_has_preview,
            "preview_before_metrics": before_metrics,
            "preview_before_size": before_metrics["size"],
        })
        if obj is None:
            row.update({"action": "no_asset_object", "error": "no asset-marked object"})
            return False

        if verify_only:
            after_metrics = _preview_metrics(obj)
            ok = bool(after_metrics["nonblank"])
            web_ok = True
            if web_preview_path is not None:
                web_ok = web_preview_path.is_file() and web_preview_path.stat().st_size > 0
            row.update({
                "status": "success" if ok and web_ok else "failed",
                "action": "verified" if ok and web_ok else "missing_preview",
                "preview_after": ok,
                "preview_after_metrics": after_metrics,
                "preview_after_size": after_metrics["size"],
                "web_preview_written": web_ok if web_preview_path is not None else False,
                "web_preview_size": web_preview_path.stat().st_size if web_ok and web_preview_path is not None else None,
                "web_preview_error": None if web_ok else "missing browser WebP preview",
            })
            return ok and web_ok

        if before_has_preview and not force:
            if web_preview_path is not None:
                written, web_size, web_error = _save_preview_to_webp(obj, web_preview_path)
                row.update({
                    "web_preview_written": written,
                    "web_preview_size": web_size,
                    "web_preview_error": web_error,
                })
                if not written:
                    row.update({"action": "web_preview_failed", "error": web_error})
                    return False
            row.update({
                "status": "success",
                "action": "already_present",
                "preview_after": True,
                "preview_after_metrics": before_metrics,
                "preview_after_size": before_metrics["size"],
            })
            return True

        with tempfile.TemporaryDirectory(prefix="rsdw_preview_") as tmp_dir:
            thumbnail_path = Path(tmp_dir) / f"{path.stem}.png"
            render_strategy = _render_thumbnail(obj, thumbnail_path)

        after_metrics = _preview_metrics(obj)
        after_has_preview = bool(after_metrics["nonblank"])
        row.update({
            "render_strategy": render_strategy,
            "preview_after": after_has_preview,
            "preview_after_metrics": after_metrics,
            "preview_after_size": after_metrics["size"],
        })
        if not after_has_preview:
            row.update({"action": "render_failed", "error": "rendered preview is empty"})
            return False

        if web_preview_path is not None:
            written, web_size, web_error = _save_preview_to_webp(obj, web_preview_path)
            row.update({
                "web_preview_written": written,
                "web_preview_size": web_size,
                "web_preview_error": web_error,
            })
            if not written:
                row.update({"action": "web_preview_failed", "error": web_error})
                return False

        _save_current_file(path)
        row.update({"status": "success", "action": "baked"})
        return True
    except Exception as exc:
        row.update({
            "status": "failed",
            "action": "exception",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        })
        return False
    finally:
        row["duration_s"] = round(time.time() - t0, 3)
        _emit(results_path, row)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bake generated previews for asset .blend files.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    jobs = payload.get("preview_jobs") or []
    if not jobs:
        jobs = [{"blend_file": value} for value in payload.get("blend_files") or []]
    force = bool(payload.get("force"))
    verify_only = bool(payload.get("verify_only"))
    args.results.parent.mkdir(parents=True, exist_ok=True)
    try:
        args.results.unlink()
    except FileNotFoundError:
        pass

    ok = 0
    failed = 0
    for job in jobs:
        path = Path(job.get("blend_file") or "")
        web_preview_path = Path(job["web_preview_path"]) if job.get("web_preview_path") else None
        if _process_one(
            path,
            force=force,
            verify_only=verify_only,
            results_path=args.results,
            web_preview_path=web_preview_path,
        ):
            ok += 1
        else:
            failed += 1

    print(f"RESULT:{json.dumps({'status': 'success' if failed == 0 else 'failed', 'ok': ok, 'failed': failed})}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
