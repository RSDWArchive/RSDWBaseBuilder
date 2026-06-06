"""Fail when generated files are too large for normal Git hosting.

GitHub rejects individual files at 100 MiB. The default limit here is lower
so generated assets have a little safety margin.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "RSDWBaseBuilder.GitFileSizeAudit.v1"
DEFAULT_LIMIT_MB = 95.0
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _iter_files(root: Path, exclude_dirs: set[str]):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in exclude_dirs for part in path.parts):
            continue
        yield path


def audit(roots: list[Path], *, limit_mb: float, repo: Path) -> dict[str, Any]:
    limit_bytes = int(limit_mb * 1024 * 1024)
    checked = 0
    over_limit: list[dict[str, Any]] = []
    largest: list[dict[str, Any]] = []

    for root in roots:
        if not root.exists():
            raise SystemExit(f"scan root not found: {root}")
        for path in _iter_files(root, DEFAULT_EXCLUDE_DIRS):
            checked += 1
            size = path.stat().st_size
            record = {
                "path": _rel(path, repo),
                "bytes": size,
                "mb": round(size / (1024 * 1024), 3),
            }
            largest.append(record)
            if size > limit_bytes:
                over_limit.append(record)

    largest.sort(key=lambda item: item["bytes"], reverse=True)
    over_limit.sort(key=lambda item: item["bytes"], reverse=True)
    return {
        "schema": SCHEMA,
        "generated_at_utc": _now_iso(),
        "repo": str(repo),
        "roots": [str(root.resolve()) for root in roots],
        "limit_mb": limit_mb,
        "limit_bytes": limit_bytes,
        "checked_files": checked,
        "over_limit_count": len(over_limit),
        "over_limit": over_limit,
        "largest": largest[:50],
        "ok": not over_limit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit generated file sizes for Git limits.")
    parser.add_argument("roots", type=Path, nargs="+")
    parser.add_argument("--limit-mb", type=float, default=DEFAULT_LIMIT_MB)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    repo = _repo_root()
    report = audit(args.roots, limit_mb=args.limit_mb, repo=repo)
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(json.dumps({
        "checked_files": report["checked_files"],
        "limit_mb": report["limit_mb"],
        "over_limit_count": report["over_limit_count"],
        "largest": report["largest"][:10],
        "out": str(args.out) if args.out else None,
    }, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
