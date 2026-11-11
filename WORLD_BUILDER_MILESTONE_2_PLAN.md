# World Builder Milestone 2: World Overview and Nearby Streaming

Status: implemented locally; automated acceptance complete, manual review pending.
The 10k-authored stress case works but does not meet the smooth-editing targets.
Prepared 2026-10-17 against the local Milestone 1 builder and standalone viewer.

## Outcome

Open the builder onto a recognizable whole-world overview, click a location to
build there, and explore across section boundaries without manually managing a
list of section IDs. Stream nearby detailed scenery while keeping every authored
placement, collection, anchor, undo history and exported transform unchanged.

The experience is one continuous world, not every detailed model permanently
resident in memory. Existing project recovery takes precedence over the new-map
startup screen. This remains a local, opt-in milestone under `?world=1`.

## Foundation at Planning Time

- Milestone 1 uses the existing editor's scene, renderer, camera and controls.
  World ownership and project saving are separate from authored placements.
- `website/world/world-layer.js` currently loads one complete section and
  releases the previous generation, including its per-generation asset caches.
  Calling that method repeatedly is not sufficient for incremental streaming.
- `website/basebuilder-world-workspace.js` currently saves one requested section
  and one camera. The project validator requires these fields.
- The standalone `tools/World/preview/world-browser.js` already provides coarse
  overview terrain, section markers, area filters and a 520 m detail window. Its
  camera-coordinate assumptions, DOM listeners and replacement lifecycle cannot
  be copied unchanged into the builder.
- The current `1.0.0.5` output has 314 sections, 574 overview terrain tiles and
  8,407 asset definitions. Read counts, bounds and labels from generated data;
  these numbers are a baseline, not constants.
- Existing generated inputs are `WorldIndex.json`, `WorldShared.json`, section
  manifests and `SpanningPlacements.json`. No world regeneration or new archive
  extraction is expected for this milestone.

## User Experience

### World Map

- A new world project starts in a whole-world overview. Restore/Open Project
  restores its saved location and navigation state instead.
- Use the existing coarse terrain and material adapters, loaded progressively.
  Show useful terrain as soon as available; no new full-screen app or renderer.
- Add a compact World Map control and a searchable area/location picker using
  existing section names and biome groups. Keep IDs in secondary details only.
  Group labels are inferred classifications, not verified game place names.
- Hover/focus identifies a destination. Clicking terrain chooses the actual hit
  location, not the center of the section. Clicking a section marker chooses a
  validated content focus. Ignore pointer drags and clicks consumed by HUD UI.
- Keep markers for areas without overview terrain. Caves, Sand Vaults and
  Outlying Scenery remain discoverable through filters and the picker, even when
  buried or isolated geometry would be hard to identify from the surface map.
  Ambiguous overlapping destinations offer a choice instead of guessing a cave.
- Add a navigation marker for the authored build, derived from authored bounds,
  with Return to Build. It is a helper, never an authored/exported object.
- Retain the existing theme and compact controls. Desktop and narrow-panel
  layouts must not overlap the asset browser, inspector or viewport hotkey HUD.

### Enter and Explore

- Clicking a destination records navigation intent, starts its detail load and
  moves toward a build-scale view. Refine elevation from detailed terrain when
  ready, or use non-helper content bounds for terrainless locations. Never move
  authored objects, change the anchor or recenter their coordinates.
- A clicked destination is not restricted to that section. Panning across a
  boundary automatically requests nearby detail. Orbiting in place must not
  repeatedly unload/reload the same scenery.
- Display destination/loading/ready/partial/error states. A failed destination
  offers retry and return; existing authored work remains saveable/exportable.
- World Map returns to the overview and remembers the last build camera.
  Return to Build restores that camera and requests nearby detail. With no saved
  build view, use authored bounds or the last chosen destination as fallback.
- Home/0 retains its current authored-build framing behavior. In build view with
  no authored objects, frame nearby loaded detail; in overview, frame the map.
  Background streaming must never trigger camera framing.
