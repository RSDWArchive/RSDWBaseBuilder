# World Builder Milestone 1: Build in One World Section

Status: implemented locally; automated acceptance and performance evidence under
`_build/world-builder-m1/`. In-game comparison remains pending user review.
Prepared 2026-10-16 against the current local BaseBuilder and World prototype.

Local entry: <http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1>.
See [the local testing/recovery guide](tools/Web/WORLD_BUILDER_LOCAL.md).
No push, deployment, world-data regeneration or Blender release was performed.

## Outcome

Use the existing browser BaseBuilder to load one game-world section, author a
base against its terrain/scenery, save a project, reload it, and export the
build. Unloading or replacing world context must never delete, move, hide,
renumber or dispose authored placements or erase their collections/undo history.

This is a local, opt-in vertical slice, not a public world-editor release.
Material verification continues independently; known approximations remain
annotated rather than becoming blockers for editor integration.

## Scope and Decisions

- Host the integration in the existing `website/index.html` editor, behind a
  local-only `?world=1` entry. Normal builder startup and production behavior
  remain unchanged. Do not load the standalone world application inside it.
- Reuse the builder's camera, renderer, input handlers, placement model,
  instancing, selection, snapping, preview controls, gizmos and export rules.
- Start with dataset `1.0.0.5` and section `x3_y1`, Dowdun Reach [3, 1]. It has
  11 terrain entries and 5,845 section placements before spanning additions,
  and passed the recent browser audit. Store the choice in local configuration;
  populate section options from `WorldIndex.json`, not hardcoded UI labels.
- Load at most one detailed section plus its intersecting spanning geometry.
  Provide explicit Load, Unload and Frame Section actions. Use `x4_y3` as a
  second, already-tested section for replacement tests. There is no automatic
  neighbor streaming or full-world overview in this milestone.
- Persist all authored objects, including hidden ones. Preserve current hidden
  object exclusion from game exports and existing single-anchor semantics.
- Keep game JSON exactly `rsdwtools.buildings.v1`. No collection, camera, world
  placement, project or streaming fields enter that format.
- No NPC/location overlays, world editing, gameplay simulation, direct game
  delivery, cloud accounts, collaborative editing, public hosting or automatic
  dataset migration. No whole-editor rewrite or replacement render engine.
- Imported reference GLB/GLTF persistence is outside this slice. Disable that
  import action in the opt-in world workspace with an explicit explanation;
  leave it unchanged in the normal builder. Never imply these references would
  survive a project reload when they are not yet serialized.

## Existing Code and Integration Risks

| Area | Current implementation | Required treatment |
| --- | --- | --- |
| Editor ownership | `website/basebuilder.js` owns `placements`, renderer, input, visuals, collections and undo inside its initialization closure | Keep it as the host; extract only the interfaces needed below |
| Coordinate conversion | `website/basebuilder-transforms.js`; editor state is centimeters with a `viewOffset` for rendering | Keep this authoritative; world display must use the same origin |
| Game serialization | `editorTransformFromJson`, `jsonTransformFromEditorState`, `exportBuildingJson` | Preserve pitch/roll inversion, IDs, scale, metadata and anchor behavior |
| Current persistence | `captureBuildSnapshot`, localStorage autosave and `restoreBuildSnapshot` | Add a separate project store; current restore silently skips missing targets and must not be used unchecked for project open |
| World renderer | `tools/World/preview/world.js` creates its own scene, camera, controls, DOM listeners and caches | Extract a host-independent world layer; do not run this entry point in the builder |
| World disposal | `replaceDetail` tears down world roots and cached materials/geometries/textures | Disposal must be restricted to owned world resources, never the host scene or editor caches |
| Section controller | `world-browser.js` assumes its own UI and has zero-origin-dependent camera queries | Reuse data contracts, not its DOM/controller wholesale; new section queries must respect the shared origin |
| Surface placement | `stagePointFromEvent` queries authored objects then a ground plane | Add world surface hits without making world meshes selectable or exportable |

The current builder catalog and world dataset both report `1.0.0.5`; the
catalog contains 3,887 targets. Validate these facts at runtime, not by assuming
that future generated outputs stay compatible.

## Architecture and Ownership

The editor owns one scene/render loop and three independent roots:

- Authored root: existing placement records, instance batches and editable
  objects. Only editor commands can mutate these.
- World root: terrain, scenery and world-only materials/resources. Not entered
  into `placements`, the Placed panel, authored spatial index or undo snapshots.
- Editor helpers: gizmos, selection outlines, preview ghosts and grid. Never
  captured as world data or included in exports.

World loading receives the renderer, current camera, scene attachment point,
origin and status callbacks. It must not create controls, global keyboard
handlers, a second canvas, a second animation loop or a full-screen editor
loading mask. World loading errors remain nonfatal to the build editor.

Proposed small interfaces (names may follow nearby conventions):

```text
createWorldLayer({ renderer, root, getCamera, originCm, onStatus, invalidate })
  loadSection({ dataset, sectionId, signal })
  unload()
  raycastSurface(ray, options) -> nearest world hit or null
  getBounds() / getStatus() / getMetrics()
  setLayerVisible(layer, visible)
  beforeRender(camera) / afterRender()
  dispose()

serializeBuildingJson(editorState) -> unchanged game JSON
captureProject(editorState, workspace) -> project document
validateProject(document, catalog, dataset) -> validated data or explicit errors
prepareProjectRestore(document) -> staged authored state
commitProjectRestore(stagedState)

projectStore.read(projectId) / commit(projectId, revision, document)
```

Keep the world and editor asset caches separate for this milestone, even when
they request the same URL. Do not dispose editor-owned resources on world
unload. Within the world layer, track shared resource ownership and release
each owned texture/material/geometry/instance buffer once. Cross-layer cache
sharing is deferred until reference-counted ownership is proven.

World water/depth/material adapters run through host render hooks and restore
render target, viewport, scissor and other modified renderer state. Support the
builder's perspective/orthographic camera replacement. Use a single world-mode
lighting setup, not both applications' light rigs added together. Normal-mode
lighting is unchanged. In world mode the existing solid-view toggle affects
authored assets only; do not rewrite streamed terrain/water materials.

## Coordinate and Export Contract

1. Authored position state remains absolute UE centimeters. Editor rotation
   channels retain today's conventions; conversion to game pitch/roll happens
   once at the existing JSON boundary. Cooked world matrices are already UE
   transforms and must not receive the actor export sign flip.
2. Choose a render origin near the initial section from source bounds/focus.
   Store it in the project and keep it fixed for the session. Rendering uses
   Three.js `(X-originX, Z-originZ, Y-originY) / 100` for both layers.
3. Section load/unload, camera framing, selecting an anchor, Clear Build and
   build import must not change that origin in a world workspace. No automatic
   floating-origin rebasing in this milestone. Test both positive and negative
   coordinates and far-from-zero world positions.
4. Existing game JSON import/append preserves its saved world coordinates.
   Disable empty-workspace median/anchor-to-zero view recentering in world mode
   only. A prefab authored at zero does not automatically move to the camera or
   selected section. Users can reposition it with existing editing tools;
   anchor-based prefab placement is a later feature.
5. Save Project preserves the origin and editor state exactly. Export Build
   serializes authored state, not scene matrices or origin-relative positions.
   Do not subtract the anchor or world origin from exported coordinates.
6. Preserve one anchor; if it is hidden/deleted, retain the existing export rule
   that no anchor fields reference a non-exported piece. Do not auto-select a
   different anchor during section changes or reload.

Compare exports as parsed data, excluding only the intentional
`generated_unix` timestamp. Fixture IDs should already be valid so export's
existing ID repair does not mask unexpected mutations.

## Surface Placement and Editor Behavior

- Keep selection, marquee, select-all, delete, collections and hotkeys scoped
  to authored placements. World hits never become selected placements.
- For placement previews, compare eligible authored and world hit distances
  along the same ray. Use the closest actual eligible surface, not a world
  bounding box as the final contact point. Broad-phase bounds may prune tests.
- Initial world surfaces: detailed terrain and visible static building/scenery
  meshes. Exclude foliage, helpers, transparent VFX and water from placement
  contact. No snapping plugs are inferred for world meshes.
- Preserve authored snap precedence and preview behavior: snapping to another
  authored piece first when compatible, then the existing bottom-of-bounds
  handling for BP/items and the user's preview height offset. Do not align an
  actor's rotation to a terrain slope automatically.
