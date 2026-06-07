"""Bake Blender-generated previews for asset-library .blend files.

The asset build intentionally avoids calling Blender's preview generation in
the main worker because background Blender may crash on exit after saving a
generated preview. This stage runs after asset files exist, records per-file
results as soon as each file is saved, and treats a crash-on-exit as tolerated
when every expected asset wrote a successful result row.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROGRESS_SCHEMA = "RSDWModel.GeneratedPreviewProgress.v1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_blender() -> Path:
    root = _repo_root()
    env_path = os.environ.get("BLENDER_EXE")
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
    return candidates[0]


def _default_worker() -> Path:
    return Path(__file__).resolve().parent / "BakeGeneratedPreviewsWorker.py"


def _default_target_file() -> Path:
    return Path(__file__).resolve().parent / "asset_library_targets.json"


def _default_library_root() -> Path:
    return _repo_root() / "_build" / "extension"


def _default_progress_file() -> Path:
    return _repo_root() / "_build" / "GeneratedPreviewProgress.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class ProgressManifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = {
            "manifest_schema": PROGRESS_SCHEMA,
            "started_utc": _now_utc(),
            "updated_utc": _now_utc(),
            "totals": {"success": 0, "failed": 0, "pending": 0},
            "entries": {},
        }
        if path.is_file():
            try:
                loaded = _load_json(path)
                if loaded.get("manifest_schema") == PROGRESS_SCHEMA:
                    self.data = loaded
                    self.data["started_utc"] = self.data.get("started_utc") or _now_utc()
            except Exception:
                pass
        self._recount()

    def _recount(self) -> None:
        totals = {"success": 0, "failed": 0, "pending": 0}
        for row in self.data.get("entries", {}).values():
            status = row.get("status") or "pending"
            totals[status if status in totals else "pending"] += 1
        self.data["totals"] = totals

    def get(self, key: str) -> dict[str, Any] | None:
        return self.data.get("entries", {}).get(key)

    def update(self, key: str, row: dict[str, Any]) -> None:
        self.data.setdefault("entries", {})[key] = row
        self.data["updated_utc"] = _now_utc()
        self._recount()
        _write_json(self.path, self.data)

    def totals(self) -> dict[str, int]:
        return dict(self.data.get("totals") or {})


def _blend_path_for_target(library_root: Path, target: dict[str, Any]) -> Path:
    planned = str(target.get("planned_blend_rel") or "").strip()
    if planned:
        return library_root / Path(planned)
    catalog_path = str(target.get("catalog_path") or "").strip("/")
    stem = str(target.get("asset_stem") or target.get("target_id") or "").strip()
    return library_root / Path(catalog_path) / f"{stem}.blend"


def _load_only_values(path: Path | None) -> set[str]:
    if path is None:
        return set()
    values: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            values.add(value)
    return values


def _matches_only(target: dict[str, Any], blend_path: Path, only_values: set[str]) -> bool:
    if not only_values:
        return True
    candidates = {
        str(target.get("target_id") or ""),
        str(target.get("asset_stem") or ""),
        str(target.get("planned_blend_rel") or ""),
        blend_path.name,
        blend_path.stem,
        str(blend_path),
    }
    return bool(candidates & only_values)


def _is_fresh_success(record: dict[str, Any] | None, blend_path: Path) -> bool:
    if not record or record.get("status") != "success":
        return False
    if record.get("preview_nonblank") is not True:
        return False
    try:
        stat = blend_path.stat()
    except FileNotFoundError:
        return False
    return (
        int(record.get("blend_mtime_ns") or -1) == int(stat.st_mtime_ns)
        and int(record.get("blend_size") or -1) == int(stat.st_size)
    )


def _select_plans(args: argparse.Namespace, progress: ProgressManifest) -> tuple[list[dict[str, Any]], dict[str, int]]:
    doc = _load_json(args.target_file)
    only_values = _load_only_values(args.only_list)
    allowed_kinds = {kind.strip() for kind in args.asset_kind if kind.strip()}
    plans: list[dict[str, Any]] = []
    counts = {
        "targets": 0,
        "selected": 0,
        "skipped_kind": 0,
        "skipped_preview_mode": 0,
        "skipped_only_list": 0,
        "missing_file": 0,
        "skipped_fresh": 0,
    }

    for target in doc.get("targets") or []:
        counts["targets"] += 1
        asset_kind = str(target.get("asset_kind") or "")
        if asset_kind not in allowed_kinds:
            counts["skipped_kind"] += 1
            continue
        if str(target.get("preview_mode") or "").lower() != "generated":
            counts["skipped_preview_mode"] += 1
            continue

        blend_path = _blend_path_for_target(args.library_root, target)
        if not _matches_only(target, blend_path, only_values):
            counts["skipped_only_list"] += 1
            continue
        if not blend_path.is_file():
            counts["missing_file"] += 1
            continue

        key = str(target.get("target_id") or blend_path)
        if not args.force and _is_fresh_success(progress.get(key), blend_path):
            counts["skipped_fresh"] += 1
            continue

        counts["selected"] += 1
        plans.append({
            "key": key,
            "target": target,
            "blend_path": blend_path,
            "asset_kind": asset_kind,
        })
        if args.limit is not None and len(plans) >= args.limit:
            break
    return plans, counts


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _run_batch(
    *,
    args: argparse.Namespace,
    batch: list[dict[str, Any]],
    batch_name: str,
    progress: ProgressManifest,
) -> dict[str, Any]:
    args.batch_log_dir.mkdir(parents=True, exist_ok=True)
    input_path = args.batch_log_dir / f"{batch_name}.input.json"
    results_path = args.batch_log_dir / f"{batch_name}.results.jsonl"
    stdout_path = args.batch_log_dir / f"{batch_name}.stdout.log"
    payload = {
        "force": bool(args.force),
        "verify_only": bool(args.verify_only),
        "blend_files": [str(plan["blend_path"]) for plan in batch],
    }
    _write_json(input_path, payload)
    try:
        results_path.unlink()
    except FileNotFoundError:
        pass

    cmd = [
        str(args.blender),
        "--background",
        "--factory-startup",
        "--python",
        str(args.worker),
        "--",
        "--input",
        str(input_path),
        "--results",
        str(results_path),
    ]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(_repo_root()), text=True, encoding="utf-8", errors="replace",
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout_path.write_text(proc.stdout or "", encoding="utf-8", errors="replace")

    rows = _read_jsonl(results_path)
    rows_by_path = {str(Path(row.get("blend_file", ""))): row for row in rows}
    ok = 0
    failed = 0
    missing: list[dict[str, Any]] = []
    actions: dict[str, int] = {}

    for plan in batch:
        blend_path = plan["blend_path"]
        row = rows_by_path.get(str(blend_path))
        key = plan["key"]
        if row is None:
            missing.append(plan)
            failed += 1
            continue
        action = str(row.get("action") or "unknown")
        actions[action] = actions.get(action, 0) + 1
        status = str(row.get("status") or "failed")
        try:
            stat = blend_path.stat()
            blend_mtime_ns = stat.st_mtime_ns
            blend_size = stat.st_size
        except FileNotFoundError:
            blend_mtime_ns = None
            blend_size = None
        record = {
            "status": status,
            "action": action,
            "asset_kind": plan["asset_kind"],
            "target_id": key,
            "blend_file": str(blend_path),
            "blend_mtime_ns": blend_mtime_ns,
            "blend_size": blend_size,
            "preview_after": row.get("preview_after"),
            "preview_after_size": row.get("preview_after_size"),
            "preview_after_metrics": row.get("preview_after_metrics"),
            "preview_nonblank": bool(row.get("preview_after")),
            "asset_object": row.get("asset_object"),
            "duration_s": row.get("duration_s"),
            "finished_utc": _now_utc(),
            "error": row.get("error"),
        }
        progress.update(key, record)
        if status == "success":
            ok += 1
        else:
            failed += 1

    crash_tolerated = proc.returncode != 0 and failed == 0 and len(rows) >= len(batch)
    return {
        "batch": batch_name,
        "returncode": proc.returncode,
        "duration_s": round(time.time() - t0, 3),
        "ok": ok,
        "failed": failed,
        "missing": missing,
        "missing_count": len(missing),
        "actions": actions,
        "crash_tolerated": crash_tolerated,
        "stdout_log": str(stdout_path),
        "results": str(results_path),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bake generated previews for asset-library .blend files.")
    parser.add_argument("--blender", type=Path, default=_default_blender())
    parser.add_argument("--worker", type=Path, default=_default_worker())
    parser.add_argument("--target-file", type=Path, default=_default_target_file())
    parser.add_argument("--library-root", type=Path, default=_default_library_root())
    parser.add_argument("--progress-file", type=Path, default=_default_progress_file())
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--batch-log-dir", type=Path, default=None)
    parser.add_argument("--only-list", type=Path, default=None)
    parser.add_argument("--asset-kind", action="append", default=["bp"],
                        help="Asset kind to process. Repeatable; defaults to bp.")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verify-only", action="store_true",
                        help="Check generated previews without baking missing ones.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    args.blender = args.blender.resolve()
    args.worker = args.worker.resolve()
    args.target_file = args.target_file.resolve()
    args.library_root = args.library_root.resolve()
    args.progress_file = args.progress_file.resolve()
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive.")
    if not args.blender.is_file():
        raise SystemExit(f"Blender executable not found: {args.blender}")
    if not args.worker.is_file():
        raise SystemExit(f"Worker script not found: {args.worker}")
    if args.batch_log_dir is None:
        args.batch_log_dir = args.progress_file.parent / "GeneratedPreviewBatches"
    else:
        args.batch_log_dir = args.batch_log_dir.resolve()

    progress = ProgressManifest(args.progress_file)
    plans, counts = _select_plans(args, progress)
    print(f"Generated preview bake: selected {len(plans)} of {counts['targets']} targets")
    print(json.dumps(counts, indent=2, sort_keys=True))

    if args.dry_run:
        for plan in plans[:50]:
            print(plan["blend_path"])
        if len(plans) > 50:
            print(f"... {len(plans) - 50} more")
        return 0

    batches = _chunks(plans, args.batch_size)
    ok = 0
    failed = 0
    crash_tolerated = 0
    retried = 0
    batch_reports: list[dict[str, Any]] = []

    for index, batch in enumerate(batches, start=1):
        name = f"batch_{index:04d}"
        report = _run_batch(args=args, batch=batch, batch_name=name, progress=progress)
        batch_reports.append({k: v for k, v in report.items() if k != "missing"})
        ok += int(report["ok"])
        failed += int(report["failed"])
        if report["crash_tolerated"]:
            crash_tolerated += 1
        print(
            f"[{index}/{len(batches)}] ok={report['ok']} failed={report['failed']} "
            f"rc={report['returncode']} actions={report['actions']}"
            f"{' crash_tolerated' if report['crash_tolerated'] else ''}"
        )

        missing = report["missing"]
        if missing and len(batch) > 1:
            for retry_index, plan in enumerate(missing, start=1):
                retried += 1
                retry_name = f"{name}_retry_{retry_index:03d}"
                retry_report = _run_batch(args=args, batch=[plan], batch_name=retry_name, progress=progress)
                batch_reports.append({k: v for k, v in retry_report.items() if k != "missing"})
                if retry_report["crash_tolerated"]:
                    crash_tolerated += 1
                if retry_report["ok"]:
                    ok += int(retry_report["ok"])
                    failed -= 1
                print(
                    f"  retry {retry_name}: ok={retry_report['ok']} "
                    f"failed={retry_report['failed']} rc={retry_report['returncode']}"
                )

    summary = {
        "schema": PROGRESS_SCHEMA,
        "generated_at_utc": _now_utc(),
        "target_file": str(args.target_file),
        "library_root": str(args.library_root),
        "progress_file": str(args.progress_file),
        "batch_log_dir": str(args.batch_log_dir),
        "counts": counts,
        "selected": len(plans),
        "ok": ok,
        "failed": failed,
        "retried": retried,
        "crash_tolerated_batches": crash_tolerated,
        "progress_totals": progress.totals(),
        "batches": batch_reports,
    }
    if args.out is not None:
        _write_json(args.out.resolve(), summary)
    print(json.dumps({k: summary[k] for k in ("selected", "ok", "failed", "retried", "crash_tolerated_batches")}, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