- Put manual section selection, Load/Unload and Frame Section under advanced
  world controls. Manual unload pauses streaming until explicitly resumed;
  camera movement must not immediately reload a deliberately unloaded world.
- Overview is navigation-only for world clicks; build view keeps existing
  selection, marquee, preview and gizmo behavior. Do not introduce conflicting
  hotkeys or feed a map-navigation click into authored-object selection.

### Placement Safety

- Coarse overview terrain is a navigation surface, never a final placement
  surface. Only eligible, committed detailed geometry provides world contact.
- Retain Milestone 1 surface rules, authored snapping precedence, BP/item bounds
  offsets and preview height offsets. Do not invent world snap plugs.
- If a required surface is loading or missing, show unavailable contact and
  block confirmation, rather than placing on the overview or an invisible plane.
  Contact with eligible authored geometry remains usable as it is today.
- During catalog drag, E-preview, object drag or a gizmo gesture, pin the active
  detail generation. Fetch/decode may continue, but queue world scene attachment,
  eviction, mode changes and camera navigation until the edit finishes/cancels.
  Recompute the desired neighborhood afterwards and discard obsolete results.

## Architecture and Ownership

Keep the existing authored root and helpers. Split the world layer internally
into independent overview, detailed-section and navigation-helper roots.

Extract reusable overview/marker rendering out of the standalone host. New
modules under `website/world/` should expose host-independent behavior; the
builder owns DOM events, camera changes and the single render loop. Adapt the
standalone viewer to the shared helpers and keep it functional for visual audits.

### Incremental Residency

- Add a pure streaming planner that consumes absolute UE camera-target
  coordinates, projection/zoom, dataset bounds, navigation intent and residency.
  It returns desired, retained, pinned and deferred section IDs with priorities.
- Maintain a section registry with unloaded, queued, loading, ready and failed
  states. Load only additions and evict only sections outside the retained set.
  Neighbor changes must not replace every already loaded world object.
- Stage each section off-scene, attach it only after validation, and preserve
  overlapping ready detail until replacements are usable. Failures must not tear
  down unrelated ready sections. Partial results cannot claim full coverage.
- Keep terrain source IDs and spanning placement IDs globally deduplicated across
  resident sections. Reference counts decide when shared geometry/instances can
  be removed. Load spanning geometry by intersection, not merely its home cell.
- Share a bounded, world-only model/material/texture cache across resident
  sections. Explicit acquisition/release must cover decoded GLTF resources,
  mirrored geometry, material variants, texture color-space variants and instance
  buffers. Evict unused entries; never dispose resources still used by neighbors.
- Preserve the separate editor asset cache. Shared URLs do not imply shared
  ownership. No world disposal may traverse or release the authored root.
- Use generation tokens and abort signals at project, dataset and section level.
  Late GLTF/decode completions are disposed/released without attaching. Failed
  cache promises must be removable for retry. Include listener/marker cleanup.
- Use one shared world depth/water pass, not a separate pass per section. Restore
  host renderer state and preserve current terrain, water, foam and material
  fixes. Keep manual-verification annotations; this is not a new parity claim.

### Initial Streaming Policy

These are explicit starting settings to measure and tune, not performance claims:

| Setting | Initial behavior |
| --- | --- |
| Detail area | 260 m XY radius around the build-view focus, matching the old 520 m window |
| Retention | 400 m radius for existing detail to reduce boundary thrashing |
| Planning | About 300 ms debounce, 100 m quantized movement; explicit destination loads immediately |
| Residency | Four ready detailed sections initially; prioritize destination/contact section, then nearest neighbors |
| Staging | One additional section building at a time; retire unneeded entries before exceeding the budget |
| Work limits | Global eight asset jobs and four Draco workers, not multiplied per section |
| CPU metadata | Bounded manifest cache, initially 12 sections |
| Overview | Coarse world context stays available; detail replaces covered overview tiles visually |

Retain complete section geometry for the first implementation; do not rebuild
instance buffers every time the camera moves a few meters. The planner uses
section bounds intersecting the detail area, not just section-center distance.
Large sections and pinned edits can exceed soft estimates; report that explicitly
and defer lower-priority requests rather than removing the active contact surface.

