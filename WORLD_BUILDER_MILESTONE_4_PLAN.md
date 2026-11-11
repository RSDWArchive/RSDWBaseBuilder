# World Builder Milestone 4: One Workspace, Shared Saves, Exact World Delivery

Status: browser implementation available for local testing. Live delivery/persistence
acceptance and the large-world performance sign-off remain open.
Prepared 2026-10-17 against the local Milestones 1-3 and whole-build import pass.

## Outcome

Give users one browser workspace with **Free Build** and **World Build**,
one project/save/recovery system, and an understood, tested route for delivering
a world-authored build to its exact saved game coordinates.

Free Build provides the existing grid and free-space placement without loading
world data. World Build provides the overview, locations, detailed scenery and
nearby streaming. Switching changes the surrounding workspace, never the build's
stored coordinates, identities, collections, visibility, anchor or undo history.

This is a local integration and delivery-verification milestone. Public world
asset hosting, world pipeline publication and full production sign-off follow it.

## Evidence and Current Gaps

- The existing free editor opens without `?world=1`. World authoring is currently
  enabled only on localhost with that query argument. Several `WORLD_MODE`
  branches also govern saves, restoration, picking and rendering, so changing
  the flag alone is insufficient to switch workspaces safely.
- Free autosave uses `RSDWBaseBuilder.autosave.v1` in localStorage; save failures
  only reach the console. World projects use IndexedDB with atomic revisions,
  current/previous recovery, visible save status and project downloads.
- World Unload pauses scenery but does not restore the free placement plane.
  Workspace mode, world navigation and temporary world residency are different
  state and must remain distinguishable.
- Project files currently use `RSDWBaseBuilder.Project.v1`, requiring world
  context. Additive catalog compatibility exists; incompatible catalogs or game
  versions still require explicit migration.
- Game JSON already stores absolute UE world centimeters and the existing
  rotation/scale values. No additional coordinate conversion is needed to
  deliver at that saved location.
- The RSDWTools source under `E:/Github/RSDToolsWorkspace/RSDWTools` already has
  **Deliver Build** calling `world.buildings.import`, which replays saved XYZ.
  **Deliver via Preview** uses the native anchor path and transforms the build
  relative to that placement. These routes also exist in the installed mod.
- Grand Exchange (1,781 pieces) and Looter Paradise 3 (12,316 pieces) pass browser
  import, whole-build preview, export, undo and recovery checks. The user has
  confirmed both imports work. This is not an in-game delivery round trip.
- Milestone 3 full-selection rotation/scale performance and the annotated world
  material/terrain comparisons remain open. This milestone does not clear them.

## User Experience

### One Entry and Two Workspaces

- Add a compact, themed **Free Build / World Build** segmented control in the
  workspace toolbar. Preserve the existing editor, catalog, inspector and HUD.
- New Project offers Free Build or World Build. Default a new ordinary project
  to Free Build; a world deep link can request World Build for a new project.
  Recovery/Open Project takes precedence and restores the saved workspace.
- Free Build shows the dynamic grid and normal placement contacts. Startup,
  editing, importing, saving and exporting must work with world URLs unavailable
  and must not fetch world manifests, overview tiles or world textures.
- World Build starts at the overview for a new world document, or restores its
  remembered location/camera for an existing one. Retain Locations, Build Here,
  Return to Build, layers, nearby streaming and the advanced unload/retry controls.
- Hide world-only navigation controls in Free Build. Retain each workspace's
  camera/projection and the world navigation state when switching away.
- Switching while a preview, marquee, gizmo gesture or atomic restore is active
  queues the request until completion/cancel. A canceled import cannot cause a
  delayed workspace change to alter its staged document.
- A mode switch preserves every authored transform and does not clear or add an
  undo action for the build. Persist the workspace/view change as project state.
- World load failure keeps authored work available and offers retry or Free
  Build. Never silently place onto an unseen floor while World Build is active.
- Keep existing Free Build reference-model behavior and its save limitations
  explicit. Reference attachments are not game export content; embedding them
  in project files is outside this milestone. Do not claim they are restored.

### Free Placement Plane and World Placement

