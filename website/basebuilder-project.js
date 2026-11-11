export const PROJECT_SCHEMA = "RSDWBaseBuilder.Project.v2";
export const LEGACY_PROJECT_SCHEMA = "RSDWBaseBuilder.Project.v1";
const axes = ["x", "y", "z", "pitch", "yaw", "roll", "scale_x", "scale_y", "scale_z"];
const requireValue = (condition, message) => { if (!condition) throw Error(message); };
const vector = value => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);
const validCamera = c => c && vector(c.position_cm) && vector(c.target_cm) &&
  ["perspective", "orthographic"].includes(c.projection) && Number.isFinite(c.size) && c.size > 0;

export function projectNavigation(workspace) {
  return structuredClone(workspace.navigation || {mode:"build",streaming_enabled:workspace.world_enabled,
    area_filter:"all",focus_cm:workspace.camera.target_cm,last_build_camera:workspace.camera,overview_camera:null});
}

export function captureProject({ id, revision, dataset, workspace, build, delivery }) {
  const document = { schema: workspace.authoring_mode ? PROJECT_SCHEMA : LEGACY_PROJECT_SCHEMA,
    project_id: id, revision, saved_at: new Date().toISOString(), dataset, workspace, build };
  if (delivery) document.delivery = delivery;
  return migrateProject(document);
}

export function migrateProject(input) {
  const document = structuredClone(input);
  if (document?.schema === PROJECT_SCHEMA) return document;
  requireValue(document?.schema === LEGACY_PROJECT_SCHEMA, "Unsupported project format");
  const old = document.workspace;
  requireValue(old && Array.isArray(old.render_origin_cm) && validCamera(old.camera), "Invalid legacy workspace");
  document.workspace = { authoring_mode: "world", render_origin_cm: old.render_origin_cm,
    camera: old.camera, orientation: old.orientation,
    free_build: { plane_z_cm: old.render_origin_cm[2], grid_visible: true, remembered_camera: null },
    world_build: { requested_section_id: old.requested_section_id, world_enabled: old.world_enabled,
      visible_world_layers: old.visible_world_layers, navigation: projectNavigation(old), camera: old.camera } };
  document.delivery = { preferred_mode: "saved_world_location" };
  document.schema = PROJECT_SCHEMA;
  return document;
}

export function migrateFreeAutosave(payload, { catalog, catalogHash, projectId, camera }) {
  requireValue(payload && (!payload.schema || payload.schema === "RSDWBaseBuilder.Autosave.v1"), "Unsupported free autosave");
  const source = payload.snapshot || payload;
  requireValue(Array.isArray(source.placements), "Invalid free autosave");
  const build = structuredClone(source), targets = new Map(catalog.targets.map(t => [t.target_id, t]));
  build.ui_collections ||= []; build.closed_placed_group_ids ||= []; build.selected_ids ||= [];
  build.unassigned_collection_collapsed ??= false;
  build.view_offset = { x: 0, y: 0, z: 0, ...build.view_offset };
  build.build_schema ||= "rsdwtools.buildings.v1"; build.build_name ||= "Recovered Free Build";
  build.anchor_piece_id ||= 0;
  const reserved = new Set();
  for (const p of build.placements) {
    if (targets.get(p.target_id)?.asset_kind !== "building_piece") continue;
    const id = Number(p.metadata?.piece_id);
    if (Number.isSafeInteger(id) && id > 0) {
      requireValue(!reserved.has(id), "Duplicate legacy piece IDs"); reserved.add(id);
    }
  }
  let nextPiece = Math.max(1, Number(build.next_piece_id) || 1);
  for (const p of build.placements) {
    p.metadata ||= {}; p.hidden = Boolean(p.hidden);
    p.ui_collection_id ??= p.uiCollectionId || ""; delete p.uiCollectionId;
    if (targets.get(p.target_id)?.asset_kind === "building_piece") {
      let id = Number(p.metadata.piece_id);
      if (!Number.isSafeInteger(id) || id <= 0) { while (reserved.has(nextPiece)) nextPiece++; id = nextPiece++; reserved.add(id); }
      p.metadata.piece_id = id;
    }
  }
  build.next_piece_id = [...reserved].reduce((n, id) => Math.max(n, id + 1), nextPiece);
  build.next_object_id = build.placements.reduce((n, p) => Math.max(n, Number(p.id?.slice(4)) + 1), Number(build.next_object_id) || 1);
  build.next_ui_collection_id = build.ui_collections.reduce((n, c) => Math.max(n, Number(c.id.match(/(\d+)$/)?.[1] || 0) + 1), Number(build.next_ui_collection_id) || 1);
  const origin = [build.view_offset.x, build.view_offset.y, build.view_offset.z];
  const view = camera || { position_cm: [origin[0] + 600, origin[1] + 800, origin[2] + 700],
    target_cm: [origin[0], origin[1], origin[2] + 40], projection: "perspective", size: 20 };
  return { schema: PROJECT_SCHEMA, project_id: projectId, revision: 0, saved_at: payload.saved_at || new Date().toISOString(),
    dataset: { game_version: catalog.version, catalog_sha256: catalogHash, world_sha256: null },
    workspace: { authoring_mode: "free", render_origin_cm: origin, camera: view, orientation: "world",
      free_build: { plane_z_cm: origin[2], grid_visible: true, remembered_camera: view }, world_build: null },
    delivery: { preferred_mode: "anchor" }, build };
}