Record estimated decoded geometry/texture bytes and resource counts as well as
section count. Browser APIs do not provide a reliable universal GPU-memory total.
Add an estimated memory ceiling to the policy after baseline measurements; four
sections alone is not a guarantee of fitting dense areas. Do not silently reduce
texture quality or omit models to satisfy the budget. Reduce distant residency,
retain overview coverage and report deferred detail instead.

Use projection-aware viewport scale for overview/detail transitions; perspective
camera distance alone fails for orthographic zoom. Add enter/exit hysteresis.
Use a terrain-tile ownership mask to prevent overview/detail z-fighting and avoid
removing coarse coverage until the detailed replacement is attached. Terrainless
areas use content bounds and markers rather than an empty framing target.

### Coordinates, Camera and Picking

- Keep UE centimeters authoritative and the Milestone 1 render origin fixed for
  each project/session. Overview, section bounds, markers, camera queries and
  surface hits must all convert through the same origin-aware helpers.
- Do not reuse the old controller's zero-origin `controls.target * 100` math.
  Do not apply authored JSON pitch/roll corrections to cooked world matrices.
- Compute overview clipping/framing separately from detailed placement picking.
  Tighten near/far planes on returning to build scale without clipping distant
  authored objects. Reuse perspective/orthographic camera switching and gizmos.
- Keep detailed surface bounds per section and query nearby candidates before
  mesh intersection. Multiple resident sections must not turn every preview
  pointermove into a full-world raycast. Preserve nearest-hit ordering.
- Test precision at the dataset's positive/negative extremes and far from the
  saved origin. Automatic floating-origin rebasing is deferred unless measured
  precision failures make it necessary; do not silently introduce it here.

## Project Saving and Compatibility

The game JSON schema stays exactly `rsdwtools.buildings.v1`. Export includes all
eligible authored placements across the project, independent of camera location,
resident sections or area filters. Hidden-object exclusion stays unchanged.

Extend the project workspace additively, retaining `RSDWBaseBuilder.Project.v1`,
the existing camera/origin fields and `requested_section_id` for compatibility:

```text
workspace.navigation (optional for old projects)
  mode: overview | build
  streaming_enabled: boolean
  area_filter: all | generated group name
  focus_cm: absolute UE destination/focus
  last_build_camera: existing absolute camera format, or null
  overview_camera: existing absolute camera format, or null
```

- Current `workspace.camera` remains the actual active camera; the two additional
  views are return locations. `requested_section_id` records the last explicit
  destination/fallback, not a list of runtime resident sections.
- Normalize older Milestone 1 projects to build view at their saved camera,
  streaming enabled if the world is enabled, and no area restriction. Loading the
  existing six-object sample must preserve its origin, IDs and export exactly.
- Validate optional navigation fields, finite coordinates and camera values.
  Stale filters fall back to All with a warning. A missing destination can resolve
  from the saved focus in a matching dataset; a dataset identity mismatch must
  retain the existing disabled-context warning, never switch world versions.
- Keep `world_enabled` as the master world visibility/load intent. Pausing nearby
  streaming and showing the overview are separate from disabling world context.
  Save both explicit intent and the current navigation view.
- Do not persist resident IDs, resource handles, cached payloads, loading states
  or temporary gesture pins. Reconstruct residency from saved intent on restore.
- Navigation changes use existing revisioned autosave with coalescing. Streaming
  completions alone do not resnapshot a large authored build or create revisions.
  Preserve quota errors, prior recovery revision and multi-tab conflict handling.
- This is forward opening of older projects in the new editor, not a promise that
  an older editor will retain new navigation fields after resaving a project.
- Keep normal-builder autosave, Blender output and build Import/Append behavior
  unchanged. Prefab placement relative to a clicked map location remains deferred.

## Implementation Sequence

1. **Capture the baseline and contracts.** Preserve Milestone 1 fixtures and
   regression tests; record hashes for authored snapshots and parsed game exports.
   Add pure tests for origin-aware section queries and projection-aware planning.
