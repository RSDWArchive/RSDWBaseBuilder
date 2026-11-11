// Import bookkeeping is independent of render objects and never changes the source JSON.
export function validateBuildImport(data) {
  if (!data || data.schema !== "rsdwtools.buildings.v1") throw Error("Unsupported build schema");
  let count = 0;
  for (const kind of ["pieces", "items", "actors"]) {
    const rows = data[kind] ?? [];
    if (!Array.isArray(rows)) throw Error(`Invalid ${kind} array`);
    count += rows.length;
    for (const row of rows) {
      if (!row || typeof row !== "object") throw Error(`Invalid ${kind} entry`);
      for (const key of ["x", "y", "z", "pitch", "yaw", "roll", "scale_x", "scale_y", "scale_z"]) {
        if (row[key] !== undefined && (typeof row[key] !== "number" || !Number.isFinite(row[key]))) {
          throw Error(`Invalid ${kind} ${key}`);
        }
      }
    }
  }
  if (!count) throw Error("This build contains no objects");
}

export function relocateBuildState(state, pivot, destination) {
  const angle = destination.yaw * Math.PI / 180;
  const c = Math.cos(angle), s = Math.sin(angle);
  const x = state.x - pivot.x, y = state.y - pivot.y;
  // A single world-yaw transform preserves tilt, signed scales, and internal spacing.
  return { ...state, x: destination.x + c * x - s * y,
    y: destination.y + s * x + c * y, z: destination.z + state.z - pivot.z,
    yaw: state.yaw + destination.yaw };
}

export function buildImportSnapshot(before, entries, { append, name, anchorEntry = null }) {
  const snapshot = structuredClone(before);
  if (!append) {
    snapshot.placements = []; snapshot.ui_collections = []; snapshot.closed_placed_group_ids = [];
    snapshot.unassigned_collection_collapsed = false; snapshot.anchor_piece_id = 0;
    snapshot.next_piece_id = 1; snapshot.next_ui_collection_id = 1;
  }
  const collectionId = `collection_${snapshot.next_ui_collection_id++}`;
  snapshot.ui_collections.push({ id: collectionId, name: String(name || "Imported Build").trim().slice(0, 200),
    order: snapshot.ui_collections.length, collapsed: false });
  const used = new Set(snapshot.placements.map(p => p.metadata.piece_id).filter(id => id > 0));
  // Reserve valid source IDs first so repairing a zero ID cannot steal a later valid ID.
  if (!append) for (const entry of entries) {
    if (entry.target.asset_kind !== "building_piece") continue;
    const id = entry.metadata.piece_id;
    if (!Number.isSafeInteger(id) || id <= 0) continue;
    if (used.has(id)) throw Error("Duplicate imported piece IDs; current project retained");
    used.add(id);
  }
  let importedAnchorId = 0;
  for (const entry of entries) {
    const metadata = { ...entry.metadata };
    if (entry.target.asset_kind === "building_piece") {
      if (append || !Number.isSafeInteger(metadata.piece_id) || metadata.piece_id <= 0) {
        while (used.has(snapshot.next_piece_id)) snapshot.next_piece_id++;
        metadata.piece_id = snapshot.next_piece_id++;
        used.add(metadata.piece_id);
      }
      snapshot.next_piece_id = Math.max(snapshot.next_piece_id, metadata.piece_id + 1);
      if (entry === anchorEntry) importedAnchorId = metadata.piece_id;
    }
    snapshot.placements.push({ id: `obj_${snapshot.next_object_id++}`, target_id: entry.target.target_id,
      state: { ...entry.transform }, metadata, hidden: false, ui_collection_id: collectionId });
  }
  if (!append || !snapshot.anchor_piece_id) snapshot.anchor_piece_id = importedAnchorId;
  if (!append || !before.placements.length) snapshot.build_name = String(name || "World Base");
  snapshot.selected_ids = [];
  return snapshot;
}