- Persist the Free Build plane's absolute UE Z. Use zero for a new free project;
  migrate an old free autosave's plane from its saved render-origin Z.
- Derive the browser plane/grid from that absolute height and the current render
  origin. Grid extent and camera clipping retain the large-build behavior.
- Switching World -> Free restores this plane without moving authored actors.
  Grid height is workspace context, not a transform applied to the build.
- World Build retains committed detailed terrain/scenery contact, authored snap
  precedence, item/BP visual-bottom alignment and preview height offsets.
  Overview terrain, water and unavailable detail remain ineligible contacts.
- Support the existing Original Location / Place Here import choice in both
  workspaces. Original Location preserves coordinates in either workspace;
  Place Here uses the free plane/authored geometry or detailed world contact.
- Add an explicit **Place Build in World** action for an existing free prefab.
  Reuse the whole-build preview foundation to apply one rigid transform to the
  current build, using its anchor or visible bottom-center. Switching alone
  never performs this operation.
- Place Build preserves IDs and collection assignment, includes hidden actors
  in the rigid data transform, and does not duplicate/re-import the document.
  Show visible actors in the preview. Commit is one undo action; cancel retains
  the original build. Preserve pitch/roll, signed scales and relative spacing.
- Preserve one global anchor, import ID remapping, per-import collections,
  selection, hotkeys, hide/show and export filtering in both workspaces.

## Shared Project and Persistence Contract

### Project Format

Use `RSDWBaseBuilder.Project.v2` for the unified document, keeping the
`.rsdwproject.json` extension. Keep the current `build` payload and authored
transform semantics. Add a pure, tested reader/migrator for existing Project.v1
files and the legacy free autosave; older clients should reject v2 explicitly
rather than interpret Free Build as an unloaded world workspace.

The proposed v2 envelope is:

```text
schema, project_id, revision, saved_at
dataset:
  game_version, catalog_sha256, world_sha256 (nullable)
workspace:
  authoring_mode: free | world
  render_origin_cm, camera, orientation
  free_build: plane_z_cm, grid_visible, remembered_camera
  world_build: nullable remembered section/layers/navigation/camera/streaming state
delivery:
  preferred_mode: anchor | saved_world_location
build:
  existing placements, metadata, hidden state, collections, IDs and anchor
```

- Authoritative XYZ remain absolute UE centimeters. Camera offsets and the
  render origin are presentation data and never become delivery offsets.
- Keep one fixed render origin per document through workspace switches. Any
  future rendering rebase needs an independent atomic update of both layers
  and indexes, with unchanged authored data and exports.
- A new Free Build document has no bound world dataset. Switching to World
  binds a matching configured dataset only after validation. Remember that
  identity when returning to Free Build, without loading scenery there.
- Keep active mode separate from overview/build navigation and world pause.
  An old world project with `world_enabled=false` migrates to World Build with
  paused scenery, not to Free Build.
- Preserve placements, transforms, IDs, metadata, collection names/order/collapse,
  hidden actors, anchor, camera, orientation and counters during migration.
- Cross-game-version remapping is outside this milestone. Retain the original
  document and report incompatibility; do not guess new classes or coordinates.

### One Store and Recovery Lifecycle

- Extract project lifecycle from world initialization into a shared manager.
  It must initialize independently of world asset availability in both modes.
- Reuse the existing IndexedDB transactional revision/current/previous model.
  A new shared store may replace the world-specific store name, but migration
  must copy and verify source records before recording completion.
- Discover both legacy sources on the current origin. If both contain work,
  present the recovery candidates as distinct named projects with date/count;
  never choose one by overwriting the other. Reads must not alter source saves.
- Preserve project identity/revision for supported world recovery. Assign a new
  identity to a copied legacy free autosave. Keep old storage intact until the
  new transaction and round-trip validation succeed, and retain a recoverable
  source afterwards. Interrupted migration must be restartable without duplicates.
- Give both workspaces New/Open/Save/Save Copy and visible Unsaved/Saving/Saved/
  Save Failed state. Saved means the IndexedDB transaction completed for the
  captured revision, not that a timer or download was started.
- Preserve atomic Open/Import/Append: validate and prepare before replacement;
  failure/cancel retains the current build and recovery record.
