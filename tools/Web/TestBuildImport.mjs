import assert from "node:assert/strict";
import {buildImportSnapshot, relocateBuildState, validateBuildImport} from "../../website/basebuilder-build-import.js";

const before = {placements: [], ui_collections: [], selected_ids: [], closed_placed_group_ids: [],
  anchor_piece_id: 0, next_piece_id: 1, next_object_id: 1, next_ui_collection_id: 1, build_name: "Before"};
const state = {x: 10, y: 20, z: 30, pitch: 17, yaw: 123, roll: -90, scale_x: -1, scale_y: 2, scale_z: .7};
const entries = [0, 1, 5, 0].map(id => ({target: {target_id: "piece", asset_kind: "building_piece"},
  transform: {...state}, metadata: {piece_id: id, stability: 0}}));
const original = structuredClone({before, entries});
const first = buildImportSnapshot(before, entries, {append: false, name: "First", anchorEntry: entries[1]});
assert.equal(first.placements.length, 4);assert.equal(first.anchor_piece_id, 1);
assert.deepEqual(first.placements.map(p => p.metadata.piece_id), [2, 1, 5, 6]);
assert.ok(first.placements.every(p => p.ui_collection_id === first.ui_collections[0].id));
assert.deepEqual({before, entries}, original);
const second = buildImportSnapshot(first, entries, {append: true, name: "Second", anchorEntry: entries[2]});
assert.equal(second.ui_collections.length, 2);assert.equal(second.anchor_piece_id, 1);
assert.deepEqual(second.placements.slice(0, 4), first.placements);
assert.equal(new Set(second.placements.map(p => p.metadata.piece_id)).size, 8);
assert.equal(new Set(second.placements.map(p => p.id)).size, 8);
assert.throws(() => buildImportSnapshot(before, [entries[1], entries[1]], {append: false, name: "Bad"}));
const rotated = relocateBuildState(state, {x: 0, y: 0, z: 10}, {x: 100, y: 200, z: 300, yaw: 90});
assert.equal(rotated.x, 80);assert.equal(rotated.y, 210);assert.equal(rotated.z, 320);assert.equal(rotated.yaw, 213);
for (const key of ["pitch", "roll", "scale_x", "scale_y", "scale_z"]) assert.equal(rotated[key], state[key]);
assert.deepEqual(relocateBuildState(state, {x: 0,y: 0,z: 0}, {x: 0,y: 0,z: 0,yaw: 0}), state);
validateBuildImport({schema: "rsdwtools.buildings.v1", pieces: [{...state}]});
for (const bad of [null, {}, {schema: "rsdwtools.buildings.v1"}, {schema: "rsdwtools.buildings.v1", pieces: [{}], items: {}},
  {schema: "rsdwtools.buildings.v1", pieces: [{x: "100"}]}, {schema: "rsdwtools.buildings.v1", pieces: [{pitch: Infinity}]}]) {
  assert.throws(() => validateBuildImport(bad));
}

const largeCount = 100_001;
validateBuildImport({schema: "rsdwtools.buildings.v1", pieces: Array(largeCount).fill(state)});
const largeEntries = Array(largeCount).fill(entries[0]);
const largeBuild = buildImportSnapshot(before, largeEntries, {append: false, name: "Large build"});
assert.equal(largeBuild.placements.length, largeCount);
assert.equal(largeBuild.placements.at(-1).metadata.piece_id, largeCount);
const largeAppend = buildImportSnapshot(first, largeEntries.slice(first.placements.length), {append: true, name: "Large append"});
assert.equal(largeAppend.placements.length, largeCount);
assert.equal(largeAppend.anchor_piece_id, first.anchor_piece_id);
assert.equal(new Set(largeAppend.placements.map(p => p.metadata.piece_id)).size, largeCount);
console.log("Build import: atomic snapshot, reserved IDs, collections, anchor, rigid yaw, validation, and import/append above 100,000 passed");
