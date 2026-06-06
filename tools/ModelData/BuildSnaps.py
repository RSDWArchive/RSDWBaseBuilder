"""
Extract base-building snap-point ("plug") data from CUE4Parse json dumps.

Each BaseBuilding piece BP carries a `BuildingSnapComponent` whose `Plugs[]`
list defines its connection points:

    plug = {
      PlugProfile: {
        PieceTag, PlugTag,
        PieceIgnoringTypes[], PlugIgnoringTypes[]
      },
      PlugTransform: { Rotation(quat xyzw), Translation(vec3 cm), Scale3D }
    }

Two plugs A and B can connect when A.PlugTag is not in B.PlugIgnoringTypes
(and vice versa) and A.PieceTag is not in B.PieceIgnoringTypes (and vice
versa).

Plugs may be defined on a parent BP and inherited; we walk Super references
when a child has no inline Plugs[].

Output: tools/ModelData/Snaps.json
{
  "count": N,
  "pieces": {
    "BP_T3_Wall_Small_C": {
      "piece_tag": "BaseBuilding.PieceType.Base",
      "plugs": [
        {
          "piece_tag": "...",
          "plug_tag": "...",
          "piece_ign": [...],
          "plug_ign":  [...],
          "pos":  [x_cm, y_cm, z_cm],
          "rot":  [qx, qy, qz, qw]
        },
        ...
      ]
    },
    ...
  }
}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT = REPO / "tools" / "ModelData" / "Snaps.json"


def _latest_archive_json_root() -> Path:
    root = Path(r"E:/Github/RSDWArchive")
    versions = []
    if root.is_dir():
        for child in root.iterdir():
            parts = child.name.split(".")
            if child.is_dir() and parts and all(part.isdigit() for part in parts):
                versions.append(child)
    if versions:
        versions.sort(key=lambda path: tuple(int(part) for part in path.name.split(".")))
        return versions[-1] / "json"
    return Path(r"E:/Github/RSDWArchive/0.11.1.4/json")


def _load(path: Path):
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return None


def _bp_class_name(entries) -> str | None:
    for e in entries:
        if e.get("Type") == "BlueprintGeneratedClass":
            return e.get("Name")
    return None


def _super_path(entries, json_root: Path) -> Path | None:
    for e in entries:
        if e.get("Type") == "BlueprintGeneratedClass":
            sup = e.get("Super") or {}
            op = sup.get("ObjectPath", "")
            # e.g. "RSDragonwilds/Content/.../BP_T1_BasePiece.0"
            if not op:
                return None
            rel = op.rsplit(".", 1)[0] + ".json"
            return json_root / rel
    return None


def _own_snap_plugs(entries):
    """Return (plugs, template_path) for this BP's BuildingSnapComponent.

    plugs is a list (possibly empty). template_path is the ObjectPath of
    the parent BuildingSnapComponent template if Plugs is empty here, so
    the caller can keep walking up the inheritance chain.
    """
    for e in entries:
        if e.get("Type") != "BuildingSnapComponent":
            continue
        plugs = (e.get("Properties") or {}).get("Plugs") or []
        if plugs:
            return plugs, None
        tmpl = (e.get("Template") or {}).get("ObjectPath", "")
        return [], tmpl
    return [], None


def _piece_tag(entries) -> str:
    """The piece's own PieceTag from its BuildingSnapComponent.PieceProfile,
    if present. Falls back to first plug's PieceTag."""
    for e in entries:
        if e.get("Type") != "BuildingSnapComponent":
            continue
        props = e.get("Properties") or {}
        pp = props.get("PieceProfile") or {}
        tag = (pp.get("PieceTag") or {}).get("TagName")
        if tag:
            return tag
    return ""