- Coalesce saves and preserve immutable action capture, epoch/revision checks,
  two-tab conflict detection and exact undo restoration. Never save preview ghosts.
- Quota/blocked storage and revision conflicts remain visible. Project download
  remains usable even when browser storage fails. Explain that game JSON cannot
  retain collections, hidden actors, workspace or camera.

## Export and In-Game Delivery Contract

### Existing JSON and Explicit Intent

Keep `rsdwtools.buildings.v1`, its pieces/items/actors arrays, current precision,
pitch/roll conventions, item metadata, hidden exclusion and single-anchor rules.
Do not add scenery, camera offsets, collection fields or world meshes to it.

Add a themed export choice and remember the user's preference in the project:

| Choice | JSON coordinates | RSDWTools route | Anchor behavior |
| --- | --- | --- | --- |
| Saved World Location | Stored absolute UE XYZ, unchanged | Deliver Build / `world.buildings.import` | No relocation; an anchor is not required |
| Place Using Anchor | Same stored XYZ used as the prefab's source layout | Deliver via Preview / native anchor route | Repositions/rotates relative to the placed anchor |

- New Free Build projects prefer anchor delivery; new World Build projects
  prefer saved-location delivery. Opening or switching an existing document
  preserves its saved preference; workspace mode alone never rewrites JSON.
- For saved-location export, show the saved position/bounds and known dataset
  version. An unpositioned free prefab should have a direct path to Place Build
  in World or explicit absolute transform editing before delivery there.
- Both choices serialize the same canonical transforms. Their difference is
  delivery intent and the chosen in-game route, not another Euler conversion or
  subtraction of the anchor. A mode choice in this website cannot automatically
  control another program; identify the corresponding RSDWTools action clearly.
- Keep the existing game JSON contract in this milestone. A future delivery
  metadata extension requires agreement with the consuming project before use;
  do not emit a field and assume older tools honor it.
- Validate missing targets, finite transforms and the chosen visible anchor
  before export, with actionable errors. Preserve exports for objects whose
  surrounding world sections are unloaded or unavailable.
- A known wrong game/dataset version cannot be labeled verified. Legacy game
  JSON without version metadata keeps its coordinates and remains explicitly
  version-unverified until tested; do not infer compatibility from its filename.

### Consumer Ownership

The delivery owner is `E:/Github/RSDToolsWorkspace/RSDWTools`, particularly:

- `Exe/RSDWToolsApp/MainWindow.BuildService.cs`: Deliver Build / preview routing.
- `Mods/RSDWTools/scripts/feature_buildings.lua`: absolute import and paced queue.
- `Mods/RSDWTools/scripts/feature_build_preview.lua`: native anchor transform.
- `USER_GUIDE.md` and `docs/DRAGONWILDS_1_0_TEST_GUIDE.md`: user flow and test context.

Reuse these routes and compare repository/installed versions during verification.
If a consumer defect prevents exact delivery, record the failing fixture and
coordinate the source fix with its owner. Do not patch only the installed game
copy and leave the source/release inconsistent. No new direct game connection
or automatic spawning from the browser is part of this milestone.

## Implementation Order

1. Record the current free/world fixtures, exports, screenshots and performance
   evidence. Define v2 validation and pure v1/free-autosave migration first.
2. Extract shared project storage/lifecycle and add restartable legacy recovery,
   project downloads, visible save errors and conflict handling in both modes.
3. Separate project ownership from active world context. Implement the workspace
   selector, plane/grid restoration, remembered views and lazy world startup.
4. Route import/append, picking, previews, gizmos, instancing, bounds/index updates
   and hotkeys through the shared editor. Add Place Build in World as a staged
   rigid operation on current placements with one-action undo.
5. Add export intent UI and consumer handoff, then run automated regression,
   migration, failure and large-build tests.
6. Prepare the in-game verification pack, complete exact-location delivery and
   persistence comparisons with the user, and record acceptance evidence.

Audit each `WORLD_MODE` branch by purpose. Replace context-specific checks with
active workspace state; move persistence/restoration requirements to shared
project ownership. Do not perform a global flag replacement.