export async function catalogIdentity(catalog) {
  const bytes = new TextEncoder().encode(JSON.stringify(catalog));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map(n => n.toString(16).padStart(2, "0")).join("");
}

export function validateProject(document, catalog, { copy = true } = {}) {
  if (document?.schema === LEGACY_PROJECT_SCHEMA) document = migrateProject(document);
  requireValue(document?.schema === PROJECT_SCHEMA, "Unsupported project format");
  requireValue(typeof document.project_id === "string" && document.project_id.length > 0 && document.project_id.length <= 128, "Invalid project ID");
  requireValue(Number.isSafeInteger(document.revision) && document.revision >= 0, "Invalid project revision");
  requireValue(document.dataset?.game_version === catalog.version, "Project and builder catalog versions do not match");
  requireValue(typeof document.dataset.catalog_sha256 === "string" &&
    (document.dataset.world_sha256 === null || typeof document.dataset.world_sha256 === "string"), "Invalid dataset identity");
  const build = document.build, workspace = document.workspace;
  requireValue(build && Array.isArray(build.placements) && build.placements.length <= 100000, "Invalid project placements");
  requireValue(build.build_schema === "rsdwtools.buildings.v1", "Unsupported build schema");
  requireValue(typeof build.build_name === "string", "Invalid build name");
  requireValue(vector(workspace?.render_origin_cm), "Invalid render origin");
  requireValue(vector(workspace?.camera?.position_cm) && vector(workspace?.camera?.target_cm), "Invalid project camera");
  requireValue(["perspective", "orthographic"].includes(workspace.camera.projection), "Invalid camera projection");
  requireValue(Number.isFinite(workspace.camera.size) && workspace.camera.size > 0, "Invalid camera size");
  requireValue(["local", "world"].includes(workspace.orientation), "Invalid orientation");
  requireValue(["free", "world"].includes(workspace.authoring_mode), "Invalid authoring workspace");
  const free = workspace.free_build, world = workspace.world_build;
  requireValue(free && Number.isFinite(free.plane_z_cm) && typeof free.grid_visible === "boolean" &&
    (free.remembered_camera === null || validCamera(free.remembered_camera)), "Invalid free workspace");
  requireValue(world === null || (typeof world.world_enabled === "boolean" &&
    typeof world.requested_section_id === "string" && validCamera(world.camera)), "Invalid world context");
  requireValue(["anchor", "saved_world_location"].includes(document.delivery?.preferred_mode), "Invalid delivery preference");
  if(world) {
    const n=world.navigation;
    requireValue(n && ["overview","build"].includes(n.mode) && typeof n.streaming_enabled==="boolean", "Invalid navigation mode");
    requireValue(typeof n.area_filter==="string" && n.area_filter.length>0 && n.area_filter.length<=200 && vector(n.focus_cm), "Invalid navigation destination");
    requireValue((n.last_build_camera===null || validCamera(n.last_build_camera)) &&
      (n.overview_camera===null || validCamera(n.overview_camera)), "Invalid navigation camera");
  }
  const layers = world?.visible_world_layers || {};
  requireValue(layers && typeof layers === "object" && !Array.isArray(layers) && Object.entries(layers).every(([key, value]) =>
    ["terrain", "trees", "buildings", "roads", "scenery", "helpers", "bounds"].includes(key) && typeof value === "boolean"), "Invalid world layer visibility");
  requireValue(build.view_offset && ["x", "y", "z"].every((axis, i) => build.view_offset[axis] === workspace.render_origin_cm[i]), "Build and world origins disagree");
  const targets = new Map(catalog.targets.map(t => [t.target_id, t]));
  const ids = new Set(), pieces = new Set(), collections = new Set([""]);
  requireValue(Array.isArray(build.ui_collections), "Invalid collections");
  requireValue(typeof build.unassigned_collection_collapsed === "boolean" && Array.isArray(build.closed_placed_group_ids) &&
    build.closed_placed_group_ids.every(id => typeof id === "string"), "Invalid collection display state");
  for (const c of build.ui_collections) {
    requireValue(typeof c.id === "string" && c.id && !collections.has(c.id), "Duplicate/invalid collection ID");
    requireValue(typeof c.name === "string" && c.name.length > 0 && c.name.length <= 200 && Number.isFinite(c.order) && typeof c.collapsed === "boolean", "Invalid collection");
    collections.add(c.id);
  }
  const missing = [];
  let maxObject = 0, maxPiece = 0, maxCollection = 0;
  for (const c of build.ui_collections) maxCollection = Math.max(maxCollection, Number(c.id.match(/(\d+)$/)?.[1] || 0));
  for (const p of build.placements) {
    requireValue(typeof p.id === "string" && /^obj_\d+$/.test(p.id) && !ids.has(p.id), "Duplicate/invalid placement ID");
    ids.add(p.id); maxObject = Math.max(maxObject, Number(p.id.slice(4)));
    requireValue(p.state && axes.every(k => Number.isFinite(p.state[k])), "Invalid transform for " + p.id);
    requireValue(p.metadata && typeof p.metadata === "object" && !Array.isArray(p.metadata), "Invalid metadata for " + p.id);
    requireValue(typeof p.hidden === "boolean" && collections.has(p.ui_collection_id || ""), "Invalid visibility/collection for " + p.id);
    const target = targets.get(p.target_id);
    if (!target) { missing.push(p.target_id); continue; }
    if (target.asset_kind === "building_piece") {
      const pid = p.metadata.piece_id;
      requireValue(Number.isSafeInteger(pid) && pid > 0 && !pieces.has(pid), "Duplicate/invalid piece ID");
      pieces.add(pid); maxPiece = Math.max(maxPiece, pid);
    }
  }
  requireValue(!missing.length, "Project targets unavailable: " + missing.slice(0, 8).join(", "));
  requireValue(Number.isSafeInteger(build.anchor_piece_id) && (build.anchor_piece_id === 0 || pieces.has(build.anchor_piece_id)), "Invalid project anchor");
  for (const [key, maximum] of [["next_object_id", maxObject], ["next_piece_id", maxPiece], ["next_ui_collection_id", maxCollection]]) {
    requireValue(Number.isSafeInteger(build[key]) && build[key] > maximum, "Invalid " + key);
  }
  requireValue(Array.isArray(build.selected_ids) && new Set(build.selected_ids).size === build.selected_ids.length && build.selected_ids.every(id => ids.has(id)), "Invalid saved selection");
  return copy ? structuredClone(document) : document;
}
