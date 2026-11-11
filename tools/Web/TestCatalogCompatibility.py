"""Catalog additions can preserve saves; visual/export/snap changes cannot."""
import copy
import hashlib
import json

from BuildBaseBuilderWebIndex import compatible_catalog_hashes


previous = {"schema": "test", "version": "1", "sources": {"model_repo": "example"},
            "targets": [{"target_id": "piece", "snap_class": "BP_Test", "components": [1], "export": {"class": "original"}}],
            "snaps": {"BP_Test": {"plugs": []}}}
current = copy.deepcopy(previous)
current["targets"].append({"target_id": "added", "snap_class": "new"})
expected = hashlib.sha256(json.dumps(previous, separators=(",", ":")).encode()).hexdigest()
assert compatible_catalog_hashes(previous, current) == [expected]
for mutate in [
    lambda value: value.update(version="2"),
    lambda value: value["targets"].pop(0),
    lambda value: value["targets"][0]["components"].append(2),
    lambda value: value["targets"][0]["export"].update({"class": "changed"}),
    lambda value: value["snaps"]["BP_Test"]["plugs"].append({"pos": [1, 2, 3]}),
]:
    changed = copy.deepcopy(current)
    mutate(changed)
    assert compatible_catalog_hashes(previous, changed) == []
current["compatible_catalog_sha256"] = [expected]
assert expected in compatible_catalog_hashes(current, current)
print("Catalog compatibility: additive acceptance, transitive history, five incompatibility rejections passed")
