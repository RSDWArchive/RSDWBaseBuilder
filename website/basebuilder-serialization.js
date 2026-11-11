import { normalizeTransform, exportTransform, roundValue } from "./basebuilder-transforms.js";
const ITEM_ACTOR_CLASS = "BlueprintGeneratedClass /Game/Gameplay/WorldItems/BP_RuntimeSpawnedWorldItem.BP_RuntimeSpawnedWorldItem_C";

export function editorTransformFromJson(row) {
  const transform = normalizeTransform(row);
  return {
    ...transform,
    pitch: -transform.pitch,
    roll: -transform.roll,
  };
}

export function jsonTransformFromEditorState(state) {
  const transform = exportTransform(state);
  return {
    ...transform,
    pitch: roundValue(-transform.pitch),
    roll: roundValue(-transform.roll),
  };
}

export function serializeBuildingJson({placements, buildSchema, buildName, anchorPieceId, allocatePieceId}, generatedUnix = Math.floor(Date.now() / 1000)) {
  const pieces = [];
  const items = [];
  const actors = [];
  const usedPieceIds = new Set();
  for (const placement of placements.values()) {
    if (placement.hidden) continue;
    if (placement.target.asset_kind !== "building_piece") continue;
    let pid = Number(placement.metadata.piece_id || 0);
    if (pid <= 0 || usedPieceIds.has(pid)) {
      pid = allocatePieceId();
      placement.metadata.piece_id = pid;
    }
    usedPieceIds.add(pid);
  }

  for (const placement of placements.values()) {
    if (placement.hidden) continue;
    const target = placement.target;
    const transform = jsonTransformFromEditorState(placement.state);
    if (target.asset_kind === "building_piece") {
      pieces.push({
        piece_id: Number(placement.metadata.piece_id || allocatePieceId()),
        piece_data_index: Number(target.export.piece_data_index || 0),
        piece_data_name: target.export.piece_data_name || "",
        class_name: target.export.class_name || "",
        ...transform,
        stability: Number(placement.metadata.stability || target.export.default_stability || 3000),
        is_ghosted: Boolean(placement.metadata.is_ghosted),
        ...(placement.metadata.spud_guid ? { spud_guid: placement.metadata.spud_guid } : {}),
      });
    } else if (target.asset_kind === "item") {
      items.push({
        actor_name: placement.metadata.actor_name || target.asset_stem,
        actor_class: placement.metadata.actor_class || target.export.actor_class || ITEM_ACTOR_CLASS,
        item_asset_name: target.export.item_asset_name || target.asset_stem,
        item_asset_path: target.export.item_asset_path || "",
        item_source: placement.metadata.item_source || target.export.item_source || "ItemData",
        count: Number(placement.metadata.item_count || target.export.item_count || 1),
        ...transform,
      });
    } else if (target.asset_kind === "bp") {
      actors.push({
        actor_name: placement.metadata.actor_name || target.asset_stem,
        actor_class: target.export.actor_class || "",
        class_path: target.export.class_path || target.export.runtime_path || "",
        ...transform,
      });
    }
  }

  const out = {
    schema: buildSchema,
    name: buildName,
    generated_unix: generatedUnix,
    count: pieces.length,
    skipped: 0,
    item_count: items.length,
    item_skipped: 0,
    hidden: 0,
    pieces,
    items,
    actors,
  };
  if (anchorPieceId && pieces.some((piece) => Number(piece.piece_id) === Number(anchorPieceId))) {
    const anchorPiece = pieces.find((piece) => Number(piece.piece_id) === Number(anchorPieceId));
    out.anchor_piece_id = Number(anchorPieceId);
    out.anchor_piece_data_index = Number(anchorPiece.piece_data_index || 0);
  }
  return out;
}