Keep one renderer, camera/control integration and render loop. Select a common
depth/precision configuration before initialization and verify free/world visual
comparisons; workspace switches must not recreate the renderer or drop authored
GPU resources. World caches, materials and section ownership remain independent.

Expected changes center on `website/basebuilder.js`, `index.html`, CSS, project
validation/store modules and the world workspace adapter. Add a small shared
project/workspace module only where it removes actual duplicated lifecycle code.
Keep `basebuilder-transforms.js` and the game serializer as the transform contract.

## Automated Acceptance

- New/open/recover in either mode, including Free Build with world requests
  deliberately failed; assert zero world-data requests during free startup.
- At least 50 Free/World switches with exact authored snapshot/export equality,
  stable IDs/collections/anchor/undo, no duplicate instances/listeners and bounded
  world-resource retention. Test queued switches during each editing gesture.
- Free plane placement, world contact placement, no world fallback plane,
  item/BP bottom alignment, snaps, preview rotation/flip/height and G/R/S editing.
- Existing free autosave and Project.v1 migration, both legacy saves present,
  interrupted migration, bad schema/version/targets and successful restart.
  Verify source records survive failures and migration creates no duplicate saves.
- Two-tab conflicts, failed/quota/blocked transactions, previous-revision recovery,
  Save Copy and downloadable projects while storage is unavailable.
- World failure/unload and canceled/failed import retain authored work. Reference
  model limitations remain explicit; game JSON continues to exclude references.
- Grand Exchange and Looter Paradise 3: Original Location and Place Here in both
  modes, separate collections, unique IDs, exact rotation/scale, undo and reload.
- Mixed piece/item/BP fixtures with nonzero rotations, supported nonuniform
  scales, negative elevations, hidden actors, one anchor and no-anchor builds.
- Place Build in World: rigid relative offsets, hidden-object transform alignment,
  unchanged IDs/collections, ghost exclusion, exact cancel and one-action undo.
- V2 download/reopen and Save Copy retain mode, plane, both cameras, world context,
  delivery preference and the complete authored payload.
- Compare canonical game JSON before/after context switches and save/reload,
  ignoring only existing timestamps. Export-choice selection itself cannot alter
  actor transforms or bake in a camera/render-origin offset.
- Match free/world desktop screenshots and canvas pixel checks against recorded
  baselines, covering perspective/orthographic, solid view, previews and selection.
  Verify the new toolbar/modal at narrow widths without adding HUD overlap.
- Reuse Milestone 3 1k/10k checks; no repeatable >10% matched-case regression.
  Record existing rotation/scale target misses as still open, not new successes.
- Run appropriate JS syntax checks, project/import/serializer/storage regressions
  and `git diff --check`. GPU browser runs stay sequential and isolated from the
  user's project; generated outputs remain under `_build/world-builder-m4/`.

## Exact-Location In-Game Acceptance

### Verification Pack

Prepare a small mixed build and known-location reference points first. Include
upright foundation/wall/floor/roof pieces, a scalable crafting station, an item
and a suitable BP actor with independent tilt/yaw/scale. Use actor-root transforms
for comparison; component mesh offsets and bounding-box bottoms are not actor XYZ.

Generate expected JSON, a browser project, screenshots/location bookmarks and a
comparison report template. Record game/catalog/world versions, RSDWTools build,
world/level identity, delivery route and fixture checksum. Legacy source builds
have unknown capture version unless supplied; record that honestly.

### Required Runs

1. Capture a known in-game fixture, import at Original Location, export without
   editing and compare canonical coordinates/rotations/scales with the capture.
2. Author/place the mixed fixture at a chosen world location, export Saved World
   Location and use RSDWTools Deliver Build. Test another location with different
   elevation, including a below-zero position where available.
3. Capture the actual spawned actor transforms through RSDWTools. Compare to the
   exported expectations and visual landmarks; screenshots alone are insufficient.
4. Save/reload the game and recapture. Verify the content persists at the same
   coordinates and report each missing, moved or transformed actor explicitly.
5. Exercise Place Using Anchor at a different point/yaw and compare the expected
   rigid anchor transform. This verifies the existing prefab workflow as well.