- Use the same contact path for catalog drag, E duplicate preview and dragging
  an already placed object. Exclude source objects/ghosts as today.
- If world context is missing/loading or the ray has no eligible contact, do
  not silently place on an invisible zero-height plane. Indicate unavailable
  contact and block preview confirmation; Escape restores/cancels the preview.
  Existing gizmos and numeric editing remain usable without the world loaded.
- Queue section replacement while a preview/gizmo gesture is active. Apply it
  after confirmation/cancellation so the active contact surface is not removed
  midway through editing. The world cannot move already committed placements.
- Home/0 continues to frame the authored build; with no authored build, it can
  frame the loaded section. Frame Section remains an explicit separate action.
  Adapt camera clipping to section/build bounds without creating another camera.

## Project Saving and Recovery

Use a separate JSON project document, for example
`RSDWBaseBuilder.Project.v1`, downloaded as `<name>.rsdwproject.json`.

```text
schema, project_id, revision, saved_at
dataset: game_version, catalog identity/hash, world identity/hash
workspace: render_origin_cm, requested_section_id, world_enabled,
           visible_world_layers, camera/projection/target, orientation
build: existing authored snapshot (placements, stable IDs, metadata,
       hidden state, collections/collapse state, anchor, next-ID counters)
```

World section/model/texture payloads and undo history are not embedded. Store
dataset identities, not machine-specific absolute paths or arbitrary fetch URLs.
Resolve sources through trusted local configuration. Persist camera in absolute
UE coordinates so it does not depend on resource load order.

### User Actions

- Add a themed Project menu with New Project, Open Project and Save Project.
  Keep Import/Append Build JSON and Export Build distinct and unchanged in
  purpose. Opening a project replaces the current project only after validation
  and an unsaved-work confirmation.
- Show Saving, Saved, Unsaved and Save Failed state unobtrusively. Never report
  Saved before the storage transaction has completed. Show a durable warning on
  storage failure, with Save Project still available.
- Keep a separate project-ID-based IndexedDB store for opt-in world workspaces.
  Do not overwrite or auto-migrate the existing normal builder localStorage
  autosave. Startup offers recovery for the last world project.
- Debounce successful edit snapshots; write completed actions, never preview
  ghosts or an intermediate bulk restore. Persist workspace-only changes too.
  Coalesce revisioned writes so an older asynchronous save cannot replace newer
  state. Keep a previous committed recovery revision atomically.
- On multi-tab revision conflict, stop overwriting and offer a saved copy; do not
  silently let the last tab erase another tab's edits. Make the origin/storage
  boundary clear: localhost and 127.0.0.1 have separate browser storage.
- Do not promise recovery of an edit interrupted before its save commits. The
  saved-state indicator and explicit download are the user's recovery contract.
  Do not rely on an asynchronous write during browser shutdown.

### Safe Open/Restore

Validate schema, numeric transforms, unique placement/piece IDs, collection
references, anchor and next-ID counters before mutating the live editor.
Resolve every catalog target and stage visuals before swapping authored roots.
On failure, dispose only staging resources and retain the current project,
selection, undo stack and last successful autosave. Do not silently skip targets.

Wrong catalog version or unavailable authored targets blocks replacement with
a clear missing-target/version report. Missing world files or a world identity
mismatch may leave the authored project available with world context disabled
and a warning; do not fetch a different world version automatically. Project
open is a session boundary with a fresh undo stack after successful restore.
World unload/reload is not: it preserves the existing undo stack unchanged.

Clear Build clears authored content only, is undoable as today, and retains
world/origin context. A deliberate empty build must save and recover as empty;
do not use the current nonzero-placement test to resurrect an older build.

## World Loading Lifecycle

Load index/shared metadata and validate dataset compatibility. Read the chosen
section and intersecting spanning placements; deduplicate by source ID. Keep
the original manifests and material adapters as the source of world visuals.

Use generation tokens and AbortController for obsolete requests. Noncancelable
decode results must be discarded/released when their generation becomes stale.
Late completions after Unload or project replacement cannot attach to the scene.
At most one world detail generation is resident in this milestone: replace only
world-owned content, present loading status, and allow retry after failures.
Authored data remains editable/saveable/exportable throughout world loading.

