"""
Categorize a SM_*.uemodel entry into a hierarchical asset-browser catalog
path, and produce stable UUIDs for those paths. Pure-Python (no bpy) so it can
be reused by both the catalog-file generator and the per-piece worker.

Catalog hierarchy (path-based on entry["path"]):

  /BuildingKit/Tier1/                  -> Building/Tier 1
  /BuildingKit/Tier2/                  -> Building/Tier 2
  /BuildingKit/Tier3/                  -> Building/Tier 3
  /Decorations/Banners/<sub>/          -> Decorations/Banners/<Pretty Sub>
  /Decorations/<sub>/                  -> Decorations/<Pretty Sub>
  /Crafting_Stations/                  -> Crafting Stations
  /Farming/                            -> Farming
  /Furniture/Cosiness/<sub>/           -> Furniture/<Pretty Sub>
  /Furniture/<sub>/                    -> Furniture/<Pretty Sub>

UUIDs are uuid5(NAMESPACE, catalog_path) so they stay stable across rebuilds.
"""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath


CATALOG_NAMESPACE = uuid.UUID("a3d5e6c0-1b2f-4d3a-8c5e-9f0a1b2c3d4e")


_BANNER_PRETTY = {
    "Single_Banner": "Single",
    "Double_Banner": "Double",
    "Framed_Banner": "Framed",
    "Wall_Horizontal_Banner": "Wall Horizontal",
    "Wall_Vertical_Banner": "Wall Vertical",
}


def _pretty(name: str) -> str:
    return name.replace("_", " ").strip()


def _is_file(name: str) -> bool:
    return name.lower().endswith((".uemodel", ".uasset"))


def categorize(entry_path: str) -> str:
    """Return the catalog path (slash-separated) for a SM_ entry path.

    The input is the repo-relative posix path stored in SM_Data.json's
    `path` field, e.g.
      RSDragonwilds/Content/Art/Env/Base_Building/BuildingKit/Tier1/SM_BB_T1_Door.uemodel
    """
    parts = PurePosixPath(entry_path).parts
    # Find the segment after "Base_Building" — that's the top-level bucket.
    try:
        bb_idx = parts.index("Base_Building")
    except ValueError:
        return "Misc"
    rest = parts[bb_idx + 1:]
    if not rest:
        return "Misc"

    top = rest[0]
    # rest[1] is either a sub-folder name or the .uemodel file itself.
    sub = rest[1] if len(rest) >= 2 and not _is_file(rest[1]) else None

    if top == "BuildingKit" and sub:
        if sub.startswith("Tier"):
            n = sub[len("Tier"):]
            return f"Building/Tier {n}"
        return f"Building/{_pretty(sub)}"

    if top == "Decorations":
        if sub == "Banners" and len(rest) >= 3 and not _is_file(rest[2]):
            banner_kind = rest[2]
            return f"Decorations/Banners/{_BANNER_PRETTY.get(banner_kind, _pretty(banner_kind))}"
        if sub:
            return f"Decorations/{_pretty(sub)}"
        return "Decorations"

    if top == "Crafting_Stations":
        return "Crafting Stations"

    if top == "Farming":
        return "Farming"

    if top == "Furniture":
        # Most pieces sit two levels deep: /Furniture/Cosiness/<Sub>/SM_X.
        # We collapse "Cosiness" and surface the sub-bucket as the leaf.
        if sub == "Cosiness" and len(rest) >= 3 and not _is_file(rest[2]):
            return f"Furniture/{_pretty(rest[2])}"
        if sub:
            return f"Furniture/{_pretty(sub)}"
        return "Furniture"

    return _pretty(top)


def catalog_uuid(catalog_path: str) -> uuid.UUID:
    """Deterministic UUIDv5 for a catalog path."""
    return uuid.uuid5(CATALOG_NAMESPACE, catalog_path)


def expand_catalog_paths(catalog_path: str) -> list[str]:
    """Return [self, parent, grandparent, ...] catalog paths so we can register
    every level in the .cats.txt file. Blender requires each level to have its
    own UUID/entry."""
    parts = catalog_path.split("/")
    out: list[str] = []
    for i in range(1, len(parts) + 1):
        out.append("/".join(parts[:i]))
    return out


__all__ = [
    "CATALOG_NAMESPACE",
    "categorize",
    "catalog_uuid",
    "expand_catalog_paths",
]