def _norm_plug(p):
    prof = p.get("PlugProfile") or {}
    pt = (prof.get("PieceTag") or {}).get("TagName", "")
    plt = (prof.get("PlugTag") or {}).get("TagName", "")
    pi = [t for t in (prof.get("PieceIgnoringTypes") or [])]
    pli = [t for t in (prof.get("PlugIgnoringTypes") or [])]
    xform = p.get("PlugTransform") or {}
    rot = xform.get("Rotation") or {}
    tr = xform.get("Translation") or {}
    return {
        "piece_tag": pt,
        "plug_tag": plt,
        "piece_ign": pi,
        "plug_ign": pli,
        "pos": [
            float(tr.get("X", 0.0)),
            float(tr.get("Y", 0.0)),
            float(tr.get("Z", 0.0)),
        ],
        "rot": [
            float(rot.get("X", 0.0)),
            float(rot.get("Y", 0.0)),
            float(rot.get("Z", 0.0)),
            float(rot.get("W", 1.0)),
        ],
    }


def collect(json_root: Path) -> dict:
    """Walk every BP_*.json under BaseBuilding folders, extract plugs.

    Inheritance: if a BP has no inline Plugs[], walk up Super chain.
    """
    all_bps: dict[Path, list] = {}
    # Index every BP_*.json so we can resolve Super paths.
    for dp, _dn, fns in os.walk(json_root):
        for fn in fns:
            if fn.startswith("BP_") and fn.endswith(".json"):
                full = Path(dp) / fn
                all_bps[full.resolve()] = []  # lazy-loaded entries

    def get_entries(p: Path):
        p = p.resolve()
        if p not in all_bps:
            return None
        cached = all_bps[p]
        if cached:
            return cached
        d = _load(p)
        if d is None:
            return None
        all_bps[p] = d
        return d

    def resolve_plugs(p: Path, depth: int = 0) -> list:
        if depth > 8:
            return []
        d = get_entries(p)
        if d is None:
            return []
        own, tmpl = _own_snap_plugs(d)
        if own:
            return own
        # Try component-template chain first (the BuildingSnapComponent
        # itself points at its parent template).
        if tmpl:
            rel = tmpl.rsplit(".", 1)[0] + ".json"
            return resolve_plugs(json_root / rel, depth + 1)
        # Otherwise climb the BP class Super chain.
        sup = _super_path(d, json_root)
        if sup is None:
            return []
        return resolve_plugs(sup, depth + 1)

    out: dict = {}
    bb_filter = ("BaseBuilding_New", "BaseBuilding")
    total = 0
    no_plugs = 0
    for p in sorted(all_bps.keys()):
        rel = p.relative_to(json_root).as_posix()
        if not any(seg in rel for seg in bb_filter):
            continue
        d = get_entries(p)
        if d is None:
            continue
        cls = _bp_class_name(d)
        if not cls:
            continue
        plugs_raw, tmpl = _own_snap_plugs(d)
        if not plugs_raw:
            if tmpl:
                rel = tmpl.rsplit(".", 1)[0] + ".json"
                plugs_raw = resolve_plugs(json_root / rel)
            if not plugs_raw:
                sup = _super_path(d, json_root)
                if sup is not None:
                    plugs_raw = resolve_plugs(sup)
        total += 1
        if not plugs_raw:
            no_plugs += 1
            continue
        out[cls] = {
            "piece_tag": _piece_tag(d),
            "plugs": [_norm_plug(p) for p in plugs_raw],
        }
    return {"count": len(out), "scanned": total, "no_plugs": no_plugs, "pieces": out}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-root", type=Path, default=_latest_archive_json_root())
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.json_root.is_dir():
        print(f"json root not found: {args.json_root}", file=sys.stderr)
        return 2

    print(f"Scanning {args.json_root} for BaseBuilding BP_*.json...")
    res = collect(args.json_root)
    print(f"  scanned={res['scanned']}, with_plugs={res['count']}, no_plugs={res['no_plugs']}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(res, indent=2, sort_keys=True), encoding="utf-8")
    print(f"  wrote {args.out}")

    # Quick stats
    by_count = {}
    for cls, info in res["pieces"].items():
        n = len(info["plugs"])
        by_count[n] = by_count.get(n, 0) + 1
    print("  pieces by plug count:", dict(sorted(by_count.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