6. Deliver the two large sample builds through saved-location delivery in an
   isolated test save, one at a time, using original and browser-chosen positions
   as appropriate. Wait for the paced queue to finish and audit all results;
   submitted requests or a few correct screenshots do not prove completion.

Use a backed-up/disposable game save and an empty test destination so repeat runs
do not create indistinguishable duplicate actors. Keep the user's normal builds
out of cleanup. Record every spawned test actor so repeated runs and cleanup
remain traceable.

### Comparison Rules

- Dispatch coordinates and rotation/scale inputs must equal the serialized JSON.
  Actual engine transforms target <=1 cm position error, <=0.1 degree orientation
  error and <=0.001 scale error per component; record the maximum and outliers.
- Compare equivalent rotation matrices/quaternions at Euler wrap/gimbal boundaries
  so alternate channel representations do not create false failures. A sign flip,
  90/180-degree offset or terrain/anchor recentering is a real failure.
- Match actual actors by verified class/data-asset identity and transform, with
  duplicate-aware one-to-one matching. Runtime-generated piece IDs/GUIDs need not
  equal browser IDs; link the first actual capture to its persistence recapture.
- Include pieces, items and actors; report expected versus actual counts and
  skipped/failed delivery entries. Hidden browser actors are absent by design.
- Separate initial delivery transforms from subsequent physics, NPC movement or
  native unsupported-transform behavior. Document those limitations explicitly;
  do not compensate by changing browser export signs or all asset origins.
- Caves/vaults need verified level context when tested. A browser section label
  is a streaming grouping, not proof of the native level needed for delivery.

BaseBuilder can prepare fixtures and comparisons locally. Live verification needs
the running game, correct companion tooling and user participation where game UI
actions are required. Keep status `pending_in_game` until actual evidence exists;
successful browser import is not a substitute. If the game is unavailable, deliver
the ready verification pack and report the milestone's acceptance gate as open.

## Completion and Follow-On Work

Implementation is complete when both workspaces use shared recoverable projects,
switching preserves all authored data, old saves migrate safely, and both export
intents have tested browser behavior and a concrete in-game route.

The milestone is accepted only after the measured exact-location delivery and
game save/reload checks pass, with all omissions/outliers explained and corrected.
Store automated reports, migration evidence, delivery inputs, actual captures and
comparisons under ignored `_build/world-builder-m4/`; summarize results and any
remaining manual gate in this plan and the local guide.

Public hosting/versioned world packages, master-pipeline publication, cross-game
project migration, reference attachments, remaining 10k optimization, lower-resource
hardware acceptance, full mobile polish, NPC/world editing and annotated terrain/
material parity remain separate work. Do not call the whole product production
ready merely because this milestone passes. Release packaging must preserve the
committed source/metadata policy and exclude generated world data and test saves.

References: [local guide](tools/Web/WORLD_BUILDER_LOCAL.md),
[Milestone 1](WORLD_BUILDER_MILESTONE_1_PLAN.md),
[Milestone 2](WORLD_BUILDER_MILESTONE_2_PLAN.md),
[Milestone 3 evidence](WORLD_BUILDER_MILESTONE_3_PLAN.md),
[world audit guide](tools/World/README.md),
[pipeline handoff](PIPELINE_HANDOFF.md).

## Implementation Results (2026-10-17)

### Available Locally

- The same editor now offers Free Build / World Build, Project.v2 downloads and
  shared transactional autosave/recovery. Free startup makes no world-data requests.
- Free plane height, fixed render origin, workspace cameras, remembered world
  context and delivery preference are saved independently of authored transforms.
  Switching waits for active edits and never relocates or adds undo entries.
- Project.v1 and legacy free autosaves migrate into the shared store without
  deleting source records. Migration markers/data commit together; restart does
  not create duplicate copies. Valid previous revisions can recover even if the
  current legacy revision is invalid. Incompatible saves remain retained.
- Original Location / Place Here imports work in both workspaces, with individual
  collections and unchanged game export. Place Build in World moves the current
  build, including hidden actors, with preserved IDs/collections and one undo.
- Export choices retain identical canonical JSON and identify the companion
  delivery route. Saved coordinates/version are shown; unversioned original game
  captures are not labeled verified. Reference attachments explicitly remain unsaved.
