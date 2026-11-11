"""Same-folder data-asset rename regression checks; never guess across folders."""
import json
import tempfile
from pathlib import Path

from BuildCatalogReconciliation import _archive_index_by_piece_data_name
from BuildAssetLibraryTargets import _resolve_archive_asset_file


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    stem = "DA_BaseBuilding_Decoration_Test"
    renamed = root / f"BUILDPIECE_{stem}.json"
    def write(path, bp):
        path.write_text(json.dumps([{"Type": "BuildingPieceData", "Properties": {
            "BuildableActor": {"AssetPathName": f"/Game/BP.{bp}"}}}]), encoding="utf-8")
    write(renamed, "BP_Renamed_C")
    index = _archive_index_by_piece_data_name([(root, "BuildingPieceData /Game")])
    alias = f"BuildingPieceData /Game/{stem}.{stem}"
    assert index[alias]["bp_class"] == "BP_Renamed_C"
    assert index[alias]["asset_stem"] == stem
    assert _resolve_archive_asset_file(stem, root, (".json",)) == renamed.resolve()
    old = root / f"{stem}.json"
    write(old, "BP_Exact_C")
    index = _archive_index_by_piece_data_name([(root, "BuildingPieceData /Game")])
    assert index[alias]["bp_class"] == "BP_Exact_C"
    assert _resolve_archive_asset_file(stem, root, (".json",)) == old.resolve()
    assert _resolve_archive_asset_file("other/" + stem, root, (".json",)) is None
print("Catalog rename: alias, exact-match precedence, directory isolation passed")
