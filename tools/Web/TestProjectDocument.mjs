import assert from "node:assert/strict";
import { captureProject, validateProject, migrateProject, migrateFreeAutosave } from "../../website/basebuilder-project.js";

const catalog = { version: "test", targets: [
  { target_id: "piece", asset_kind: "building_piece" },
  { target_id: "item", asset_kind: "item" },
  { target_id: "bp", asset_kind: "bp" },
] };
const project = captureProject({ id: "fixture", revision: 0,
  dataset: { game_version: "test", catalog_sha256: "catalog", world_sha256: "world" },
  workspace: { render_origin_cm: [-100000, 50000, 12000], requested_section_id: "x3_y1", world_enabled: true,
    visible_world_layers: { terrain: true, trees: false }, orientation: "world",
    camera: { position_cm: [1, 2, 3], target_cm: [-4, 5, -6], projection: "perspective", size: 10 } },
  build: { build_schema: "rsdwtools.buildings.v1", build_name: "Fixture", view_offset: { x: -100000, y: 50000, z: 12000 },
    placements: [{ id: "obj_1", target_id: "piece", state: { x: -99999, y: 40000, z: -123,
      pitch: 17, roll: -23, yaw: 123, scale_x: -1, scale_y: 0.7, scale_z: 2 }, metadata: { piece_id: 1 }, hidden: true, ui_collection_id: "collection_1" }],
    ui_collections: [{ id: "collection_1", name: "Walls", order: 0, collapsed: true }],
    unassigned_collection_collapsed: false, closed_placed_group_ids: [], selected_ids: ["obj_1"],
    anchor_piece_id: 1, next_object_id: 2, next_piece_id: 2, next_ui_collection_id: 2 },
});
const validated = validateProject(project, catalog);
assert.deepEqual(validated, project);assert.notEqual(validated, project);
validated.build.placements[0].state.x = 0;
assert.notEqual(validated.build.placements[0].state.x, project.build.placements[0].state.x);
const invalid = [
  p => { p.schema = "unknown"; }, p => { p.revision = -1; }, p => { p.dataset.game_version = "other"; },
  p => { p.dataset.catalog_sha256 = null; }, p => { p.workspace.render_origin_cm[1] = Infinity; },
  p => { p.workspace.camera.projection = "invalid"; }, p => { p.workspace.camera.size = 0; },
  p => { p.workspace.camera.target_cm = [1, 2]; }, p => { p.workspace.world_build.visible_world_layers.terrain = "false"; },
  p => { p.workspace.world_build.visible_world_layers.unknown = true; }, p => { p.workspace.orientation = "invalid"; },
  p => { p.build.placements[0].state.z = NaN; }, p => { p.build.placements[0].target_id = "missing"; },
  p => { p.build.placements[0].hidden = "false"; }, p => { p.build.placements[0].metadata.piece_id = 0; },
  p => { p.build.placements[0].ui_collection_id = "missing"; }, p => { p.build.anchor_piece_id = 2; },
  p => { p.build.next_object_id = 1; }, p => { p.build.next_piece_id = 1; },
  p => { p.build.view_offset.z = 0; }, p => { p.build.selected_ids = ["missing"]; },
  p => { p.build.selected_ids = ["obj_1", "obj_1"]; }, p => { p.build.ui_collections[0].collapsed = "false"; },
];
for (const mutate of invalid) {
  const value = structuredClone(project);mutate(value);
  const before = structuredClone(value);assert.throws(() => validateProject(value, catalog));assert.deepEqual(value, before);
}
const empty = structuredClone(project);empty.build.placements = [];empty.build.selected_ids = [];empty.build.anchor_piece_id = 0;
assert.deepEqual(validateProject(empty, catalog), empty);
console.log(`Project documents: valid/empty/hidden-anchor/negative-scale round trips and ${invalid.length} nondestructive rejection cases passed`);
const legacy = structuredClone(project);
legacy.schema = "RSDWBaseBuilder.Project.v1";
legacy.workspace = { ...legacy.workspace.world_build, render_origin_cm: legacy.workspace.render_origin_cm,
  orientation: legacy.workspace.orientation };
delete legacy.delivery;
const legacyBefore = structuredClone(legacy), migrated = validateProject(legacy, catalog);
assert.equal(migrated.schema, "RSDWBaseBuilder.Project.v2");
assert.deepEqual(legacy, legacyBefore); assert.deepEqual(migrated.build, project.build);
assert.deepEqual(migrateProject(migrated), migrated);
const autosave = {schema:"RSDWBaseBuilder.Autosave.v1",snapshot:structuredClone(project.build)};
const sourceBefore = structuredClone(autosave);
const free = validateProject(migrateFreeAutosave(autosave,{catalog,catalogHash:"catalog",projectId:"free"}),catalog);
assert.deepEqual(autosave,sourceBefore);assert.deepEqual(free.build,project.build);
assert.equal(free.workspace.free_build.plane_z_cm,12000);assert.equal(free.workspace.authoring_mode,"free");
assert.equal(free.workspace.world_build,null);
for (const mutate of [p=>p.workspace.authoring_mode="bad",p=>p.workspace.free_build.plane_z_cm=NaN,
  p=>p.delivery.preferred_mode="bad",p=>p.workspace.free_build.remembered_camera.size=0]) {
  const invalidFree=structuredClone(free);mutate(invalidFree);assert.throws(()=>validateProject(invalidFree,catalog));
}
console.log("V1 world and free autosave migrations preserve source, build, IDs, counters, hidden anchor and signed scales; V2 workspace/delivery validation passed");