- One logarithmic-depth renderer is used throughout. World contexts are lazy,
  deactivate independently of authored content, remove their event listeners on
  disposal, and retain compatible rendering caches. Editing/depth shader variants
  are prepared for newly created contexts. Camera restoration avoids overview
  zoom clamping; unchanged save-status text no longer rewrites the HUD every orbit frame.

### Automated Evidence

Ignored reports are under `_build/world-builder-m4/`:

- `acceptance-final/Acceptance.json`: final combined run, 15 passing checks with
  no browser errors, including both real builds and the additional failure cases.
- `acceptance/Acceptance.json`: both actual sample builds tested with Original
  Location and Place Here in Free and World modes, undo, collections, export
  transforms and reload. Grand Exchange: 1,781 pieces; Looter Paradise 3: 12,316.
- `final-workspace/Acceptance.json`: shared recovery, both delivery choices,
  plane persistence, two-tab revision conflict, Save Copy, quota fallback, both
  legacy recovery sources, reference limitations and unavailable-world fallback.
- Switch checks cover 52 switches, including 25 cycles with paused world context,
  exact authored/export equality and stable renderer/root/resource counts. Actual
  detailed-world loading is covered by import and whole-build-placement tests;
  these are not 50 full dense-section residency cycles.
- Place Build checks include hidden-actor rigid transforms, exact cancel,
  unchanged identities/collections/anchor and one-action undo. Desktop, narrow,
  perspective, orthographic and solid-view screenshots/canvas checks are included.
- `storage/Storage.json`: immutable revisions, previous-save retention, conflict,
  interrupted migration/restart, aborted transaction rollback and blocked-store errors.
- `free-adapter/AdapterValidation.json`: normal Free Build duplicate/delete/hide,
  undo, shared autosave recovery, desktop/mobile canvas and static NPC instances.
- Pure project/migration/import/game-comparison checks pass. The world-data scan
  validates 314 sections, 871,578 distinct placements and 574 terrain/overview tiles.
- 47 JavaScript modules pass syntax checks. Whitespace/static checks pass; generated
  benchmark IDs use the project-compatible `obj_` format so project validation and
  recovery also work for synthetic scenes.

### Remaining Acceptance Gates

The performance runs recorded an unresolved wide-view slowdown in this test
environment. `performance-matched/Performance.json` uses the prior 820 x 767
render buffer and fixed sample origin: 10k full-view p95 was about 46 ms and
orthographic p95 about 46-50 ms. `performance-final/Performance.json` repeats the
full view after cache/status/shader changes: about 42-46 ms, with some clicks above
100 ms. Previous evidence was about 29-33 ms for wide views. Historical browser
foreground/driver conditions are not fully matched, so this is not proof of one
specific code regression; it is also not a passed <=10% regression gate. Keep the
performance gate open and profile/retest in a controlled foreground environment.
No quality reduction was made to compensate. Milestone 3's existing move-all,
full-selection rotation/scale and lower-resource hardware gates remain separate.

The local wide-view follow-up below supersedes this earlier wide-view result,
not the separate continuous bulk-edit, hardware or in-game acceptance gates.

`game-verification/` contains a small mixed fixture, browser projects, canonical
exports, checksums, consumer script hashes, instructions and a report template.
The repository and installed `feature_buildings.lua` / `feature_build_preview.lua`
hashes match. `VerifyGameDelivery.mjs` compares actor-root transforms with duplicate-
aware one-to-one assignment and equivalent quaternions, ignores runtime IDs, and
fails missing/extra actors or incomplete captures. It also accepts an actual native
anchor/delta file for relative-delivery expectations. Mathematical below-zero
fixtures still need a safe in-game destination chosen manually.

The game was not running during this implementation. No actors were delivered,
and no live engine or save/reload captures exist. Status remains `pending_in_game`.
Use the verification pack in a backed-up/disposable save, wait for paced queues,
and record actual game/tool versions and level identity before acceptance. Existing
terrain/material manual verification annotations and production-hosting gates
remain open. Nothing has been committed, pushed or published by this pass.

## Wide-View Follow-Up (2026-10-17)

### Changes