World status tracks requested section versus successfully loaded section. Save
the requested context for retry, but do not claim missing scenery has loaded.
No camera jump when a background request completes; only explicit load/frame
actions or project camera restoration may change the user's view.

## Implementation Sequence

1. **Lock existing behavior with tests.** Extract the game JSON payload builder
   from its download side effect without changing output. Capture mixed
   piece/item/BP fixtures with rotations, nonuniform scale, hidden actors,
   collections and one anchor. Test existing import/export and empty workspace.
2. **Extract the world layer.** Put host-independent modules under
   `website/world/`; leave the standalone preview as a thin host using them.
   Add explicit lifecycle/surface/renderer hooks and owned-resource teardown.
   Keep local data roots in a small opt-in config; use no production CDN fallback
   for missing generated world data.
3. **Attach one section to the editor.** Add the local feature gate and compact
   world controls, fixed shared origin, version checks, surface placement and
   compatible camera/render hooks. Keep existing editor interactions unchanged.
4. **Add project documents and storage.** Implement validation, transactional
   restore, IndexedDB revisions/recovery, Save/Open/New UI and separate build
   export. Ensure empty projects and missing-world recovery work.
5. **Prove unload/reload safety.** Exercise section replacement, failed requests,
   stale completions, repeated disposal and editing/undo through those cycles.
   Fix regressions before increasing world scope.
6. **Run the local acceptance build.** Record screenshots, hashes, interaction
   checks and resource/load metrics. Supply one project and its exported build
   for the user's final game comparison. Do not push/deploy as part of this plan.

Likely code areas: `website/basebuilder.js`, `basebuilder-transforms.js`,
`index.html`, `basebuilder.css`; new `basebuilder-project.js`,
`basebuilder-project-store.js`, a small serialization module and `website/world/`.
Update the standalone prototype imports as needed and add focused tests under
`tools/Web/`/`tools/World/`. Avoid unrelated UI, add-on or pipeline refactors.

## Acceptance Tests

### Data and Behavior

- Place a foundation/wall/floor/roof sample plus an item and BP on the section.
  Exercise selection, Ctrl-deselect marquee, G/R/S, preview rotate/flip/height,
  snapping, E, Shift+D, directional duplicate, hide/show, collections and undo.
- Record canonical authored-state hash, IDs, anchor and export payload. Unload
  world, load the second section, unload and return. All authored data and
  export fields match exactly; no world object appears in Placed or export.
- While world is unloaded, move and undo an authored object. Reload the world;
  the correct object/state survives, with no transform or anchor drift.
- Save/Open Project and reload after a confirmed autosave. Restore hidden
  placements, collections, IDs, origin, section request and camera. Export
  remains identical except `generated_unix`; project fields never leak into it.
- Repeat with no anchor, a hidden/deleted anchor, only items/BPs, empty builds,
  collection-only projects, append imports and far-from-zero coordinates.
- Existing normal-mode saved builds, reference-model import and hotkeys remain
  unchanged. World mode never overwrites their autosave.

### Failure and Lifecycle

- Missing target, malformed project, duplicate IDs, unsupported schema and
  failed authored model load leave the current project/autosave intact.
- Missing section/texture, world version/hash mismatch and cancelled requests
  preserve authored content and offer retry/disabled-context recovery.
- Force late load completion after Unload, project open and rapid section
  changes. No stale geometry, listeners, captures or UI state reappear.
- Simulate storage quota/transaction failure and two-tab revision conflicts.
  No false Saved state or overwrite of the last good revision.
- Perform 20 section load/unload cycles, including identical model URLs used
  by authored objects and scenery. Editor resources stay usable; world owned
  resources and listeners return to baseline. After garbage collection where
  available, check for monotonic heap/GPU-resource growth, not exact byte equality.

### Rendering and Performance

- Playwright desktop/mobile screenshots, canvas nonblank checks and camera
  movement; no console errors, HUD overlaps or incorrect pointer interception.
- Test perspective/orthographic camera changes, water/depth passes, world layer
  visibility and authored solid view without contaminating editor/helper renders.