2. **Extract and integrate overview navigation.** Share terrain/marker helpers,
   add map/build navigation and search, and enter a clicked destination using the
   existing single-section loader first. Validate pointer ownership and cameras.
3. **Implement section residency and resource ownership.** Add incremental loads,
   deduplication, world-only cache leases, staged commits and bounded scheduling.
   Prove resource lifetime before enabling automatic camera-driven requests.
4. **Enable nearby streaming.** Add planner, hysteresis, gesture pinning, progressive
   coverage, failure/retry status and advanced manual overrides. Preserve existing
   material adapters and detailed surface contact behavior.
5. **Extend project persistence.** Normalize old documents, save map/build views
   and navigation intent, and retain transactional restore/recovery safeguards.
6. **Validate and tune locally.** Run full manifest/section coverage checks,
   targeted live navigation and editor tests, and dense-area performance passes.
   Supply a local sample project, metrics and manual-review checklist.

Likely files: `website/basebuilder-world-workspace.js`, `website/world/world-layer.js`,
new overview/navigation/streaming/cache helpers under `website/world/`,
`website/basebuilder-project.js`, narrowly scoped editor host hooks,
`website/index.html`, `website/basebuilder.css`, standalone preview adapters and
tests under `tools/Web/` and `tools/World/`.

## Acceptance Tests

### Navigation and Coverage

- New project opens the whole map; old/new saved projects restore their own view.
  Terrain click, marker click, picker search, Return to Build and World Map work.
- Test all 314 current manifests automatically for valid destinations, bounds,
  coverage and ID ownership. Use generated counts for future versions.
- Live browser cases include Dowdun Reach, an adjacent boundary crossing, dense
  trees/buildings, water/shoreline, dunes, caves, Sand Vaults, Outlying Scenery and
  both coordinate extremes. Distinguish unloaded, deferred and failed content.
- Test continuous pan, orbit, orthographic zoom, rapid teleports and repeated
  boundary crossings. No repeated requests for unchanged residency, duplicate
  world objects, stale attachments, missing seams or camera jumps after loading.
- Overview and detailed terrain never visibly double-render. Terrainless markers
  enter useful content, and no underground blocker determines surface framing.

### Authored Data and Editing

- Build across at least three sections with pieces/items/BPs, nonuniform scale,
  rotations, one anchor, hidden objects and collections. Navigate away, unload,
  return, save/open and recover after refresh.
- Authored state and game export stay identical before/after scenery-only changes,
  excluding only intentional timestamps/workspace navigation fields. Nothing is
  hidden, deselected, renumbered, reassigned or removed by background streaming.
- Move/undo in unloaded areas and reload. Test clear/undo, import/append, empty
  projects, collection-only projects and anchors outside resident detail.
- Exercise all preview paths across boundaries plus selection/marquee, gizmos,
  snapping, duplicates, hide/show, solid view and export. Section completion during
  an active gesture cannot replace its contact surface or intercept its input.
- Saving while detail loads/fails preserves complete authored state. No world
  object, navigation helper or project-only field enters game export.

### Failure, Lifecycle and Performance

- Missing/invalid overview, section and asset requests, version mismatch, retry,
  cancellation, out-of-order decode and project replacement preserve builds.
- At least 50 load/evict cycles plus rapid destination changes: world resources
  return to a stable bounded baseline; authored caches remain usable. Measure
  texture/geometry/instance counts, estimated bytes and heap trend, not just roots.
- Verify one renderer, one control stack, one depth pass and no listener growth.
  Keep UI responsive during progressive loading, especially synchronous GPU upload.
- Benchmark one/four resident sections with 100/1,000 authored objects, including
  varied assets, not only one repeated model. Add a 10k-authored stress result,
  explicitly separate from the primary acceptance target.
- Record cold/warm overview and destination load times, first useful map frame,
  frame p50/p95, input latency, load-time long tasks, draw calls, triangles,
  network/cache reuse, resource estimates, export and autosave time.
