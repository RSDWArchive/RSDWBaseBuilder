"""
Build the shippable Blender extension zip for RSDW Base Builder.

Uses the portable Blender's built-in extension builder so the resulting zip
matches what the Blender extensions platform expects:

    blender --command extension build --source-dir <addon> --output-dir <dist>

Output: dist/rsdw_base_builder-<version>.zip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _read_manifest_info(manifest: Path) -> tuple[str, str]:
    text = manifest.read_text(encoding="utf-8")
    id_match = re.search(r'^\s*id\s*=\s*"([^"]+)"', text, re.MULTILINE)
    version_match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not id_match:
        raise RuntimeError(f"could not parse id from {manifest}")
    if not version_match:
        raise RuntimeError(f"could not parse version from {manifest}")
    return id_match.group(1), version_match.group(1)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _candidate_blenders() -> list[Path]:
    repo = _repo_root()
    candidates: list[Path] = [
        repo / "_local" / "blender-5.0.0-windows-x64" / "blender.exe",
    ]
    env_path = os.environ.get("BLENDER_EXE")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend([
        Path(r"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe"),
        Path(r"C:/Program Files/Blender Foundation/Blender 4.5/blender.exe"),
        Path(r"C:/Program Files/Blender Foundation/Blender 4.4/blender.exe"),
        Path(r"C:/Program Files/Blender Foundation/Blender 4.3/blender.exe"),
        Path(r"C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"),
    ])
    return candidates


def _find_blender(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.is_file() else None
    for candidate in _candidate_blenders():
        if candidate.is_file():
            return candidate
    return None


def _split_file(path: Path, *, chunk_mb: float, remove_original: bool) -> Path:
    chunk_size = int(chunk_mb * 1024 * 1024)
    if chunk_size <= 0:
        raise ValueError("--split-size-mb must be positive")

    parts_dir = path.parent / f"{path.name}.parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    for old in parts_dir.glob("*"):
        if old.is_file():
            old.unlink()

    source_size = path.stat().st_size
    source_hash = _sha256(path)
    parts: list[dict] = []
    with path.open("rb") as source:
        idx = 0
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            part_path = parts_dir / f"{path.name}.part{idx:04d}"
            part_path.write_bytes(chunk)
            parts.append({
                "index": idx,
                "name": part_path.name,
                "bytes": len(chunk),
                "sha256": _sha256(part_path),
            })
            idx += 1

    manifest = {
        "schema": "RSDWBaseBuilder.SplitPackage.v1",
        "generated_at_utc": _now_iso(),
        "source_name": path.name,
        "source_bytes": source_size,
        "source_sha256": source_hash,
        "chunk_size_bytes": chunk_size,
        "part_count": len(parts),
        "parts": parts,
        "reassemble_windows_cmd": f"copy /b {path.name}.part* ..\\{path.name}",
    }
    manifest_path = parts_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if remove_original:
        path.unlink()
    return manifest_path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--blender", type=Path, default=None)
    p.add_argument(
        "--source-dir",
        type=Path,
        default=_repo_root() / "_build" / "extension",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=_repo_root() / "dist",
    )
    p.add_argument(
        "--split-size-mb",
        type=float,
        default=None,
        help="Split the resulting zip into chunks no larger than this many MiB.",
    )
    p.add_argument(
        "--remove-unsplit",
        action="store_true",
        help="Remove the original zip after writing split chunks.",
    )
    p.add_argument(
        "--max-size-mb",
        type=float,
        default=1900.0,
        help="Fail if the single extension zip exceeds this size. Use --allow-large to override.",
    )
    p.add_argument("--allow-large", action="store_true")
    p.add_argument("--keep-existing", action="store_true",
                   help="Do not remove an existing same-version zip before building.")
    p.add_argument("--manifest-out", type=Path, default=None,
                   help="Write a JSON package report. Defaults beside the zip.")
    args = p.parse_args()

    blender = _find_blender(args.blender)
    if blender is None:
        print(
            "blender.exe not found. Pass --blender or set BLENDER_EXE.",
            file=sys.stderr,
        )
        return 2

    manifest = args.source_dir / "blender_manifest.toml"
    if not manifest.is_file():
        print(f"manifest not found: {manifest}", file=sys.stderr)
        return 2
    extension_id, version = _read_manifest_info(manifest)
    print(f"Building extension {extension_id} v{version}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    expected_zip = args.output_dir / f"{extension_id}-{version}.zip"
    if expected_zip.is_file() and not args.keep_existing:
        expected_zip.unlink()

    cmd = [
        str(blender),
        "--command", "extension", "build",
        "--source-dir", str(args.source_dir.resolve()),
        "--output-dir", str(args.output_dir.resolve()),
    ]
    print("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        return proc.returncode

    # Blender names the zip after the manifest id + version.
    # Locate the freshest zip in output_dir for the user's convenience.
    zips = sorted(args.output_dir.glob(f"{extension_id}*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        print(f"no extension zip found in {args.output_dir}", file=sys.stderr)
        return 1
    package_report = None
    if zips:
        zp = zips[-1]
        size_mb = zp.stat().st_size / (1024 * 1024)
        print(f"\nBuilt: {zp}  ({size_mb:.1f} MB)")
        package_report = {
            "schema": "RSDWBaseBuilder.ExtensionPackage.v1",
            "generated_at_utc": _now_iso(),
            "source_dir": str(args.source_dir.resolve()),
            "output_zip": str(zp.resolve()),
            "extension_id": extension_id,
            "version": version,
            "bytes": zp.stat().st_size,
            "mb": round(size_mb, 3),
            "sha256": _sha256(zp),
            "max_size_mb": args.max_size_mb,
            "single_zip_ok": args.allow_large or size_mb <= args.max_size_mb,
        }
        manifest_out = args.manifest_out or (args.output_dir / f"{extension_id}-{version}.package.json")
        manifest_out.write_text(json.dumps(package_report, indent=2) + "\n", encoding="utf-8")
        print(f"Package report: {manifest_out}")
        if size_mb > args.max_size_mb and not args.allow_large:
            print(
                f"zip is {size_mb:.1f} MB, above --max-size-mb {args.max_size_mb:.1f} MB",
                file=sys.stderr,
            )
            return 3
        if args.split_size_mb is not None:
            manifest_path = _split_file(
                zp,
                chunk_mb=args.split_size_mb,
                remove_original=args.remove_unsplit,
            )
            print(f"Split package manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
