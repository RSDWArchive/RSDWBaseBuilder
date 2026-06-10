import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";
import { ViewHelper } from "three/addons/helpers/ViewHelper.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import * as SkeletonUtils from "three/addons/utils/SkeletonUtils.js";

import {
  UNIT_SCALE,
  componentTransformToThreeMatrix4,
  distanceSquared,
  exportTransform,
  matrixTranslation,
  normalizeTransform,
  plugWorldMatrix,
  roundValue,
  threeVectorToUe,
  updateObjectFromState,
  updateStateFromObject,
} from "./basebuilder-transforms.js";

(function () {
  "use strict";

  const CONFIG_URL = "./data.config.json";
  const INDEX_URL = "./basebuilder-index.json";
  const RESULT_LIMIT = 180;
  const SNAP_MAX_DISTANCE_CM = 200;
  const DRAG_START_DISTANCE_PX = 8;
  const DRAG_ROTATE_STEPS_DEGREES = [15, 1, 3, 5, 10];
  const PREVIEW_Z_STEP = 10;
  const NUDGE_ARROW_MARGIN_PX = 42;
  const GIZMO_TRANSLATE_SNAP_CM = 10;
  const GIZMO_ROTATE_SNAP_DEGREES = 10;
  const GIZMO_SCALE_SNAP = 0.1;
  const UNDO_LIMIT = 50;
  const GLTF_PRELOAD_CONCURRENCY = 8;
  const IMPORT_RENDER_BATCH_SIZE = 100;
  const PLACED_LIST_LIMIT = 500;
  const SPATIAL_CELL_SIZE_CM = 1000;
  const SPATIAL_PICK_RADIUS_CM = 2500;
  const SPATIAL_SURFACE_RADIUS_CM = 3500;
  const SPATIAL_SNAP_RADIUS_CM = SNAP_MAX_DISTANCE_CM + 250;
  const MOVE_PREVIEW_START_MIN_PX = 12;
  const MOVE_PREVIEW_START_MAX_PX = 30;
  const MARQUEE_FROM_HIT_NEAR_PX = 36;
  const MARQUEE_FROM_HIT_FAR_PX = 16;
  const MARQUEE_FROM_HIT_MIN_AXIS_PX = 8;
  const MARQUEE_SPATIAL_PADDING_RATIO = 0.08;
  const MARQUEE_SPATIAL_MAX_PADDING_CM = 12000;
  const FAVORITES_STORAGE_KEY = "RSDWBaseBuilder.favoriteTargetIds.v1";
  const ASSET_VIEW_STORAGE_KEY = "RSDWBaseBuilder.assetViewMode.v1";
  const SCALE_OVERRIDE_STORAGE_KEY = "RSDWBaseBuilder.scaleRestrictionOverride.v1";
  const AUTOSAVE_STORAGE_KEY = "RSDWBaseBuilder.autosave.v1";
  const AUTOSAVE_DEBOUNCE_MS = 350;
  const CAMERA_FOV_DEGREES = 45;
  const CAMERA_DEFAULT_DISTANCE = 12;
  const ORTHOGRAPHIC_PADDING = 1.25;
  const GROUND_GRID_DEFAULT_SIZE = 80;
  const GROUND_GRID_MIN_SIZE = 80;
  const GROUND_GRID_PADDING_RATIO = 0.35;
  const GROUND_GRID_MIN_PADDING = 20;
  const GROUND_GRID_TARGET_DIVISIONS = 120;
  const GROUND_GRID_MIN_DIVISIONS = 40;
  const GROUND_GRID_MAX_DIVISIONS = 240;
  const GROUND_GRID_Y = -0.001;
  const INSTANCE_INITIAL_CAPACITY = 64;
  const SELECTION_PROMOTION_LIMIT = 250;
  const SHOW_ICON_URL = "./shared/assets/ShowHide/Show.png";
  const HIDE_ICON_URL = "./shared/assets/ShowHide/Hide.png";
  const VIEW_HELPER_SIZE = 128;
  const VIEW_HELPER_TOP = 86;
  const VIEW_HELPER_RIGHT = 14;
  const VIEW_HELPER_DRAG_THRESHOLD_PX = 4;
  const WORLD_UP = new THREE.Vector3(0, 1, 0);
  const ITEM_ACTOR_CLASS = "BlueprintGeneratedClass /Game/Gameplay/WorldItems/BP_RuntimeSpawnedWorldItem.BP_RuntimeSpawnedWorldItem_C";
  const VIEW_SNAP_SHORTCUTS = {
    Numpad1: {
      front: { label: "Front View", direction: new THREE.Vector3(0, 0, -1), up: WORLD_UP },
      back: { label: "Back View", direction: new THREE.Vector3(0, 0, 1), up: WORLD_UP },
    },
    Numpad3: {
      front: { label: "Right View", direction: new THREE.Vector3(1, 0, 0), up: WORLD_UP },
      back: { label: "Left View", direction: new THREE.Vector3(-1, 0, 0), up: WORLD_UP },
    },
    Numpad7: {
      front: { label: "Top View", direction: new THREE.Vector3(0, 1, 0), up: WORLD_UP },
      back: { label: "Bottom View", direction: new THREE.Vector3(0, -1, 0), up: WORLD_UP },
    },
  };
  const SMART_NUDGE_DIRECTIONS = [
    { id: "left", icon: "4", label: "Left", codes: ["Numpad4", "ArrowLeft"], right: -1, forward: 0, vertical: 0 },
    { id: "right", icon: "6", label: "Right", codes: ["Numpad6", "ArrowRight"], right: 1, forward: 0, vertical: 0 },
    { id: "backward", icon: "8", label: "Backward", codes: ["Numpad8"], right: 0, forward: -1, vertical: 0 },
    { id: "forward", icon: "2", label: "Forward", codes: ["Numpad2"], right: 0, forward: 1, vertical: 0 },
    { id: "up", icon: "5", label: "Up", codes: ["Numpad5", "ArrowUp"], right: 0, forward: 0, vertical: 1 },
    { id: "down", icon: "0", label: "Down", codes: ["Numpad0", "ArrowDown"], right: 0, forward: 0, vertical: -1 },
    { id: "left-backward", icon: "7", label: "Left backward", codes: ["Numpad7"], right: -1, forward: -1, vertical: 0 },
    { id: "right-backward", icon: "9", label: "Right backward", codes: ["Numpad9"], right: 1, forward: -1, vertical: 0 },
    { id: "left-forward", icon: "1", label: "Left forward", codes: ["Numpad1"], right: -1, forward: 1, vertical: 0 },
    { id: "right-forward", icon: "3", label: "Right forward", codes: ["Numpad3"], right: 1, forward: 1, vertical: 0 },
  ];
  const SMART_NUDGE_BY_CODE = new Map(
    SMART_NUDGE_DIRECTIONS.flatMap((direction) => direction.codes.map((code) => [code, direction]))
  );
  const SMART_NUDGE_BY_ID = new Map(SMART_NUDGE_DIRECTIONS.map((direction) => [direction.id, direction]));

  const els = {
    assetStatus: document.getElementById("asset-status"),
    assetSearch: document.getElementById("asset-search"),
    assetViewToggle: document.getElementById("asset-view-toggle"),
    assetCategoryPrimary: document.getElementById("asset-category-primary"),
    assetCategoryChildren: document.getElementById("asset-category-children"),
    assetList: document.getElementById("asset-list"),
    assetResultsFooter: document.getElementById("asset-results-footer"),
    loadMoreAssets: document.getElementById("load-more-assets"),
    favoriteStrip: document.getElementById("favorite-strip"),
    kindButtons: Array.from(document.querySelectorAll("[data-kind]")),
    stage: document.getElementById("builder-stage"),
    loading: document.getElementById("stage-loading"),
    orientationToggle: document.getElementById("orientation-toggle"),
    viewportNotice: document.getElementById("viewport-notice"),
    controlsHud: document.getElementById("controls-hud"),
    selectionHotkeys: document.getElementById("selection-hotkeys"),
    previewHotkeys: document.getElementById("preview-hotkeys"),
    previewPlaceLabel: document.getElementById("preview-place-label"),
    gizmoHotkeys: document.getElementById("gizmo-hotkeys"),
    importJson: document.getElementById("import-json"),
    exportJson: document.getElementById("export-json"),
    clearBuild: document.getElementById("clear-build"),
    fileInput: document.getElementById("file-input"),
    setAnchor: document.getElementById("set-anchor"),
    clearAnchor: document.getElementById("clear-anchor"),
    buildCount: document.getElementById("build-count"),
    anchorStatus: document.getElementById("anchor-status"),
    selectionTitle: document.getElementById("selection-title"),
    selectionMeta: document.getElementById("selection-meta"),
    placedList: document.getElementById("placed-list"),
    transformInputs: Array.from(document.querySelectorAll("[data-transform]")),
  };

  let config = {
    modelRepoOwner: "RSDWArchive",
    modelRepoName: "RSDWModel",
    modelRepoBranch: "main",
    assetBaseUrl: "auto",
    archiveRepoOwner: "RSDWArchive",
    archiveRepoName: "RSDWArchive",
    archiveRepoBranch: "main",
    archiveAssetBaseUrl: "auto",
  };
  let index = null;
  let activeKind = "building_piece";
  let activeCategoryPath = "";
  let visibleAssetResultCount = RESULT_LIMIT;
  let assetViewMode = "list";
  let selectedTargetId = "";
  let selectedPlacedIds = new Set();
  let activePlacementId = "";
  let orientationMode = "world";
  let closedPlacedGroupIds = new Set();
  let favoriteTargetIds = new Set();
  let viewOffset = { x: 0, y: 0, z: 0 };
  let buildName = "Browser Base";
  let buildSchema = "rsdwtools.buildings.v1";
  let anchorPieceId = 0;
  let nextObjectId = 1;
  let nextPieceId = 1;
  let renderer = null;
  let scene = null;
  let camera = null;
  let controls = null;
  let transformControls = null;
  let viewHelper = null;
  let viewHelperHitZone = null;
  let viewHelperDrag = null;
  let viewHelperClock = new THREE.Clock();
  let rootGroup = null;
  let groundGrid = null;
  let groundGridSignature = "";
  let groundGridUpdateHandle = 0;
  let loader = null;
  let raycaster = null;
  let pointer = null;
  let cameraProjectionMode = "perspective";
  let orthographicViewSize = CAMERA_DEFAULT_DISTANCE;
  let targetLookup = null;
  let dragCandidate = null;
  let dragSession = null;
  let selectionGesture = null;
  let selectionMarquee = null;
  let orientationNudgeOverlay = null;
  let orientationNudgeMode = null;
  const orientationNudgeArrows = new Map();
  let selectionPivot = null;
  let pendingTransformUndo = null;
  let pendingTransformChanged = false;
  let activeGizmoMode = "";
  let gizmoSnapModifierActive = false;
  let duplicateNudgeModifierActive = false;
  let smartDuplicateNudgeActive = false;
  let scaleRestrictionOverride = false;
  let autosaveReady = false;
  let autosaveTimer = 0;
  let previewPreviousEnableZoom = null;
  let restoringSnapshot = false;
  let bulkMutationActive = false;
  let controlsHudCollapsed = false;
  let viewportNoticeTimer = 0;
  let screenBoundsRevision = 0;
  const dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const gltfCache = new Map();
  const targetVisualTemplateCache = new Map();
  const targetVisualResolvedCache = new Map();
  const targetInstanceTemplateCache = new Map();
  const instanceBatches = new Map();
  const promotedPlacementIds = new Set();
  const placements = new Map();
  const selectionBoxes = new Map();
  const undoStack = [];
  const spatialIndex = {
    cells: new Map(),
    placementCells: new Map(),
  };

  function isLocalHost() {
    return ["localhost", "127.0.0.1", "::1", ""].includes(window.location.hostname);
  }

  function trimSlash(value) {
    return String(value || "").replace(/\/+$/, "");
  }

  function encodePath(path) {
    return String(path || "").split("/").map(encodeURIComponent).join("/");
  }

  function rawModelBase() {
    return `https://raw.githubusercontent.com/${config.modelRepoOwner}/${config.modelRepoName}/${config.modelRepoBranch}`;
  }

  function rawArchiveBase() {
    return `https://raw.githubusercontent.com/${config.archiveRepoOwner}/${config.archiveRepoName}/${config.archiveRepoBranch}`;
  }

  function webAssetBase() {
    if (config.assetBaseUrl && config.assetBaseUrl !== "auto") {
      return trimSlash(config.assetBaseUrl);
    }
    const version = index?.version || "0.11.2.2";
    if (isLocalHost()) {
      const path = window.location.pathname.replace(/\\/g, "/");
      const marker = "/RSDWBaseBuilder/";
      const markerAt = path.indexOf(marker);
      if (markerAt >= 0) {
        const prefix = path.slice(0, markerAt);
        return `${window.location.origin}${prefix}/RSDWModel/${encodePath(version)}/WebAssets`;
      }
    }
    return `${rawModelBase()}/${encodePath(version)}/WebAssets`;
  }

  function assetUrl(relPath) {
    return `${webAssetBase()}/${encodePath(relPath)}`;
  }

  function archiveAssetBase() {
    if (config.archiveAssetBaseUrl && config.archiveAssetBaseUrl !== "auto") {
      return trimSlash(config.archiveAssetBaseUrl);
    }
    const version = index?.version || "0.11.2.2";
    if (isLocalHost()) {
      const path = window.location.pathname.replace(/\\/g, "/");
      const marker = "/RSDWBaseBuilder/";
      const markerAt = path.indexOf(marker);
      if (markerAt >= 0) {
        const prefix = path.slice(0, markerAt);
        return `${window.location.origin}${prefix}/RSDWArchive/${encodePath(version)}`;
      }
    }
    return `${rawArchiveBase()}/${encodePath(version)}`;
  }

  function iconUrl(relPath) {
    return `${archiveAssetBase()}/${encodePath(relPath)}`;
  }

  function siteAssetUrl(relPath) {
    return `./${encodePath(relPath)}`;
  }

  function keyIcon(name) {
    return siteAssetUrl(`shared/assets/Keyboard/T_Keys-Standard-${name}.png`);
  }

  function specialKeyIcon(name) {
    return siteAssetUrl(`shared/assets/Keyboard/T_Keys-Special-${name}.png`);
  }

  function mouseIcon(name) {
    return siteAssetUrl(`shared/assets/Mouse/T_Mouse-Buttons-${name}.png`);
  }

  function hudIcon(src, label) {
    return { src, label };
  }

  function renderControlsHud() {
    if (!els.controlsHud) return;
    syncSelectionHotkeys();
    els.controlsHud.classList.toggle("is-collapsed", controlsHudCollapsed);
    els.controlsHud.setAttribute("aria-expanded", String(!controlsHudCollapsed));
    els.controlsHud.title = controlsHudCollapsed ? "Show camera controls" : "Hide camera controls";
    if (controlsHudCollapsed) {
      els.controlsHud.replaceChildren(createHudCollapsedRow());
      els.controlsHud.hidden = false;
      return;
    }
    const rows = defaultHudRows();
    els.controlsHud.replaceChildren(...rows.map(createHudRow));
    els.controlsHud.hidden = !rows.length;
  }

  function toggleControlsHud() {
    controlsHudCollapsed = !controlsHudCollapsed;
    renderControlsHud();
  }

  function syncSelectionHotkeys() {
    const previewActive = Boolean(dragSession);
    const selectionHidden = !selectedPlacedIds.size || previewActive;
    if (els.selectionHotkeys) els.selectionHotkeys.hidden = selectionHidden;
    if (els.gizmoHotkeys) els.gizmoHotkeys.hidden = selectionHidden;
    if (els.previewHotkeys) els.previewHotkeys.hidden = !previewActive;
    if (els.previewPlaceLabel && previewActive) {
      els.previewPlaceLabel.textContent = dragSession?.moveExisting ? "Release Move" : "Place Preview";
    }
  }

  function defaultHudRows() {
    return [
      { icons: [hudIcon(keyIcon("0"), "0")], label: "Frame View" },
      { icons: [hudIcon(keyIcon("1"), "Numpad 1")], label: "Front view" },
      { icons: [hudIcon(specialKeyIcon("Ctrl"), "Ctrl"), hudIcon(keyIcon("1"), "Numpad 1")], label: "Back view" },
      { icons: [hudIcon(keyIcon("3"), "Numpad 3")], label: "Right view" },
      { icons: [hudIcon(specialKeyIcon("Ctrl"), "Ctrl"), hudIcon(keyIcon("3"), "Numpad 3")], label: "Left view" },
      { icons: [hudIcon(keyIcon("7"), "Numpad 7")], label: "Top view" },
      { icons: [hudIcon(specialKeyIcon("Ctrl"), "Ctrl"), hudIcon(keyIcon("7"), "Numpad 7")], label: "Bottom view" },
      { icons: [hudIcon(keyIcon("5"), "Numpad 5")], label: "Ortho / perspective" },
      { icons: [hudIcon(keyIcon("9"), "Numpad 9")], label: "Opposite view" },
    ];
  }

  function createHudRow(row) {
    const item = document.createElement("div");
    item.className = "hud-row";
    const icons = document.createElement("span");
    icons.className = "hud-icons";
    row.icons.forEach((icon, index) => {
      if (index > 0) {
        const plus = document.createElement("span");
        plus.className = "hud-plus";
        plus.textContent = "+";
        icons.appendChild(plus);
      }
      const image = document.createElement("img");
      image.className = "hud-icon";
      image.src = icon.src;
      image.alt = icon.label;
      image.draggable = false;
      icons.appendChild(image);
    });
    const label = document.createElement("span");
    label.className = "hud-label";
    label.textContent = row.label;
    item.append(icons, label);
    return item;
  }

  function createHudCollapsedRow() {
    const item = document.createElement("div");
    item.className = "hud-collapsed-row";
    item.textContent = "Camera Controls";
    return item;
  }

  function createOrientationNudgeOverlay() {
    if (orientationNudgeOverlay) return;
    orientationNudgeOverlay = document.createElement("div");
    orientationNudgeOverlay.className = "nudge-overlay";
    orientationNudgeOverlay.hidden = true;
    orientationNudgeMode = document.createElement("div");
    orientationNudgeMode.className = "nudge-mode";
    orientationNudgeOverlay.appendChild(orientationNudgeMode);
    for (const direction of SMART_NUDGE_DIRECTIONS) {
      const image = document.createElement("img");
      image.className = "nudge-arrow";
      image.src = keyIcon(direction.icon);
      image.alt = direction.label;
      image.title = direction.label;
      image.draggable = false;
      orientationNudgeArrows.set(direction.id, image);
      orientationNudgeOverlay.appendChild(image);
    }
    els.stage.appendChild(orientationNudgeOverlay);
  }

  function showViewportNotice(message, { actionLabel = "", onAction = null, duration = 2000 } = {}) {
    if (!els.viewportNotice) return;
    els.viewportNotice.replaceChildren();
    const text = document.createElement("span");
    text.textContent = message;
    els.viewportNotice.appendChild(text);
    if (actionLabel && typeof onAction === "function") {
      const action = document.createElement("button");
      action.type = "button";
      action.className = "viewport-notice-action";
      action.textContent = actionLabel;
      action.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        onAction();
      });
      els.viewportNotice.appendChild(action);
    }
    els.viewportNotice.classList.toggle("has-action", Boolean(actionLabel && typeof onAction === "function"));
    els.viewportNotice.hidden = false;
    els.viewportNotice.classList.remove("is-visible");
    void els.viewportNotice.offsetWidth;
    els.viewportNotice.classList.add("is-visible");
    if (viewportNoticeTimer) window.clearTimeout(viewportNoticeTimer);
    viewportNoticeTimer = window.setTimeout(() => {
      els.viewportNotice.classList.remove("is-visible");
      viewportNoticeTimer = window.setTimeout(() => {
        els.viewportNotice.hidden = true;
      }, 180);
    }, duration);
  }

  function syncOrientationUi() {
    if (!els.orientationToggle) return;
    const isLocal = orientationMode === "local";
    const label = els.orientationToggle.querySelector("span");
    if (label) {
      label.textContent = isLocal ? "Local Orientation" : "World Orientation";
    } else {
      els.orientationToggle.textContent = isLocal ? "Local Orientation" : "World Orientation";
    }
    els.orientationToggle.setAttribute("aria-pressed", String(isLocal));
    els.orientationToggle.title = isLocal
      ? "Using active object's local orientation"
      : "Using world orientation";
  }

  function setOrientationMode(mode, { notify = true } = {}) {
    orientationMode = mode === "world" ? "world" : "local";
    syncOrientationUi();
    updateSelectionPivot();
    syncTransformControlMode();
    updateOrientationNudgeOverlay();
    if (notify) {
      showViewportNotice(orientationMode === "local" ? "Local Orientation" : "World Orientation");
    }
  }

  function toggleOrientationMode() {
    setOrientationMode(orientationMode === "local" ? "world" : "local");
  }

  async function loadJson(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${url} returned ${response.status}`);
    return response.json();
  }

  function kindLabel(kind) {
    if (kind === "building_piece") return "Piece";
    if (kind === "item") return "Item";
    if (kind === "bp") return "BP";
    return "Asset";
  }

  function kindPluralLabel(kind) {
    if (kind === "building_piece") return "Pieces";
    if (kind === "item") return "Items";
    if (kind === "bp") return "BP";
    return "Assets";
  }

  function catalogPathParts(value) {
    return String(value || "").split("/").map((part) => part.trim()).filter(Boolean);
  }

  function categoryPathParts(value) {
    return catalogPathParts(value);
  }

  function categoryTreeForKind(kind = activeKind) {
    const tree = index?.category_tree?.[kind];
    if (tree && Array.isArray(tree.nodes)) return tree;
    return buildFallbackCategoryTree(kind);
  }

  function buildFallbackCategoryTree(kind) {
    const kindTargets = (index?.targets || []).filter((target) => target.asset_kind === kind);
    const firstSegments = new Set();
    for (const target of kindTargets) {
      const first = catalogPathParts(target.catalog_path)[0];
      if (first) firstSegments.add(first);
    }
    const rootLabel = firstSegments.size === 1 ? Array.from(firstSegments)[0] : "";
    const root = new Map();
    for (const target of kindTargets) {
      let map = root;
      const parts = targetCategorySegments(target, rootLabel);
      const pathParts = [];
      for (const part of parts) {
        pathParts.push(part);
        if (!map.has(part)) {
          map.set(part, { label: part, path: pathParts.join("/"), count: 0, children: new Map() });
        }
        const node = map.get(part);
        node.count += 1;
        map = node.children;
      }
    }
    const toRows = (map) => {
      const nodes = Array.from(map.values());
      const isTierRow = nodes.length > 0 && nodes.every((node) => /^tier\s+\d+\b/i.test(node.label));
      nodes.sort((a, b) => {
        if (isTierRow) return a.label.localeCompare(b.label, undefined, { numeric: true });
        return b.count - a.count || a.label.localeCompare(b.label, undefined, { numeric: true });
      });
      return nodes.map((node) => ({
        label: node.label,
        path: node.path,
        count: node.count,
        children: toRows(node.children),
      }));
    };
    return { root_label: rootLabel, nodes: toRows(root) };
  }

  function targetCategorySegments(target, rootOverride = null) {
    const parts = String(target.catalog_path || "").split("/").map((part) => part.trim()).filter(Boolean);
    const rootLabel = rootOverride === null ? (categoryTreeForKind(target.asset_kind).root_label || "") : rootOverride;
    if (rootLabel && parts[0] === rootLabel) parts.shift();
    return parts.length ? parts : ["Unsorted"];
  }

  function targetTopCategoryName(target) {
    return targetCategorySegments(target)[0] || "Unsorted";
  }

  function findCategoryNode(nodes, path) {
    const parts = categoryPathParts(path);
    let currentNodes = nodes || [];
    let node = null;
    for (const part of parts) {
      node = currentNodes.find((candidate) => candidate.label === part);
      if (!node) return null;
      currentNodes = node.children || [];
    }
    return node;
  }

  function normalizeActiveCategory() {
    const nodes = categoryTreeForKind().nodes || [];
    if (!nodes.length) {
      activeCategoryPath = "";
      return;
    }
    if (activeCategoryPath && !findCategoryNode(nodes, activeCategoryPath)) activeCategoryPath = "";
  }

  function targetMatchesActiveCategory(target) {
    if (!activeCategoryPath) return true;
    const activeParts = categoryPathParts(activeCategoryPath);
    const targetParts = targetCategorySegments(target);
    return activeParts.every((part, index) => targetParts[index] === part);
  }

  function activeCategoryLabel() {
    return categoryPathParts(activeCategoryPath).join(" / ");
  }

  function canScaleTarget(target) {
    if (!target) return false;
    if (scaleRestrictionOverride) return true;
    if (target.asset_kind !== "building_piece") return true;
    return targetTopCategoryName(target) === "Crafting Stations";
  }

  function canScalePlacement(placement) {
    return canScaleTarget(placement?.target);
  }

  function loadScaleOverride() {
    try {
      scaleRestrictionOverride = window.sessionStorage.getItem(SCALE_OVERRIDE_STORAGE_KEY) === "1";
    } catch {
      scaleRestrictionOverride = false;
    }
  }

  function enableScaleOverride() {
    scaleRestrictionOverride = true;
    try {
      window.sessionStorage.setItem(SCALE_OVERRIDE_STORAGE_KEY, "1");
    } catch {
      // Session-only override still works for the current page lifetime.
    }
    renderInspector();
    activateGizmo("scale");
    showViewportNotice("Scale override enabled");
  }

  function renderScaleOverrideMessage() {
    showViewportNotice("Only Crafting Station pieces, items, and BP actors can be scaled.", {
      actionLabel: "Click here to override.",
      duration: 5000,
      onAction: enableScaleOverride,
    });
  }

  function shortenClass(className) {
    const text = String(className || "");
    if (!text) return "";
    return text.split("/").pop().split(".").pop();
  }

  function pieceDataStem(pieceDataName) {
    const text = String(pieceDataName || "").replace(/^BuildingPieceData\s+/, "");
    return text ? text.split("/").pop().split(".")[0] : "";
  }

  function targetSearchScore(target, query) {
    if (!query) return 1;
    const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
    const haystack = target.search_text || "";
    for (const token of tokens) {
      if (!haystack.includes(token)) return 0;
    }
    let score = 10;
    const name = target.display_name.toLowerCase();
    const stem = target.asset_stem.toLowerCase();
    if (name.startsWith(query)) score += 100;
    if (stem.startsWith(query)) score += 80;
    return score;
  }

  function buildLookups() {
    const byId = new Map();
    const byPieceClass = new Map();
    const byPieceDataName = new Map();
    const byItemName = new Map();
    const byBpClass = new Map();
    for (const target of index.targets) {
      byId.set(target.target_id, target);
      if (target.asset_kind === "building_piece") {
        if (target.export.bp_class) byPieceClass.set(target.export.bp_class, target);
        if (target.export.class_name) byPieceClass.set(shortenClass(target.export.class_name), target);
        if (target.export.piece_data_name) byPieceDataName.set(pieceDataStem(target.export.piece_data_name), target);
      } else if (target.asset_kind === "item") {
        byItemName.set(target.export.item_asset_name || target.asset_stem, target);
      } else if (target.asset_kind === "bp") {
        byBpClass.set(target.export.bp_class, target);
        byBpClass.set(shortenClass(target.export.actor_class), target);
      }
    }
    targetLookup = { byId, byPieceClass, byPieceDataName, byItemName, byBpClass };
  }

  function stageAspect() {
    const width = Math.max(1, els.stage?.clientWidth || 1);
    const height = Math.max(1, els.stage?.clientHeight || 1);
    return width / height;
  }

  function createViewportCamera(mode = cameraProjectionMode) {
    const aspect = stageAspect();
    if (mode === "orthographic") {
      const halfHeight = orthographicViewSize / 2;
      const cameraObject = new THREE.OrthographicCamera(
        -halfHeight * aspect,
        halfHeight * aspect,
        halfHeight,
        -halfHeight,
        0.01,
        1500,
      );
      cameraObject.zoom = 1;
      return cameraObject;
    }
    return new THREE.PerspectiveCamera(CAMERA_FOV_DEGREES, aspect, 0.01, 1500);
  }

  function updateCameraProjection() {
    if (!camera) return;
    const aspect = stageAspect();
    if (camera.isOrthographicCamera) {
      const halfHeight = orthographicViewSize / 2;
      camera.left = -halfHeight * aspect;
      camera.right = halfHeight * aspect;
      camera.top = halfHeight;
      camera.bottom = -halfHeight;
    } else if (camera.isPerspectiveCamera) {
      camera.aspect = aspect;
    }
    camera.updateProjectionMatrix();
  }

  function niceGridStep(minStep) {
    const value = Math.max(Number(minStep) || 1, 0.01);
    const exponent = Math.floor(Math.log10(value));
    const base = 10 ** exponent;
    for (const multiplier of [1, 2, 5, 10]) {
      const step = multiplier * base;
      if (step >= value) return step;
    }
    return 10 * base;
  }

  function evenDivisionCount(value) {
    let divisions = Math.max(GROUND_GRID_MIN_DIVISIONS, Math.ceil(value));
    if (divisions % 2 !== 0) divisions += 1;
    return Math.min(GROUND_GRID_MAX_DIVISIONS, divisions);
  }

  function buildPlacementsWorldBox(rows = placements.values()) {
    const box = new THREE.Box3();
    for (const placement of rows) {
      if (placement.hidden) continue;
      box.union(getWorldBounds(placement));
    }
    return box;
  }

  function groundGridMetricsForBox(box) {
    if (!box || box.isEmpty()) {
      return {
        size: GROUND_GRID_DEFAULT_SIZE,
        divisions: GROUND_GRID_DEFAULT_SIZE,
        centerX: 0,
        centerZ: 0,
      };
    }
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const footprint = Math.max(size.x, size.z, GROUND_GRID_MIN_SIZE);
    const paddedSize = Math.max(
      GROUND_GRID_MIN_SIZE,
      footprint * (1 + GROUND_GRID_PADDING_RATIO) + GROUND_GRID_MIN_PADDING,
    );
    const step = niceGridStep(paddedSize / GROUND_GRID_TARGET_DIVISIONS);
    const divisions = evenDivisionCount(paddedSize / step);
    const gridSize = divisions * step;
    return {
      size: gridSize,
      divisions,
      centerX: Math.round(center.x / step) * step,
      centerZ: Math.round(center.z / step) * step,
    };
  }

  function installGroundGrid(metrics = groundGridMetricsForBox()) {
    if (!scene) return;
    const signature = [
      roundValue(metrics.size, 4),
      metrics.divisions,
      roundValue(metrics.centerX, 4),
      roundValue(metrics.centerZ, 4),
    ].join(":");
    if (signature === groundGridSignature && groundGrid) return;
    if (groundGrid) {
      scene.remove(groundGrid);
      groundGrid.geometry?.dispose?.();
      if (Array.isArray(groundGrid.material)) {
        groundGrid.material.forEach((material) => material.dispose?.());
      } else {
        groundGrid.material?.dispose?.();
      }
    }
    groundGrid = new THREE.GridHelper(metrics.size, metrics.divisions, 0x88928c, 0xd2d8d1);
    groundGrid.name = "Dynamic Ground Grid";
    groundGrid.position.set(metrics.centerX, GROUND_GRID_Y, metrics.centerZ);
    groundGrid.renderOrder = -10;
    scene.add(groundGrid);
    groundGridSignature = signature;
    if (els.stage) {
      els.stage.dataset.gridSize = String(roundValue(metrics.size, 3));
      els.stage.dataset.gridDivisions = String(metrics.divisions);
      els.stage.dataset.gridCenter = `${roundValue(metrics.centerX, 3)},${roundValue(metrics.centerZ, 3)}`;
    }
  }

  function updateGroundGrid() {
    groundGridUpdateHandle = 0;
    const box = placements.size ? buildPlacementsWorldBox() : null;
    installGroundGrid(groundGridMetricsForBox(box));
    syncCameraRangeWithBox(box);
  }

  function scheduleGroundGridUpdate() {
    if (groundGridUpdateHandle) return;
    groundGridUpdateHandle = window.requestAnimationFrame(updateGroundGrid);
  }

  function syncCameraRangeWithBox(box, { distance = 0 } = {}) {
    if (!camera || !controls || !box || box.isEmpty()) return;
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(box.getBoundingSphere(new THREE.Sphere()).radius, CAMERA_DEFAULT_DISTANCE);
    const maxSize = Math.max(size.x, size.y, size.z, radius);
    const targetDistance = distance || camera.position.distanceTo(controls.target);
    camera.near = Math.max(0.01, Math.min(2, maxSize / 5000));
    camera.far = Math.max(1500, maxSize * 30, radius * 16, targetDistance + radius * 8);
    controls.maxDistance = Math.max(150, maxSize * 6, radius * 8);
    if (els.stage) {
      els.stage.dataset.cameraFar = String(roundValue(camera.far, 3));
      els.stage.dataset.controlsMaxDistance = String(roundValue(controls.maxDistance, 3));
    }
    updateCameraProjection();
  }

  function perspectiveFitDistance(box) {
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const radius = Math.max(sphere.radius, 1);
    const verticalFov = THREE.MathUtils.degToRad(camera.fov || CAMERA_FOV_DEGREES);
    return Math.max(radius / Math.sin(verticalFov / 2) * 1.08, CAMERA_DEFAULT_DISTANCE / 2);
  }

  function matchingOrthographicSize() {
    if (!camera || !controls) return orthographicViewSize || CAMERA_DEFAULT_DISTANCE;
    if (camera.isOrthographicCamera) return orthographicViewSize / Math.max(camera.zoom || 1, 0.001);
    const distance = Math.max(camera.position.distanceTo(controls.target), 1);
    return 2 * distance * Math.tan(THREE.MathUtils.degToRad((camera.fov || CAMERA_FOV_DEGREES) / 2));
  }

  function viewportSpanCm() {
    return Math.max(matchingOrthographicSize() / UNIT_SCALE, 1);
  }

  function selectionZoomOutFactor() {
    return THREE.MathUtils.clamp((viewportSpanCm() - 8000) / 40000, 0, 1);
  }

  function movePreviewStartDistancePx() {
    return THREE.MathUtils.lerp(MOVE_PREVIEW_START_MIN_PX, MOVE_PREVIEW_START_MAX_PX, selectionZoomOutFactor());
  }

  function shouldMarqueeFromHitDrag(dx, dy) {
    const absX = Math.abs(dx);
    const absY = Math.abs(dy);
    if (Math.min(absX, absY) < MARQUEE_FROM_HIT_MIN_AXIS_PX) return false;
    const threshold = THREE.MathUtils.lerp(MARQUEE_FROM_HIT_NEAR_PX, MARQUEE_FROM_HIT_FAR_PX, selectionZoomOutFactor());
    return Math.hypot(dx, dy) >= threshold;
  }

  function marqueeSpatialPaddingCm() {
    return THREE.MathUtils.clamp(
      viewportSpanCm() * MARQUEE_SPATIAL_PADDING_RATIO,
      SPATIAL_CELL_SIZE_CM,
      MARQUEE_SPATIAL_MAX_PADDING_CM,
    );
  }

  function switchCameraProjection(mode, { notify = true } = {}) {
    const nextMode = mode === "orthographic" ? "orthographic" : "perspective";
    if (cameraProjectionMode === nextMode && camera) return;
    stopViewHelperAnimation();
    const previousCamera = camera;
    if (nextMode === "orthographic") {
      orthographicViewSize = Math.max(matchingOrthographicSize(), 1);
    }
    const nextCamera = createViewportCamera(nextMode);
    if (previousCamera) {
      nextCamera.position.copy(previousCamera.position);
      nextCamera.quaternion.copy(previousCamera.quaternion);
      nextCamera.up.copy(previousCamera.up);
      nextCamera.near = previousCamera.near;
      nextCamera.far = previousCamera.far;
    }
    camera = nextCamera;
    cameraProjectionMode = nextMode;
    updateCameraProjection();
    if (controls) {
      controls.object = camera;
      controls.update();
    }
    if (transformControls) {
      transformControls.camera = camera;
      transformControls.updateMatrixWorld?.(true);
    }
    refreshViewHelper();
    if (notify) {
      showViewportNotice(nextMode === "orthographic" ? "Orthographic View" : "Perspective View");
    }
  }

  function toggleCameraProjection() {
    switchCameraProjection(cameraProjectionMode === "orthographic" ? "perspective" : "orthographic");
  }

  function createViewHelperHitZone() {
    if (viewHelperHitZone) return;
    viewHelperHitZone = document.createElement("div");
    viewHelperHitZone.className = "view-helper-hit-zone";
    viewHelperHitZone.setAttribute("role", "application");
    viewHelperHitZone.tabIndex = 0;
    viewHelperHitZone.title = "View gizmo: drag to orbit, click an axis to snap";
    viewHelperHitZone.setAttribute("aria-label", "View gizmo. Drag to orbit. Click an axis to snap the view.");
    viewHelperHitZone.addEventListener("pointerdown", onViewHelperPointerDown);
    applyViewHelperHitZoneStyle(false);
    els.stage.appendChild(viewHelperHitZone);
  }

  function refreshViewHelper() {
    if (!renderer || !camera) return;
    if (viewHelper) viewHelper.dispose();
    viewHelper = new ViewHelper(camera, renderer.domElement);
    viewHelper.location.top = VIEW_HELPER_TOP;
    viewHelper.location.right = VIEW_HELPER_RIGHT;
    viewHelper.location.bottom = null;
    viewHelper.location.left = null;
    viewHelper.setLabels("X", "Y", "Z");
    viewHelper.setLabelStyle("700 20px Sofia Sans, Arial, sans-serif", "#14120f", 15);
    if (viewHelperHitZone) {
      viewHelperHitZone.style.setProperty("--view-helper-size", `${VIEW_HELPER_SIZE}px`);
      viewHelperHitZone.style.setProperty("--view-helper-top", `${VIEW_HELPER_TOP}px`);
      viewHelperHitZone.style.setProperty("--view-helper-right", `${VIEW_HELPER_RIGHT}px`);
      viewHelperHitZone.style.position = "absolute";
      viewHelperHitZone.style.top = `${VIEW_HELPER_TOP}px`;
      viewHelperHitZone.style.right = `${VIEW_HELPER_RIGHT}px`;
      viewHelperHitZone.style.width = `${VIEW_HELPER_SIZE}px`;
      viewHelperHitZone.style.height = `${VIEW_HELPER_SIZE}px`;
      applyViewHelperHitZoneStyle(viewHelperHitZone.classList.contains("is-dragging"));
    }
    viewHelperClock.getDelta();
  }

  function applyViewHelperHitZoneStyle(isDragging) {
    if (!viewHelperHitZone) return;
    viewHelperHitZone.style.zIndex = "4";
    viewHelperHitZone.style.border = `1px solid ${isDragging ? "rgba(243, 207, 137, 0.58)" : "rgba(243, 207, 137, 0.2)"}`;
    viewHelperHitZone.style.borderRadius = "50%";
    viewHelperHitZone.style.background = "radial-gradient(circle at 50% 50%, rgba(8, 8, 11, 0.08), rgba(8, 8, 11, 0.28) 68%, rgba(8, 8, 11, 0.44))";
    viewHelperHitZone.style.boxShadow = "inset 0 0 0 1px rgba(245, 239, 224, 0.05), 0 12px 28px rgba(0, 0, 0, 0.26)";
    viewHelperHitZone.style.cursor = isDragging ? "grabbing" : "grab";
    viewHelperHitZone.style.pointerEvents = "auto";
    viewHelperHitZone.style.touchAction = "none";
    viewHelperHitZone.style.userSelect = "none";
  }

  function renderViewHelper() {
    if (!viewHelper || !renderer || !controls) return;
    viewHelper.center.copy(controls.target);
    viewHelper.render(renderer);
  }

  function stopViewHelperAnimation() {
    if (viewHelper) viewHelper.animating = false;
  }

  function onViewHelperPointerDown(event) {
    if (event.button !== 0 || !viewHelper || !controls) return;
    event.preventDefault();
    event.stopPropagation();
    stopViewHelperAnimation();
    viewHelperDrag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      dragged: false,
    };
    viewHelperHitZone.classList.add("is-dragging");
    applyViewHelperHitZoneStyle(true);
    viewHelperHitZone.setPointerCapture?.(event.pointerId);
    viewHelperHitZone.addEventListener("pointermove", onViewHelperPointerMove);
    viewHelperHitZone.addEventListener("pointerup", onViewHelperPointerUp);
    viewHelperHitZone.addEventListener("pointercancel", onViewHelperPointerUp);
    window.addEventListener("pointerup", onViewHelperPointerUp);
    window.addEventListener("pointercancel", onViewHelperPointerUp);
    window.addEventListener("mouseup", onViewHelperMouseUpFallback);
  }

  function onViewHelperPointerMove(event) {
    if (!viewHelperDrag || event.pointerId !== viewHelperDrag.pointerId) return;
    event.preventDefault();
    event.stopPropagation();
    const totalDistance = Math.hypot(event.clientX - viewHelperDrag.startX, event.clientY - viewHelperDrag.startY);
    if (totalDistance >= VIEW_HELPER_DRAG_THRESHOLD_PX) viewHelperDrag.dragged = true;
    if (!viewHelperDrag.dragged) return;
    const dx = event.clientX - viewHelperDrag.lastX;
    const dy = event.clientY - viewHelperDrag.lastY;
    viewHelperDrag.lastX = event.clientX;
    viewHelperDrag.lastY = event.clientY;
    const rotateScale = 2 * Math.PI / Math.max(1, renderer.domElement.clientHeight || VIEW_HELPER_SIZE);
    controls.rotateLeft(dx * rotateScale);
    controls.rotateUp(dy * rotateScale);
    controls.update();
  }

  function onViewHelperPointerUp(event) {
    const pointerId = event.pointerId ?? viewHelperDrag?.pointerId;
    if (!viewHelperDrag || pointerId !== viewHelperDrag.pointerId) return;
    event.preventDefault();
    event.stopPropagation();
    const wasDrag = viewHelperDrag.dragged;
    viewHelperHitZone.releasePointerCapture?.(pointerId);
    viewHelperHitZone.classList.remove("is-dragging");
    applyViewHelperHitZoneStyle(false);
    viewHelperHitZone.removeEventListener("pointermove", onViewHelperPointerMove);
    viewHelperHitZone.removeEventListener("pointerup", onViewHelperPointerUp);
    viewHelperHitZone.removeEventListener("pointercancel", onViewHelperPointerUp);
    window.removeEventListener("pointerup", onViewHelperPointerUp);
    window.removeEventListener("pointercancel", onViewHelperPointerUp);
    window.removeEventListener("mouseup", onViewHelperMouseUpFallback);
    viewHelperDrag = null;
    if (!wasDrag && viewHelper) {
      viewHelper.center.copy(controls.target);
      viewHelper.handleClick(event);
    }
  }

  function onViewHelperMouseUpFallback(event) {
    if (!viewHelperDrag) return;
    onViewHelperPointerUp(event);
  }

  function initThree() {
    scene = new THREE.Scene();
    camera = createViewportCamera("perspective");
    camera.position.set(6, 7, 8);

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.autoClear = false;
    els.stage.appendChild(renderer.domElement);

    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    pmrem.dispose();

    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0, 0.4, 0);
    controls.maxDistance = 150;
    controls.mouseButtons = {
      LEFT: null,
      MIDDLE: THREE.MOUSE.ROTATE,
      RIGHT: THREE.MOUSE.PAN,
    };
    controls.addEventListener("change", invalidateAllScreenBounds);
    createViewHelperHitZone();
    refreshViewHelper();

    transformControls = new TransformControls(camera, renderer.domElement);
    transformControls.setSpace(orientationMode);
    transformControls.addEventListener("dragging-changed", (event) => {
      controls.enabled = !event.value;
      if (event.value) {
        pendingTransformUndo = selectedPlacedIds.size ? captureBuildSnapshot() : null;
        pendingTransformChanged = false;
        syncTransformSnaps();
      } else {
        if (pendingTransformUndo && pendingTransformChanged) pushUndoSnapshot(pendingTransformUndo);
        pendingTransformUndo = null;
        pendingTransformChanged = false;
        syncTransformSnaps();
        scheduleGroundGridUpdate();
      }
    });
    transformControls.addEventListener("objectChange", () => {
      handleTransformObjectChange();
    });
    scene.add(transformControls.getHelper());

    rootGroup = new THREE.Group();
    scene.add(rootGroup);

    selectionPivot = new THREE.Object3D();
    selectionPivot.name = "Selection Pivot";
    selectionPivot.userData.previousPosition = new THREE.Vector3();
    selectionPivot.userData.previousMatrix = new THREE.Matrix4();
    scene.add(selectionPivot);

    installGroundGrid();

    const hemi = new THREE.HemisphereLight(0xfff4df, 0x6f7d72, 2.3);
    scene.add(hemi);
    const key = new THREE.DirectionalLight(0xffe3bd, 2.1);
    key.position.set(8, 10, 6);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xb8d8ff, 0.85);
    fill.position.set(-7, 5, -4);
    scene.add(fill);

    const draco = new DRACOLoader();
    draco.setDecoderPath("https://unpkg.com/three@0.184.0/examples/jsm/libs/draco/");
    loader = new GLTFLoader();
    loader.setDRACOLoader(draco);

    raycaster = new THREE.Raycaster();
    pointer = new THREE.Vector2();
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("wheel", onStageWheel, { passive: false });
    selectionMarquee = document.createElement("div");
    selectionMarquee.className = "selection-marquee";
    selectionMarquee.hidden = true;
    els.stage.appendChild(selectionMarquee);
    createOrientationNudgeOverlay();
    window.addEventListener("resize", resize);
    resize();
    animate();
  }

  function resize() {
    if (!renderer || !camera) return;
    const width = Math.max(1, els.stage.clientWidth);
    const height = Math.max(1, els.stage.clientHeight);
    renderer.setSize(width, height);
    updateCameraProjection();
    invalidateAllScreenBounds();
  }

  function animate() {
    requestAnimationFrame(animate);
    const delta = viewHelperClock.getDelta();
    if (viewHelper?.animating) {
      viewHelper.center.copy(controls.target);
      viewHelper.update(delta);
    }
    controls.update();
    updateOrientationNudgeOverlay();
    renderer.clear();
    renderer.render(scene, camera);
    renderViewHelper();
  }

  async function loadGltf(gltfPath) {
    if (!gltfCache.has(gltfPath)) {
      gltfCache.set(gltfPath, loader.loadAsync(assetUrl(gltfPath)));
    }
    return gltfCache.get(gltfPath);
  }

  function uniqueGltfPathsForTargets(targets) {
    const paths = new Set();
    for (const target of targets) {
      for (const component of target?.components || []) {
        if (component.gltf_path) paths.add(component.gltf_path);
      }
    }
    return Array.from(paths);
  }

  async function preloadGltfsForTargets(targets, { statusPrefix = "Preloading models" } = {}) {
    const paths = uniqueGltfPathsForTargets(targets);
    if (!paths.length) return;
    let nextIndex = 0;
    let completed = 0;
    const workerCount = Math.min(GLTF_PRELOAD_CONCURRENCY, paths.length);
    const workers = Array.from({ length: workerCount }, async () => {
      while (nextIndex < paths.length) {
        const path = paths[nextIndex++];
        await loadGltf(path);
        completed += 1;
        if (completed === paths.length || completed % 25 === 0) {
          els.assetStatus.textContent = `${statusPrefix} ${completed.toLocaleString()} of ${paths.length.toLocaleString()}`;
          await nextFrame();
        }
      }
    });
    await Promise.all(workers);
  }

  function nextFrame() {
    return new Promise((resolve) => window.requestAnimationFrame(resolve));
  }

  function cloneScene(source, { cloneMaterials = false } = {}) {
    const cloned = SkeletonUtils.clone(source);
    cloned.traverse((obj) => {
      if (!obj.isMesh && !obj.isSkinnedMesh) return;
      obj.frustumCulled = false;
      if (!cloneMaterials) return;
      if (Array.isArray(obj.material)) {
        obj.material = obj.material.map((mat) => mat.clone());
      } else if (obj.material) {
        obj.material = obj.material.clone();
      }
    });
    return cloned;
  }

  function targetCacheKey(target) {
    return target?.target_id || target?.asset_stem || "";
  }

  async function buildVisualTemplate(target) {
    const assetRoot = new THREE.Group();
    assetRoot.name = target.asset_stem || target.target_id;
    if (!target.components.length) {
      const geometry = new THREE.BoxGeometry(0.5, 0.5, 0.5);
      const material = new THREE.MeshStandardMaterial({ color: 0xb45f31, roughness: 0.75 });
      assetRoot.add(new THREE.Mesh(geometry, material));
      return assetRoot;
    }
    const jobs = target.components.map(async (component) => {
      const gltf = await loadGltf(component.gltf_path);
      const clone = cloneScene(gltf.scene);
      const componentRoot = new THREE.Group();
      componentRoot.name = component.name || "component";
      componentRoot.add(clone);
      const matrix = componentTransformToThreeMatrix4(component.transform || {});
      componentRoot.matrixAutoUpdate = true;
      const position = new THREE.Vector3();
      const quaternion = new THREE.Quaternion();
      const scale = new THREE.Vector3();
      matrix.decompose(position, quaternion, scale);
      componentRoot.position.copy(position);
      componentRoot.quaternion.copy(quaternion);
      componentRoot.scale.copy(scale);
      return componentRoot;
    });
    const children = await Promise.all(jobs);
    for (const child of children) assetRoot.add(child);
    return assetRoot;
  }

  async function visualTemplateForTarget(target) {
    const key = targetCacheKey(target);
    if (!targetVisualTemplateCache.has(key)) {
      const promise = buildVisualTemplate(target).then((template) => {
        template.updateMatrixWorld(true);
        targetVisualResolvedCache.set(key, template);
        return template;
      });
      targetVisualTemplateCache.set(key, promise);
    }
    return targetVisualTemplateCache.get(key);
  }

  function resolvedVisualTemplateForTarget(target) {
    return targetVisualResolvedCache.get(targetCacheKey(target)) || null;
  }

  function cloneResolvedVisualGroup(target) {
    const template = resolvedVisualTemplateForTarget(target);
    if (!template) return null;
    const visual = cloneScene(template);
    visual.name = target.asset_stem || target.target_id;
    return visual;
  }

  async function buildVisualGroup(target) {
    await visualTemplateForTarget(target);
    return cloneResolvedVisualGroup(target);
  }

  function instanceTemplateForTarget(target) {
    const key = targetCacheKey(target);
    if (targetInstanceTemplateCache.has(key)) return targetInstanceTemplateCache.get(key);
    const template = resolvedVisualTemplateForTarget(target);
    if (!template) return null;
    template.updateMatrixWorld(true);
    const descriptors = [];
    const bounds = new THREE.Box3();
    let eligible = true;
    template.traverse((obj) => {
      if (obj.isSkinnedMesh) {
        eligible = false;
        return;
      }
      if (!obj.isMesh || !obj.geometry || !obj.material) return;
      obj.updateMatrixWorld(true);
      descriptors.push({
        geometry: obj.geometry,
        material: obj.material,
        localMatrix: obj.matrixWorld.clone(),
      });
      const meshBounds = new THREE.Box3().setFromObject(obj);
      if (!meshBounds.isEmpty()) bounds.union(meshBounds);
    });
    const instanceTemplate = {
      key,
      eligible: eligible && descriptors.length > 0 && !bounds.isEmpty(),
      descriptors,
      bounds,
    };
    targetInstanceTemplateCache.set(key, instanceTemplate);
    return instanceTemplate;
  }

  function createHiddenInstanceMatrix() {
    return new THREE.Matrix4().makeScale(0, 0, 0);
  }

  function placementRootMatrix(placement) {
    const object = new THREE.Object3D();
    updateObjectFromState(object, placement.state, viewOffset);
    object.updateMatrix();
    return object.matrix.clone();
  }

  function instancingEligibleForPlacement(placement) {
    const instanceTemplate = instanceTemplateForTarget(placement.target);
    return Boolean(instanceTemplate?.eligible);
  }

  function ensureInstanceBatch(target) {
    const instanceTemplate = instanceTemplateForTarget(target);
    if (!instanceTemplate?.eligible) return null;
    if (instanceBatches.has(instanceTemplate.key)) return instanceBatches.get(instanceTemplate.key);
    const batch = {
      key: instanceTemplate.key,
      target,
      template: instanceTemplate,
      meshes: [],
      placementSlots: new Map(),
      slotIds: [],
      count: 0,
      capacity: 0,
    };
    instanceBatches.set(instanceTemplate.key, batch);
    growInstanceBatch(batch, INSTANCE_INITIAL_CAPACITY);
    return batch;
  }

  function growInstanceBatch(batch, minCapacity) {
    const nextCapacity = Math.max(INSTANCE_INITIAL_CAPACITY, batch.capacity ? batch.capacity * 2 : 0, minCapacity);
    const previousMeshes = batch.meshes;
    const nextMeshes = batch.template.descriptors.map((descriptor, index) => {
      const mesh = new THREE.InstancedMesh(descriptor.geometry, descriptor.material, nextCapacity);
      mesh.name = `${batch.target.asset_stem || batch.target.target_id} Instances ${index + 1}`;
      mesh.frustumCulled = false;
      mesh.count = batch.count;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      mesh.userData.instanceBatchKey = batch.key;
      if (previousMeshes[index]) {
        const matrix = new THREE.Matrix4();
        for (let slot = 0; slot < batch.count; slot += 1) {
          previousMeshes[index].getMatrixAt(slot, matrix);
          mesh.setMatrixAt(slot, matrix);
        }
      }
      mesh.instanceMatrix.needsUpdate = true;
      rootGroup.add(mesh);
      return mesh;
    });
    for (const mesh of previousMeshes) {
      rootGroup.remove(mesh);
      mesh.dispose?.();
    }
    batch.meshes = nextMeshes;
    batch.capacity = nextCapacity;
  }

  function addPlacementToInstanceBatch(placement) {
    const batch = ensureInstanceBatch(placement.target);
    if (!batch) return false;
    if (batch.count >= batch.capacity) growInstanceBatch(batch, batch.count + 1);
    const slot = batch.count;
    batch.count += 1;
    batch.placementSlots.set(placement.id, slot);
    batch.slotIds[slot] = placement.id;
    for (const mesh of batch.meshes) mesh.count = batch.count;
    const visual = ensurePlacementVisualState(placement);
    visual.backend = "instanced";
    visual.root = null;
    visual.batchKey = batch.key;
    visual.instanceSlot = slot;
    visual.localBounds = batch.template.bounds.clone();
    visual.visible = true;
    placement.group = null;
    updateInstancePlacementTransform(placement);
    syncInstanceStatsDataset();
    return true;
  }

  function removePlacementFromInstanceBatch(placement) {
    const visual = ensurePlacementVisualState(placement);
    if (visual.backend !== "instanced" || !visual.batchKey) return false;
    const batch = instanceBatches.get(visual.batchKey);
    if (!batch) return false;
    const slot = batch.placementSlots.get(placement.id);
    if (slot === undefined) return false;
    const lastSlot = batch.count - 1;
    const hiddenMatrix = createHiddenInstanceMatrix();
    if (slot !== lastSlot) {
      const movedId = batch.slotIds[lastSlot];
      const matrix = new THREE.Matrix4();
      for (const mesh of batch.meshes) {
        mesh.getMatrixAt(lastSlot, matrix);
        mesh.setMatrixAt(slot, matrix);
        mesh.setMatrixAt(lastSlot, hiddenMatrix);
        mesh.instanceMatrix.needsUpdate = true;
      }
      batch.slotIds[slot] = movedId;
      batch.placementSlots.set(movedId, slot);
      const moved = placements.get(movedId);
      if (moved?.visual) moved.visual.instanceSlot = slot;
    } else {
      for (const mesh of batch.meshes) {
        mesh.setMatrixAt(lastSlot, hiddenMatrix);
        mesh.instanceMatrix.needsUpdate = true;
      }
    }
    batch.slotIds.pop();
    batch.placementSlots.delete(placement.id);
    batch.count -= 1;
    for (const mesh of batch.meshes) mesh.count = batch.count;
    visual.backend = "";
    visual.batchKey = "";
    visual.instanceSlot = -1;
    syncInstanceStatsDataset();
    return true;
  }

  function updateInstancePlacementTransform(placement) {
    const visual = ensurePlacementVisualState(placement);
    if (visual.backend !== "instanced" || !visual.batchKey) return;
    const batch = instanceBatches.get(visual.batchKey);
    if (!batch) return;
    const slot = batch.placementSlots.get(placement.id);
    if (slot === undefined) return;
    const rootMatrix = placementVisualRenderable(placement) ? placementRootMatrix(placement) : createHiddenInstanceMatrix();
    const matrix = new THREE.Matrix4();
    batch.template.descriptors.forEach((descriptor, index) => {
      matrix.copy(rootMatrix).multiply(descriptor.localMatrix);
      batch.meshes[index].setMatrixAt(slot, matrix);
      batch.meshes[index].instanceMatrix.needsUpdate = true;
    });
  }

  function instanceBatchMeshesForPlacements(candidates) {
    const keys = new Set();
    for (const placement of candidates) {
      const visual = ensurePlacementVisualState(placement);
      if (visual.backend === "instanced" && visual.batchKey) keys.add(visual.batchKey);
    }
    return Array.from(keys)
      .map((key) => instanceBatches.get(key))
      .filter(Boolean)
      .flatMap((batch) => batch.meshes);
  }

  function placementIdFromInstanceHit(hit) {
    const key = hit?.object?.userData?.instanceBatchKey;
    if (!key || hit.instanceId === undefined) return "";
    const batch = instanceBatches.get(key);
    return batch?.slotIds?.[hit.instanceId] || "";
  }

  function instanceStats() {
    let meshCount = 0;
    let instanceCount = 0;
    for (const batch of instanceBatches.values()) {
      if (!batch.count) continue;
      meshCount += batch.meshes.length;
      instanceCount += batch.count;
    }
    return {
      batches: Array.from(instanceBatches.values()).filter((batch) => batch.count > 0).length,
      meshes: meshCount,
      instances: instanceCount,
      promoted: promotedPlacementIds.size,
    };
  }

  function syncInstanceStatsDataset() {
    if (!els.stage) return;
    const stats = instanceStats();
    els.stage.dataset.instanceBatches = String(stats.batches);
    els.stage.dataset.instanceMeshes = String(stats.meshes);
    els.stage.dataset.instancePlacements = String(stats.instances);
    els.stage.dataset.promotedPlacements = String(stats.promoted);
  }

  function resetVisibleAssetResults() {
    visibleAssetResultCount = RESULT_LIMIT;
  }

  function updateLoadMoreAssetsState(totalCount, shownCount) {
    if (!els.assetResultsFooter || !els.loadMoreAssets) return;
    const remaining = Math.max(0, totalCount - shownCount);
    els.assetResultsFooter.hidden = remaining <= 0;
    els.loadMoreAssets.hidden = remaining <= 0;
    if (remaining > 0) {
      const nextCount = Math.min(RESULT_LIMIT, remaining);
      els.loadMoreAssets.textContent = `Load ${nextCount.toLocaleString()} More`;
      els.loadMoreAssets.title = `${remaining.toLocaleString()} more matching assets available`;
    }
  }

  function loadMoreAssets() {
    visibleAssetResultCount += RESULT_LIMIT;
    renderAssets();
  }

  function renderAssets() {
    normalizeActiveCategory();
    const query = els.assetSearch.value.trim().toLowerCase();
    const kindTargets = index.targets.filter((target) => target.asset_kind === activeKind);
    const scopedTargets = kindTargets.filter(targetMatchesActiveCategory);
    const scored = scopedTargets
      .map((target) => ({ target, score: targetSearchScore(target, query) }))
      .filter((row) => row.score > 0)
      .sort((a, b) => b.score - a.score || a.target.display_name.localeCompare(b.target.display_name));
    const visible = scored.slice(0, visibleAssetResultCount);
    els.assetList.textContent = "";
    for (const row of visible) {
      els.assetList.appendChild(createAssetRow(row.target));
    }
    updateLoadMoreAssetsState(scored.length, visible.length);
    renderFavorites();
    const categorySuffix = activeCategoryPath ? ` in ${activeCategoryLabel()}` : "";
    const visibleText = visible.length < scored.length
      ? `Showing ${visible.length.toLocaleString()} of ${scored.length.toLocaleString()}`
      : `Showing ${scored.length.toLocaleString()}`;
    els.assetStatus.textContent = `${visibleText} from ${kindTargets.length.toLocaleString()} ${kindPluralLabel(activeKind)}${categorySuffix}`;
  }

  function createAssetRow(target) {
    const row = document.createElement("div");
    row.className = `asset-row${target.target_id === selectedTargetId ? " is-active" : ""}`;
    row.dataset.targetId = target.target_id;
    row.draggable = false;
    row.tabIndex = 0;
    row.setAttribute("role", "button");
    row.setAttribute("aria-label", `${target.display_name} ${target.catalog_path}`);
    row.innerHTML = `
      <span class="asset-thumb" aria-hidden="true"></span>
      <span class="asset-copy">
        <span class="asset-name"></span>
        <span class="asset-path"></span>
      </span>
      <button class="asset-favorite" type="button"></button>
      <span class="asset-kind"></span>
    `;
    renderAssetThumb(row.querySelector(".asset-thumb"), target);
    row.querySelector(".asset-name").textContent = target.display_name;
    row.querySelector(".asset-path").textContent = target.catalog_path;
    row.querySelector(".asset-kind").textContent = kindLabel(target.asset_kind);
    wireFavoriteButton(row.querySelector(".asset-favorite"), target);
    row.addEventListener("pointerdown", (event) => startAssetPointer(event, target));
    row.addEventListener("contextmenu", (event) => openAssetContextMenu(event, target));
    row.addEventListener("keydown", (event) => {
      if (event.key !== " " && event.key !== "Enter") return;
      event.preventDefault();
      toggleFavorite(target.target_id);
    });
    return row;
  }

  function renderFavorites() {
    els.favoriteStrip.textContent = "";
    const favorites = Array.from(favoriteTargetIds)
      .map((id) => targetLookup.byId.get(id))
      .filter((target) => target && target.asset_kind === activeKind);
    if (!favorites.length) {
      const empty = document.createElement("span");
      empty.className = "favorite-empty";
      empty.textContent = "No favorites yet";
      els.favoriteStrip.appendChild(empty);
      return;
    }
    for (const target of favorites) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `favorite-tile${target.target_id === selectedTargetId ? " is-active" : ""}`;
      button.dataset.targetId = target.target_id;
      button.draggable = false;
      button.title = target.display_name;
      button.setAttribute("aria-label", target.display_name);
      const thumb = document.createElement("span");
      thumb.className = "asset-thumb";
      thumb.setAttribute("aria-hidden", "true");
      renderAssetThumb(thumb, target);
      button.appendChild(thumb);
      button.addEventListener("pointerdown", (event) => startAssetPointer(event, target));
      button.addEventListener("contextmenu", (event) => openAssetContextMenu(event, target));
      els.favoriteStrip.appendChild(button);
    }
  }

  function loadAssetViewMode() {
    try {
      assetViewMode = window.localStorage.getItem(ASSET_VIEW_STORAGE_KEY) === "grid" ? "grid" : "list";
    } catch {
      assetViewMode = "list";
    }
    syncAssetViewMode();
  }

  function saveAssetViewMode() {
    try {
      window.localStorage.setItem(ASSET_VIEW_STORAGE_KEY, assetViewMode);
    } catch {
      // The toggle still works for the current page lifetime.
    }
  }

  function syncAssetViewMode() {
    const isGrid = assetViewMode === "grid";
    els.assetList?.classList.toggle("is-grid", isGrid);
    if (!els.assetViewToggle) return;
    els.assetViewToggle.textContent = isGrid ? "List" : "Grid";
    els.assetViewToggle.setAttribute("aria-pressed", String(isGrid));
    els.assetViewToggle.title = isGrid ? "Switch to list view" : "Switch to grid view";
  }

  function toggleAssetViewMode() {
    assetViewMode = assetViewMode === "grid" ? "list" : "grid";
    saveAssetViewMode();
    syncAssetViewMode();
    showViewportNotice(assetViewMode === "grid" ? "Grid View" : "List View");
  }

  function createCategoryButton(node, isActive, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `category-button${isActive ? " is-active" : ""}`;
    button.setAttribute("aria-pressed", String(isActive));
    button.title = `${node.label} (${Number(node.count || 0).toLocaleString()})`;
    button.setAttribute("aria-label", `${node.label}, ${Number(node.count || 0).toLocaleString()} assets`);

    const label = document.createElement("span");
    label.className = "category-button-label";
    label.textContent = node.label;
    const count = document.createElement("span");
    count.className = "category-button-count";
    count.textContent = Number(node.count || 0).toLocaleString();
    button.append(label, count);
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      onClick();
    });
    return button;
  }

  function renderCategoryButtons() {
    if (!els.assetCategoryPrimary || !els.assetCategoryChildren) return;
    normalizeActiveCategory();
    const tree = categoryTreeForKind();
    const nodes = tree.nodes || [];
    const activeParts = categoryPathParts(activeCategoryPath);

    els.assetCategoryPrimary.textContent = "";
    const allNode = {
      label: "All",
      path: "",
      count: index.targets.filter((target) => target.asset_kind === activeKind).length,
    };
    els.assetCategoryPrimary.appendChild(createCategoryButton(allNode, !activeCategoryPath, () => {
      activeCategoryPath = "";
      resetVisibleAssetResults();
      renderCategoryButtons();
      renderAssets();
    }));
    for (const node of nodes) {
      const isActive = activeParts[0] === node.label;
      els.assetCategoryPrimary.appendChild(createCategoryButton(node, isActive, () => {
        activeCategoryPath = node.path || node.label || "";
        resetVisibleAssetResults();
        renderCategoryButtons();
        renderAssets();
      }));
    }

    els.assetCategoryChildren.textContent = "";
    let currentNodes = nodes;
    for (let depth = 0; depth < activeParts.length; depth += 1) {
      const selected = currentNodes.find((node) => node.label === activeParts[depth]);
      if (!selected || !selected.children?.length) break;
      const selectedChild = activeParts[depth + 1] || "";
      const row = document.createElement("div");
      row.className = "category-button-row category-button-row--child";
      for (const child of selected.children) {
        row.appendChild(createCategoryButton(child, selectedChild === child.label, () => {
          activeCategoryPath = child.path || child.label || "";
          resetVisibleAssetResults();
          renderCategoryButtons();
          renderAssets();
        }));
      }
      els.assetCategoryChildren.appendChild(row);
      currentNodes = selected.children;
    }
  }

  function renderAssetThumb(thumb, target) {
    thumb.textContent = "";
    thumb.classList.remove("is-generated");
    if (target.icon_path) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.decoding = "async";
      img.draggable = false;
      img.alt = "";
      img.src = iconUrl(target.icon_path);
      thumb.appendChild(img);
      return;
    }
    if (target.web_preview_path) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.decoding = "async";
      img.draggable = false;
      img.alt = "";
      img.src = siteAssetUrl(target.web_preview_path);
      thumb.appendChild(img);
      return;
    }
    thumb.classList.add("is-generated");
    thumb.textContent = kindLabel(target.asset_kind);
  }

  function wireFavoriteButton(button, target) {
    const isFavorite = favoriteTargetIds.has(target.target_id);
    button.classList.toggle("is-favorite", isFavorite);
    button.innerHTML = isFavorite ? "&#9733;" : "&#9734;";
    button.title = isFavorite ? "Unfavorite" : "Favorite";
    button.setAttribute("aria-label", `${isFavorite ? "Unfavorite" : "Favorite"} ${target.display_name}`);
    button.addEventListener("pointerdown", (event) => event.stopPropagation());
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggleFavorite(target.target_id);
    });
  }

  function loadFavorites() {
    try {
      const ids = JSON.parse(window.localStorage.getItem(FAVORITES_STORAGE_KEY) || "[]");
      favoriteTargetIds = new Set(Array.isArray(ids) ? ids.filter((id) => typeof id === "string") : []);
    } catch {
      favoriteTargetIds = new Set();
    }
  }

  function saveFavorites() {
    window.localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(Array.from(favoriteTargetIds)));
  }

  function pruneFavorites() {
    favoriteTargetIds = new Set(Array.from(favoriteTargetIds).filter((id) => targetLookup.byId.has(id)));
    saveFavorites();
  }

  function toggleFavorite(targetId) {
    if (!targetLookup.byId.has(targetId)) return;
    if (favoriteTargetIds.has(targetId)) favoriteTargetIds.delete(targetId);
    else favoriteTargetIds.add(targetId);
    saveFavorites();
    renderAssets();
  }

  function openAssetContextMenu(event, target) {
    event.preventDefault();
    event.stopPropagation();
    closeAssetContextMenu();
    const menu = document.createElement("div");
    menu.className = "asset-context-menu";
    menu.setAttribute("role", "menu");
    const action = document.createElement("button");
    action.type = "button";
    action.setAttribute("role", "menuitem");
    action.textContent = favoriteTargetIds.has(target.target_id) ? "Unfavorite" : "Favorite";
    action.addEventListener("click", () => {
      toggleFavorite(target.target_id);
      closeAssetContextMenu();
    });
    menu.appendChild(action);
    document.body.appendChild(menu);
    const x = Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8);
    const y = Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8);
    menu.style.left = `${Math.max(8, x)}px`;
    menu.style.top = `${Math.max(8, y)}px`;
    window.addEventListener("click", closeAssetContextMenu, { once: true });
  }

  function closeAssetContextMenu() {
    document.querySelectorAll(".asset-context-menu").forEach((menu) => menu.remove());
  }

  function startAssetPointer(event, target) {
    if (event.button !== undefined && event.button !== 0) return;
    event.preventDefault();
    dragCandidate = {
      target,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
    };
    window.addEventListener("pointermove", onAssetPointerMove);
    window.addEventListener("pointerup", onAssetPointerUp);
    window.addEventListener("pointercancel", onAssetPointerCancel);
  }

  function onAssetPointerMove(event) {
    if (dragSession) {
      updateDragPlacement(event);
      return;
    }
    if (!dragCandidate || event.pointerId !== dragCandidate.pointerId) return;
    const dx = event.clientX - dragCandidate.startX;
    const dy = event.clientY - dragCandidate.startY;
    if (Math.hypot(dx, dy) < DRAG_START_DISTANCE_PX) return;
    beginDragPlacement(dragCandidate.target, event);
  }

  async function onAssetPointerUp(event) {
    if (dragSession && event.pointerId === dragSession.pointerId) {
      const session = dragSession;
      const state = session.state ? { ...session.state } : null;
      const canDrop = Boolean(session.canDrop && state);
      endDragPlacement();
      if (canDrop) {
        pushUndoSnapshot();
        setLoading(true);
        try {
          await commitDragSessionPlacement(session, state);
        } catch (error) {
          console.error(error);
          els.assetStatus.textContent = `Load failed: ${error.message}`;
        } finally {
          setLoading(false);
        }
      }
      return;
    }
    clearDragCandidate();
  }

  function onAssetPointerCancel() {
    if (dragSession) {
      endDragPlacement();
    } else {
      clearDragCandidate();
    }
  }

  function beginDragPlacement(target, event) {
    const pointerId = dragCandidate?.pointerId ?? event.pointerId;
    dragCandidate = null;
    clearActiveGizmo();
    selectedTargetId = target.target_id;
    renderAssets();
    const token = Symbol("drag");
    dragSession = {
      token,
      pointerId,
      target,
      ghost: null,
      state: null,
      baseState: null,
      yawOffset: 0,
      zOffset: 0,
      rotateStepIndex: 0,
      templateState: null,
      metadata: {},
      sourcePlacementId: "",
      moveExisting: false,
      clickToPlace: false,
      canDrop: false,
      snapped: false,
    };
    document.body.classList.add("is-dragging-asset");
    els.stage.classList.add("is-drag-target");
    disablePreviewZoom();
    renderControlsHud();
    window.addEventListener("wheel", onPreviewWheel, { passive: false });
    updateDragPlacement(event);
    buildDragGhost(target, token);
  }

  function beginSmartDuplicatePlacement() {
    const placement = selectedPlacement();
    if (!placement || dragSession) return false;
    clearActiveGizmo();
    const metadata = { ...placement.metadata };
    delete metadata.piece_id;
    const token = Symbol("smart-duplicate");
    dragSession = {
      token,
      pointerId: null,
      target: placement.target,
      ghost: null,
      state: { ...placement.state },
      baseState: { ...placement.state },
      yawOffset: normalizeYaw(placement.state.yaw || 0),
      zOffset: 0,
      rotateStepIndex: 0,
      templateState: { ...placement.state },
      metadata,
      sourcePlacementId: "",
      moveExisting: false,
      clickToPlace: true,
      canDrop: true,
      snapped: false,
    };
    selectedTargetId = placement.target.target_id;
    renderAssets();
    document.body.classList.add("is-dragging-asset");
    els.stage.classList.add("is-drag-target", "is-drop-ready");
    disablePreviewZoom();
    renderPreviewRotationStatus("Move preview, wheel rotates, R changes step, left click places");
    renderControlsHud();
    buildDragGhost(placement.target, token);
    window.addEventListener("pointermove", onClickPreviewPointerMove);
    window.addEventListener("wheel", onPreviewWheel, { passive: false });
    return true;
  }

  function beginMovePreviewPlacement(placement, event) {
    if (!placement || dragSession) return false;
    clearActiveGizmo();
    const pointerId = event.pointerId;
    const token = Symbol("move-preview");
    dragSession = {
      token,
      pointerId,
      target: placement.target,
      ghost: null,
      state: { ...placement.state },
      baseState: { ...placement.state },
      yawOffset: normalizeYaw(placement.state.yaw || 0),
      zOffset: 0,
      rotateStepIndex: 0,
      templateState: { ...placement.state },
      metadata: { ...placement.metadata },
      sourcePlacementId: placement.id,
      moveExisting: true,
      clickToPlace: false,
      canDrop: true,
      snapped: false,
    };
    setVisualVisible(placement, false);
    const helper = selectionBoxes.get(placement.id);
    if (helper) helper.visible = false;
    selectedTargetId = placement.target.target_id;
    renderAssets();
    document.body.classList.add("is-dragging-asset");
    els.stage.classList.add("is-drag-target", "is-drop-ready");
    disablePreviewZoom();
    renderControlsHud();
    window.addEventListener("wheel", onPreviewWheel, { passive: false });
    window.addEventListener("pointermove", onAssetPointerMove);
    window.addEventListener("pointerup", onAssetPointerUp);
    window.addEventListener("pointercancel", onAssetPointerCancel);
    updateDragPlacement(event);
    buildDragGhost(placement.target, token);
    renderPreviewRotationStatus("Move preview, wheel rotates, release places");
    return true;
  }

  function onClickPreviewPointerMove(event) {
    if (!dragSession?.clickToPlace) return;
    updateDragPlacement(event);
  }

  async function buildDragGhost(target, token) {
    try {
      const ghost = await buildVisualGroup(target);
      if (!dragSession || dragSession.token !== token) return;
      prepareGhostObject(ghost);
      scene.add(ghost);
      dragSession.ghost = ghost;
      if (dragSession.state) {
        updateDragPreviewFromBaseState();
      }
    } catch (error) {
      console.error(error);
      if (dragSession && dragSession.token === token) {
        els.assetStatus.textContent = `Preview failed: ${error.message}`;
      }
    }
  }

  function prepareGhostObject(ghost) {
    ghost.userData.dragGhost = true;
    ghost.traverse((obj) => {
      obj.userData.dragGhost = true;
      if (!obj.isMesh && !obj.isSkinnedMesh) return;
      const isMaterialArray = Array.isArray(obj.material);
      const materials = isMaterialArray ? obj.material : [obj.material];
      const clones = materials.filter(Boolean).map((material) => {
        const clone = material.clone();
        clone.transparent = true;
        clone.opacity = 0.48;
        clone.depthWrite = false;
        if (clone.emissive) clone.emissive.set(0x000000);
        if (clone.emissiveIntensity !== undefined) clone.emissiveIntensity = 0;
        return clone;
      });
      obj.material = isMaterialArray ? clones : (clones[0] || obj.material);
    });
  }

  function updateDragPlacement(event) {
    if (!dragSession) return;
    const baseState = stateFromStagePointer(event);
    dragSession.canDrop = Boolean(baseState);
    els.stage.classList.toggle("is-drop-ready", dragSession.canDrop);
    if (!baseState) {
      if (dragSession.ghost) dragSession.ghost.visible = false;
      return;
    }
    const resolved = resolveDragPreviewState(baseState);
    dragSession.baseState = baseState;
    dragSession.state = resolved.state;
    dragSession.snapped = resolved.snapped;
    if (dragSession.ghost) {
      dragSession.ghost.visible = true;
      updateObjectFromState(dragSession.ghost, dragSession.state, viewOffset);
      setGhostSnapVisual(dragSession.ghost, dragSession.snapped);
    }
  }

  function stateFromStagePointer(event) {
    const point = stagePointFromEvent(event);
    if (!point) return null;
    const pos = threeVectorToUe(point, viewOffset);
    const template = dragSession?.templateState || {};
    return {
      x: pos.x,
      y: pos.y,
      z: pos.z,
      pitch: Number(template.pitch || 0),
      yaw: normalizeYaw(dragSession?.yawOffset || 0),
      roll: Number(template.roll || 0),
      scale_x: Number(template.scale_x || 1),
      scale_y: Number(template.scale_y || 1),
      scale_z: Number(template.scale_z || 1),
    };
  }

  function rotateDragPreviewBy(direction) {
    if (!dragSession) return false;
    const step = currentDragRotateStep();
    dragSession.yawOffset = normalizeYaw((Number(dragSession.yawOffset) || 0) + step * direction);
    updateDragPreviewFromBaseState();
    renderPreviewRotationStatus();
    return true;
  }

  function moveDragPreviewZBy(direction) {
    if (!dragSession) return false;
    dragSession.zOffset = roundValue((Number(dragSession.zOffset) || 0) + PREVIEW_Z_STEP * direction);
    updateDragPreviewFromBaseState();
    renderPreviewRotationStatus();
    return true;
  }

  function flipDragPreviewYaw() {
    if (!dragSession) return false;
    dragSession.yawOffset = normalizeYaw((Number(dragSession.yawOffset) || 0) + 180);
    updateDragPreviewFromBaseState();
    renderPreviewRotationStatus("Preview flipped");
    showViewportNotice("Flipped 180");
    return true;
  }

  function updateDragPreviewFromBaseState() {
    if (!dragSession?.baseState) return;
    const resolved = resolveDragPreviewState(dragSession.baseState);
    dragSession.state = resolved.state;
    dragSession.snapped = resolved.snapped;
    if (dragSession.ghost) {
      updateObjectFromState(dragSession.ghost, dragSession.state, viewOffset);
      setGhostSnapVisual(dragSession.ghost, dragSession.snapped);
    }
  }

  function resolveDragPreviewState(baseState) {
    const state = {
      ...baseState,
      yaw: normalizeYaw(dragSession?.yawOffset || baseState.yaw || 0),
    };
    const snapped = snapStateForTarget(dragSession.target, state, dragSession.sourcePlacementId || "");
    const surfaceAligned = alignDragStateVisualBottomToSurface(snapped.state);
    return {
      state: {
        ...surfaceAligned,
        z: roundValue((Number(surfaceAligned.z) || 0) + (Number(dragSession.zOffset) || 0)),
      },
      snapped: snapped.snapped,
    };
  }

  function alignDragStateVisualBottomToSurface(state) {
    if (!shouldAlignDragVisualBottom() || !dragSession?.ghost) return state;
    const bottomOffset = dragVisualBottomOffsetCm(state);
    if (!Number.isFinite(bottomOffset) || Math.abs(bottomOffset) < 0.001) return state;
    return {
      ...state,
      z: roundValue((Number(state.z) || 0) + bottomOffset),
    };
  }

  function shouldAlignDragVisualBottom() {
    return dragSession?.target?.asset_kind === "bp" || dragSession?.target?.asset_kind === "item";
  }

  function dragVisualBottomOffsetCm(state) {
    const ghost = dragSession?.ghost;
    if (!ghost) return 0;
    updateObjectFromState(ghost, state, viewOffset);
    ghost.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(ghost);
    if (box.isEmpty()) return 0;
    return (ghost.position.y - box.min.y) / UNIT_SCALE;
  }

  function cycleDragRotateStep() {
    if (!dragSession) return false;
    dragSession.rotateStepIndex = ((Number(dragSession.rotateStepIndex) || 0) + 1) % DRAG_ROTATE_STEPS_DEGREES.length;
    renderPreviewRotationStatus("Wheel rotates preview");
    return true;
  }

  function currentDragRotateStep() {
    return DRAG_ROTATE_STEPS_DEGREES[dragSession?.rotateStepIndex || 0] || DRAG_ROTATE_STEPS_DEGREES[0];
  }

  function renderPreviewRotationStatus(prefix = "") {
    if (!dragSession) return;
    const step = currentDragRotateStep();
    const details = `step ${step} deg, yaw ${roundValue(dragSession.yawOffset || 0)} deg, Z ${roundValue(dragSession.zOffset || 0)}`;
    els.assetStatus.textContent = prefix ? `${prefix} (${details})` : `Preview ${details}`;
  }

  function onPreviewWheel(event) {
    if (!dragSession) return;
    event.preventDefault();
    event.stopPropagation();
    const direction = event.deltaY < 0 ? 1 : -1;
    if (event.ctrlKey || event.metaKey) {
      moveDragPreviewZBy(direction);
    } else {
      rotateDragPreviewBy(direction);
    }
  }

  function onStageWheel(event) {
    if (dragSession) {
      onPreviewWheel(event);
    }
  }

  function normalizeYaw(value) {
    return ((Number(value) % 360) + 360) % 360;
  }

  function stagePointFromEvent(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    if (
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom
    ) {
      return null;
    }
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const surfacePoint = placementSurfacePointFromRay();
    if (surfacePoint) return surfacePoint;
    const point = new THREE.Vector3();
    return raycaster.ray.intersectPlane(dragPlane, point) ? point : null;
  }

  function placementSurfacePointFromRay() {
    const excludedIds = new Set();
    if (dragSession?.sourcePlacementId) excludedIds.add(dragSession.sourcePlacementId);
    const candidates = raycastPlacementCandidates(raycaster.ray, { radius: SPATIAL_SURFACE_RADIUS_CM, excludeIds: excludedIds });
    const roots = candidates
      .map((placement) => getVisualRoot(placement))
      .filter(Boolean);
    if (roots.length) {
      const hits = raycaster.intersectObjects(roots, true);
      const hit = hits.find((row) => {
        const id = row.object.userData.placedId;
        return id && !excludedIds.has(id) && !row.object.userData.dragGhost && objectTreeVisible(row.object);
      });
      if (hit?.point) return hit.point.clone();
    }
    return placementSurfacePointFromBounds(candidates, excludedIds);
  }

  function placementSurfacePointFromBounds(candidates, excludedIds) {
    let best = null;
    const point = new THREE.Vector3();
    for (const placement of candidates) {
      if (excludedIds.has(placement.id)) continue;
      if (!placementPickable(placement)) continue;
      const box = getWorldBounds(placement);
      if (!box || box.isEmpty()) continue;
      const hit = raycaster.ray.intersectBox(box, point);
      if (!hit) continue;
      const distance = raycaster.ray.origin.distanceToSquared(hit);
      if (!best || distance < best.distance) best = { distance, point: hit.clone() };
    }
    return best?.point || null;
  }

  function objectTreeVisible(object) {
    for (let node = object; node; node = node.parent) {
      if (!node.visible) return false;
    }
    return true;
  }

  function setGhostSnapVisual(ghost, snapped) {
    ghost.traverse((obj) => {
      if (!obj.material) return;
      const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
      for (const material of materials) {
        if (material.emissive) material.emissive.set(snapped ? 0xe0c896 : 0x000000);
        if (material.emissiveIntensity !== undefined) material.emissiveIntensity = snapped ? 0.55 : 0;
      }
    });
  }

  function endDragPlacement() {
    if (dragSession?.moveExisting && dragSession.sourcePlacementId) {
      const placement = placements.get(dragSession.sourcePlacementId);
      if (placement) setVisualVisible(placement, true);
      const helper = selectionBoxes.get(dragSession.sourcePlacementId);
      if (helper) helper.visible = true;
    }
    if (dragSession?.ghost) {
      scene.remove(dragSession.ghost);
    }
    dragSession = null;
    dragCandidate = null;
    document.body.classList.remove("is-dragging-asset");
    els.stage.classList.remove("is-drag-target", "is-drop-ready");
    clearDragListeners();
    window.removeEventListener("pointermove", onClickPreviewPointerMove);
    window.removeEventListener("wheel", onPreviewWheel);
    restorePreviewZoom();
    renderControlsHud();
    if (index) renderAssets();
  }

  function disablePreviewZoom() {
    if (!controls || previewPreviousEnableZoom !== null) return;
    previewPreviousEnableZoom = controls.enableZoom;
    controls.enableZoom = false;
  }

  function restorePreviewZoom() {
    if (!controls || previewPreviousEnableZoom === null) return;
    controls.enableZoom = previewPreviousEnableZoom;
    previewPreviousEnableZoom = null;
  }

  function clearDragCandidate() {
    dragCandidate = null;
    clearDragListeners();
  }

  function clearDragListeners() {
    window.removeEventListener("pointermove", onAssetPointerMove);
    window.removeEventListener("pointerup", onAssetPointerUp);
    window.removeEventListener("pointercancel", onAssetPointerCancel);
  }

  async function commitClickPreviewPlacement(event) {
    if (!dragSession?.clickToPlace || event.button !== 0) return false;
    updateDragPlacement(event);
    const session = dragSession;
    const state = session.state ? { ...session.state } : null;
    const canDrop = Boolean(session.canDrop && state);
    endDragPlacement();
    if (!canDrop) return true;
    pushUndoSnapshot();
    setLoading(true);
    try {
      await commitDragSessionPlacement(session, state);
    } catch (error) {
      console.error(error);
      els.assetStatus.textContent = `Load failed: ${error.message}`;
    } finally {
      setLoading(false);
    }
    return true;
  }

  async function commitDragSessionPlacement(session, state) {
    if (session.moveExisting && session.sourcePlacementId) {
      const placement = placements.get(session.sourcePlacementId);
      if (!placement) return null;
      placement.state = normalizeTransform(state);
      setVisualVisible(placement, true);
      applyPlacementTransform(placement);
      selectPlacement(placement.id);
      scheduleGroundGridUpdate();
      return placement;
    }
    return createPlacement(session.target, state, session.metadata || {});
  }

  function ensurePlacementVisualState(placement) {
    if (!placement.visual) {
      placement.visual = {
        backend: "",
        root: placement.group || null,
        batchKey: "",
        instanceSlot: -1,
        localBounds: null,
        visible: true,
        worldBounds: new THREE.Box3(),
        screenBounds: null,
        worldBoundsDirty: true,
        screenBoundsRevision: -1,
      };
    }
    return placement.visual;
  }

  function getVisualRoot(placement) {
    const visual = ensurePlacementVisualState(placement);
    return visual.backend === "real" ? visual.root : null;
  }

  function attachRootUserData(root, placementId) {
    root.userData.placedId = placementId;
    root.traverse((child) => {
      child.userData.placedId = placementId;
    });
  }

  function createRealVisualFromResolvedTemplate(placement) {
    const root = cloneResolvedVisualGroup(placement.target);
    if (!root) return null;
    attachRootUserData(root, placement.id);
    rootGroup.add(root);
    placement.group = root;
    const visual = ensurePlacementVisualState(placement);
    visual.backend = "real";
    visual.root = root;
    visual.batchKey = "";
    visual.instanceSlot = -1;
    visual.visible = true;
    visual.localBounds = null;
    markPlacementBoundsDirty(placement);
    if (instancingEligibleForPlacement(placement)) promotedPlacementIds.add(placement.id);
    syncInstanceStatsDataset();
    return root;
  }

  async function createVisual(placement, { preferReal = false } = {}) {
    await visualTemplateForTarget(placement.target);
    if (!preferReal && addPlacementToInstanceBatch(placement)) return null;
    const root = createRealVisualFromResolvedTemplate(placement);
    if (!root) throw new Error(`Unable to create visual for ${placement.target.display_name || placement.target.target_id}`);
    return root;
  }

  function promotePlacementVisual(placement) {
    const visual = ensurePlacementVisualState(placement);
    if (visual.backend === "real") return true;
    if (visual.backend === "instanced") removePlacementFromInstanceBatch(placement);
    const root = createRealVisualFromResolvedTemplate(placement);
    if (!root) return false;
    setVisualTransform(placement);
    promotedPlacementIds.add(placement.id);
    return true;
  }

  function demotePlacementVisual(placement, { force = false } = {}) {
    if (!placement || (selectedPlacedIds.has(placement.id) && !force)) return false;
    const visual = ensurePlacementVisualState(placement);
    if (visual.backend !== "real" || !instancingEligibleForPlacement(placement)) return false;
    const root = visual.root;
    if (root) rootGroup.remove(root);
    visual.root = null;
    placement.group = null;
    const added = addPlacementToInstanceBatch(placement);
    if (!added && root) {
      rootGroup.add(root);
      visual.backend = "real";
      visual.root = root;
      placement.group = root;
      return false;
    }
    promotedPlacementIds.delete(placement.id);
    syncInstanceStatsDataset();
    markPlacementBoundsDirty(placement);
    updatePlacementSpatialIndex(placement);
    return true;
  }

  function syncVisualBackendsForSelection() {
    const promoteSelection = selectedPlacedIds.size <= SELECTION_PROMOTION_LIMIT;
    for (const id of Array.from(promotedPlacementIds)) {
      if (!selectedPlacedIds.has(id) || !promoteSelection) demotePlacementVisual(placements.get(id), { force: !promoteSelection });
    }
    if (!promoteSelection) {
      syncInstanceStatsDataset();
      return;
    }
    for (const placement of selectedPlacements()) promotePlacementVisual(placement);
  }

  function disposeVisual(placement) {
    removePlacementFromSpatialIndex(placement.id);
    const visual = ensurePlacementVisualState(placement);
    if (visual.backend === "instanced") {
      removePlacementFromInstanceBatch(placement);
    } else {
      const root = getVisualRoot(placement);
      if (root) rootGroup.remove(root);
    }
    visual.root = null;
    visual.backend = "";
    placement.group = null;
    promotedPlacementIds.delete(placement.id);
  }

  function setVisualTransform(placement, { updateIndex = true } = {}) {
    const visual = ensurePlacementVisualState(placement);
    if (visual.backend === "instanced") {
      updateInstancePlacementTransform(placement);
      markPlacementBoundsDirty(placement);
      if (updateIndex) updatePlacementSpatialIndex(placement);
      return;
    }
    const root = getVisualRoot(placement);
    if (!root) return;
    updateObjectFromState(root, placement.state, viewOffset);
    root.updateMatrixWorld(true);
    root.visible = placementVisualRenderable(placement);
    markPlacementBoundsDirty(placement);
    if (updateIndex) updatePlacementSpatialIndex(placement);
  }

  function setVisualVisible(placement, visible) {
    const visual = ensurePlacementVisualState(placement);
    visual.visible = visible;
    if (visual.backend === "instanced") {
      updateInstancePlacementTransform(placement);
      return;
    }
    const root = getVisualRoot(placement);
    if (root) root.visible = placementVisualRenderable(placement);
  }

  function placementVisualRenderable(placement) {
    const visual = ensurePlacementVisualState(placement);
    return visual.visible !== false && !placement.hidden;
  }

  function placementPickable(placement) {
    const visual = ensurePlacementVisualState(placement);
    return visual.visible !== false && !placement.hidden;
  }

  function applyPlacementRenderVisibility(placement) {
    const visual = ensurePlacementVisualState(placement);
    if (visual.backend === "instanced") {
      updateInstancePlacementTransform(placement);
      return;
    }
    const root = getVisualRoot(placement);
    if (root) root.visible = placementVisualRenderable(placement);
  }

  function setPlacementHidden(placement, hidden) {
    if (!placement) return;
    placement.hidden = Boolean(hidden);
    applyPlacementRenderVisibility(placement);
    syncSelectionBoxes();
  }

  function markPlacementBoundsDirty(placement) {
    if (!placement) return;
    const visual = ensurePlacementVisualState(placement);
    visual.worldBoundsDirty = true;
    visual.screenBoundsRevision = -1;
  }

  function invalidateAllScreenBounds() {
    screenBoundsRevision += 1;
  }

  function getWorldBounds(placement) {
    const visual = ensurePlacementVisualState(placement);
    if (visual.worldBoundsDirty) {
      if (visual.backend === "instanced" && visual.localBounds) {
        visual.worldBounds.copy(visual.localBounds).applyMatrix4(placementRootMatrix(placement));
      } else {
        const root = getVisualRoot(placement);
        if (!root) return visual.worldBounds.makeEmpty();
        root.updateMatrixWorld(true);
        visual.worldBounds.setFromObject(root);
      }
      visual.worldBoundsDirty = false;
    }
    return visual.worldBounds;
  }

  function getScreenBounds(placement) {
    const visual = ensurePlacementVisualState(placement);
    if (visual.screenBoundsRevision === screenBoundsRevision) return visual.screenBounds;
    const box = getWorldBounds(placement);
    visual.screenBounds = worldBoxScreenBounds(box);
    visual.screenBoundsRevision = screenBoundsRevision;
    return visual.screenBounds;
  }

  function worldBoxScreenBounds(box) {
    if (!box || box.isEmpty()) return null;
    const stageRect = renderer.domElement.getBoundingClientRect();
    let left = Infinity;
    let right = -Infinity;
    let top = Infinity;
    let bottom = -Infinity;
    for (const point of boxCorners(box)) {
      point.project(camera);
      if (point.z < -1 || point.z > 1) continue;
      const x = stageRect.left + ((point.x + 1) / 2) * stageRect.width;
      const y = stageRect.top + ((-point.y + 1) / 2) * stageRect.height;
      left = Math.min(left, x);
      right = Math.max(right, x);
      top = Math.min(top, y);
      bottom = Math.max(bottom, y);
    }
    return Number.isFinite(left) ? { left, right, top, bottom } : null;
  }

  function spatialCell(value) {
    return Math.floor(Number(value || 0) / SPATIAL_CELL_SIZE_CM);
  }

  function spatialKey(cx, cy) {
    return `${cx},${cy}`;
  }

  function placementSpatialBounds(placement) {
    const box = getWorldBounds(placement);
    if (!box || box.isEmpty()) {
      const state = placement.state || {};
      const x = Number(state.x || 0);
      const y = Number(state.y || 0);
      return { minX: x, maxX: x, minY: y, maxY: y };
    }
    return {
      minX: (box.min.x / UNIT_SCALE) + viewOffset.x,
      maxX: (box.max.x / UNIT_SCALE) + viewOffset.x,
      minY: (box.min.z / UNIT_SCALE) + viewOffset.y,
      maxY: (box.max.z / UNIT_SCALE) + viewOffset.y,
    };
  }

  function cellsForSpatialBounds(bounds) {
    const cells = [];
    const minCx = spatialCell(Math.min(bounds.minX, bounds.maxX));
    const maxCx = spatialCell(Math.max(bounds.minX, bounds.maxX));
    const minCy = spatialCell(Math.min(bounds.minY, bounds.maxY));
    const maxCy = spatialCell(Math.max(bounds.minY, bounds.maxY));
    for (let cx = minCx; cx <= maxCx; cx += 1) {
      for (let cy = minCy; cy <= maxCy; cy += 1) {
        cells.push(spatialKey(cx, cy));
      }
    }
    return cells;
  }

  function insertPlacementInSpatialIndex(placement) {
    if (!placement || !placements.has(placement.id)) return;
    const cells = cellsForSpatialBounds(placementSpatialBounds(placement));
    spatialIndex.placementCells.set(placement.id, cells);
    for (const key of cells) {
      if (!spatialIndex.cells.has(key)) spatialIndex.cells.set(key, new Set());
      spatialIndex.cells.get(key).add(placement.id);
    }
  }

  function removePlacementFromSpatialIndex(id) {
    const cells = spatialIndex.placementCells.get(id);
    if (!cells) return;
    for (const key of cells) {
      const bucket = spatialIndex.cells.get(key);
      if (!bucket) continue;
      bucket.delete(id);
      if (!bucket.size) spatialIndex.cells.delete(key);
    }
    spatialIndex.placementCells.delete(id);
  }

  function updatePlacementSpatialIndex(placement) {
    removePlacementFromSpatialIndex(placement.id);
    insertPlacementInSpatialIndex(placement);
  }

  function rebuildSpatialIndex() {
    spatialIndex.cells.clear();
    spatialIndex.placementCells.clear();
    for (const placement of placements.values()) insertPlacementInSpatialIndex(placement);
  }

  function spatialCandidateIdsForBounds(bounds) {
    const ids = new Set();
    for (const key of cellsForSpatialBounds(bounds)) {
      const bucket = spatialIndex.cells.get(key);
      if (!bucket) continue;
      for (const id of bucket) ids.add(id);
    }
    return ids;
  }

  function queryBounds(bounds) {
    return Array.from(spatialCandidateIdsForBounds(bounds))
      .map((id) => placements.get(id))
      .filter(Boolean);
  }

  function queryPointRadius(point, radius) {
    const x = Number(point.x || 0);
    const y = Number(point.y || 0);
    return queryBounds({
      minX: x - radius,
      maxX: x + radius,
      minY: y - radius,
      maxY: y + radius,
    });
  }

  function querySegmentRadius(start, end, radius) {
    if (!start || !end) return [];
    const dx = Number(end.x || 0) - Number(start.x || 0);
    const dy = Number(end.y || 0) - Number(start.y || 0);
    const length = Math.hypot(dx, dy);
    const stepSize = Math.max(SPATIAL_CELL_SIZE_CM * 0.75, 1);
    const steps = Math.max(1, Math.ceil(length / stepSize));
    const ids = new Set();
    for (let i = 0; i <= steps; i += 1) {
      const t = i / steps;
      const x = Number(start.x || 0) + dx * t;
      const y = Number(start.y || 0) + dy * t;
      for (const id of spatialCandidateIdsForBounds({
        minX: x - radius,
        maxX: x + radius,
        minY: y - radius,
        maxY: y + radius,
      })) {
        ids.add(id);
      }
    }
    return Array.from(ids)
      .map((id) => placements.get(id))
      .filter(Boolean);
  }

  function uePointFromThreePoint(point) {
    const ue = threeVectorToUe(point, viewOffset);
    return { x: ue.x, y: ue.y };
  }

  function placementQueryCandidatesFromRay(ray, radius = SPATIAL_PICK_RADIUS_CM) {
    const groundPoint = new THREE.Vector3();
    if (!ray.intersectPlane(dragPlane, groundPoint)) return Array.from(placements.values());
    if (!spatialIndex.placementCells.size && placements.size) return Array.from(placements.values());
    const candidates = queryPointRadius(uePointFromThreePoint(groundPoint), radius);
    return candidates;
  }

  function placementPickCandidatesFromRay(ray, radius = SPATIAL_PICK_RADIUS_CM) {
    if (!spatialIndex.placementCells.size && placements.size) return Array.from(placements.values());
    const groundPoint = new THREE.Vector3();
    if (!ray.intersectPlane(dragPlane, groundPoint)) return placementQueryCandidatesFromRay(ray, radius);
    const candidates = querySegmentRadius(uePointFromThreePoint(ray.origin), uePointFromThreePoint(groundPoint), radius);
    return candidates.length ? candidates : placementQueryCandidatesFromRay(ray, radius);
  }

  function raycastPlacementCandidates(ray, { radius = SPATIAL_PICK_RADIUS_CM, excludeIds = new Set(), useRayPath = false } = {}) {
    const source = useRayPath
      ? placementPickCandidatesFromRay(ray, radius)
      : placementQueryCandidatesFromRay(ray, radius);
    return source
      .filter((placement) => !excludeIds.has(placement.id) && placementPickable(placement));
  }

  function clientPointOnDragPlane(x, y, localRaycaster = new THREE.Raycaster()) {
    const rect = els.stage.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const point = new THREE.Vector2(
      ((x - rect.left) / rect.width) * 2 - 1,
      -((y - rect.top) / rect.height) * 2 + 1,
    );
    localRaycaster.setFromCamera(point, camera);
    const hit = new THREE.Vector3();
    return localRaycaster.ray.intersectPlane(dragPlane, hit) ? uePointFromThreePoint(hit) : null;
  }

  function marqueePlacementCandidates(rect) {
    if (!spatialIndex.placementCells.size && placements.size) return Array.from(placements.values());
    const localRaycaster = new THREE.Raycaster();
    const points = [
      clientPointOnDragPlane(rect.left, rect.top, localRaycaster),
      clientPointOnDragPlane(rect.right, rect.top, localRaycaster),
      clientPointOnDragPlane(rect.left, rect.bottom, localRaycaster),
      clientPointOnDragPlane(rect.right, rect.bottom, localRaycaster),
    ].filter(Boolean);
    if (points.length < 2) return Array.from(placements.values());
    const minX = Math.min(...points.map((point) => point.x));
    const maxX = Math.max(...points.map((point) => point.x));
    const minY = Math.min(...points.map((point) => point.y));
    const maxY = Math.max(...points.map((point) => point.y));
    const padding = marqueeSpatialPaddingCm();
    return queryBounds({
      minX: minX - padding,
      maxX: maxX + padding,
      minY: minY - padding,
      maxY: maxY + padding,
    });
  }

  async function createPlacement(target, transform, metadata = {}, options = {}) {
    const id = options.id || `obj_${nextObjectId++}`;
    const placement = {
      id,
      target,
      state: normalizeTransform(transform),
      metadata: { ...metadata },
      hidden: Boolean(options.hidden),
      group: null,
      visual: null,
    };
    placements.set(id, placement);
    await createVisual(placement, { preferReal: options.preferReal === true || options.select !== false });
    if (target.asset_kind === "building_piece") {
      const pid = Number(placement.metadata.piece_id || 0);
      if (pid >= nextPieceId) nextPieceId = pid + 1;
    }
    applyPlacementTransform(placement);
    if (!bulkMutationActive && options.updateGrid !== false) scheduleGroundGridUpdate();
    if (!activePlacementId) activePlacementId = id;
    const shouldRender = options.render !== false;
    if (options.select !== false) {
      selectPlacement(id, { render: shouldRender, activeId: id });
    } else if (shouldRender) {
      renderPlacedList();
      updateCounters();
    }
    return placement;
  }

  function applyPlacementTransform(placement) {
    setVisualTransform(placement);
  }

  function selectedPlacements() {
    return Array.from(selectedPlacedIds)
      .map((id) => placements.get(id))
      .filter(Boolean);
  }

  function selectedPlacement() {
    const selected = selectedPlacements();
    return selected.length === 1 ? selected[0] : null;
  }

  function activeSelectedPlacement() {
    const active = activePlacementId ? placements.get(activePlacementId) : null;
    if (active && selectedPlacedIds.has(active.id)) return active;
    return selectedPlacements()[0] || null;
  }

  function hasSelection(id) {
    return selectedPlacedIds.has(id);
  }

  function selectionModifierFromEvent(event) {
    if (event.ctrlKey || event.metaKey) return "subtract";
    if (event.shiftKey) return "add";
    return "replace";
  }

  function subtractSelection(id) {
    if (!selectedPlacedIds.has(id)) return;
    const next = new Set(selectedPlacedIds);
    next.delete(id);
    setSelection(next);
  }

  function selectPlacement(id, options = {}) {
    const next = new Set(selectedPlacedIds);
    let nextActiveId = options.activeId || id || activePlacementId;
    if (!id) {
      if (!options.additive) next.clear();
    } else if (options.toggle) {
      if (next.has(id)) {
        next.delete(id);
        if (nextActiveId === id) nextActiveId = "";
      } else {
        next.add(id);
        nextActiveId = id;
      }
    } else if (options.additive) {
      next.add(id);
      nextActiveId = id;
    } else {
      next.clear();
      next.add(id);
      nextActiveId = id;
    }
    setSelection(next, { render: options.render, activeId: nextActiveId });
  }

  function setSelection(ids, options = {}) {
    selectedPlacedIds = new Set(Array.from(ids || []).filter((id) => placements.has(id)));
    const requestedActive = options.activeId || activePlacementId;
    if (requestedActive && selectedPlacedIds.has(requestedActive)) {
      activePlacementId = requestedActive;
    } else {
      activePlacementId = selectedPlacedIds.values().next().value || "";
    }
    if (!selectedPlacedIds.size) activeGizmoMode = "";
    syncVisualBackendsForSelection();
    syncSelectionAttachment();
    syncSelectionHotkeys();
    if (options.render !== false) {
      renderInspector();
      renderPlacedList();
      updateCounters();
    }
  }

  function syncSelectionAttachment() {
    if (!transformControls) return;
    const selected = selectedPlacements();
    if (selected.length === 1) {
      transformControls.attach(getVisualRoot(selected[0]));
    } else if (selected.length > 1) {
      updateSelectionPivot();
      transformControls.attach(selectionPivot);
    } else {
      transformControls.detach();
    }
    syncTransformControlMode();
    syncSelectionBoxes();
  }

  function updateSelectionPivot() {
    const box = new THREE.Box3();
    for (const placement of selectedPlacements()) {
      box.union(getWorldBounds(placement));
    }
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    selectionPivot.position.copy(center);
    const active = activeSelectedPlacement();
    const yaw = orientationMode === "local" && active ? THREE.MathUtils.degToRad(active.state.yaw || 0) : 0;
    selectionPivot.rotation.set(0, yaw, 0);
    selectionPivot.scale.set(1, 1, 1);
    selectionPivot.userData.previousPosition.copy(center);
    selectionPivot.updateMatrixWorld(true);
    selectionPivot.userData.previousMatrix.copy(selectionPivot.matrixWorld);
  }

  function handleTransformObjectChange() {
    const selected = selectedPlacements();
    if (!selected.length) return;
    pendingTransformChanged = true;
    if (selected.length === 1) {
      const placement = selected[0];
      const root = getVisualRoot(placement);
      placement.state = updateStateFromObject(root, placement.state, viewOffset);
      markPlacementBoundsDirty(placement);
      updatePlacementSpatialIndex(placement);
    } else {
      selectionPivot.updateMatrixWorld(true);
      const previousMatrix = selectionPivot.userData.previousMatrix;
      const currentMatrix = selectionPivot.matrixWorld.clone();
      const deltaMatrix = currentMatrix.clone().multiply(previousMatrix.clone().invert());
      for (const placement of selected) {
        const root = getVisualRoot(placement);
        if (root) root.updateMatrixWorld(true);
        const currentWorldMatrix = root ? root.matrixWorld.clone() : placementRootMatrix(placement);
        const nextWorldMatrix = currentWorldMatrix.premultiply(deltaMatrix);
        if (root) {
          applyWorldMatrixToObject(root, nextWorldMatrix);
          placement.state = updateStateFromObject(root, placement.state, viewOffset);
        } else {
          placement.state = stateFromWorldMatrix(placement, nextWorldMatrix);
        }
        markPlacementBoundsDirty(placement);
        setVisualTransform(placement);
      }
      previousMatrix.copy(currentMatrix);
    }
    syncSelectionBoxes();
    renderInspector();
    renderPlacedList();
    updateCounters();
  }

  function applyWorldMatrixToObject(object, worldMatrix) {
    const localMatrix = worldMatrix.clone();
    if (object.parent) {
      object.parent.updateMatrixWorld(true);
      const parentInverse = object.parent.matrixWorld.clone().invert();
      localMatrix.premultiply(parentInverse);
    }
    localMatrix.decompose(object.position, object.quaternion, object.scale);
    object.updateMatrixWorld(true);
  }

  function stateFromWorldMatrix(placement, worldMatrix) {
    const object = new THREE.Object3D();
    worldMatrix.decompose(object.position, object.quaternion, object.scale);
    object.updateMatrixWorld(true);
    return updateStateFromObject(object, placement.state, viewOffset);
  }

  function syncSelectionBoxes() {
    for (const [id, helper] of selectionBoxes) {
      if (!selectedPlacedIds.has(id) || !placements.has(id)) {
        scene.remove(helper);
        helper.geometry?.dispose?.();
        helper.material?.dispose?.();
        selectionBoxes.delete(id);
      }
    }
    for (const placement of selectedPlacements()) {
      const visual = ensurePlacementVisualState(placement);
      const root = getVisualRoot(placement);
      const helperType = root ? "root" : "bounds";
      const bounds = root ? null : getWorldBounds(placement).clone();
      if (!root && (!bounds || bounds.isEmpty())) continue;
      const existing = selectionBoxes.get(placement.id);
      if (existing?.userData.selectionHelperType === helperType) continue;
      if (existing) {
        scene.remove(existing);
        existing.geometry?.dispose?.();
        existing.material?.dispose?.();
        selectionBoxes.delete(placement.id);
      }
      const helper = root
        ? new THREE.BoxHelper(root, 0xf3cf89)
        : new THREE.Box3Helper(bounds, 0xf3cf89);
      helper.name = `Selection Box ${placement.id}`;
      helper.material.depthTest = false;
      helper.material.transparent = true;
      helper.material.opacity = 0.96;
      helper.renderOrder = 999;
      helper.userData.selectionHelperType = helperType;
      helper.visible = placementPickable(placement);
      selectionBoxes.set(placement.id, helper);
      scene.add(helper);
    }
    updateSelectionBoxes();
  }

  function updateSelectionBoxes() {
    for (const [id, helper] of selectionBoxes) {
      const placement = placements.get(id);
      if (!placement) continue;
      const root = getVisualRoot(placement);
      if (root && helper.userData.selectionHelperType === "root") {
        helper.update();
      } else if (helper.userData.selectionHelperType === "bounds" && helper.box) {
        helper.box.copy(getWorldBounds(placement));
        helper.updateMatrixWorld(true);
      }
    }
  }

  function setDuplicateNudgeModifier(active) {
    if (duplicateNudgeModifierActive === active) return;
    duplicateNudgeModifierActive = active;
    updateOrientationNudgeOverlay();
  }

  function updateOrientationNudgeOverlay() {
    if (!orientationNudgeOverlay || !renderer || !camera) return;
    if (!duplicateNudgeModifierActive || dragSession || !selectedPlacedIds.size) {
      orientationNudgeOverlay.hidden = true;
      return;
    }
    const orientedBounds = selectedOrientationBounds();
    const localBounds = orientedBoundsStageBounds(orientedBounds);
    if (!orientedBounds || !localBounds) {
      orientationNudgeOverlay.hidden = true;
      return;
    }

    const stageRect = renderer.domElement.getBoundingClientRect();
    const center = {
      x: (localBounds.left + localBounds.right) / 2,
      y: (localBounds.top + localBounds.bottom) / 2,
    };
    const width = Math.max(24, localBounds.right - localBounds.left);
    const height = Math.max(24, localBounds.bottom - localBounds.top);
    const directions = nudgeScreenDirections(orientedBounds);
    for (const direction of SMART_NUDGE_DIRECTIONS) {
      const image = orientationNudgeArrows.get(direction.id);
      if (!image) continue;
      const vector = directions[direction.id] || fallbackScreenDirection(direction);
      const length = Math.hypot(vector.x, vector.y) || 1;
      const unit = { x: vector.x / length, y: vector.y / length };
      const edgeDistance = Math.abs(unit.x) * width / 2 + Math.abs(unit.y) * height / 2;
      const distance = edgeDistance + NUDGE_ARROW_MARGIN_PX;
      const x = clamp(center.x + unit.x * distance, 24, stageRect.width - 24);
      const y = clamp(center.y + unit.y * distance, 24, stageRect.height - 24);
      image.style.left = `${x}px`;
      image.style.top = `${y}px`;
    }
    if (orientationNudgeMode) {
      orientationNudgeMode.textContent = orientationMode === "local" ? "Local Nudge" : "World Nudge";
      orientationNudgeMode.style.left = `${clamp(center.x, 52, stageRect.width - 52)}px`;
      orientationNudgeMode.style.top = `${clamp(localBounds.top - 22, 18, stageRect.height - 18)}px`;
    }
    orientationNudgeOverlay.hidden = false;
  }

  function selectedScreenBounds() {
    const bounds = { left: Infinity, right: -Infinity, top: Infinity, bottom: -Infinity };
    for (const placement of selectedPlacements()) {
      const placementBounds = placementScreenBounds(placement);
      if (!placementBounds) continue;
      bounds.left = Math.min(bounds.left, placementBounds.left);
      bounds.right = Math.max(bounds.right, placementBounds.right);
      bounds.top = Math.min(bounds.top, placementBounds.top);
      bounds.bottom = Math.max(bounds.bottom, placementBounds.bottom);
    }
    return Number.isFinite(bounds.left) ? bounds : null;
  }

  function selectedOrientationBounds(basis = nudgeWorldBasisVectors()) {
    const bounds = {
      basis,
      minRight: Infinity,
      maxRight: -Infinity,
      minForward: Infinity,
      maxForward: -Infinity,
      minVertical: Infinity,
      maxVertical: -Infinity,
      hasPoint: false,
    };
    for (const placement of selectedPlacements()) {
      const root = getVisualRoot(placement);
      if (root) {
        root.updateMatrixWorld(true);
        expandOrientationBoundsByObject(bounds, root);
      } else {
        expandOrientationBoundsByBox(bounds, getWorldBounds(placement));
      }
    }
    if (!bounds.hasPoint) return null;
    bounds.width = bounds.maxRight - bounds.minRight;
    bounds.depth = bounds.maxForward - bounds.minForward;
    bounds.height = bounds.maxVertical - bounds.minVertical;
    bounds.center = basis.right.clone().multiplyScalar((bounds.minRight + bounds.maxRight) / 2)
      .add(basis.forward.clone().multiplyScalar((bounds.minForward + bounds.maxForward) / 2))
      .add(basis.vertical.clone().multiplyScalar((bounds.minVertical + bounds.maxVertical) / 2));
    return bounds;
  }

  function expandOrientationBoundsByObject(bounds, object) {
    let expanded = false;
    object.traverse((child) => {
      if ((!child.isMesh && !child.isSkinnedMesh) || !child.geometry) return;
      if (!child.geometry.boundingBox) child.geometry.computeBoundingBox();
      const box = child.geometry.boundingBox;
      if (!box || box.isEmpty()) return;
      for (const point of boxCorners(box)) {
        expandOrientationBoundsByPoint(bounds, point.applyMatrix4(child.matrixWorld));
        expanded = true;
      }
    });
    if (expanded) return;
    const fallbackBox = new THREE.Box3().setFromObject(object);
    if (fallbackBox.isEmpty()) return;
    for (const point of boxCorners(fallbackBox)) expandOrientationBoundsByPoint(bounds, point);
  }

  function expandOrientationBoundsByBox(bounds, box) {
    if (!box || box.isEmpty()) return;
    for (const point of boxCorners(box)) expandOrientationBoundsByPoint(bounds, point);
  }

  function expandOrientationBoundsByPoint(bounds, point) {
    const right = point.dot(bounds.basis.right);
    const forward = point.dot(bounds.basis.forward);
    const vertical = point.dot(bounds.basis.vertical);
    bounds.minRight = Math.min(bounds.minRight, right);
    bounds.maxRight = Math.max(bounds.maxRight, right);
    bounds.minForward = Math.min(bounds.minForward, forward);
    bounds.maxForward = Math.max(bounds.maxForward, forward);
    bounds.minVertical = Math.min(bounds.minVertical, vertical);
    bounds.maxVertical = Math.max(bounds.maxVertical, vertical);
    bounds.hasPoint = true;
  }

  function boxCorners(box) {
    return [
      new THREE.Vector3(box.min.x, box.min.y, box.min.z),
      new THREE.Vector3(box.min.x, box.min.y, box.max.z),
      new THREE.Vector3(box.min.x, box.max.y, box.min.z),
      new THREE.Vector3(box.min.x, box.max.y, box.max.z),
      new THREE.Vector3(box.max.x, box.min.y, box.min.z),
      new THREE.Vector3(box.max.x, box.min.y, box.max.z),
      new THREE.Vector3(box.max.x, box.max.y, box.min.z),
      new THREE.Vector3(box.max.x, box.max.y, box.max.z),
    ];
  }

  function orientedBoundsStageBounds(bounds) {
    if (!bounds) return null;
    const screenBounds = { left: Infinity, right: -Infinity, top: Infinity, bottom: -Infinity };
    for (const point of orientedBoundsCorners(bounds)) {
      const screenPoint = worldToStagePoint(point);
      if (!screenPoint) continue;
      screenBounds.left = Math.min(screenBounds.left, screenPoint.x);
      screenBounds.right = Math.max(screenBounds.right, screenPoint.x);
      screenBounds.top = Math.min(screenBounds.top, screenPoint.y);
      screenBounds.bottom = Math.max(screenBounds.bottom, screenPoint.y);
    }
    return Number.isFinite(screenBounds.left) ? screenBounds : null;
  }

  function orientedBoundsCorners(bounds) {
    const corners = [];
    for (const right of [bounds.minRight, bounds.maxRight]) {
      for (const forward of [bounds.minForward, bounds.maxForward]) {
        for (const vertical of [bounds.minVertical, bounds.maxVertical]) {
          corners.push(bounds.basis.right.clone().multiplyScalar(right)
            .add(bounds.basis.forward.clone().multiplyScalar(forward))
            .add(bounds.basis.vertical.clone().multiplyScalar(vertical)));
        }
      }
    }
    return corners;
  }

  function nudgeScreenDirections(orientedBounds) {
    const center = orientedBounds.center;
    const probeDistance = Math.max(orientedBounds.width, orientedBounds.depth, orientedBounds.height, 1);
    const basis = orientedBounds.basis;
    const directions = {};
    for (const direction of SMART_NUDGE_DIRECTIONS) {
      const vector = basis.right.clone().multiplyScalar(direction.right)
        .add(basis.forward.clone().multiplyScalar(direction.forward))
        .add(basis.vertical.clone().multiplyScalar(direction.vertical));
      directions[direction.id] = projectedScreenDirection(center, vector, probeDistance) || fallbackScreenDirection(direction);
    }
    return directions;
  }

  function nudgeWorldBasisVectors() {
    if (orientationMode === "world") {
      return {
        right: new THREE.Vector3(1, 0, 0),
        forward: new THREE.Vector3(0, 0, 1),
        vertical: new THREE.Vector3(0, 1, 0),
      };
    }
    const active = activeSelectedPlacement();
    const yaw = THREE.MathUtils.degToRad(active?.state?.yaw || 0);
    return {
      right: new THREE.Vector3(Math.cos(yaw), 0, Math.sin(yaw)),
      forward: new THREE.Vector3(-Math.sin(yaw), 0, Math.cos(yaw)),
      vertical: new THREE.Vector3(0, 1, 0),
    };
  }

  function projectedScreenDirection(origin, direction, distance) {
    const start = worldToStagePoint(origin);
    const end = worldToStagePoint(origin.clone().add(direction.clone().normalize().multiplyScalar(distance)));
    if (!start || !end) return null;
    const x = end.x - start.x;
    const y = end.y - start.y;
    return Math.hypot(x, y) > 0.001 ? { x, y } : null;
  }

  function worldToStagePoint(point) {
    const projected = point.clone().project(camera);
    if (projected.z < -1 || projected.z > 1) return null;
    const stageRect = renderer.domElement.getBoundingClientRect();
    return {
      x: ((projected.x + 1) / 2) * stageRect.width,
      y: ((-projected.y + 1) / 2) * stageRect.height,
    };
  }

  function fallbackScreenDirection(direction) {
    const x = direction.right + direction.forward * 0.65;
    const y = -direction.vertical - direction.forward * 0.65;
    if (Math.hypot(x, y) > 0.001) return { x, y };
    return { x: direction.right || 1, y: 0 };
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function syncTransformControlMode() {
    if (!transformControls) return;
    const selected = selectedPlacements();
    transformControls.setSpace(orientationMode);
    if (activeGizmoMode === "scale" && selected.length && !selected.every(canScalePlacement)) {
      activeGizmoMode = "";
    }
    if (!activeGizmoMode || !selected.length) {
      transformControls.detach();
      transformControls.showX = true;
      transformControls.showY = true;
      transformControls.showZ = true;
      syncTransformSnaps();
      if (controls && previewPreviousEnableZoom === null) controls.enableZoom = true;
      return;
    }
    transformControls.setMode(activeGizmoMode);
    if (activeGizmoMode === "rotate") {
      const yawOnly = selected.some((placement) => placement.target.asset_kind === "building_piece");
      transformControls.showX = !yawOnly;
      transformControls.showY = true;
      transformControls.showZ = !yawOnly;
    } else {
      transformControls.showX = true;
      transformControls.showY = true;
      transformControls.showZ = true;
    }
    syncTransformSnaps();
  }

  function updateGizmoSnapModifierFromEvent(event) {
    setGizmoSnapModifier(Boolean(event.ctrlKey || event.metaKey));
  }

  function setGizmoSnapModifier(active) {
    if (gizmoSnapModifierActive === active) return;
    gizmoSnapModifierActive = active;
    syncTransformSnaps();
  }

  function syncTransformSnaps() {
    if (!transformControls) return;
    const enabled = Boolean(transformControls.dragging && gizmoSnapModifierActive);
    transformControls.setTranslationSnap(enabled ? GIZMO_TRANSLATE_SNAP_CM * UNIT_SCALE : null);
    transformControls.setRotationSnap(enabled ? THREE.MathUtils.degToRad(GIZMO_ROTATE_SNAP_DEGREES) : null);
    transformControls.setScaleSnap(enabled ? GIZMO_SCALE_SNAP : null);
  }

  function activateGizmo(mode) {
    const nextMode = ["translate", "rotate", "scale"].includes(mode) ? mode : "";
    if (activeGizmoMode === nextMode) {
      clearActiveGizmo();
      return;
    }
    if (nextMode === "scale") {
      const selected = selectedPlacements();
      if (selected.length && !selected.every(canScalePlacement)) {
        activeGizmoMode = "";
        syncSelectionAttachment();
        renderScaleOverrideMessage();
        return;
      }
    }
    activeGizmoMode = nextMode;
    if (controls && previewPreviousEnableZoom === null) controls.enableZoom = true;
    syncSelectionAttachment();
  }

  function clearActiveGizmo() {
    activeGizmoMode = "";
    syncTransformControlMode();
  }

  function toggleSelectAll() {
    if (selectedPlacedIds.size === placements.size && placements.size > 0) {
      setSelection([]);
      return;
    }
    setSelection(Array.from(placements.keys()));
  }

  function renderInspector() {
    const selected = selectedPlacements();
    const placement = selectedPlacement();
    const hasSingleSelection = selected.length === 1;
    els.setAnchor.disabled = !hasSingleSelection || placement.target.asset_kind !== "building_piece";
    els.clearAnchor.disabled = !anchorPieceId;
    for (const input of els.transformInputs) {
      const key = input.dataset.transform;
      const scaleLocked = hasSingleSelection && key.startsWith("scale") && !canScalePlacement(placement);
      input.disabled = !hasSingleSelection || scaleLocked;
      if (!hasSingleSelection) {
        input.value = "";
      } else {
        input.value = roundValue(placement.state[key], key.startsWith("scale") ? 4 : 3);
      }
    }
    if (!selected.length) {
      els.selectionTitle.textContent = "No Selection";
      els.selectionMeta.textContent = "Select an object";
      return;
    }
    if (!hasSingleSelection) {
      els.selectionTitle.textContent = `${selected.length} Selected`;
      els.selectionMeta.textContent = "Transform selected objects as a group";
      return;
    }
    els.selectionTitle.textContent = placement.target.display_name;
    els.selectionMeta.textContent = `${kindLabel(placement.target.asset_kind)} | ${placement.target.catalog_path}`;
  }

  function placedGroupId(placement) {
    return placement.target.target_id || placement.target.asset_stem || placement.target.display_name;
  }

  function placedGroups() {
    const groups = new Map();
    for (const placement of placements.values()) {
      const id = placedGroupId(placement);
      if (!groups.has(id)) {
        groups.set(id, {
          id,
          target: placement.target,
          placements: [],
          selectedCount: 0,
          hiddenCount: 0,
        });
      }
      const group = groups.get(id);
      group.placements.push(placement);
      if (selectedPlacedIds.has(placement.id)) group.selectedCount += 1;
      if (placement.hidden) group.hiddenCount += 1;
    }
    return Array.from(groups.values())
      .sort((a, b) => a.target.display_name.localeCompare(b.target.display_name, undefined, { numeric: true }));
  }

  function createPlacedVisibilityButton({ hidden, label, onClick }) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `placed-visibility${hidden ? " is-hidden" : ""}`;
    button.title = hidden ? `Hidden, click to show ${label}` : `Visible, click to hide ${label}`;
    button.setAttribute("aria-label", button.title);
    const img = document.createElement("img");
    img.src = hidden ? HIDE_ICON_URL : SHOW_ICON_URL;
    img.alt = "";
    img.draggable = false;
    button.appendChild(img);
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      onClick();
    });
    return button;
  }

  function setPlacementsHidden(rows, hidden, { recordUndo = true } = {}) {
    const affected = rows.filter((placement) => placement && placement.hidden !== Boolean(hidden));
    if (!affected.length) return;
    if (recordUndo) pushUndoSnapshot();
    for (const placement of affected) setPlacementHidden(placement, hidden);
    renderInspector();
    renderPlacedList();
    scheduleGroundGridUpdate();
    updateCounters();
    scheduleAutosave();
    const action = hidden ? "Hidden" : "Shown";
    showViewportNotice(affected.length === 1 ? action : `${action} ${affected.length}`);
  }

  function togglePlacementHidden(placement) {
    if (!placement) return;
    setPlacementsHidden([placement], !placement.hidden);
  }

  function toggleSelectedHidden() {
    const selected = selectedPlacements();
    if (!selected.length) return;
    const shouldHide = selected.some((placement) => !placement.hidden);
    setPlacementsHidden(selected, shouldHide);
  }

  function renderPlacedRow(placement) {
    const row = document.createElement("div");
    row.className = `placed-row${hasSelection(placement.id) ? " is-active" : ""}${placement.hidden ? " is-hidden" : ""}`;

    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "placed-select";
    selectButton.innerHTML = `
      <span>
        <span class="placed-name"></span>
        <span class="placed-meta"></span>
      </span>
    `;
    selectButton.querySelector(".placed-name").textContent = placement.target.display_name;
    selectButton.querySelector(".placed-meta").textContent =
      `${roundValue(placement.state.x)}, ${roundValue(placement.state.y)}, ${roundValue(placement.state.z)}`;
    selectButton.addEventListener("click", (event) => {
      const mode = selectionModifierFromEvent(event);
      if (mode === "subtract") {
        subtractSelection(placement.id);
        return;
      }
      selectPlacement(placement.id, { toggle: mode === "add" });
    });

    const visibilityButton = createPlacedVisibilityButton({
      hidden: placement.hidden,
      label: placement.target.display_name,
      onClick: () => togglePlacementHidden(placement),
    });
    const kind = document.createElement("span");
    kind.className = "asset-kind";
    kind.textContent = kindLabel(placement.target.asset_kind);
    row.append(selectButton, visibilityButton, kind);
    return row;
  }

  function renderPlacedList() {
    els.placedList.textContent = "";
    let shownRows = 0;
    let capped = false;
    for (const group of placedGroups()) {
      const hasGroupHeader = group.placements.length > 1;
      let groupBody = els.placedList;
      let isOpen = true;
      if (hasGroupHeader) {
        isOpen = !closedPlacedGroupIds.has(group.id);
        const wrapper = document.createElement("section");
        wrapper.className = `placed-group${isOpen ? " is-open" : ""}`;
        const header = document.createElement("div");
        header.className = "placed-group-header";

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "placed-group-toggle";
        toggle.setAttribute("aria-expanded", String(isOpen));
        const hiddenText = group.hiddenCount ? `, ${group.hiddenCount.toLocaleString()} hidden` : "";
        const toggleGroupOpen = () => {
          if (isOpen) closedPlacedGroupIds.add(group.id);
          else closedPlacedGroupIds.delete(group.id);
          renderPlacedList();
        };
        toggle.innerHTML = `
          <span class="placed-group-caret" aria-hidden="true"></span>
          <span>
            <span class="placed-name"></span>
            <span class="placed-meta"></span>
          </span>
        `;
        toggle.querySelector(".placed-name").textContent = group.target.display_name;
        toggle.querySelector(".placed-meta").textContent =
          `${group.placements.length.toLocaleString()} ${kindPluralLabel(group.target.asset_kind)}${hiddenText}`;
        toggle.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          toggleGroupOpen();
        });
        header.addEventListener("click", (event) => {
          if (event.target?.closest?.(".placed-visibility")) return;
          event.preventDefault();
          event.stopPropagation();
          toggleGroupOpen();
        });

        const allHidden = group.hiddenCount === group.placements.length;
        const visibilityButton = createPlacedVisibilityButton({
          hidden: allHidden,
          label: `${group.target.display_name} group`,
          onClick: () => setPlacementsHidden(group.placements, !allHidden),
        });
        header.append(toggle, visibilityButton);
        groupBody = document.createElement("div");
        groupBody.className = "placed-group-body";
        wrapper.append(header, groupBody);
        els.placedList.appendChild(wrapper);
      }

      if (!isOpen) continue;
      for (const placement of group.placements) {
        if (shownRows >= PLACED_LIST_LIMIT) {
          capped = true;
          break;
        }
        groupBody.appendChild(renderPlacedRow(placement));
        shownRows += 1;
      }
    }
    if (capped || placements.size > shownRows) {
      const summary = document.createElement("div");
      summary.className = "placed-row placed-summary";
      summary.textContent = `Showing row details for ${shownRows.toLocaleString()} of ${placements.size.toLocaleString()} placed objects`;
      els.placedList.appendChild(summary);
    }
  }

  function updateCounters() {
    const total = placements.size;
    const hiddenTotal = Array.from(placements.values()).filter((placement) => placement.hidden).length;
    els.buildCount.textContent = hiddenTotal
      ? `${total.toLocaleString()} placed, ${hiddenTotal.toLocaleString()} hidden`
      : `${total.toLocaleString()} placed`;
    if (anchorPieceId) {
      const anchor = Array.from(placements.values()).find((placement) => Number(placement.metadata.piece_id) === anchorPieceId);
      els.anchorStatus.textContent = anchor
        ? `${anchor.target.display_name}${anchor.hidden ? " (hidden)" : ""}`
        : "Anchor missing";
    } else {
      els.anchorStatus.textContent = "No anchor";
    }
    scheduleAutosave();
  }

  async function onPointerDown(event) {
    if (dragSession?.clickToPlace) {
      await commitClickPreviewPlacement(event);
      return;
    }
    if (dragSession) return;
    if (transformControls.dragging) return;
    if (event.button !== 0) return;
    if (transformControls.axis) return;
    const selectionMode = selectionModifierFromEvent(event);
    selectionGesture = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      currentX: event.clientX,
      currentY: event.clientY,
      mode: selectionMode,
      additive: selectionMode === "add",
      subtract: selectionMode === "subtract",
      dragging: false,
      hitId: hitPlacementId(event, { allowScreenFallback: false }),
    };
    renderer.domElement.setPointerCapture?.(event.pointerId);
    window.addEventListener("pointermove", onSelectionPointerMove);
    window.addEventListener("pointerup", onSelectionPointerUp);
    window.addEventListener("pointercancel", onSelectionPointerCancel);
  }

  function onSelectionPointerMove(event) {
    if (!selectionGesture || event.pointerId !== selectionGesture.pointerId) return;
    selectionGesture.currentX = event.clientX;
    selectionGesture.currentY = event.clientY;
    const dx = event.clientX - selectionGesture.startX;
    const dy = event.clientY - selectionGesture.startY;
    const distance = Math.hypot(dx, dy);
    if (!selectionGesture.dragging && distance < DRAG_START_DISTANCE_PX) return;
    if (!selectionGesture.dragging && selectionGesture.hitId && !selectionGesture.additive && !selectionGesture.subtract) {
      if (shouldMarqueeFromHitDrag(dx, dy)) {
        selectionGesture.hitId = "";
      } else if (distance < movePreviewStartDistancePx()) {
        return;
      } else {
        const placement = placements.get(selectionGesture.hitId);
        endSelectionGesture();
        beginMovePreviewPlacement(placement, event);
        return;
      }
    }
    selectionGesture.dragging = true;
    controls.enabled = false;
    updateSelectionMarquee();
  }

  function onSelectionPointerUp(event) {
    if (!selectionGesture || event.pointerId !== selectionGesture.pointerId) return;
    selectionGesture.currentX = event.clientX;
    selectionGesture.currentY = event.clientY;
    if (selectionGesture.dragging) {
      selectByMarquee(selectionGesture);
    } else {
      const hitId = selectionGesture.hitId || hitPlacementId(event);
      if (!hitId) {
        if (!selectionGesture.additive && !selectionGesture.subtract) selectPlacement("");
        endSelectionGesture();
        return;
      }
      if (selectionGesture.subtract) {
        subtractSelection(hitId);
      } else {
        selectPlacement(hitId, { toggle: selectionGesture.additive });
      }
    }
    endSelectionGesture();
  }

  function onSelectionPointerCancel() {
    endSelectionGesture();
  }

  function endSelectionGesture() {
    if (selectionGesture?.pointerId !== undefined) {
      renderer.domElement.releasePointerCapture?.(selectionGesture.pointerId);
    }
    selectionGesture = null;
    controls.enabled = true;
    if (selectionMarquee) selectionMarquee.hidden = true;
    window.removeEventListener("pointermove", onSelectionPointerMove);
    window.removeEventListener("pointerup", onSelectionPointerUp);
    window.removeEventListener("pointercancel", onSelectionPointerCancel);
  }

  function hitPlacementId(event, { allowScreenFallback = true } = {}) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const candidates = raycastPlacementCandidates(raycaster.ray, { useRayPath: true });
    const candidateIds = new Set(candidates.map((placement) => placement.id));
    const roots = candidates.map((placement) => getVisualRoot(placement)).filter(Boolean);
    const instanceMeshes = instanceBatchMeshesForPlacements(candidates);
    const hits = raycaster.intersectObjects([...roots, ...instanceMeshes], true);
    for (const hit of hits) {
      const id = hit.object.userData.placedId || placementIdFromInstanceHit(hit);
      if (!id || !candidateIds.has(id)) continue;
      const placement = placements.get(id);
      if (placement && ensurePlacementVisualState(placement).visible !== false) return id;
    }
    return allowScreenFallback ? screenBoundsHitPlacementId(event, candidates, raycaster.ray) : "";
  }

  function screenBoundsHitPlacementId(event, candidates = Array.from(placements.values()), ray = null) {
    const point = {
      left: event.clientX - 6,
      right: event.clientX + 6,
      top: event.clientY - 6,
      bottom: event.clientY + 6,
    };
    let best = null;
    const boxHit = new THREE.Vector3();
    for (const placement of candidates) {
      const bounds = placementScreenBounds(placement);
      if (!bounds || !rectsIntersect(point, bounds)) continue;
      const area = Math.max(1, bounds.right - bounds.left) * Math.max(1, bounds.bottom - bounds.top);
      const worldBounds = ray ? getWorldBounds(placement) : null;
      const hit = ray && worldBounds && !worldBounds.isEmpty() ? ray.intersectBox(worldBounds, boxHit) : null;
      const distanceScore = hit ? ray.origin.distanceToSquared(hit) : Number.MAX_SAFE_INTEGER;
      const selectedBias = selectedPlacedIds.has(placement.id) ? -0.001 : 0;
      const score = distanceScore + area * 0.000001 + selectedBias;
      if (!best || score < best.score) best = { id: placement.id, score };
    }
    return best?.id || "";
  }

  function updateSelectionMarquee() {
    if (!selectionMarquee || !selectionGesture) return;
    const stageRect = els.stage.getBoundingClientRect();
    const left = Math.min(selectionGesture.startX, selectionGesture.currentX) - stageRect.left;
    const top = Math.min(selectionGesture.startY, selectionGesture.currentY) - stageRect.top;
    const width = Math.abs(selectionGesture.currentX - selectionGesture.startX);
    const height = Math.abs(selectionGesture.currentY - selectionGesture.startY);
    selectionMarquee.hidden = false;
    selectionMarquee.style.left = `${Math.max(0, left)}px`;
    selectionMarquee.style.top = `${Math.max(0, top)}px`;
    selectionMarquee.style.width = `${width}px`;
    selectionMarquee.style.height = `${height}px`;
  }

  function selectByMarquee(gesture) {
    const rect = normalizedClientRect(gesture.startX, gesture.startY, gesture.currentX, gesture.currentY);
    const ids = [];
    for (const placement of marqueePlacementCandidates(rect)) {
      if (!placementPickable(placement)) continue;
      const screenBox = placementScreenBounds(placement);
      if (screenBox && rectsIntersect(rect, screenBox)) ids.push(placement.id);
    }
    const next = gesture.additive || gesture.subtract ? new Set(selectedPlacedIds) : new Set();
    if (gesture.subtract) {
      for (const id of ids) next.delete(id);
    } else {
      for (const id of ids) next.add(id);
    }
    setSelection(next);
  }

  function normalizedClientRect(x1, y1, x2, y2) {
    return {
      left: Math.min(x1, x2),
      right: Math.max(x1, x2),
      top: Math.min(y1, y2),
      bottom: Math.max(y1, y2),
    };
  }

  function placementScreenBounds(placement) {
    return getScreenBounds(placement);
  }

  function rectsIntersect(a, b) {
    return a.left <= b.right && a.right >= b.left && a.top <= b.bottom && a.bottom >= b.top;
  }

  function setLoading(value) {
    els.loading.hidden = !value;
  }

  function captureBuildSnapshot() {
    return {
      placements: Array.from(placements.values()).map((placement) => ({
        id: placement.id,
        target_id: placement.target.target_id,
        state: { ...placement.state },
        metadata: { ...placement.metadata },
        hidden: Boolean(placement.hidden),
      })),
      selected_ids: Array.from(selectedPlacedIds),
      view_offset: { ...viewOffset },
      build_name: buildName,
      build_schema: buildSchema,
      anchor_piece_id: anchorPieceId,
      next_object_id: nextObjectId,
      next_piece_id: nextPieceId,
    };
  }

  function scheduleAutosave() {
    if (!autosaveReady || restoringSnapshot || bulkMutationActive) return;
    if (autosaveTimer) window.clearTimeout(autosaveTimer);
    const delay = placements.size >= 10000
      ? 3000
      : placements.size >= 5000
        ? 1500
        : AUTOSAVE_DEBOUNCE_MS;
    autosaveTimer = window.setTimeout(saveAutosave, delay);
  }

  function saveAutosave() {
    if (!autosaveReady || restoringSnapshot || bulkMutationActive) return;
    if (autosaveTimer) {
      window.clearTimeout(autosaveTimer);
      autosaveTimer = 0;
    }
    try {
      window.localStorage.setItem(AUTOSAVE_STORAGE_KEY, JSON.stringify({
        schema: "RSDWBaseBuilder.Autosave.v1",
        saved_at: new Date().toISOString(),
        snapshot: captureBuildSnapshot(),
      }));
    } catch (error) {
      console.warn("Autosave failed", error);
    }
  }

  function loadAutosaveSnapshot() {
    try {
      const payload = JSON.parse(window.localStorage.getItem(AUTOSAVE_STORAGE_KEY) || "null");
      if (!payload) return null;
      const snapshot = payload.snapshot || payload;
      return Array.isArray(snapshot.placements) ? snapshot : null;
    } catch {
      return null;
    }
  }

  async function restoreBuildSnapshot(snapshot) {
    const entries = [];
    for (const row of snapshot.placements || []) {
      const target = targetLookup.byId.get(row.target_id);
      if (!target) continue;
      entries.push({
        id: row.id,
        target,
        transform: row.state,
        metadata: row.metadata,
        hidden: Boolean(row.hidden),
      });
    }
    await preloadGltfsForTargets(entries.map((entry) => entry.target), { statusPrefix: "Preloading restored models" });
    bulkMutationActive = true;
    try {
      clearBuild({ resetOffset: false, render: false });
      viewOffset = { x: 0, y: 0, z: 0, ...(snapshot.view_offset || {}) };
      buildName = snapshot.build_name || "Browser Base";
      buildSchema = snapshot.build_schema || "rsdwtools.buildings.v1";
      anchorPieceId = Number(snapshot.anchor_piece_id || 0);
      nextObjectId = Number(snapshot.next_object_id || 1);
      nextPieceId = Number(snapshot.next_piece_id || 1);
      await createPlacementsBulk(entries, { statusPrefix: "Restoring" });
      nextObjectId = Number(snapshot.next_object_id || nextObjectId);
      nextPieceId = Number(snapshot.next_piece_id || nextPieceId);
    } finally {
      bulkMutationActive = false;
    }
    setSelection(snapshot.selected_ids || [], { render: false });
    renderInspector();
    renderPlacedList();
    updateCounters();
  }

  async function restoreAutosavedBuild() {
    const snapshot = loadAutosaveSnapshot();
    if (!snapshot || !snapshot.placements?.length) return false;
    restoringSnapshot = true;
    try {
      await restoreBuildSnapshot(snapshot);
      focusCameraOnBuild({ notify: false });
      els.assetStatus.textContent = "Autosaved build restored";
      return true;
    } catch (error) {
      console.error(error);
      els.assetStatus.textContent = `Autosave restore failed: ${error.message}`;
      return false;
    } finally {
      restoringSnapshot = false;
    }
  }

  function pushUndoSnapshot(snapshot = captureBuildSnapshot()) {
    if (restoringSnapshot) return;
    undoStack.push(snapshot);
    if (undoStack.length > UNDO_LIMIT) undoStack.shift();
  }

  async function undoLastAction() {
    if (restoringSnapshot || !undoStack.length) return;
    const snapshot = undoStack.pop();
    restoringSnapshot = true;
    setLoading(true);
    try {
      await restoreBuildSnapshot(snapshot);
    } catch (error) {
      console.error(error);
      els.selectionMeta.textContent = `Undo failed: ${error.message}`;
    } finally {
      restoringSnapshot = false;
      setLoading(false);
      saveAutosave();
    }
  }

  async function duplicateSelected() {
    const selected = selectedPlacements();
    if (!selected.length) return;
    pushUndoSnapshot();
    const newIds = [];
    setLoading(true);
    try {
      for (const placement of selected) {
        const transform = { ...placement.state };
        const metadata = { ...placement.metadata };
        delete metadata.piece_id;
        const duplicated = await createPlacement(placement.target, transform, metadata, { select: false });
        newIds.push(duplicated.id);
      }
      setSelection(newIds);
      showViewportNotice(newIds.length === 1 ? "Duplicated" : `Duplicated ${newIds.length}`);
    } catch (error) {
      console.error(error);
      els.selectionMeta.textContent = `Duplicate failed: ${error.message}`;
    } finally {
      setLoading(false);
    }
  }

  async function smartDuplicateNudge(directionId) {
    if (smartDuplicateNudgeActive || dragSession) return;
    const selected = selectedPlacements();
    if (!selected.length) return;
    const offset = smartDuplicateNudgeOffset(directionId);
    if (!offset) return;
    smartDuplicateNudgeActive = true;
    pushUndoSnapshot();
    const duplicatedPlacements = [];
    const newIds = [];
    setLoading(true);
    try {
      for (const placement of selected) {
        const transform = {
          ...placement.state,
          x: placement.state.x + offset.x,
          y: placement.state.y + offset.y,
          z: placement.state.z + offset.z,
        };
        const metadata = { ...placement.metadata };
        delete metadata.piece_id;
        const duplicated = await createPlacement(placement.target, transform, metadata, { select: false });
        duplicatedPlacements.push(duplicated);
        newIds.push(duplicated.id);
      }
      setSelection(newIds);
      const snapResult = snapPlacements(duplicatedPlacements, {
        excludedIds: new Set(newIds),
        recordUndo: false,
      });
      els.selectionMeta.textContent = smartDuplicateNudgeMessage(newIds.length, offset, snapResult);
      showViewportNotice(newIds.length === 1 ? "Smart duplicated" : `Smart duplicated ${newIds.length}`);
    } catch (error) {
      console.error(error);
      els.selectionMeta.textContent = `Smart duplicate failed: ${error.message}`;
    } finally {
      smartDuplicateNudgeActive = false;
      setLoading(false);
    }
  }

  function smartDuplicateNudgeOffset(directionId) {
    const direction = SMART_NUDGE_BY_ID.get(directionId);
    if (!direction) return null;
    const bounds = selectedOrientationBounds();
    if (!bounds) return null;
    const rightStep = Math.max(roundValue(bounds.width / UNIT_SCALE), 10);
    const forwardStep = Math.max(roundValue(bounds.depth / UNIT_SCALE), 10);
    const zStep = Math.max(roundValue(bounds.height / UNIT_SCALE), 10);
    const right = { x: bounds.basis.right.x, y: bounds.basis.right.z };
    const forward = { x: bounds.basis.forward.x, y: bounds.basis.forward.z };
    return {
      x: roundValue((right.x * direction.right * rightStep) + (forward.x * direction.forward * forwardStep)),
      y: roundValue((right.y * direction.right * rightStep) + (forward.y * direction.forward * forwardStep)),
      z: roundValue(direction.vertical * zStep),
    };
  }

  function smartDuplicateNudgeMessage(count, offset, snapResult) {
    const moved = [];
    if (offset.x) moved.push(`X ${signedNumber(offset.x)}`);
    if (offset.y) moved.push(`Y ${signedNumber(offset.y)}`);
    if (offset.z) moved.push(`Z ${signedNumber(offset.z)}`);
    const snapText = snapResult.snapped
      ? `, snapped ${snapResult.snapped} of ${snapResult.total} pieces`
      : "";
    const orientationText = offset.z ? "vertical" : orientationMode;
    return `Smart duplicated ${count} selected (${orientationText}: ${moved.join(", ")})${snapText}`;
  }

  function signedNumber(value) {
    return `${value > 0 ? "+" : ""}${roundValue(value)}`;
  }

  function smartDuplicateNudgeDirectionFromEvent(event) {
    return SMART_NUDGE_BY_CODE.get(event.code) || null;
  }

  function handleViewportViewShortcut(event) {
    if (duplicateNudgeModifierActive || event.altKey || event.shiftKey) return false;
    const hasCtrl = event.ctrlKey || event.metaKey;
    const snapShortcut = VIEW_SNAP_SHORTCUTS[event.code];
    if (snapShortcut) {
      snapCameraToView(hasCtrl ? snapShortcut.back : snapShortcut.front);
      return true;
    }
    if (hasCtrl) return false;
    if (event.code === "Numpad5") {
      toggleCameraProjection();
      return true;
    }
    if (event.code === "Numpad9") {
      snapCameraToOppositeView();
      return true;
    }
    if (event.code === "NumpadDecimal" || event.code === "NumpadPeriod") {
      if (!focusCameraOnSelected()) showViewportNotice("No selection to frame");
      return true;
    }
    if (event.code === "Home" || event.code === "Digit0" || event.code === "Numpad0") {
      if (placements.size) focusCameraOnBuild();
      else showViewportNotice("No objects to frame");
      return true;
    }
    return false;
  }

  function deleteSelected() {
    const selected = selectedPlacements();
    if (!selected.length) return;
    pushUndoSnapshot();
    for (const placement of selected) {
      if (Number(placement.metadata.piece_id) === anchorPieceId) anchorPieceId = 0;
      disposeVisual(placement);
      placements.delete(placement.id);
    }
    selectPlacement("");
    renderPlacedList();
    scheduleGroundGridUpdate();
    updateCounters();
  }

  function clearBuild({ resetOffset = true, recordUndo = false, render = true } = {}) {
    if (recordUndo && placements.size) pushUndoSnapshot();
    for (const placement of placements.values()) {
      disposeVisual(placement);
    }
    placements.clear();
    spatialIndex.cells.clear();
    spatialIndex.placementCells.clear();
    selectedPlacedIds.clear();
    activePlacementId = "";
    activeGizmoMode = "";
    closedPlacedGroupIds.clear();
    anchorPieceId = 0;
    nextPieceId = 1;
    if (resetOffset) viewOffset = { x: 0, y: 0, z: 0 };
    transformControls.detach();
    syncSelectionBoxes();
    syncSelectionHotkeys();
    if (!bulkMutationActive) updateGroundGrid();
    if (!render) return;
    if (index) renderAssets();
    renderInspector();
    renderPlacedList();
    updateCounters();
  }

  function setSelectedAnchor() {
    const placement = selectedPlacement();
    if (!placement || placement.target.asset_kind !== "building_piece") return;
    pushUndoSnapshot();
    if (!placement.metadata.piece_id) {
      placement.metadata.piece_id = allocatePieceId();
    }
    anchorPieceId = Number(placement.metadata.piece_id);
    updateCounters();
  }

  function allocatePieceId() {
    const used = new Set();
    for (const placement of placements.values()) {
      const pid = Number(placement.metadata.piece_id || 0);
      if (pid > 0) used.add(pid);
    }
    while (used.has(nextPieceId)) nextPieceId += 1;
    return nextPieceId++;
  }

  function snapSelected() {
    const selected = selectedPlacements();
    const movers = selected.filter((placement) => placement.target.asset_kind === "building_piece");
    if (!movers.length) return;
    const excludedIds = movers.length > 1 ? new Set(selectedPlacedIds) : new Set([movers[0].id]);
    const result = snapPlacements(movers, { excludedIds });
    if (!result.snapped) {
      els.selectionMeta.textContent = "No compatible snap in range";
      showViewportNotice("No snap found");
      return;
    }
    showViewportNotice(result.snapped === 1 ? "Snapped" : `Snapped ${result.snapped}`);
    if (movers.length > 1) {
      els.selectionMeta.textContent = `${result.snapped} of ${result.total} selected pieces snapped`;
    }
  }

  function snapPlacements(movers, { excludedIds = null, recordUndo = true } = {}) {
    const pieces = movers.filter((placement) => placement?.target.asset_kind === "building_piece");
    const excludeSet = excludedIds ? toIdSet(excludedIds) : new Set(pieces.map((placement) => placement.id));
    const snapPlans = [];
    for (const mover of pieces) {
      const best = findCompatibleSnap(mover.target, mover.state, excludeSet);
      if (best) snapPlans.push({ mover, best });
    }
    if (!snapPlans.length) return { snapped: 0, total: pieces.length };
    if (recordUndo) pushUndoSnapshot();
    for (const { mover, best } of snapPlans) {
      mover.state.x += best.candidatePos.x - best.moverPos.x;
      mover.state.y += best.candidatePos.y - best.moverPos.y;
      mover.state.z += best.candidatePos.z - best.moverPos.z;
      applyPlacementTransform(mover);
    }
    scheduleGroundGridUpdate();
    renderInspector();
    renderPlacedList();
    updateCounters();
    return { snapped: snapPlans.length, total: pieces.length };
  }

  function snapStateForTarget(target, state, excludeId = "") {
    const best = findCompatibleSnap(target, state, excludeId);
    if (!best) return { state, snapped: false };
    return {
      state: {
        ...state,
        x: state.x + best.candidatePos.x - best.moverPos.x,
        y: state.y + best.candidatePos.y - best.moverPos.y,
        z: state.z + best.candidatePos.z - best.moverPos.z,
      },
      snapped: true,
    };
  }

  function findCompatibleSnap(target, state, excludeIds = "") {
    if (!target || target.asset_kind !== "building_piece") return null;
    const moverSnaps = index.snaps[target.snap_class];
    if (!moverSnaps || !Array.isArray(moverSnaps.plugs)) return null;
    const excludedIds = toIdSet(excludeIds);
    const moverPlugRows = moverSnaps.plugs.map((plug) => {
      const matrix = plugWorldMatrix(state, plug);
      return { plug, pos: matrixTranslation(matrix) };
    });
    const candidateIds = new Set();
    for (const row of moverPlugRows) {
      for (const candidate of queryPointRadius({ x: row.pos.x, y: row.pos.y }, SPATIAL_SNAP_RADIUS_CM)) {
        if (!excludedIds.has(candidate.id)) candidateIds.add(candidate.id);
      }
    }
    const candidates = candidateIds.size
      ? Array.from(candidateIds).map((id) => placements.get(id)).filter(Boolean)
      : (!spatialIndex.placementCells.size && placements.size ? Array.from(placements.values()) : []);

    let best = null;
    for (const candidate of candidates) {
      if (excludedIds.has(candidate.id) || candidate.hidden || candidate.target.asset_kind !== "building_piece") continue;
      const candidateSnaps = index.snaps[candidate.target.snap_class];
      if (!candidateSnaps || !Array.isArray(candidateSnaps.plugs)) continue;
      for (const moverRow of moverPlugRows) {
        for (const candidatePlug of candidateSnaps.plugs) {
          if (!plugsCompatible(moverRow.plug, candidatePlug)) continue;
          const candidateMatrix = plugWorldMatrix(candidate.state, candidatePlug);
          const candidatePos = matrixTranslation(candidateMatrix);
          const d2 = distanceSquared(moverRow.pos, candidatePos);
          if (d2 > SNAP_MAX_DISTANCE_CM * SNAP_MAX_DISTANCE_CM) continue;
          if (!best || d2 < best.d2) {
            best = { d2, moverPos: moverRow.pos, candidatePos };
          }
        }
      }
    }
    return best;
  }

  function toIdSet(ids) {
    if (ids instanceof Set) return ids;
    if (Array.isArray(ids)) return new Set(ids.filter(Boolean));
    return ids ? new Set([ids]) : new Set();
  }

  function plugsCompatible(a, b) {
    const aPlugIgn = new Set(a.plug_ign || []);
    const bPlugIgn = new Set(b.plug_ign || []);
    const aPieceIgn = new Set(a.piece_ign || []);
    const bPieceIgn = new Set(b.piece_ign || []);
    if (bPlugIgn.has(a.plug_tag)) return false;
    if (aPlugIgn.has(b.plug_tag)) return false;
    if (bPieceIgn.has(a.piece_tag)) return false;
    if (aPieceIgn.has(b.piece_tag)) return false;
    return true;
  }

  function buildImportPlacementEntries(data) {
    const entries = [];
    let skipped = 0;
    for (const row of data.pieces || []) {
      const target =
        targetLookup.byPieceClass.get(shortenClass(row.class_name)) ||
        targetLookup.byPieceDataName.get(pieceDataStem(row.piece_data_name));
      if (!target) {
        skipped += 1;
        continue;
      }
      entries.push({
        target,
        transform: editorTransformFromJson(row),
        metadata: {
          piece_id: Number(row.piece_id || 0),
          stability: Number(row.stability || target.export.default_stability || 3000),
          is_ghosted: Boolean(row.is_ghosted),
          spud_guid: row.spud_guid || "",
        },
      });
    }
    for (const row of data.items || []) {
      const target = targetLookup.byItemName.get(row.item_asset_name);
      if (!target) {
        skipped += 1;
        continue;
      }
      entries.push({
        target,
        transform: editorTransformFromJson(row),
        metadata: {
          actor_name: row.actor_name || "",
          actor_class: row.actor_class || ITEM_ACTOR_CLASS,
          item_count: Number(row.count || 1),
          item_source: row.item_source || "ItemData",
        },
      });
    }
    for (const row of data.actors || []) {
      const target = targetLookup.byBpClass.get(shortenClass(row.actor_class || row.class_path));
      if (!target) {
        skipped += 1;
        continue;
      }
      entries.push({
        target,
        transform: editorTransformFromJson(row),
        metadata: {
          actor_name: row.actor_name || "",
        },
      });
    }
    return { entries, skipped };
  }

  async function createPlacementsBulk(entries, { statusPrefix = "Importing" } = {}) {
    for (let index = 0; index < entries.length; index += 1) {
      const entry = entries[index];
      await createPlacement(entry.target, entry.transform, entry.metadata, {
        id: entry.id,
        hidden: entry.hidden,
        select: false,
        render: false,
      });
      const completed = index + 1;
      if (completed === entries.length || completed % IMPORT_RENDER_BATCH_SIZE === 0) {
        els.assetStatus.textContent = `${statusPrefix} ${completed.toLocaleString()} of ${entries.length.toLocaleString()}`;
        await nextFrame();
      }
    }
    updateGroundGrid();
  }

  async function importBuildingJson(file) {
    setLoading(true);
    try {
      els.assetStatus.textContent = "Parsing import";
      const data = JSON.parse(await file.text());
      pushUndoSnapshot();
      const rows = [...(data.pieces || []), ...(data.items || []), ...(data.actors || [])];
      const importedAnchor = importedAnchorPiece(data);
      els.assetStatus.textContent = "Resolving import targets";
      const { entries, skipped } = buildImportPlacementEntries(data);
      await preloadGltfsForTargets(entries.map((entry) => entry.target), { statusPrefix: "Preloading import models" });
      viewOffset = importViewOffset(rows, importedAnchor);
      bulkMutationActive = true;
      clearBuild({ resetOffset: false, render: false });
      buildName = data.name || file.name.replace(/\.json$/i, "") || "Browser Base";
      buildSchema = data.schema || "rsdwtools.buildings.v1";
      anchorPieceId = Number(importedAnchor?.piece_id || data.anchor_piece_id || 0);
      await createPlacementsBulk(entries);
      bulkMutationActive = false;
      els.assetStatus.textContent = "Finalizing import";
      setSelection([], { render: false });
      renderInspector();
      renderPlacedList();
      updateCounters();
      focusCameraOnBuild({ notify: false });
      const skippedText = skipped ? `, skipped ${skipped.toLocaleString()} missing targets` : "";
      els.assetStatus.textContent = `Imported ${entries.length.toLocaleString()} objects${skippedText}`;
    } catch (error) {
      console.error(error);
      els.assetStatus.textContent = `Import failed: ${error.message}`;
    } finally {
      bulkMutationActive = false;
      setLoading(false);
    }
  }

  async function debugGenerateSyntheticBuild(options = {}) {
    const count = Math.max(1, Math.min(Number(options.count || 1000), 20000));
    const kind = options.kind || "building_piece";
    const target = targetLookup.byId.get(options.targetId || "") ||
      index.targets.find((row) => row.asset_kind === kind) ||
      index.targets.find((row) => row.asset_kind === "building_piece");
    if (!target) throw new Error("No target available for synthetic build.");
    const spacing = Number(options.spacing || 400);
    const columns = Math.max(1, Math.ceil(Math.sqrt(count)));
    const entries = [];
    for (let i = 0; i < count; i += 1) {
      const col = i % columns;
      const row = Math.floor(i / columns);
      entries.push({
        id: `bench_${i + 1}`,
        target,
        transform: {
          x: roundValue((col - columns / 2) * spacing),
          y: roundValue(row * spacing),
          z: 0,
          pitch: 0,
          yaw: 0,
          roll: 0,
          scale_x: 1,
          scale_y: 1,
          scale_z: 1,
        },
        metadata: target.asset_kind === "building_piece" ? { piece_id: i + 1 } : {},
      });
    }

    const started = performance.now();
    const previousAutosaveReady = autosaveReady;
    const persistAutosave = options.persist === true;
    setLoading(true);
    bulkMutationActive = true;
    if (!persistAutosave) autosaveReady = false;
    try {
      els.assetStatus.textContent = `Preparing ${count.toLocaleString()} synthetic placements`;
      await preloadGltfsForTargets([target], { statusPrefix: "Preloading benchmark model" });
      clearBuild({ resetOffset: true, render: false });
      buildName = `Synthetic ${count.toLocaleString()} ${target.display_name}`;
      buildSchema = "rsdwtools.buildings.v1";
      anchorPieceId = 0;
      await createPlacementsBulk(entries, { statusPrefix: "Benchmark importing" });
    } finally {
      bulkMutationActive = false;
      setLoading(false);
      autosaveReady = previousAutosaveReady;
    }
    setSelection([], { render: false });
    renderInspector();
    renderPlacedList();
    const autosaveReadyForCounters = autosaveReady;
    if (!persistAutosave) autosaveReady = false;
    updateCounters();
    autosaveReady = autosaveReadyForCounters;
    focusCameraOnBuild({ notify: false });
    const elapsedMs = Math.round(performance.now() - started);
    els.assetStatus.textContent = `Synthetic ${count.toLocaleString()} placements in ${elapsedMs.toLocaleString()} ms`;
    return {
      count,
      target_id: target.target_id,
      elapsed_ms: elapsedMs,
      spatial_cells: spatialIndex.cells.size,
    };
  }

  function installDebugHelpers() {
    window.__RSDW_BASE_BUILDER_DEBUG__ = {
      objectCount: () => placements.size,
      selectedName: () => selectedPlacement()?.target.display_name || "",
      dragActive: () => Boolean(dragSession),
      spatialCells: () => spatialIndex.cells.size,
      visualTemplateCount: () => targetVisualTemplateCache.size,
      instanceStats,
      generateSyntheticBuild: debugGenerateSyntheticBuild,
    };
  }

  function debugBenchmarkOptionsFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const count = Number(params.get("benchmark") || params.get("bench") || 0);
    if (!count) return null;
    return {
      count,
      kind: params.get("kind") || "building_piece",
      targetId: params.get("target") || "",
      spacing: Number(params.get("spacing") || 400),
      persist: params.get("persist") === "1" || params.get("autosave") === "1",
    };
  }

  function importViewOffset(rows, anchorPiece) {
    const offset = medianOffset(rows);
    if (anchorPiece) {
      const anchorZ = Number(anchorPiece.z ?? 0);
      if (Number.isFinite(anchorZ)) offset.z = anchorZ;
    }
    return offset;
  }

  function importedAnchorPiece(data) {
    const pieces = Array.isArray(data.pieces) ? data.pieces : [];
    if (!pieces.length) return null;

    const anchorPieceIdValue = Number(data.anchor_piece_id || 0);
    if (anchorPieceIdValue > 0) {
      const byPieceId = pieces.find((piece) => Number(piece.piece_id || 0) === anchorPieceIdValue);
      if (byPieceId) return byPieceId;
    }

    const anchorPieceDataIndex = Number(data.anchor_piece_data_index || 0);
    if (anchorPieceDataIndex > 0) {
      return pieces.find((piece) => Number(piece.piece_data_index || 0) === anchorPieceDataIndex) || null;
    }

    return null;
  }

  function editorTransformFromJson(row) {
    const transform = normalizeTransform(row);
    return {
      ...transform,
      pitch: -transform.pitch,
      roll: -transform.roll,
    };
  }

  function jsonTransformFromEditorState(state) {
    const transform = exportTransform(state);
    return {
      ...transform,
      pitch: roundValue(-transform.pitch),
      roll: roundValue(-transform.roll),
    };
  }

  function medianOffset(rows) {
    if (!rows.length) return { x: 0, y: 0, z: 0 };
    const xs = rows.map((row) => Number(row.x || 0)).sort((a, b) => a - b);
    const ys = rows.map((row) => Number(row.y || 0)).sort((a, b) => a - b);
    const zs = rows.map((row) => Number(row.z || 0)).sort((a, b) => a - b);
    const mid = Math.floor(rows.length / 2);
    return { x: xs[mid] || 0, y: ys[mid] || 0, z: zs[mid] || 0 };
  }

  function exportBuildingJson() {
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
      generated_unix: Math.floor(Date.now() / 1000),
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
    downloadJson(out, `${safeFileName(buildName || "browser_build")}.json`);
  }

  function downloadJson(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2) + "\n"], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    URL.revokeObjectURL(link.href);
    link.remove();
  }

  function safeFileName(value) {
    return String(value || "building").replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "") || "building";
  }

  function snapCameraToView(view) {
    if (!camera || !controls || !view) return;
    stopViewHelperAnimation();
    const target = controls.target.clone();
    const distance = Math.max(camera.position.distanceTo(target), CAMERA_DEFAULT_DISTANCE);
    camera.position.copy(target).add(view.direction.clone().normalize().multiplyScalar(distance));
    camera.up.copy(view.up).normalize();
    camera.lookAt(target);
    controls.update();
    showViewportNotice(view.label);
  }

  function snapCameraToOppositeView() {
    if (!camera || !controls) return;
    stopViewHelperAnimation();
    const target = controls.target.clone();
    const offset = camera.position.clone().sub(target);
    if (offset.lengthSq() < 0.0001) offset.set(1, 1, 1).normalize().multiplyScalar(CAMERA_DEFAULT_DISTANCE);
    camera.position.copy(target).sub(offset);
    camera.lookAt(target);
    controls.update();
    showViewportNotice("Opposite View");
  }

  function focusCameraOnBox(box, { selectedOnly = false, notify = true } = {}) {
    if (!camera || !controls || !box || box.isEmpty()) return false;
    stopViewHelperAnimation();
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxSize = Math.max(size.x, size.y, size.z, selectedOnly ? 1 : 3);
    const offset = camera.position.clone().sub(controls.target);
    if (offset.lengthSq() < 0.0001) offset.set(0.85, 0.7, 0.85).normalize();
    const distance = camera.isPerspectiveCamera
      ? perspectiveFitDistance(box)
      : Math.max(maxSize * 1.45, CAMERA_DEFAULT_DISTANCE / 2);
    controls.target.copy(center);
    camera.position.copy(center).add(offset.normalize().multiplyScalar(distance));
    syncCameraRangeWithBox(box, { distance });
    if (camera.isOrthographicCamera) {
      const radius = Math.max(box.getBoundingSphere(new THREE.Sphere()).radius, 1);
      orthographicViewSize = Math.max(radius * 2 * ORTHOGRAPHIC_PADDING, 1);
      camera.zoom = 1;
      updateCameraProjection();
    }
    controls.update();
    if (notify) showViewportNotice(selectedOnly ? "Frame Selected" : "Frame All");
    return true;
  }

  function focusCameraOnSelected({ notify = true } = {}) {
    const selected = selectedPlacements();
    if (!selected.length) return false;
    const box = buildPlacementsWorldBox(selected);
    return focusCameraOnBox(box, { selectedOnly: true, notify });
  }

  function focusCameraOnBuild({ notify = true } = {}) {
    if (!placements.size) return;
    const box = buildPlacementsWorldBox();
    focusCameraOnBox(box, { notify });
  }

  function bindEvents() {
    setMenu("discord-toggle", "discord-menu");
    setMenu("links-toggle", "links-menu");
    document.addEventListener("click", () => {
      closeMenus();
      closeAssetContextMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeMenus();
        closeAssetContextMenu();
      }
    });
    els.assetSearch.addEventListener("input", () => {
      resetVisibleAssetResults();
      renderAssets();
    });
    els.assetViewToggle?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggleAssetViewMode();
    });
    els.loadMoreAssets?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      loadMoreAssets();
    });
    document.addEventListener("dragstart", (event) => {
      if (event.target?.closest?.(".asset-row, .favorite-tile")) event.preventDefault();
    });
    els.controlsHud?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggleControlsHud();
    });
    els.controlsHud?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      event.stopPropagation();
      toggleControlsHud();
    });
    els.orientationToggle?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggleOrientationMode();
    });
    for (const button of els.kindButtons) {
      button.addEventListener("click", () => {
        activeKind = button.dataset.kind;
        activeCategoryPath = "";
        resetVisibleAssetResults();
        for (const other of els.kindButtons) other.classList.toggle("is-active", other === button);
        renderCategoryButtons();
        renderAssets();
      });
    }
    els.importJson.addEventListener("click", () => els.fileInput.click());
    els.fileInput.addEventListener("change", () => {
      const file = els.fileInput.files && els.fileInput.files[0];
      if (file) importBuildingJson(file);
      els.fileInput.value = "";
    });
    els.exportJson.addEventListener("click", exportBuildingJson);
    els.clearBuild.addEventListener("click", () => clearBuild({ recordUndo: true }));
    els.setAnchor.addEventListener("click", setSelectedAnchor);
    els.clearAnchor.addEventListener("click", () => {
      pushUndoSnapshot();
      anchorPieceId = 0;
      updateCounters();
      renderInspector();
      scheduleAutosave();
    });
    for (const input of els.transformInputs) {
      input.addEventListener("change", () => {
        const placement = selectedPlacement();
        if (!placement) return;
        const key = input.dataset.transform;
        if (key.startsWith("scale") && !canScalePlacement(placement)) {
          renderInspector();
          renderScaleOverrideMessage();
          return;
        }
        pushUndoSnapshot();
        placement.state[key] = Number(input.value);
        if (key.startsWith("scale") && placement.state[key] <= 0) placement.state[key] = 0.01;
        applyPlacementTransform(placement);
        renderInspector();
        renderPlacedList();
        scheduleAutosave();
      });
    }
    window.addEventListener("beforeunload", saveAutosave);
    window.addEventListener("pointermove", (event) => {
      if (transformControls?.dragging) updateGizmoSnapModifierFromEvent(event);
    }, { passive: true });
    window.addEventListener("keyup", (event) => {
      updateGizmoSnapModifierFromEvent(event);
      if (event.key.toLowerCase() === "d") setDuplicateNudgeModifier(false);
    });
    window.addEventListener("blur", () => {
      setGizmoSnapModifier(false);
      setDuplicateNudgeModifier(false);
    });
    window.addEventListener("keydown", (event) => {
      updateGizmoSnapModifierFromEvent(event);
      if (event.target && ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
      const key = event.key.toLowerCase();
      if (key === "d") setDuplicateNudgeModifier(true);
      const smartNudgeDirection = smartDuplicateNudgeDirectionFromEvent(event);
      if (duplicateNudgeModifierActive && smartNudgeDirection) {
        event.preventDefault();
        if (!event.repeat) smartDuplicateNudge(smartNudgeDirection.id);
        return;
      }
      if (handleViewportViewShortcut(event)) {
        event.preventDefault();
        return;
      }
      if ((event.ctrlKey || event.metaKey) && key === "z" && !event.shiftKey) {
        event.preventDefault();
        undoLastAction();
      } else if (dragSession && key === "r") {
        event.preventDefault();
        cycleDragRotateStep();
      } else if (dragSession && key === "f") {
        event.preventDefault();
        flipDragPreviewYaw();
      } else if (event.key === "Escape") {
        event.preventDefault();
        if (dragSession) endDragPlacement();
        if (selectionGesture) endSelectionGesture();
        else selectPlacement("");
      } else if (event.key === "Delete" || event.key === "Backspace" || key === "x") {
        event.preventDefault();
        deleteSelected();
      } else if (key === "h") {
        event.preventDefault();
        toggleSelectedHidden();
      } else if (key === "d" && (event.ctrlKey || event.metaKey || event.shiftKey)) {
        event.preventDefault();
        duplicateSelected();
      } else if (key === "e") {
        event.preventDefault();
        beginSmartDuplicatePlacement();
      } else if (key === "g") {
        event.preventDefault();
        activateGizmo("translate");
      } else if (key === "r") {
        event.preventDefault();
        activateGizmo("rotate");
      } else if (key === "s") {
        event.preventDefault();
        activateGizmo("scale");
      } else if (key === "q") {
        event.preventDefault();
        snapSelected();
      } else if (key === "o") {
        event.preventDefault();
        toggleOrientationMode();
      } else if (key === "a") {
        event.preventDefault();
        toggleSelectAll();
      }
    });
  }

  function setMenu(toggleId, menuId) {
    const toggle = document.getElementById(toggleId);
    const menu = document.getElementById(menuId);
    if (!toggle || !menu) return;
    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = menu.hidden;
      closeMenus();
      menu.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
    });
  }

  function closeMenus() {
    document.querySelectorAll(".rsdw-menu__panel").forEach((panel) => {
      panel.hidden = true;
    });
    document.querySelectorAll(".rsdw-iconbtn[aria-expanded]").forEach((button) => {
      button.setAttribute("aria-expanded", "false");
    });
  }

  async function init() {
    bindEvents();
    config = { ...config, ...(await loadJson(CONFIG_URL).catch(() => ({}))) };
    index = await loadJson(INDEX_URL);
    buildLookups();
    loadScaleOverride();
    loadFavorites();
    loadAssetViewMode();
    pruneFavorites();
    initThree();
    syncOrientationUi();
    renderCategoryButtons();
    renderAssets();
    renderControlsHud();
    installDebugHelpers();
    const benchmarkOptions = debugBenchmarkOptionsFromUrl();
    if (benchmarkOptions) {
      await debugGenerateSyntheticBuild(benchmarkOptions);
    } else {
      await restoreAutosavedBuild();
    }
    renderInspector();
    updateCounters();
    autosaveReady = true;
    setLoading(false);
  }

  init().catch((error) => {
    console.error(error);
    els.assetStatus.textContent = "Unable to load browser builder data.";
    els.loading.textContent = error.message;
  });
})();