- Retain provisional local desktop gates: steady editing p95 frame <=33 ms and
  p95 click/preview response <=100 ms; no multi-second main-thread stall during
  normal navigation/editing. Compare identical hardware/viewports against M1.
  Report/tune dense-area misses; do not claim smoothness by silently dropping
  nearby required geometry or downgrading visual quality.
- Run existing project/serialization, material/depth and normal-editor regressions,
  JS syntax and whitespace checks. Capture desktop/narrow/mobile screenshots,
  nonblank canvas checks and real camera/placement interaction evidence.

## Delivery and Manual Review

Deliver a local working URL, updated local guide, old/new compatible sample
projects, a cross-section sample export, automated results and measured streaming
policy. Store generated test artifacts under ignored `_build/world-builder-m2/`.

Ask the user to verify recognizable map navigation, destination choice, loading
transitions, editor feel and game delivery of the cross-section sample. Existing
terrain/material approximation notes remain pending where not verified in-game.
Absolute-location game delivery still depends on the external delivery tool;
map navigation does not change that contract.

No deployment, commit/push, Blender packaging, NPC overlays, terrain editing,
custom bookmarks, cloud saves, public world hosting or all-detail-resident mode
is included. Location/NPC integration can build on this navigation layer later.

Done means the whole world is navigable in the builder, nearby detail streams
within a measured budget, and authored work is demonstrably independent of every
navigation/loading/eviction path. Manual verification is recorded separately from
automated completion.

References: [Milestone 1](WORLD_BUILDER_MILESTONE_1_PLAN.md),
[local builder guide](tools/Web/WORLD_BUILDER_LOCAL.md),
[world prototype/audit guide](tools/World/README.md).

## Implementation Handoff (2026-10-17)

The local `?world=1` builder now provides the overview, map/terrain/marker
navigation, generated area/search controls, Return to Build, nearby residency,
manual pause/unload/retry, and additive project navigation persistence described
above. Normal builder startup and the public game JSON format are unchanged.

### Implementation Boundaries

- `website/world/world-streaming.js`: pure planner, job limits and lease cache.
- `website/world/world-resources.js`: separate world resource ownership,
  material/model sharing and decoded resource estimates.
- `website/world/world-layer.js`: staged section commits, overlapping source ID
  deduplication, shared terrain/spanning ownership, contact queries and one depth
  pass. Texture upload is spread across frames; shaders prepare before attachment.
- `website/world/world-overview.js` and `world-navigation-visuals.js`: progressive
  navigation terrain/markers. Marker/picker focus uses actual overview terrain
  contact where available; final placement still requires committed detail.
- `website/basebuilder-world-workspace.js`: editor navigation and saving. Camera
  navigation and scene commits wait for active editing gestures.
- `website/basebuilder-project.js`: optional validated navigation fields and
  backward-compatible Milestone 1 defaults.
- Narrow world-mode editor hooks prepare editable shader variants on project load
  and update Placed-row/collection selection state in place. This avoids rebuilding
  hundreds of controls on every selection; normal-builder behavior is unchanged.

The initial soft resident-detail estimate is **2.5 GiB**, four ready sections and
one staged section. This is not a hard VRAM cap. A mandatory destination can exceed
it; optional neighbors are explicitly deferred. Dense-area tests measured roughly
3.3-4.9 GiB in some destinations. Complete-section loading remains intentionally
unchanged; subdividing those dense sections is a future optimization, not a visual
quality reduction hidden in this milestone.

### Verification Evidence

- Pure/data tests checked all 314 manifests, 574 terrain/overview tiles, 871,578
  unique source placements and 10,060 intentional overlap references. Planner,
  resource leases, late completion cleanup, retry, concurrency and old/new project
  validation passed.
- Navigation acceptance includes real map-marker clicks, picker entry, adjacent
  streaming with no duplicate source instances, exact authored/export comparisons,
  save/reload, missing-section retry, manual unload and orthographic navigation.
- All 12 navigation checks and 27 final editor regression checks passed. The
  cross-section fixture preserved all six authored objects, hidden state,
  collections and game export across three destinations and unload/save/reload.
  Desktop, narrow and mobile screenshots/pixel checks passed; the lower inspector
  remains scrollable to its Placed controls at narrow widths.
