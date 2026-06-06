"""Run the RSDW Base Builder asset-library update pipeline.

This project is the consumer stage after RSDWArchive and RSDWModel have
already produced matching versioned outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_ARCHIVE_ROOT = Path(r"E:/Github/RSDWArchive")
DEFAULT_MODEL_ROOT = Path(r"E:/Github/RSDWModel")
DEFAULT_RELEASE_MAX_MB = 1900.0
DEFAULT_GIT_BATCH_GB = 1.9


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_extension_source_root() -> Path:
    return repo_root() / "addon"


def default_build_root() -> Path:
    return repo_root() / "_build"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def print_section(title: str) -> None:
    print(f"\n== {title} ==")


def command_text(cmd: Sequence[str | Path]) -> str:
    return subprocess.list2cmdline([str(part) for part in cmd])


def candidate_blenders(root: Path) -> list[Path]:
    out: list[Path] = []
    out.append(root / "_local" / "blender-5.0.0-windows-x64" / "blender.exe")
    env_path = os.environ.get("BLENDER_EXE")
    if env_path:
        out.append(Path(env_path))
    out.extend([
        Path(r"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe"),
        Path(r"C:/Program Files/Blender Foundation/Blender 4.5/blender.exe"),
        Path(r"C:/Program Files/Blender Foundation/Blender 4.4/blender.exe"),
        Path(r"C:/Program Files/Blender Foundation/Blender 4.3/blender.exe"),
        Path(r"C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"),
    ])
    return out


def find_blender(root: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.is_file() else None
    for candidate in candidate_blenders(root):
        if candidate.is_file():
            return candidate
    return None


def extension_stage_dir(args: argparse.Namespace) -> Path:
    return args.library_root or (args.build_root / "extension")


def read_manifest_version(source_root: Path) -> str:
    return read_manifest_info(source_root)[1]


def read_manifest_info(source_root: Path) -> tuple[str, str]:
    manifest = source_root / "blender_manifest.toml"
    if not manifest.is_file():
        return "", ""
    text = manifest.read_text(encoding="utf-8")
    id_match = re.search(r'^\s*id\s*=\s*"([^"]+)"', text, re.MULTILINE)
    version_match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return (
        id_match.group(1) if id_match else "",
        version_match.group(1) if version_match else "",
    )


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def version_dirs(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    out = set()
    for child in root.iterdir():
        if child.is_dir() and re.match(r"^\d+(?:\.\d+)+$", child.name):
            out.add(child.name)
    return out


def detect_version(archive_root: Path, model_root: Path) -> str:
    common = sorted(version_dirs(archive_root) & version_dirs(model_root), key=version_key)
    if not common:
        raise SystemExit("Could not detect a shared Archive/Model version. Pass --version.")
    return common[-1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_inputs(args: argparse.Namespace) -> dict[str, Path | str | None]:
    version = args.version or detect_version(args.archive_root, args.model_root)
    root = repo_root()
    archive_version_root = (args.archive_root / version).resolve()
    model_version_root = (args.model_root / version).resolve()
    archive_json_root = archive_version_root / "json"
    archive_texture_root = archive_version_root / "textures"
    item_data = args.item_data or (args.archive_root / "website" / "tools" / "ItemData" / "ItemData.json")
    bp_data = args.bp_data or (args.archive_root / "website" / "tools" / "BPData" / "BPData.json")
    sm_data = model_version_root / "ModelData" / "SM_Data.json"
    sk_data = model_version_root / "ModelData" / "SK_Data.json"
    library_root = extension_stage_dir(args)
    blender = find_blender(root, args.blender)

    paths = {
        "archive_version_root": archive_version_root,
        "model_version_root": model_version_root,
        "archive_json_root": archive_json_root,
        "archive_texture_root": archive_texture_root,
        "item_data": item_data,
        "bp_data": bp_data,
        "sm_data": sm_data,
        "sk_data": sk_data,
        "library_root": library_root,
        "blender": blender,
        "build_root": args.build_root,
        "extension_source_root": args.extension_source_root,
    }
    missing = [
        f"{name}: {path}"
        for name, path in paths.items()
        if name not in {"blender", "library_root", "build_root"} and isinstance(path, Path) and not path.exists()
    ]
    if missing:
        raise SystemExit("Missing required input(s):\n  " + "\n  ".join(missing))
    if blender is None and args.mode != "targets" and not args.dry_run:
        raise SystemExit("blender.exe not found. Pass --blender or set BLENDER_EXE.")

    item_doc = load_json(item_data)
    item_version = str(item_doc.get("version") or "")
    if item_version and item_version != version:
        raise SystemExit(f"ItemData version {item_version!r} does not match requested {version!r}.")

    bp_doc = load_json(bp_data)
    bp_json_root = str((bp_doc.get("_meta") or {}).get("jsonRoot") or "").replace("\\", "/")
    if bp_json_root and version not in bp_json_root:
        raise SystemExit(f"BPData jsonRoot does not appear to match requested {version!r}: {bp_json_root}")

    return {"version": version, **paths}


def run_command(
    title: str,
    cmd: Sequence[str | Path],
    *,
    log_path: Path,
    cwd: Path,
    allow_failure: bool = False,
) -> dict[str, Any]:
    print_section(title)
    print("$ " + command_text(cmd))
    t0 = datetime.now(timezone.utc)
    proc = subprocess.run(
        [str(part) for part in cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_text = [
        "$ " + command_text(cmd),
        "",
        "## stdout",
        proc.stdout or "",
        "",
        "## stderr",
        proc.stderr or "",
        "",
        f"exit_code: {proc.returncode}",
        f"duration_s: {elapsed:.3f}",
    ]
    log_path.write_text("\n".join(log_text), encoding="utf-8")
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    if proc.returncode != 0 and not allow_failure:
        raise SystemExit(f"{title} failed with exit code {proc.returncode}. See {log_path}")
    return {
        "title": title,
        "cmd": command_text(cmd),
        "log": str(log_path),
        "exit_code": proc.returncode,
        "duration_s": round(elapsed, 3),
        "ok": proc.returncode == 0,
    }


def write_smoke_list(target_file: Path, out_path: Path, limit: int | None) -> list[str]:
    doc = load_json(target_file)
    ids = list(doc.get("smoke_target_ids") or [])
    if limit is not None and limit >= 0:
        ids = ids[:limit]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
    return ids


def load_git_plan_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = load_json(path)
    batches = data.get("batches") if isinstance(data.get("batches"), list) else []
    return {
        "changed_path_count": data.get("changed_path_count"),
        "allowed_path_count": data.get("allowed_path_count"),
        "blocked_path_count": data.get("blocked_path_count"),
        "batch_count": len(batches),
        "max_batch_bytes": data.get("max_batch_bytes"),
        "file_limit_bytes": data.get("file_limit_bytes"),
        "status_counts": data.get("status_counts") or {},
    }


def should_run_git_plan(args: argparse.Namespace) -> bool:
    if args.skip_git_plan or args.dry_run:
        return False
    return (
        args.mode in {"full", "package-current"}
        or args.run_git_plan
        or args.git_plan
        or args.git_commit_batches
    )


def skipped_git_plan_reason(args: argparse.Namespace) -> str:
    if args.skip_git_plan:
        return "--skip-git-plan"
    if args.dry_run:
        return "--dry-run"
    return "partial/smoke pipeline run"


def resolve_git_plan_output(args: argparse.Namespace, root: Path, log_dir: Path) -> Path:
    out_path = args.git_plan_output or (log_dir / "GitCommitPlan.json")
    if not out_path.is_absolute():
        out_path = (root / out_path).resolve()
    return out_path


def run_git_plan_stage(
    args: argparse.Namespace,
    *,
    root: Path,
    log_dir: Path,
    version: str,
    log_name: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not should_run_git_plan(args):
        print_section("Git commit plan")
        print(f"Skipped: {skipped_git_plan_reason(args)}.")
        return {"skipped": True, "reason": skipped_git_plan_reason(args)}, None

    git_plan_output = resolve_git_plan_output(args, root, log_dir)
    git_mode = "commit-batches" if args.git_commit_batches else "plan"
    git_cmd: list[str | Path] = [
        sys.executable,
        root / "tools" / "PlanGitCommits.py",
        git_mode,
        "--repo",
        root,
        "--out",
        git_plan_output,
        "--max-batch-gb",
        str(args.git_max_batch_gb),
        "--file-limit-mb",
        str(args.git_file_limit_mb),
        "--message-prefix",
        f"Update RSDWBaseBuilder {version}",
    ]
    if args.git_commit_batches:
        git_cmd.append("--execute")
    if args.git_push_each:
        git_cmd.append("--push-each")

    stage = run_command(
        "Git commit plan" if not args.git_commit_batches else "Git commit batches",
        git_cmd,
        log_path=log_dir / log_name,
        cwd=root,
    )
    summary = {
        "skipped": False,
        "mode": git_mode,
        "plan": str(git_plan_output),
        "commit_batches": args.git_commit_batches,
        "push_each": args.git_push_each,
        **load_git_plan_summary(git_plan_output),
    }
    return summary, stage


def stage_command(args: argparse.Namespace, *, include_current_assets: bool, log_dir: Path) -> list[str | Path]:
    cmd: list[str | Path] = [
        sys.executable,
        repo_root() / "tools" / "AssetLibrary" / "PrepareExtensionStage.py",
        "--source-root", args.extension_source_root,
        "--build-root", args.build_root,
        "--stage-dir", extension_stage_dir(args),
        "--out-manifest", log_dir / "extension_stage_manifest.json",
    ]
    if args.clean_stage:
        cmd.append("--clean")
    if include_current_assets:
        cmd.append("--include-current-assets")
    return cmd


def package_command(args: argparse.Namespace) -> list[str | Path]:
    cmd: list[str | Path] = [
        sys.executable,
        repo_root() / "tools" / "AssetLibrary" / "BuildExtensionZip.py",
        "--source-dir", extension_stage_dir(args),
        "--output-dir", repo_root() / "dist",
        "--max-size-mb", str(args.release_max_mb),
    ]
    if args.blender is not None:
        cmd.extend(["--blender", args.blender])
    return cmd


def resolve_portable_extension_dir(
    args: argparse.Namespace,
    *,
    root: Path,
    extension_id: str,
) -> Path:
    if args.portable_extension_dir is not None:
        target = args.portable_extension_dir
        return target.resolve() if target.is_absolute() else (root / target).resolve()

    blender = find_blender(root, args.blender)
    if blender is None:
        raise SystemExit("blender.exe not found. Pass --blender or --portable-extension-dir.")
    return (
        blender.parent
        / "portable"
        / "extensions"
        / "user_default"
        / extension_id
    ).resolve()


def validate_portable_extension_target(target_dir: Path, extension_id: str) -> None:
    target = target_dir.resolve()
    if target.name != extension_id:
        raise SystemExit(f"refusing to sync extension to unexpected target name: {target}")
    if (
        target.parent.name != "user_default"
        or target.parent.parent.name != "extensions"
        or target.parent.parent.parent.name != "portable"
    ):
        raise SystemExit(f"refusing to sync outside portable/extensions/user_default: {target}")


def sync_portable_extension(
    *,
    stage_dir: Path,
    target_dir: Path,
) -> dict[str, Any]:
    stage_dir = stage_dir.resolve()
    target_dir = target_dir.resolve()
    extension_id, version = read_manifest_info(stage_dir)
    if not extension_id:
        raise SystemExit(f"staged extension manifest is missing id: {stage_dir / 'blender_manifest.toml'}")
    validate_portable_extension_target(target_dir, extension_id)
    if stage_dir == target_dir or is_relative_to(stage_dir, target_dir):
        raise SystemExit(f"refusing to sync stage into itself: {stage_dir} -> {target_dir}")

    source_files = [path for path in stage_dir.rglob("*") if path.is_file()]
    source_bytes = sum(path.stat().st_size for path in source_files)
    previous_file_count = (
        len([path for path in target_dir.rglob("*") if path.is_file()])
        if target_dir.is_dir()
        else 0
    )

    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(stage_dir, target_dir)

    copied_files = [path for path in target_dir.rglob("*") if path.is_file()]
    copied_bytes = sum(path.stat().st_size for path in copied_files)
    return {
        "schema": "RSDWBaseBuilder.PortableExtensionSync.v1",
        "generated_at_utc": now_iso(),
        "extension_id": extension_id,
        "version": version,
        "stage_dir": str(stage_dir),
        "target_dir": str(target_dir),
        "previous_file_count": previous_file_count,
        "source_files": len(source_files),
        "source_bytes": source_bytes,
        "copied_files": len(copied_files),
        "copied_bytes": copied_bytes,
        "copied_mb": round(copied_bytes / (1024 * 1024), 3),
    }


def run_portable_sync_stage(
    args: argparse.Namespace,
    *,
    root: Path,
    log_dir: Path,
    stage_dir: Path,
    log_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    extension_id, _version = read_manifest_info(stage_dir)
    if not extension_id:
        raise SystemExit(f"staged extension manifest is missing id: {stage_dir / 'blender_manifest.toml'}")
    target_dir = resolve_portable_extension_dir(args, root=root, extension_id=extension_id)

    print_section("Sync portable extension")
    print(f"stage:  {stage_dir}")
    print(f"target: {target_dir}")
    t0 = datetime.now(timezone.utc)
    report = sync_portable_extension(stage_dir=stage_dir, target_dir=target_dir)
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    report_path = log_dir / "portable_extension_sync.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**report, "report": str(report_path)}, indent=2))
    stage = {
        "title": "Sync portable extension",
        "log": str(report_path),
        "duration_s": round(elapsed, 3),
        "ok": True,
        "target_dir": str(target_dir),
        "copied_files": report["copied_files"],
    }
    log_path = log_dir / log_name
    log_path.write_text(json.dumps({**stage, "report": report}, indent=2) + "\n", encoding="utf-8")
    stage["log"] = str(log_path)
    return report, stage


def run_sync_portable(args: argparse.Namespace) -> int:
    root = repo_root()
    log_dir = root / "PipelineLogs" / utc_stamp()
    log_dir.mkdir(parents=True, exist_ok=True)
    stage_dir = extension_stage_dir(args)
    extension_id, version = read_manifest_info(stage_dir)
    if not extension_id:
        raise SystemExit(f"staged extension manifest is missing id: {stage_dir / 'blender_manifest.toml'}")

    if args.dry_run:
        target_dir = resolve_portable_extension_dir(args, root=root, extension_id=extension_id)
        print_section("Sync portable extension")
        print("Dry run: no files were copied.")
        print(f"stage:  {stage_dir}")
        print(f"target: {target_dir}")
        sync_report = {
            "skipped": True,
            "reason": "--dry-run",
            "stage_dir": str(stage_dir),
            "target_dir": str(target_dir),
        }
        sync_stage = {"title": "Sync portable extension", "skipped": True, "reason": "--dry-run"}
    else:
        sync_report, sync_stage = run_portable_sync_stage(
            args,
            root=root,
            log_dir=log_dir,
            stage_dir=stage_dir,
            log_name="00_sync_portable_extension.log",
        )
    run_summary = {
        "schema": "RSDWBaseBuilder.PipelineRun.v1",
        "generated_at_utc": now_iso(),
        "version": version or "unknown",
        "mode": args.mode,
        "dry_run": False,
        "inputs": {
            "stage_dir": str(stage_dir),
        },
        "outputs": {
            "log_dir": str(log_dir),
            "portable_extension_sync": str(log_dir / "portable_extension_sync.json"),
        },
        "stages": [sync_stage],
        "portable_extension_sync": sync_report,
        "git_plan": {"skipped": True, "reason": "sync-portable mode"},
        "git_commit_plan": {"skipped": True, "reason": "sync-portable mode"},
    }
    (root / "PipelineRun.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    print_section("Pipeline summary")
    print(json.dumps({
        "version": version,
        "mode": args.mode,
        "log_dir": str(log_dir),
        "run_summary": str(root / "PipelineRun.json"),
    }, indent=2))
    return 0


def run_package_current(args: argparse.Namespace) -> int:
    root = repo_root()
    log_dir = root / "PipelineLogs" / utc_stamp()
    log_dir.mkdir(parents=True, exist_ok=True)
    run_summary_path = root / "PipelineRun.json"
    stage_dir = extension_stage_dir(args)
    version = read_manifest_version(args.extension_source_root) or "unknown"
    stages: list[dict[str, Any]] = []

    print_section("Package Current Extension")
    print(f"extension_source_root: {args.extension_source_root}")
    print(f"stage_dir: {stage_dir}")
    print(f"release_max_mb: {args.release_max_mb}")
    print(f"git plan: {resolve_git_plan_output(args, root, log_dir) if should_run_git_plan(args) else '<skipped>'}")
    print(f"logs: {log_dir}")

    if args.dry_run:
        print("Dry run: stage/package commands were not executed.")
        stages.append({"title": "Prepare extension stage", "skipped": True, "reason": "--dry-run"})
        stages.append({"title": "Package extension", "skipped": True, "reason": "--dry-run"})
    else:
        old_clean_stage = args.clean_stage
        args.clean_stage = True
        stages.append(run_command(
            "Prepare extension stage",
            stage_command(args, include_current_assets=args.include_current_assets, log_dir=log_dir),
            log_path=log_dir / "00_stage_current.log",
            cwd=root,
        ))
        args.clean_stage = old_clean_stage

        stages.append(run_command(
            "Git file-size audit",
            [
                sys.executable,
                root / "tools" / "AssetLibrary" / "AuditGitFileSizes.py",
                stage_dir,
                "--limit-mb", str(args.git_file_limit_mb),
                "--out", log_dir / "git_file_size_audit.json",
            ],
            log_path=log_dir / "01_git_file_size_audit.log",
            cwd=root,
        ))

        if args.skip_package:
            stages.append({"title": "Package extension", "skipped": True, "reason": "--skip-package"})
        else:
            stages.append(run_command(
                "Package extension",
                package_command(args),
                log_path=log_dir / "02_package.log",
                cwd=root,
            ))

    portable_sync: dict[str, Any] = {"skipped": True, "reason": "--sync-portable-extension not supplied"}
    if args.sync_portable_extension:
        if args.dry_run:
            print_section("Sync portable extension")
            print("Skipped because --dry-run was supplied.")
            portable_sync = {"skipped": True, "reason": "--dry-run"}
            stages.append({"title": "Sync portable extension", "skipped": True, "reason": "--dry-run"})
        else:
            portable_sync, portable_sync_stage = run_portable_sync_stage(
                args,
                root=root,
                log_dir=log_dir,
                stage_dir=stage_dir,
                log_name="03_sync_portable_extension.log",
            )
            stages.append(portable_sync_stage)

    git_plan, git_plan_stage = run_git_plan_stage(
        args,
        root=root,
        log_dir=log_dir,
        version=version,
        log_name="04_git_commit_plan.log" if args.sync_portable_extension else "03_git_commit_plan.log",
    )
    if git_plan_stage is not None:
        stages.append(git_plan_stage)

    run_summary = {
        "schema": "RSDWBaseBuilder.PipelineRun.v1",
        "generated_at_utc": now_iso(),
        "version": version,
        "mode": args.mode,
        "dry_run": args.dry_run,
        "inputs": {
            "extension_source_root": str(args.extension_source_root),
            "stage_dir": str(stage_dir),
            "build_root": str(args.build_root),
        },
        "outputs": {
            "log_dir": str(log_dir),
            "stage_manifest": str(log_dir / "extension_stage_manifest.json"),
            "git_file_size_audit": str(log_dir / "git_file_size_audit.json"),
            "portable_extension_sync": str(log_dir / "portable_extension_sync.json"),
            "git_commit_plan": str(resolve_git_plan_output(args, root, log_dir)),
            "dist": str(root / "dist"),
        },
        "stages": stages,
        "portable_extension_sync": portable_sync,
        "git_plan": git_plan,
        "git_commit_plan": git_plan,
    }
    run_summary_path.write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    print_section("Pipeline summary")
    print(json.dumps({
        "version": version,
        "mode": args.mode,
        "log_dir": str(log_dir),
        "run_summary": str(run_summary_path),
    }, indent=2))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update the RSDW Base Builder asset library.")
    parser.add_argument("--version", default=None, help="Game version. Defaults to latest shared Archive/Model version.")
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("--model-root", type=Path, default=DEFAULT_MODEL_ROOT)
    parser.add_argument("--item-data", type=Path, default=None)
    parser.add_argument("--bp-data", type=Path, default=None)
    parser.add_argument("--build-root", type=Path, default=default_build_root())
    parser.add_argument("--extension-source-root", type=Path, default=default_extension_source_root())
    parser.add_argument("--library-root", type=Path, default=None)
    parser.add_argument("--blender", type=Path, default=None)
    parser.add_argument("--mode", choices=("package-current", "sync-portable", "targets", "smoke", "full"), default="smoke")
    parser.add_argument("--dry-run", action="store_true", help="Generate plans/catalogs, but do not write asset blends or package.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only", default=None)
    parser.add_argument("--package", action="store_true", help="Build the shippable extension zip after a successful full/smoke build.")
    parser.add_argument("--skip-package", action="store_true")
    parser.add_argument("--clean-stage", action="store_true", help="Remove _build/extension before staging runtime files.")
    parser.add_argument("--sync-portable-extension", action="store_true",
                        help="After the pipeline succeeds, replace the portable Blender installed extension with the staged extension.")
    parser.add_argument("--portable-extension-dir", type=Path, default=None,
                        help="Installed extension directory to sync. Defaults beside the selected portable blender.exe.")
    parser.add_argument("--include-current-assets", action="store_true",
                        help="Copy the currently tracked public asset folders into the stage.")
    parser.add_argument("--material-mode", choices=("light", "fallback", "none"), default="light",
                        help="light keeps imported/linked materials without packing fallbacks; fallback preserves the old packed fallback behavior.")
    parser.add_argument("--skip-shared-materials", action="store_true",
                        help="Compatibility flag. Shared material shards are only built when --material-mode fallback is selected.")
    parser.add_argument("--git-file-limit-mb", type=float, default=95.0,
                        help="Generated-file size limit for Git-safe source assets and commit planning.")
    parser.add_argument("--release-max-mb", type=float, default=DEFAULT_RELEASE_MAX_MB,
                        help="Fail packaging if the single release zip exceeds this size.")
    parser.add_argument("--git-plan", action="store_true",
                        help="Legacy alias for --run-git-plan. Full/package-current runs plan by default.")
    parser.add_argument("--skip-git-plan", action="store_true",
                        help="Skip final Git commit batch planning.")
    parser.add_argument("--run-git-plan", action="store_true",
                        help="Run Git commit planning even for targets/smoke/partial runs.")
    parser.add_argument("--git-plan-output", type=Path, default=None,
                        help="Git commit plan JSON output path. Defaults to PipelineLogs/<stamp>/GitCommitPlan.json.")
    parser.add_argument("--git-max-batch-gb", type=float, default=DEFAULT_GIT_BATCH_GB,
                        help="Estimated uncompressed size limit per commit batch.")
    parser.add_argument("--git-commit-batches", action="store_true",
                        help="Create Git commits from the final batch plan. This stages and commits files.")
    parser.add_argument("--git-push-each", action="store_true",
                        help="Push after each Git commit batch. Requires --git-commit-batches.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    args.build_root = args.build_root.resolve()
    args.extension_source_root = args.extension_source_root.resolve()
    if args.library_root is not None:
        args.library_root = args.library_root.resolve()
    if args.git_push_each and not args.git_commit_batches:
        raise SystemExit("--git-push-each requires --git-commit-batches.")
    if args.mode == "sync-portable":
        return run_sync_portable(args)
    if args.mode == "package-current":
        return run_package_current(args)

    inputs = resolve_inputs(args)
    version = str(inputs["version"])
    log_dir = root / "PipelineLogs" / utc_stamp()
    log_dir.mkdir(parents=True, exist_ok=True)

    catalog_reconciliation = root / "tools" / "AssetLibrary" / "catalog_reconciliation.json"
    building_targets = root / "tools" / "AssetLibrary" / "catalog_asset_targets.json"
    unified_targets = root / "tools" / "AssetLibrary" / "asset_library_targets.json"
    catalog_file = Path(inputs["library_root"]) / "blender_assets.cats.txt"
    material_inventory = root / "tools" / "ModelData" / "MaterialInventory.json"
    materials_blend = Path(inputs["library_root"]) / "_Materials.blend"
    materials_manifest = Path(inputs["library_root"]) / "_Materials.manifest.json"
    progress_file = args.build_root / f"AssetLibraryProgress.{version}.json"
    run_summary_path = root / "PipelineRun.json"

    print_section("Inputs")
    for key in (
        "version",
        "archive_version_root",
        "model_version_root",
        "item_data",
        "bp_data",
        "library_root",
    ):
        print(f"{key}: {inputs[key]}")
    print(f"mode: {args.mode}")
    print(f"dry_run: {args.dry_run}")
    print(f"git plan: {resolve_git_plan_output(args, root, log_dir) if should_run_git_plan(args) else '<skipped>'}")
    print(f"logs: {log_dir}")

    stages: list[dict[str, Any]] = []

    if not args.dry_run or args.package or args.mode != "targets":
        stages.append(run_command(
            "Prepare extension stage",
            stage_command(
                args,
                include_current_assets=args.include_current_assets,
                log_dir=log_dir,
            ),
            log_path=log_dir / "00_stage.log",
            cwd=root,
        ))

    stages.append(run_command(
        "BPMap refresh",
        [
            sys.executable,
            root / "tools" / "ModelData" / "BuildBPMap.py",
            "--json-root", Path(inputs["archive_json_root"]),
            "--out", root / "tools" / "ModelData" / "BPMap.json",
        ],
        log_path=log_dir / "01_bpmap.log",
        cwd=root,
    ))

    stages.append(run_command(
        "Catalog reconciliation",
        [
            sys.executable,
            root / "tools" / "AssetLibrary" / "BuildCatalogReconciliation.py",
            "--catalog-file", root / "CatalogData" / "_catalog.json",
            "--disk-catalog-file", root / "CatalogData" / "_catalog_disk.json",
            "--piece-data-map", args.extension_source_root / "data" / "PieceDataMap.json",
            "--bpmap", root / "tools" / "ModelData" / "BPMap.json",
            "--archive-json-root", Path(inputs["archive_json_root"]),
            "--blend-root", Path(inputs["library_root"]),
            "--out", catalog_reconciliation,
        ],
        log_path=log_dir / "02_catalog_reconciliation.log",
        cwd=root,
    ))

    stages.append(run_command(
        "Building-piece targets",
        [
            sys.executable,
            root / "tools" / "AssetLibrary" / "BuildCatalogAssetTargets.py",
            "--reconciliation", catalog_reconciliation,
            "--source-root", Path(inputs["model_version_root"]),
            "--model-data", Path(inputs["sm_data"]),
            "--model-data", Path(inputs["sk_data"]),
            "--archive-json-root", Path(inputs["archive_json_root"]),
            "--bpmap", root / "tools" / "ModelData" / "BPMap.json",
            "--library-root", Path(inputs["library_root"]),
            "--out", building_targets,
        ],
        log_path=log_dir / "03_building_targets.log",
        cwd=root,
    ))

    stages.append(run_command(
        "Unified asset targets",
        [
            sys.executable,
            root / "tools" / "AssetLibrary" / "BuildAssetLibraryTargets.py",
            "--version", version,
            "--archive-root", args.archive_root,
            "--model-root", args.model_root,
            "--archive-json-root", Path(inputs["archive_json_root"]),
            "--item-data", Path(inputs["item_data"]),
            "--bp-data", Path(inputs["bp_data"]),
            "--model-data", Path(inputs["sm_data"]),
            "--model-data", Path(inputs["sk_data"]),
            "--building-targets", building_targets,
            "--library-root", Path(inputs["library_root"]),
            "--out", unified_targets,
        ],
        log_path=log_dir / "04_asset_targets.log",
        cwd=root,
    ))

    stages.append(run_command(
        "Asset catalog file",
        [
            sys.executable,
            root / "tools" / "AssetLibrary" / "BuildAssetCatalog.py",
            "--target-file", unified_targets,
            "--library-root", Path(inputs["library_root"]),
            "--out", catalog_file,
        ],
        log_path=log_dir / "05_asset_catalog.log",
        cwd=root,
    ))

    build_target_ids: list[str] = []
    only_list: Path | None = None
    if args.mode == "smoke":
        only_list = log_dir / "smoke_targets.txt"
        build_target_ids = write_smoke_list(unified_targets, only_list, args.limit)
        print(f"Smoke target count: {len(build_target_ids)}")

    if args.mode != "targets":
        stages.append(run_command(
            "Material inventory",
            [
                sys.executable,
                root / "tools" / "ModelData" / "InventoryMaterials.py",
                "--target-file", unified_targets,
                "--out-dir", root / "tools" / "ModelData",
            ],
            log_path=log_dir / "06_material_inventory.log",
            cwd=root,
        ))

        build_shared_materials = (
            args.mode == "full"
            and args.material_mode == "fallback"
            and not args.skip_shared_materials
        )
        if build_shared_materials:
            if args.dry_run:
                print_section("Shared materials")
                print("Skipped because --dry-run was supplied.")
                stages.append({"title": "Shared materials", "skipped": True, "reason": "--dry-run"})
            else:
                stages.append(run_command(
                    "Shared materials",
                    [
                        sys.executable,
                        root / "tools" / "AssetLibrary" / "BuildSharedMaterials.py",
                        "--blender", Path(inputs["blender"]),
                        "--source-root", Path(inputs["model_version_root"]),
                        "--material-data-root", Path(inputs["archive_json_root"]),
                        "--material-data-root", Path(inputs["archive_texture_root"]),
                        "--inventory", material_inventory,
                        "--out-blend", materials_blend,
                        "--manifest", materials_manifest,
                        "--shard-size-mb", str(args.git_file_limit_mb),
                    ],
                    log_path=log_dir / "07_shared_materials.log",
                    cwd=root,
                ))
        elif args.mode == "full":
            print_section("Shared materials")
            reason = "--skip-shared-materials" if args.skip_shared_materials else f"--material-mode {args.material_mode}"
            print(f"Skipped by {reason}.")
            stages.append({"title": "Shared materials", "skipped": True, "reason": reason})

        build_cmd: list[str | Path] = [
            sys.executable,
            root / "tools" / "AssetLibrary" / "BuildAssetLibrary.py",
            "--data-file", Path(inputs["sm_data"]),
            "--extra-data-file", Path(inputs["sk_data"]),
            "--source-root", Path(inputs["model_version_root"]),
            "--material-data-root", Path(inputs["archive_json_root"]),
            "--material-data-root", Path(inputs["archive_texture_root"]),
            "--library-root", Path(inputs["library_root"]),
            "--materials-blend", materials_blend,
            "--target-file", unified_targets,
            "--progress-file", progress_file,
            "--workers", str(args.workers),
            "--material-mode", args.material_mode,
        ]
        if materials_manifest.is_file():
            build_cmd.extend(["--materials-manifest", materials_manifest])
        if only_list is not None:
            build_cmd.extend(["--only-list", only_list])
        if args.mode == "full" and args.limit is not None:
            build_cmd.extend(["--limit", str(args.limit)])
        if args.only:
            build_cmd.extend(["--only", args.only])
        if args.force:
            build_cmd.append("--force")
        if args.dry_run:
            build_cmd.append("--dry-run")
        stages.append(run_command(
            "Asset blend build",
            build_cmd,
            log_path=log_dir / "08_asset_build.log",
            cwd=root,
        ))

        verify_cmd: list[str | Path] = [
            Path(inputs["blender"]),
            "--background",
            "--factory-startup",
            "--python", root / "tools" / "AssetLibrary" / "VerifyCatalogAssetMetadata.py",
            "--",
            "--target-file", unified_targets,
            "--library-root", Path(inputs["library_root"]),
            "--out", log_dir / "asset_metadata_report.json",
        ]
        if only_list is not None:
            verify_cmd.extend(["--only-list", only_list])
        if args.dry_run:
            print_section("Metadata verification")
            print("Skipped because --dry-run was supplied.")
            stages.append({"title": "Metadata verification", "skipped": True, "reason": "--dry-run"})
        else:
            stages.append(run_command(
                "Metadata verification",
                verify_cmd,
                log_path=log_dir / "09_verify_metadata.log",
                cwd=root,
            ))

        stages.append(run_command(
            "Git file-size audit",
            [
                sys.executable,
                root / "tools" / "AssetLibrary" / "AuditGitFileSizes.py",
                Path(inputs["library_root"]),
                "--limit-mb", str(args.git_file_limit_mb),
                "--out", log_dir / "git_file_size_audit.json",
            ],
            log_path=log_dir / "10_git_file_size_audit.log",
            cwd=root,
        ))

    package_requested = args.package and not args.skip_package and args.mode != "targets"
    if package_requested:
        if args.dry_run:
            print_section("Package")
            print("Skipped because --dry-run was supplied.")
            stages.append({"title": "Package", "skipped": True, "reason": "--dry-run"})
        else:
            stages.append(run_command(
                "Package extension",
                package_command(args),
                log_path=log_dir / "11_package.log",
                cwd=root,
            ))

    portable_sync: dict[str, Any] = {"skipped": True, "reason": "--sync-portable-extension not supplied"}
    if args.sync_portable_extension:
        if args.dry_run:
            print_section("Sync portable extension")
            print("Skipped because --dry-run was supplied.")
            portable_sync = {"skipped": True, "reason": "--dry-run"}
            stages.append({"title": "Sync portable extension", "skipped": True, "reason": "--dry-run"})
        else:
            sync_log_name = "12_sync_portable_extension.log" if package_requested else "11_sync_portable_extension.log"
            portable_sync, portable_sync_stage = run_portable_sync_stage(
                args,
                root=root,
                log_dir=log_dir,
                stage_dir=Path(inputs["library_root"]),
                log_name=sync_log_name,
            )
            stages.append(portable_sync_stage)

    git_plan, git_plan_stage = run_git_plan_stage(
        args,
        root=root,
        log_dir=log_dir,
        version=version,
        log_name=(
            "13_git_commit_plan.log"
            if args.sync_portable_extension and package_requested
            else "12_git_commit_plan.log"
        ),
    )
    if git_plan_stage is not None:
        stages.append(git_plan_stage)

    target_summary = load_json(unified_targets).get("summary") if unified_targets.is_file() else {}
    run_summary = {
        "schema": "RSDWBaseBuilder.PipelineRun.v1",
        "generated_at_utc": now_iso(),
        "version": version,
        "mode": args.mode,
        "dry_run": args.dry_run,
        "inputs": {key: str(value) for key, value in inputs.items()},
        "outputs": {
            "log_dir": str(log_dir),
            "catalog_reconciliation": str(catalog_reconciliation),
            "building_targets": str(building_targets),
            "asset_library_targets": str(unified_targets),
            "asset_catalog": str(catalog_file),
            "material_inventory": str(material_inventory),
            "materials_blend": str(materials_blend),
            "materials_manifest": str(materials_manifest),
            "git_file_size_audit": str(log_dir / "git_file_size_audit.json"),
            "portable_extension_sync": str(log_dir / "portable_extension_sync.json"),
            "git_commit_plan": str(resolve_git_plan_output(args, root, log_dir)),
            "progress_file": str(progress_file),
        },
        "target_summary": target_summary,
        "smoke_target_ids": build_target_ids,
        "stages": stages,
        "portable_extension_sync": portable_sync,
        "git_plan": git_plan,
        "git_commit_plan": git_plan,
    }
    run_summary_path.write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    print_section("Pipeline summary")
    print(json.dumps({
        "version": version,
        "mode": args.mode,
        "dry_run": args.dry_run,
        "target_summary": target_summary,
        "log_dir": str(log_dir),
        "run_summary": str(run_summary_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
