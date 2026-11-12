import { captureProject, validateProject, migrateFreeAutosave, catalogIdentity } from "./basebuilder-project.js";
import { openProjectStore, LEGACY_DB_NAME } from "./basebuilder-project-store.js";

const WORLD_WORKSPACE_LABEL = "World (beta)";
const WORLD_UNAVAILABLE = `${WORLD_WORKSPACE_LABEL} is available in the local preview`;

export async function createBuilderWorkspace(host, { defaultMode = "free", worldAvailable = false } = {}) {
  const store = openProjectStore(), catalogHash = await catalogIdentity(host.catalog);
  const status = document.querySelector("#project-save-status"), worldPanel = document.querySelector("#world-workspace");
  const modeButtons = [...document.querySelectorAll("[data-workspace-mode]")];
  let mode = "free", world = null, worldState = null, pendingMode = null;
  let free = { plane_z_cm: 0, grid_visible: true, remembered_camera: null };
  let delivery = { preferred_mode: defaultMode === "world" ? "saved_world_location" : "anchor" };
  let dataset = { game_version: host.catalog.version, catalog_sha256: catalogHash, world_sha256: null };
  let projectId = crypto.randomUUID(), revision = 0, epoch = 0, savedEpoch = 0;
  let suspended = true, transitioning = false, saving = null, saveError = null, timer = 0, lastSaveMetrics = null;
  const cameraState = () => host.captureCamera();
  const noticeError = error => { host.notice(error.message); };

  function updateStatus(label = savedEpoch === epoch ? "Saved" : "Unsaved") {
    const text = label + (host.hasReferences() ? " | Reference models not saved" : "");
    const error = String(Boolean(saveError));
    if (status.textContent !== text) status.textContent = text;
    if (status.dataset.error !== error) status.dataset.error = error;
  }
  function showSaveError(error) { saveError = error; updateStatus("Save Failed: " + error.message); }
  function capture() {
    const camera = cameraState();
    if (mode === "world" && world) worldState = world.captureContext();
    return captureProject({ id: projectId, revision, dataset, delivery, build: host.captureBuild(), workspace: {
      authoring_mode: mode, render_origin_cm: host.getOrigin(), camera, orientation: host.getOrientation(),
      free_build: { ...free, remembered_camera: mode === "free" ? camera : free.remembered_camera }, world_build: worldState,
    } });
  }
  function markChanged({ cameraOnly = false } = {}) {
    if (suspended) return;
    epoch++; clearTimeout(timer);
    if (!cameraOnly && mode === "world") world?.updateBuildMarker();
    if (saveError) return;
    updateStatus("Unsaved");
    scheduleSave();
  }
  function scheduleSave() {
    clearTimeout(timer);
    timer = setTimeout(() => saveNow({ background: true }).catch(() => {}), host.count() >= 5000 ? 1500 : 350);
  }
  async function saveNow({ background = false } = {}) {
    if (suspended || transitioning || host.busy()) { if (!suspended) scheduleSave(); return null; }
    if (saveError) throw saveError;
    const requestedEpoch = epoch;
    if (saving) {
      const saved = await saving;
      if (background || savedEpoch >= requestedEpoch) return saved;
      return saveNow();
    }
    if (savedEpoch >= epoch) return capture();
    clearTimeout(timer);
    saving = (async () => {
      const writeEpoch = epoch, start = performance.now(), document = capture(), captured = performance.now();
      validateProject(document, host.catalog, { copy: false });
      const validated = performance.now(); updateStatus("Saving");
      const saved = await store.commit(projectId, revision, document);
      revision = saved.revision; savedEpoch = writeEpoch;
      lastSaveMetrics = { capture_ms: captured - start, validate_ms: validated - captured,
        transaction_ms: performance.now() - validated, total_ms: performance.now() - start };
      updateStatus(); return saved;
    })().catch(error => { showSaveError(error); throw error; }).finally(() => {
      saving = null;
      // A write acknowledges its captured epoch, not edits made during that write.
      // Let the existing trailing debounce save those edits instead of chasing orbit frames.
      if (!suspended && !saveError && savedEpoch < epoch) scheduleSave();
    });
    return saving;
  }
  function syncUi() {
    worldPanel.hidden = mode !== "world";
    for (const button of modeButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.workspaceMode === mode));
      button.disabled = button.dataset.workspaceMode === "world" && !worldAvailable;
      if (button.disabled) button.title = WORLD_UNAVAILABLE;
    }
    host.setAuthoringMode(mode, free);
    document.querySelector("#place-build-world").hidden = mode !== "world";
    document.querySelector("#free-plane-field").hidden = mode !== "free";
    document.querySelector("#free-plane-z").value = free.plane_z_cm;
  }
  async function ensureWorld() {
    if (world) return world;
    if (!worldAvailable) throw Error(WORLD_UNAVAILABLE);
    const { createWorldWorkspace } = await import("./basebuilder-world-workspace.js");
    world = await createWorldWorkspace({ ...host, markChanged, getWorldIdentity: () => dataset.world_sha256 });
    if (!dataset.world_sha256 && world.identity()) dataset.world_sha256 = world.identity();
    return world;
  }
  async function setMode(next, { remember = true } = {}) {
    if (!["free", "world"].includes(next)) throw Error("Invalid workspace mode");
    if (next === "world" && !worldAvailable) throw Error(WORLD_UNAVAILABLE);
    if (transitioning || host.busy()) { pendingMode = next; host.notice("Workspace change queued until editing finishes"); return false; }
    if (next === mode && (next === "free" || world)) return true;
    transitioning = true;
    try {
      if (remember) {
        if (mode === "free") free.remembered_camera = cameraState();
        else if (world) worldState = world.captureContext();
      }
      if (mode === "world") await world?.deactivate();
      mode = next; syncUi();
      if (mode === "free") {
        host.setMapMode(false);
        if (free.remembered_camera) host.restoreView({ camera: free.remembered_camera, orientation: host.getOrientation() });
        else if (host.count()) host.frameBuild();
      } else {
        const adapter = await ensureWorld();
        host.setProjectBusy(true);
        try { await host.prepareWorldShaders(adapter.layer); } finally { host.setProjectBusy(false); }
        await adapter.start(worldState);
        worldState = adapter.captureContext();
        if (adapter.error()) host.notice(adapter.error());
      }
      markChanged(); return true;
    } finally { transitioning = false; syncUi(); }
  }
  async function confirmReplace() {
    if (transitioning || host.busy()) { host.notice("Finish the current edit first"); return false; }
    if (epoch !== savedEpoch || saveError) return Boolean(await host.dialog({ eyebrow: "Project", title: "Replace unsaved project?",
      message: "Download a project before replacing work you want to keep.", showInput: false, confirmLabel: "Replace", danger: true }));
    return true;
  }
  async function openDocument(input, { recovery = false, confirm = true } = {}) {
    if (transitioning || host.busy()) throw Error("Finish the current edit first");
    const document = validateProject(input, host.catalog);
    if (document.dataset.catalog_sha256 !== catalogHash && !host.catalog.compatible_catalog_sha256?.includes(document.dataset.catalog_sha256))
      throw Error("Project catalog identity differs. Automatic catalog migration is not supported.");
    if (document.workspace.authoring_mode === "world" && !worldAvailable) throw Error("Open this world project in the local preview");
    if (confirm && !await confirmReplace()) return false;
    transitioning = true; suspended = true; pendingMode = null; clearTimeout(timer); host.setProjectBusy(true);
    if (saving) await saving.catch(() => {});
    let committed = false;
    try {
      const staged = await host.prepareRestore(document.build);
      if (world) {
        if (JSON.stringify(host.getOrigin()) !== JSON.stringify(document.workspace.render_origin_cm)) { await world.dispose(); world = null; }
        else await world.deactivate();
      }
      host.commitRestore(staged, document.build);
      host.clearReferences();
      dataset = { ...document.dataset, catalog_sha256: catalogHash };
      free = structuredClone(document.workspace.free_build); worldState = structuredClone(document.workspace.world_build);
      if (document.workspace.authoring_mode === "world" && worldState) worldState.camera = structuredClone(document.workspace.camera);
      delivery = { ...document.delivery }; mode = document.workspace.authoring_mode;
      projectId = recovery ? document.project_id : crypto.randomUUID(); revision = recovery ? document.revision : 0;
      epoch = 1; savedEpoch = 0; saveError = null; committed = true;
      syncUi(); host.restoreView(document.workspace);
    } finally { host.setProjectBusy(false); suspended = false; transitioning = false; syncUi(); }
    if (committed && mode === "world") {
      try {
        const adapter = await ensureWorld(); host.setProjectBusy(true);
        try { await host.prepareWorldShaders(adapter.layer); } finally { host.setProjectBusy(false); }
        await adapter.start(worldState); worldState = adapter.captureContext();
      }
      catch (error) { host.notice("World unavailable: " + error.message); }
    }
    markChanged(); await saveNow(); return true;
  }
  async function newProject({ authoringMode = null, confirm = true } = {}) {
    if (confirm && !await confirmReplace()) return false;
    const chosen = authoringMode || await host.dialog({ eyebrow: "New Project", title: "Choose Workspace", showInput: false,
      confirmLabel: "Free Build", confirmValue: "free", secondaryLabel: worldAvailable ? WORLD_WORKSPACE_LABEL : "", secondaryValue: "world" });
    if (!chosen) return false;
    if (saving) await saving.catch(() => {});
    suspended = true; pendingMode = null; clearTimeout(timer);
    if (world) { await world.dispose(); world = null; }
    host.clearProject(); host.setOrigin([0, 0, 0]); host.resetView();
    free = { plane_z_cm: 0, grid_visible: true, remembered_camera: cameraState() }; worldState = null;
    dataset = { game_version: host.catalog.version, catalog_sha256: catalogHash, world_sha256: null };
    delivery = { preferred_mode: chosen === "world" ? "saved_world_location" : "anchor" };
    projectId = crypto.randomUUID(); revision = 0; epoch = 0; savedEpoch = 0; saveError = null;
    mode = "free"; suspended = false; syncUi();
    if (chosen === "world") await setMode("world");
    markChanged(); await saveNow(); return true;
  }
  async function download(copy = false) {
    if (host.busy() || transitioning) { host.notice("Finish the current edit first"); return; }
    if (copy) { if (saving) await saving.catch(() => {}); projectId = crypto.randomUUID(); revision = 0; saveError = null; epoch++; savedEpoch = 0; }
    const document = validateProject(capture(), host.catalog);
    host.download(document, `${host.name() || "build"}.rsdwproject.json`);
    if (copy) await saveNow(); host.notice(copy ? "Project copy saved" : "Project downloaded");
  }
  async function recoverLegacy() {
    const issues = [];
    let hasLegacy = true;
    try { if (indexedDB.databases) hasLegacy = (await indexedDB.databases()).some(db => db.name === LEGACY_DB_NAME); }
    catch (error) { issues.push(error.message); }
    if (hasLegacy) {
      const legacy = openProjectStore(indexedDB, LEGACY_DB_NAME);
      try {
        for (const record of await legacy.records()) {
          try {
            let current = null, previous = null;
            try { current = validateProject(record.current, host.catalog); } catch (error) { issues.push(error.message); }
            if (record.previous) try { previous = validateProject(record.previous, host.catalog); } catch (error) { issues.push(error.message); }
            const fingerprint = await catalogIdentity(record);
            if (!current && previous) { current = previous; previous = null; current.project_id = "previous-" + fingerprint; }
            if (!current) continue;
            if (current.dataset.catalog_sha256 !== catalogHash && !host.catalog.compatible_catalog_sha256?.includes(current.dataset.catalog_sha256))
              throw Error("Legacy world catalog differs");
            await store.migrate({ current, previous }, "world:" + fingerprint);
          } catch (error) { issues.push(error.message); }
        }
      } catch (error) { issues.push(error.message); }
      finally { await legacy.close().catch(() => {}); }
    }
    let raw = null;
    try { raw = localStorage.getItem("RSDWBaseBuilder.autosave.v1"); } catch (error) { issues.push(error.message); }
    if (raw) {
      try {
        const hash = await catalogIdentity(JSON.parse(raw)), projectId = "free-" + hash;
        const current = validateProject(migrateFreeAutosave(JSON.parse(raw), { catalog: host.catalog, catalogHash, projectId }), host.catalog);
        await store.migrate({ current, previous: null }, "free:" + hash);
      } catch (error) { issues.push(error.message); }
    }
    return issues;
  }
  async function start() {
    syncUi();
    try {
      const issues = await recoverLegacy(), latest = await store.last(), records = await store.records();
      if (issues.length) host.notice("Legacy save retained: " + issues[0]);
      if (latest?.current || records.length) {
        const options = [];
        for (const record of records) for (const [key, document] of [["current", record.current], ["previous", record.previous]]) {
          if (!document) continue;
          try { validateProject(document, host.catalog, {copy:false}); }
          catch (error) { host.notice("Saved revision retained: " + error.message); continue; }
          const value = `${options.length}`;
          options.push({ value, label: `${document.build.build_name} | ${document.workspace.authoring_mode === "world" ? WORLD_WORKSPACE_LABEL : "Free"} | ${document.build.placements.length.toLocaleString()} objects${key === "previous" ? " | Previous Save" : ""}`, document, recovery: key === "current" });
        }
        if (!options.length) throw Error("No compatible saved revisions; source records retained");
        const preferred = options.find(o => o.recovery && o.document.project_id === latest?.current.project_id) || options[0];
        const recover = await host.dialog({ eyebrow: "Project Recovery", title: "Restore project?", showInput: false,
          message: "Choose a saved project to continue.", confirmLabel: "Restore", cancelLabel: "New Project",
          choices: options, choiceValue: preferred.value });
        if (recover !== null) {
          const selected = options.find(o => o.value === recover);
          if (!selected) throw Error("Saved project selection unavailable");
          await openDocument(selected.document, { recovery: selected.recovery, confirm: false }); return;
        }
      }
    } catch (error) { suspended = true; showSaveError(Error("Recovery unavailable: " + error.message)); host.notice("Saved project retained; open a project or choose New Project."); return; }
    suspended = false;
    if (defaultMode === "world") await setMode("world");
    markChanged();
  }
  function action(id, callback) { document.querySelector(id).addEventListener("click", () => Promise.resolve().then(callback).catch(noticeError)); }
  action("#project-new", () => newProject()); action("#project-save", () => download()); action("#project-copy", () => download(true));
  const file = document.querySelector("#project-file"); action("#project-open", () => file.click());
  file.addEventListener("change", async () => { try { if (file.files[0]) await openDocument(JSON.parse(await file.files[0].text())); }
    catch (error) { noticeError(error); } finally { file.value = ""; } });
  for (const button of modeButtons) button.addEventListener("click", () => setMode(button.dataset.workspaceMode).catch(noticeError));
  action("#place-build-world", host.placeBuild);
  document.querySelector("#free-plane-z").addEventListener("change", event => {
    const value = Number(event.target.value);
    if (host.busy() || !Number.isFinite(value)) { event.target.value = free.plane_z_cm; return; }
    free.plane_z_cm = value; syncUi(); markChanged();
  });
  const cameraChanged = () => markChanged({ cameraOnly: true }); host.controls.addEventListener("change", cameraChanged);
  const gestureTimer = setInterval(() => { if (pendingMode && !transitioning && !host.busy()) { const next = pendingMode; pendingMode = null; setMode(next).catch(noticeError); } }, 100);
  const emptyLayer = { getStatus: () => ({ phase: "unloaded", placements: 0, loadedSectionIds: [], loadedSectionId: null, failed: [] }) };
  return { start, capture, store, markChanged, saveNow, openDocument, newProject, download, setMode,
    mode: () => mode, planeHeight: () => free.plane_z_cm, worldIdentity: () => dataset.world_sha256,
    deliveryMode: () => delivery.preferred_mode,
    setDeliveryMode(value) { if (!["anchor", "saved_world_location"].includes(value)) throw Error("Invalid delivery preference"); delivery.preferred_mode = value; markChanged(); },
    saveMetrics: () => lastSaveMetrics && { ...lastSaveMetrics },
    get layer() { return world?.layer || emptyLayer; },
    isMap: () => mode === "world" && Boolean(world?.isMap()),
    getNavigation: () => world?.getNavigation() || worldState?.navigation,
    getOverviewMetrics: () => world?.getOverviewMetrics(),
    async enterLocation(...args) { if (mode !== "world") await setMode("world"); return (await ensureWorld()).enterLocation(...args); },
    async showMap(...args) { if (mode !== "world") await setMode("world"); return (await ensureWorld()).showMap(...args); },
    async returnToBuild() { if (mode !== "world") await setMode("world"); return (await ensureWorld()).returnToBuild(); },
    runWorld: (...args) => mode === "world" ? world?.runWorld(...args) : null,
    stream: (...args) => mode === "world" ? world?.stream(...args) : null,
    beforeFrameBuild: () => { if (mode === "world") world?.beforeFrameBuild(); },
    frame: () => mode === "world" ? world?.frame() : host.frameBuild(),
    surface: ray => mode === "world" ? world?.surface(ray) : null,
    clipDistance: () => mode === "world" ? world?.clipDistance() || 0 : 0,
    render: scene => mode === "world" && world ? world.render(scene) : host.renderer.render(scene, host.getCamera()),
    async dispose() { suspended = true; clearTimeout(timer); clearInterval(gestureTimer); host.controls.removeEventListener("change", cameraChanged); await world?.dispose(); await store.close(); },
  };
}