- Benchmark cold/warm section loading and 100/1,000 authored placements in the
  default section. Record hardware, viewport, p50/p95 frame time, long tasks,
  input-to-response latency, export/save timing, draw calls and resource counts.
- Provisional local desktop target after loading: p95 frame time <=33 ms,
  p95 click/preview response <=100 ms. No multi-second main-thread stalls during
  normal editing. Compare with the existing builder and isolate load/decode/GPU
  costs. Report misses and address them before claiming the milestone smooth;
  do not silently remove geometry or downgrade materials to pass.
- Tests for transforms, serializer, projects, storage/lifecycle and existing
  world material adapters pass, plus JS syntax and `git diff --check`.

### In-Game Acceptance

Deliver the exported mixed sample through the user's existing game tooling and
compare anchor-relative placement, pitch/yaw/roll and scale. Verify the intended
world location through that tool's existing anchor/delivery behavior; do not
assume the browser export adds automatic absolute-location delivery.
This user-assisted check is an explicit acceptance gate, not an automated claim.

## Done Means

The source of truth is demonstrably independent of world resources. A user can
build, save, close, reopen, unload/reload context and export the same authored
build without silent omission or transform drift. Automated acceptance evidence
is recorded, known visual approximations remain visible in the audit, and the
in-game comparison is either verified by the user or explicitly pending.

## Implementation Evidence

Local validation on 2026-10-16 (reports use UTC timestamps):

- 26 browser acceptance checks passed, including 20 section load/unload cycles,
  exact authored snapshot/export equality, real terrain drag/E/move previews,
  queued unloads, import/append, collection-only/empty projects, hidden actors,
  G/R/S toggles, below-zero picking and undo persistence.
- Project rejection and missing authored-model tests retained the live build;
  retry succeeded. Missing world requests and identity mismatches retained the
  authored project. Revision conflicts, Save Copy, injected storage failure and
  failed startup recovery passed without overwriting the last good save.
- World unload resource counts stayed at 19 geometries / 43 textures / zero
  world roots throughout the 20-cycle mixed-fixture test. These are renderer
  resource counts, not a proof of zero retained browser/driver memory.
- 23 project-validation rejection cases, 92 upstream World Python tests, three
  existing JS material/pixel suites and 36 GPU depth/foam pixel cases passed.
  Desktop/mobile screenshots, nonblank canvas checks, perspective/orthographic
  switching, JS syntax and whitespace checks passed.
- The standalone viewer still passed `x3_y1` and `x4_y3` after shared-adapter
  extraction. This is not a new full-world material/parity audit.

Headless Chrome on the local i5-14600K / RTX 3090, 1600x1000 viewport:

| Authored pieces plus Dowdun | Orbit p95 | Selection p95 | Export | IndexedDB save |
| --- | --- | --- | --- | --- |
| 100 | 4.3 ms | 14.9 ms | 0.4 ms | 15.3 ms |
| 1,000 | 8.4 ms | 44.1 ms | 0.7 ms | 65.1 ms |

Cold page/section startup was 7.1 s; warm section loads were about 2.6-2.7 s.
The normal 1,000-piece builder's idle p95 was 4.3 ms. The measured 1,000-piece
world frame used 475 draw calls / 7.7 million triangles; no visual-quality
downgrade was used. Largest recorded editing/measurement long task was 90 ms.
These are provisional local measurements with repeated synthetic assets, not
claims for all hardware, all materials, mixed 10k builds or every world section.

Two integration regressions were fixed in the shared editor: stale instanced
raycast bounds after duplication/movement, and autosave not marking an undo as
a new revision in world mode. World-mode ray queries now clip against authored
bounds rather than a zero-height plane, including negative world elevations.

Evidence lives in ignored `_build/world-builder-m1/`: `acceptance-final/`,
`performance/`, `preview-regression/`, `depth-regression/` and `Validation.json`.
The visible mixed manual sample is `acceptance-final/manual-review.rsdwproject.json`
with `acceptance-final/manual-review-building.json`. Game delivery, final editor
feel and existing material approximations remain explicit user-review gates.

References: [World prototype plan](WORLD_REGION_PROTOTYPE_PLAN.md),
[world run/audit guide](tools/World/README.md), [README](README.md),
[developer guide](DEVELOPERS.md), [pipeline contract](PIPELINE_HANDOFF.md).