- The depth and color passes share one scene-transform update and one frustum
  classification per frame. Visibility/culling flags are restored synchronously,
  including on render errors. Parent-mesh culling never suppresses visible children.
  Unknown scene/object/material render callbacks keep automatic matrix updates.
- Autosave makes one acknowledged write per background attempt, then debounces
  any newer edits. It no longer continuously writes full projects while camera
  changes arrive during an in-flight save. Explicit saves still wait for older
  writes and acknowledge the requested edits; failures retain the last revision.
- No mesh, texture, material, shader, resolution, world-streaming policy,
  placement transform, project format or game export format changed.

### Measured Results

`_build/world-builder-wide/final-performance/Performance.json` passes all frame/
input targets across 18 samples: 1,000 and 10,000 mixed authored objects, three
views and three repetitions of 240 moving-camera frames. The 10k case includes
17,008 read-only world placements in `x3_y1` / `x4_y1` and all 574 overview tiles.

| 10k View | Frame p95 Across Runs | Click p95 Across Runs |
| --- | --- | --- |
| Full perspective | 20.9-25.0 ms | 48.8-76.3 ms |
| Close perspective | 8.4-8.5 ms | 20.4-23.6 ms |
| Full orthographic | 25.0 ms | 50.1-71.0 ms |

All measured p99 frame values are below 30 ms. The full perspective still submits
2,154 color draws / 81,799,103 triangles at the starting camera, with the same
1,051 depth draws / 17,028,671 triangles. This is not a quality or visibility cut.
The run uses isolated headless Chrome, RTX 3090 / i5-14600K, a 1600 x 1060 browser
viewport and an 820 x 739 render buffer. It does not guarantee performance at
larger buffers or on lower-resource hardware. The 50 NPC select/deselect cycles
also pass the texture/resource retention check.

The pre-change source snapshot and diagnostic profiles are under `baseline/`;
`first-pass/` and `culling-pass/` retain intermediate measurements. Profiling
confirmed repeated matrix traversal and a first-run autosave write storm.
Historical 42-46 ms measurements were not taken under identical driver/browser
conditions, so do not attribute that entire difference to these changes or claim
an exact percentage improvement from those historical numbers.

### Regression Evidence

- `images/Rendering.json`: the same 10k/world scene is pixel-identical before and
  after, in both perspective and orthographic views; game exports remain identical.
- `render-flags/Rendering.json`: 10 focused cases, including transform-mutating
  render callbacks, manually updated scenes, visible children of off-screen mesh
  parents, hidden objects, instancing and exception cleanup. Matrix traversal is
  reduced from three to one for the ordinary two-pass scene.
- `depth/WaterDepthValidation.json`: 48 GPU pixel cases covering water/foam,
  standard/logarithmic depth, both projections, alpha cutouts and render-state
  restoration. Unknown deformation retains the existing conservative fallback.
- `instances/InstanceValidation.json`: signed transforms, rendering equivalence,
  instance mapping, depth-region filtering, visibility, migration and disposal.
- `large-editor/Acceptance.json`: nine 10k checks covering selection/marquee,
  move/rotate/scale, snap, duplication, hidden export exclusion, undo and recovery
  with unloaded world detail. Duplicating all 10k produces 20k unique objects and
  remains one undo action; this is not a 20k rendering acceptance claim.
- `autosave/Autosave.json`: four checks covering background-write coalescing,
  an explicit save queued behind an older write, an automatic trailing camera
  save and failed-save retention. Free adapter, transform-intent, project
  validation, storage, build-import and delivery-comparison checks pass.
- `workspaces/Acceptance.json`: all 15 shared-workspace checks pass, including
  both real builds (1,781 / 12,316 pieces) using Original Location and Place Here
  in Free and World modes, shared recovery, workspace switching, conflicts,
  failed-save fallback, hidden actors, references and narrow-screen rendering.
- All 67 JavaScript modules pass syntax checks; whitespace checks pass for the
  tracked changes and all eight files edited by this follow-up.

The remaining in-game delivery, material/terrain verification, public hosting,
lower-resource hardware and continuous full-selection edit gates stay open.
Generated reports, profiles, screenshots and fixtures remain ignored in `_build/`.