- The editor regression completed 50 load/unload cycles. After both destinations
  warmed, renderer allocations remained at 23 geometries / 47 textures; detailed
  world roots and model-material bundle/override-texture leases returned to zero.
  These are retained editor/overview allocations, not a zero-memory browser claim.
- Browser coverage reached all eight generated area groups, including Outlying
  Scenery. The initial long area sweep stalled before its last Dowdun destination;
  the isolated rerun passed Dowdun and Outlying Scenery after the terrain-focus and
  texture-upload fixes. Keep the interrupted trace as diagnostic evidence rather
  than treating it as a passed sweep.
- Standalone preview regression passed `x3_y1` and `x4_y3`. Shared water/depth tests
  passed all 36 GPU pixel cases. Existing manual material annotations remain open.

Generated evidence is under ignored `_build/world-builder-m2/`: `editor-acceptance`
(50 cycles), `editor-tuned` (final 27 checks), `acceptance-final`,
`terrain-navigation`, `area-audit`, `preview-regression`, `depth-regression`,
`cross-section`, `performance-tuned` and `performance-four`. `performance` is the
pre-tuning comparison, not the final acceptance result. Read each report's status;
interrupted runs are retained as diagnostics, not acceptance results.

### Measured Performance

Local headless Chrome, 1600 x 1000, i5-14600K, RTX 3090, approximately 128 GiB RAM.
Values below are p95 milliseconds, not a guarantee for other devices or regions.
The four-section case uses a lower-density border; dense cases correctly defer
neighbors under the soft memory policy instead of forcing four sections resident.

| Authored objects | Ready sections | Frame | Selection to next frame |
| --- | --- | --- | --- |
| 100, varied | 2 | 12.6 | 24.6 |
| 1,000, repeated | 1 | 12.7 | 26.9 |
| 1,000, varied | 2 | 20.7 | 26.2 |
| 100, varied | 4 | 8.5 | 27.1 |
| 1,000, varied | 4 | 12.6 | 35.0 |
| 10,000, varied stress case | 2 | 83.2 | 207.8 |

Both final benchmark reports meet the provisional <=33 ms frame / <=100 ms
selection targets for the primary 100/1,000-object milestone. The earlier selection
miss (186-299 ms) was reduced by avoiding placed-list reconstruction and preparing
editable shader variants ahead of selection. No scenery/model quality was reduced.

The stress case successfully created, selected, saved and exported 10,000 authored
objects, but is **not smooth**. Its p95 picking and selection CPU work were about
2.9/3.7 ms; frame/rendering cost is now the larger limitation. Export took about
11 ms and the awaited project save about 543 ms. Further rendering work should
investigate spatially chunked instance batches and dense-section subdivision;
do not treat this as a completed 10k world-editor performance milestone.

The first overview tile appeared in about 1.1 seconds. Initial requested-neighborhood
settling took roughly 23-25 seconds; HTTP-cache-warm rebuilds after project
replacement took roughly 8-22 seconds. Tiles/detail appear progressively before
the entire queue settles. These timings include loading and preparation, and are
separate from steady editing results. They do not imply all 574 tiles appear in
1.1 seconds or that a retained neighboring section takes that long to activate.

### Manual Review Still Required

1. Verify recognizable destinations, area filters, loading transitions, orbit/pan,
   orthographic views and the narrow-screen layout in your normal browser.
2. Place and snap pieces/items/BPs on detailed scenery. Navigate away, unload,
   save/reopen, return and verify the authored work and undo behavior.
3. Use the mixed sample for in-game delivery checks. The separate cross-section
   fixture deliberately spreads objects across three sections; it is not a compact
   prefab. Verify the delivery tool's anchor/absolute-location behavior separately.
4. Recheck prior terrain, water, shoreline, dune and material approximations in-game.
   Navigation success is not visual-parity approval.

No deployment, commit/push, generated-world regeneration or Blender packaging was
performed for this milestone.
