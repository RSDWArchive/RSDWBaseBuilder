# World Builder Milestone 3: Quality-Preserving 10k Performance

Status: implemented locally; functional/visual checks passing, performance
acceptance remains open. This milestone is not fully signed off.
Prepared 2026-10-17 against the implemented Milestone 2 workspace.

## Outcome

Make 10,000 authored placements responsive to navigate, select and edit while
nearby world scenery is loaded. Preserve the existing visual result, controls,
building behavior, project recovery and game exports. Improve loading without
replacing a valid build with a partially prepared one.

This is an optimization of the existing editor, not another editor or a new
rendering engine. World mode remains local and opt-in under `?world=1`.

## Evidence and Diagnosis

The final Milestone 2 measurements are in ignored
`_build/world-builder-m2/performance-tuned/Performance.json`. They used headless
Chrome, a 1600 x 1000 browser viewport, i5-14600K, RTX 3090 and approximately
128 GiB RAM. The actual drawing buffer is smaller than the browser viewport.

| Case | Frame p95 | Selection to next frame p95 | Pick CPU p95 | Selection CPU p95 |
| --- | --- | --- | --- | --- |
| 1,000 authored, 7 targets, 2 ready sections | 20.7 ms | 26.2 ms | 0.8 ms | 2.9 ms |
| 10,000 authored, 7 targets, 2 ready sections | 83.2 ms | 207.8 ms | 2.9 ms | 3.7 ms |

The 10k run restored authored content in about 2.7 seconds, exported in 10.9 ms,
and awaited a project save in 543 ms. Its load phases included a 4.1-second main
thread task. Saving duration is not itself a measurement of UI blocking.
The saved render sample submitted about 42.7 million triangles in the color
pass, with a similar count in a separate water/foam depth capture. Those counts
are individual samples, not frame averages or a measured GPU-time breakdown.

Pre-implementation code inspection identified these specific opportunities:

- Authored instances are grouped globally by target in `basebuilder.js`.
  Their `InstancedMesh` objects have `frustumCulled = false`, so off-camera
  instances still reach rendering. Small selections become real editable objects;
  selections above 250 already use the existing instanced/shared-pivot path.
- World scenery already uses approximately 64 m XY batches in
  `world/world-assets.js`, with aggregate bounds and normal frustum culling.
  Do not propose adding world instancing or spatial batching as if absent.
  Residency and preparation still operate on complete section manifests.
- `world/world-depth.js` renders opaque geometry with its normal materials into
  the depth target whenever a depth-aware surface is in view. Despite the dirty
  frame comment, there is no reusable depth-cache invalidation mechanism yet.
- Project restore prepares a real cloned group for every placement, then most
  groups are demoted back into instances during commit/selection synchronization.
  Instance capacity growth also copies existing matrices.
- Spatial picking and cached bounds already exist. Candidate selection can still
  lead to raycasting an entire target batch, but the measured selection CPU cost
  is currently much smaller than frame latency.

Rendering is the leading hypothesis, not proof of a GPU-only bottleneck. Measure
CPU submission, GPU work, scene traversal, shader preparation and save tasks
separately before attributing the remaining cost. Culling cannot remove geometry
when all 10,000 objects are genuinely in view; that remains a required test.

## Non-Negotiable Contracts

- Keep source geometry, texture resolution, material maps, lighting, opacity,
  alpha cutouts, water/foam, terrain blending and current rendering resolution.
  No automatic LOD, decimation, texture downgrade, reduced scenery distance,
  missing objects or placeholder materials to make a benchmark pass.
- Placement records remain authoritative. Render batches, slots, visibility
  caches and streaming tasks are disposable implementation details.
- Rendering culling is not user Hide. It must not change hidden flags, selection,
  collections, IDs, anchors, undo, snapping, export eligibility or autosave.
- Preserve existing real-object promotion and large-selection pivot semantics,
  local/world orientation, scale restrictions/override and transform signs.
- Keep `RSDWBaseBuilder.Project.v1`, existing project defaults and
  `rsdwtools.buildings.v1` unchanged. Save all authored data, including hidden or
  off-camera objects and objects outside resident world sections. Game export
  keeps its existing hidden-object exclusion and single-anchor rules.
- World context stays read-only and separately owned. Streaming never edits or
  relocates a build. Preserve fixed render origin, absolute UE coordinates,
  section overlap deduplication and gesture-pinned placement surfaces.
- `Saved` still means the IndexedDB transaction completed. Preserve previous
  revision recovery, conflict/quota reporting, Save Copy and download fallback.

## Implementation Stages

Implement and measure each stage independently. Keep a local diagnostic switch
for comparison with the previous backend until visual and behavioral gates pass;
do not expose experimental switches as new user-facing modes.

### 1. Make the 10k Baseline Reproducible

Extend `tools/Web/BenchmarkWorldBuilder.mjs` before optimizing:

- Promote 10k from optional stress reporting to primary acceptance. Keep 100,
  1,000 and 5,000 as scaling controls. Record deterministic target IDs, transforms,
  dataset identity, camera paths, loaded sections and render settings per fixture.
- Compare identical authored scenes/cameras with and without world context.
  Use repeated, seven-target legacy and broader mixed piece/item/BP fixtures.
  Include varied geometry complexity, not only a low-poly foundation grid.
- Run close-up editing, full-build framing, continuous orbit/pan, orthographic
  views, water/shoreline, dense scenery and a cross-section build. Record visible
  versus resident counts so off-screen culling cannot disguise a changed test.
- Separate idle, camera movement, active edits, streaming, project restore,
  autosave and export phases. Measure real pointer/keyboard interactions as well
  as diagnostic function timings, including first selection and warmed selection.
- Record per-pass CPU time, available GPU timer measurements, submitted triangles,
  draw calls, culled batches, instance buffer uploads, shader preparation, heap,
  resource estimates and long tasks. Discard invalid GPU samples; lack of GPU
  timers must be reported rather than inferred from animation-frame intervals.
- Capture metrics after queues settle and at the same point in each scenario.
  Fix resource timing buffer coverage and distinguish HTTP-warm reconstruction
  from retained-neighbor activation. Existing reports contain early world metrics
  captured before overview/resource jobs finish.
- Run at least three isolated repetitions and longer frame samples. Report p50,
  p95, p99 and worst task; do not combine independent percentile timings. Keep
  other benchmark browsers closed and add a headed-browser user-feel check.

Deliver baseline fixtures and reports under ignored `_build/world-builder-m3/`.
Do not overwrite the Milestone 2 evidence or the user's browser project.

### 2. Spatial Authored Batches and Bounded Updates

Route authored instancing through the existing visual adapter with batches keyed
by compatible target/material variant and spatial cell, rather than target alone.
Keep this implementation scoped; extract a small batching module only where it
reduces the complexity of the existing adapter.

- Determine cell membership from absolute placement coordinates, independent of
  camera and fixed render origin. Benchmark 16/32/64 m cells before choosing the
  default. Add vertical subdivision only if tall-build measurements justify it.
- Compute conservative aggregate bounds from transformed component geometry,
  not just actor roots or cell extents. Large/rotated objects can extend beyond
  their cell. Maintain bounds after edits, growth, deletion and slot compaction.
  Use conservative fallback rendering for unsupported deformation bounds.
- Enable frustum culling only once those bounds are valid. Invisible/zero-scale
  slots must not drag a batch's bounds back to the origin. Never change
  `placement.hidden` or logical pickability to implement rendering culling.
- Maintain bidirectional placement ID / batch / slot mappings. Cross-cell moves,
  undo, hide/show, duplication, promotion and demotion update them atomically.
  Never derive persistent IDs from transient instance slots.
- Preserve component transforms, nonuniform/mirrored scale and material groups.
  Order-sensitive transparent assets keep the legacy path until image comparison
  proves that spatial partitioning does not change their blending.
- Preallocate known import counts per batch, bound excess capacity, release empty
  batches and update only dirty matrix ranges where supported. Coalesce bounds,
  spatial-index and debug-stat updates once per action/frame, not per slot.
- Keep small active edits as real objects and larger selections on the current
  shared pivot. Do not lower the selection limit to hide a performance problem.
- Keep picking/marquee based on logical candidate placements and exact hit order,
  not the last frame's rendered list. Bound instance raycasting to relevant
  batches; preserve screen-bounds fallback, distant selection and Ctrl-deselect.
- Profile selection boxes and multi-selection transforms separately. If needed,
  pool or batch identical outline geometry while preserving every visible box,
  active-object distinction and orientation behavior.

Success requires fewer submitted off-camera instances without more costly draw
calls or missing geometry in representative views. A cell-size change is not an
improvement unless total frame time improves. Regress the normal builder too,
because its authored visual adapter is shared.

### 3. Remove Redundant Depth and Static-Scene Work

Optimize `world/world-depth.js` while preserving its captured depth exactly:

- Add a versioned depth cache. Invalidate for camera/projection/viewport changes,
  opaque geometry transforms or visibility, instance updates, section commits,
  previews, material alpha/depth behavior and any depth-affecting animation.
  Water-color/foam animation alone need not recapture unchanged opaque depth.
- Keep animated opaque geometry on a continuously invalidated path. On uncertain
  invalidation, recapture. Never trade stale intersections for a faster frame.
- Introduce depth-only material variants for supported opaque meshes, retaining
  instancing, side/culling, alpha tests/maps, UV transforms, skinning/morphs,
  clipping, logarithmic depth and any vertex displacement. Source-backed dune
  deformation and custom vertex shaders must retain matching depth behavior.
- Use the current material capture as a fallback for unsupported variants. Do not
  replace every material with a generic override and lose foliage cutouts or
  deformation. Manage cached depth variants with their owning resources.
- Evaluate freezing static world matrices and removing redundant traversals only
  with explicit invalidation for streaming, visibility and origin changes.
  Do not freeze editable roots, gizmos or animations.
- Retain one shared depth system and existing pixel dimensions. Cache reuse helps
  idle scenes; moving-camera performance must come from less capture work and
  better batching, not a reduced depth resolution or delayed updates.

Run the existing 36-case water/depth audit plus new deformation, moving authored
objects, hide/show, preview, chunk-edge and cache-invalidation cases. Verify both
the builder and standalone viewer because they share these material modules.

### 4. Prepare Directly for the Final Visual Backend

Change restore preparation to stage data and final instance batches directly for
eligible placements, with real groups only for ineligible/promoted objects.

- Resolve/validate targets first, preload unique assets and warm editable shader
  variants once per target as today. No clone-and-demote cycle for every instance.
- Build matrices, bounds and spatial membership with elapsed-time budgets and
  frame yielding, initially targeting 4-6 ms preparation slices. Batch size must
  respond to asset cost, not an arbitrary fixed count of 100 objects.
- Keep the old document, visuals and resource ownership intact until the new
  document is fully ready. Attach a prepared state/root with a short atomic
  commit; do not clear live state then run a long loop that can fail halfway.
- Build indexes off to the side, then swap them consistently with placement state.
  Restore selection, collections, counters and inspector once after commit.
- Cancellation, missing assets, allocation errors and project replacement dispose
  staged resources and retain the old build. Late asynchronous completion cannot
  attach to a newer document or change its save/history state.
- Use background workers only for measured expensive pure-data preparation.
  Keep Three.js scene mutation and GPU upload on their existing owner; bound
  concurrency and transfer costs instead of saturating the UI thread.

Apply the same preparation foundation to Open, recovery and build Import/Append
without changing coordinate, ID-remapping or anchor behavior. A progress display
must remain responsive while the editor is intentionally locked for replacement.

### 5. Budget World Preparation Without Removing Scenery

Retain the existing 64 m world batches initially. Profile dense-section matrix
construction, ownership registration, surface bounds, texture upload, shader
preparation and final attachment separately.

- Divide expensive preparation into bounded internal jobs; yield within a large
  asset's instance loop and ownership/bounds work, not only between asset jobs.
  Reuse immutable lookup tables rather than rebuilding them for each section.
- Prioritize destination/contact preparation ahead of background overview work,
  with bounded queues and cancellation. Preserve all mandatory destination
  content, optional-neighbor reporting and the current scenery coverage policy.
- Batch GPU uploads and use the existing compilation path; measure individual
  uploads that exceed the budget since one synchronous upload is not preemptible.
  Do not claim every stall is solved merely because the outer loop yields.
- Keep logical section identity, shared terrain/source owners, spanning objects,
  retries and coverage masks intact. Internal work chunks are not new selectable
  sections, saved project fields or reasons to hide visible detail.
- Publish usable detail only through a consistent commit, and wait for active
  editing gestures before changing their contact surfaces. Preserve the old
  destination until the required replacement is ready.
- If surface-query profiling warrants it, index committed world batch bounds so
  preview rays query nearby candidates rather than scanning all surface rows.
  Keep the current eligible-surface rules and exact nearest-hit behavior.

No archive/model extraction or generated-world schema change is required for this
pass. A new distance-based sub-section residency policy is a separate decision:
it must not silently reduce today's visible scenery to reach the performance goal.

### 6. Keep Saving and Large Actions Responsive

Instrument capture, validation, cloning, serialization and IndexedDB transaction
time independently before changing persistence. Prioritize measured main-thread
stalls over total asynchronous save duration.

- Reuse an immutable action-revision snapshot where safe; avoid repeated whole
  document copies in one save. Never yield while reading mutable placement state
  and produce a snapshot containing parts of different user actions.
- Coalesce saves as today. If serialization/validation moves to a worker, retain
  revision and epoch checks, capture ordering and stale-result cancellation.
  Keep IndexedDB's atomic conflict check and completed-transaction acknowledgement.
- Camera-only navigation may reuse unchanged authored snapshot data. A new edit
  must invalidate it. Deferred background work cannot mark an unsaved edit Saved.
- Preserve undo semantics and existing session-local history. No lossy history,
  collection omission or export filtering based on render residency.
- Profile Select All, collection selection, batch snap, duplicate/delete and
  large transforms. Coalesce visual/index/UI updates while retaining a single
  coherent undo action. Keep Placed pagination and its Show More/All behavior.

## Acceptance and Safety Gates

### Performance

On the same documented local hardware, require the 10k mixed fixtures to meet:

| Measure | Acceptance target |
| --- | --- |
| Steady orbit/edit frame p95 | <=33.3 ms; 16.7 ms is the preferred goal |
| Steady frame p99 | <=50 ms after warm-up |
| Pointer action / drag-preview response p95 | <=100 ms to updated rendered frame |
| Warm pick, marquee and snap CPU p95 | <=50 ms each, measured separately |
| Editing and loading responsiveness | No task >=1 second; report every task >50 ms |
| Prepared authored restore and awaited save | No regression against matched baseline; reduce blocking time |
| Small-scene performance | No repeatable >10% regression outside measurement noise |

Include full-build framing with all 10k placements visible, close-up editing,
dense scenery and water in primary results. Also test selecting all 10k and
transforming/undoing them, not just selecting one object in a large scene.
Cold network time is reported separately from preparation and interaction stalls.

These are local acceptance gates, not a promise that arbitrary 10k high-poly BPs
will run at 60 fps on every device. Add a representative lower-resource browser
run when available and report it separately. A missed gate remains a documented
miss; do not lower quality, remove difficult fixtures or declare the milestone
complete. Profile the remaining limit before proposing further renderer changes.

### Visual Equivalence

- Capture before/after screenshots at identical camera, viewport, pixel ratio,
  assets and fixed animation time. Use nonblank canvas checks plus pixel-difference
  comparisons with a recorded tolerance for rasterization noise.
- Cover perspective/orthographic and close/far views, batch boundaries, large and
  mirrored objects, translucent materials, cutouts, selected/preview objects,
  solid view, terrain/dunes, water/foam and shoreline intersections.
- Orbit and move objects across cell boundaries; no popping, duplicate instances,
  missing components, altered transparency ordering or stale selection boxes.
- Preserve existing manual in-game material-verification annotations. Matching
  today's browser output is not approval of unverified in-game approximations.

### Building, Persistence and Lifecycle

- Re-run project/serialization, streaming, navigation, journey and editor tests.
  Add mixed 10k fixtures with hidden objects, collections, nonuniform/negative
  scale, nonzero rotations, one anchor and authored objects in unloaded sections.
- Exercise direct/marquee/Ctrl-deselect selection, collection selection, preview
  drag/E, rotation steps/flip/height offset, gizmos, batch snap, both duplicate
  paths, Hide, undo, import/append and export across batch boundaries.
- Compare canonical authored snapshots and exports before/after scenery changes,
  culling, save/reopen and reload. Ignore only intentional timestamps/navigation
  changes; preserve object ordering and IDs where the existing contract does.
- Inject missing assets, stale async jobs, cancellation, storage quota/conflict
  failures and replacement while preparation is pending. The previous valid
  project/recovery record must remain available and errors must stay visible.
- Run at least 50 section load/evict cycles and repeated project replacements.
  Track buffers, geometries, textures, owned decoded images, depth variants,
  workers/listeners, heap trend and peak staging memory. Require a bounded warmed
  baseline, not just an empty scene root. Verify no accidental resource sharing
  or disposal between the world and authored layers.

## Delivery and Scope

Deliver the local test URL, deterministic small/10k projects, before/after
performance and visual reports, updated local guide, measured batch/job policy
and a manual checklist. Keep generated evidence in `_build/world-builder-m3/`.

Existing regression entry points include `TestProjectDocument.mjs`,
`TestWorldStreaming.mjs`, `TestWorldBuilder.mjs`, `TestWorldBuilderStreaming.mjs`,
`TestWorldBuilderJourney.mjs` and `BenchmarkWorldBuilder.mjs` under `tools/Web/`,
plus `AuditWaterDepth.mjs` and `AuditWorldPreview.mjs` under `tools/World/`.
Extend these rather than creating an unrelated benchmark application. Run syntax
checks on modified JS modules and `git diff --check` as part of implementation.

No commit/push, deployment, Blender package, schema migration, NPC editing,
texture-quality mode, WebGPU rewrite or public world hosting is included.
Do not redesign the UI or controls as part of performance work.

Manual review follows the automated gates: verify camera/editing feel, placement
contacts, selection feedback, save/reload across unloaded areas and delivery of
the unchanged mixed export in-game. Report any unverified items explicitly.

References: [Milestone 2](WORLD_BUILDER_MILESTONE_2_PLAN.md),
[Milestone 1](WORLD_BUILDER_MILESTONE_1_PLAN.md),
[local builder guide](tools/Web/WORLD_BUILDER_LOCAL.md),
[world prototype and material audit](tools/World/README.md).

## Implementation Record

Implemented locally on 2026-10-17. No data extraction, generated-world schema,
game JSON, project schema, quality settings or public deployment changed.

- `website/basebuilder-instances.js` owns stable placement-to-slot mappings,
  absolute-coordinate cells, conservative bounds, reservations, migration,
  visibility and disposal. Cells are the culling/picking unit. Visible cells of
  the same compatible target are submitted together, avoiding one draw call per
  small cell in the full-build view. Transparent targets retain global ordering.
  The measured default is 64 m. Buffers reserve known import counts and release
  empty batches; nonempty buffers retain their high-water capacity until disposal.
  Idle shrinking of oversized buffers is not implemented.
- `website/basebuilder-static-pose.js` caches full-detail skeleton poses for
  inactive NPC instances. The current editor does not play animations. Small
  active selections still use the original editable skeleton/model. A future
  animation feature must opt those actors out or explicitly refresh the pose;
  this is not an animated-crowd implementation or a geometry simplification.
  Editable picking uses the same full-detail cached pose and maps hits back to
  the editable object. Transparent skeletons stay unbatched. The cache adds one
  posed geometry per source mesh, not one per placement. Owned clone skeleton
  textures and preview materials are released when those visuals are discarded.
- `website/basebuilder-selection-outline.js` draws all large-selection boxes
  in one line batch. Individual selection, logical IDs and shared-pivot behavior
  remain unchanged. Bulk duplication coalesces UI work and yields between slices.
- World project Open, recovery, Import/Append and undo stage final instances,
  bounds and indexes before swapping the live build. Normal non-world imports
  keep the existing path with elapsed-time yielding. Missing target/model
  failures retain the previous world project.
- `world/world-depth.js` caches safe depth variants and unchanged captures.
  Uncertain custom vertex/alpha behavior falls back to source materials;
  animated/unsupported depth behavior forces capture. Pixel dimensions and
  geometry remain unchanged. Optional GPU timers are local diagnostics only.
- World asset preparation shares a 5 ms cooperative CPU budget, checking inside
  instance loops. This is not a hard deadline for an individual GPU upload or
  shader compile. Section identity, resident coverage and surface pinning stay
  under the existing streaming policy.
- Large snap actions yield between planning/apply slices under the existing edit
  lock. Duplication does not rescan all piece IDs or rebuild the Placed tree for
  every copy. One action still produces one undo entry.
- Save avoids redundant whole-document capture/validation copies. The store
  still owns a copied snapshot and performs its atomic revision check and
  completed-transaction acknowledgement. Save metrics separate capture,
  validation and transaction duration.

The initial cell-per-draw experiment was slower in a full-build view and was
replaced by visible-cell merging. Its failed evidence remains in
`_build/world-builder-m3/first-pass/`; it is not an acceptance result.
The local `performance=legacy` comparison bypasses spatial authored merging,
static pose caching and depth optimization, but is not a byte-for-byte checkout
of the earlier application. Keep historical baseline reports for that purpose.

### Evidence Locations

All reports and fixtures are ignored local outputs under
`_build/world-builder-m3/`. Their individual status fields are authoritative;
an unfinished or failed harness run must not be counted as a passing gate.

- `baseline-retry/`: matched seven-row legacy fixture before the runtime changes.
- `instance-unit/` and `pose-validation/`: initial image/identity/culling checks.
- `depth-validation/`: initial expanded 44-case depth audit.
- `acceptance-performance-v2/`: mixed 100/1k/5k/10k scaling measurements.
- `cell-16/`, `cell-32-repeated/`, `cell-64-repeated/`: cell-size comparison.
- `small-legacy/` and `small-optimized/`: matched 100/1k controls.
- `large-default-final/`: final 64 m 10k action/persistence regression and sample.
- `normal-final-v2/`: normal-builder adapter/undo/export/autosave regression.
- `navigation-final/`, `journey-final/`, `preview-final/`: map, cross-section
  persistence and standalone world-viewer regression.
- `editor-large/`: earlier functional checks, predating the fixed-pose cache;
  retain as historical evidence, not final performance acceptance.

Automated browser comparisons certify consistency with the prior browser
rendering, not correctness against the running game. Existing crystal, dune,
shoreline, foam and Kuldra manual-verification annotations remain open.

### Acceptance Results and Remaining Limits

Local hardware: i5-14600K, RTX 3090, approximately 128 GiB RAM; Chrome,
1600 x 1000 CSS viewport, device pixel ratio 1. Record actual drawing-buffer
dimensions from each report; the canvas is smaller than the browser viewport.

The mixed performance fixture uses ten repeating catalog rows: seven piece rows
(six unique pieces), Doric, the statue and an item. Thus 20% of the 10k fixture
is BP actors. Every authored object is submitted in the full-build cases; no
quality or scenery-distance reduction is used to improve results.

`acceptance-performance-v2/Performance.json` records three repetitions per view:

| 10k mixed case | Frame p95 across repetitions | Native click p95 |
| --- | --- | --- |
| World disabled, full build | 16.7 ms | 47.8-51.9 ms |
| World enabled, full build | 37.6 ms | 171-198 ms |
| World enabled, close editing | 12.5-12.6 ms | 21-22.5 ms |
| World enabled, orthographic full build | 41.7-41.8 ms | 163-181 ms |

That run predates the last editable-pose picking/bounds and skeleton cleanup
fixes. It retains the full 100/1k/5k/10k scaling evidence. Its 10k authored
restore took 795 ms; awaited saves were 68-110 ms. The largest recorded task
was 465 ms. That older harness did not retain initial startup/world-load tasks;
it does not prove the full loading gate. Current runs retain those phases too.
The old multi-count harness inherited the preceding camera's orbit angle;
current runs explicitly reset it and record view matrices/buffer dimensions.
Do not compare that older table directly with differently framed single-count
runs or the Milestone 2 table.

The matched historical seven-row fixture (`baseline-retry/` versus
`merged-pass/`) retained the same camera, 50,440,959 color-pass triangles and
2,159 draw calls. Frame p95 improved from 37.5 to 29.2 ms; authored restore from
1,997 to 1,207 ms. These are not the broader mixed-BP fixture or native input
latency measurements.

### Final Cell Policy and Controls

The 16/32/64 m comparison retained the same full-build camera and full authored
geometry. The 16 m initial run measured 37.5 ms full-view p95. The repeated
32 m run measured 37.4-37.5 ms; 64 m measured 33.4-33.5 ms. Close editing stayed
12.5-12.6 ms. Therefore 64 m is the default, reducing logical-batch overhead
without a close-view regression. Its coarser cells submit more off-screen
geometry in close views; they do not discard visible geometry.

`cell-64-repeated/Performance.json` has three isolated repetitions, 240 frames
each, with two world sections loaded:

| 10k mixed, final 64 m default | Frame p95 | Native click p95 |
| --- | --- | --- |
| Full build, perspective | 33.4-33.5 ms | 134-189 ms |
| Close editing | 12.5 ms | 19.6-21.9 ms |
| Full build, orthographic | 37.5 ms | 151-192 ms |

The 33.3 ms and 100 ms acceptance thresholds still fail in wide views. Do not
round those misses into passes. Initial 16 m instrumented loading recorded
534 ms startup, 373 ms world load and 441 ms authored-restore maximum tasks;
those are phase maxima from that run, not universal bounds.

Matched small-scene controls use the fixed camera path and three repetitions:

| World-enabled case | Comparison backend frame p95 | Optimized 64 m frame p95 |
| --- | --- | --- |
| 100, perspective full/close | 12.5 ms | 8.4-8.5 ms |
| 100, orthographic | 8.5 ms | 8.4 ms |
| 1,000, perspective full | 25.2-29.2 ms | 12.6 ms |
| 1,000, close/orthographic | 25.1 ms | 12.5-12.6 ms |

The comparison backend retains common UI/cleanup fixes, so these controls
isolate rendering choices rather than reproduce the old checkout exactly.
There was no repeatable >10% frame regression in these small-scene controls.

### Headed and Functional Results

`performance-final/Performance.json` is the later **headed** 10k run, not a
direct headless comparison: full-build frame p95 was 50-54.2 ms, close editing
12.5 ms, and orthographic full-build 54.2-54.3 ms. Native click p95 still exceeded
100 ms in full-build views. Fifty NPC selection/deselection cycles held renderer
resources steady at 892 geometries / 843 textures. Do not claim that headed
performance or every interaction gate has passed.

That headed run used 32 m cells; a headed rerun of the final 64 m default remains
part of acceptance. The current matched cell tests submit about 82 million
triangles per full-view depth pass, with additional color work. GPU timer samples demonstrate substantial work
in both passes, but do not alone explain all headed/input latency. Next work
must profile frame scheduling/submission and removal of duplicate opaque
rendering without compromising cutouts, deformation, water intersections or AA.
Do not introduce LOD or lower resolution as an unannounced workaround.

`editor-final/Acceptance.json` passed the existing editor checks plus 10k actions:
select-all CPU 12.1 ms, cold full-scene marquee 38.3 ms, Ctrl-deselect 1.8 ms,
duplicate-to-20k 401 ms total with yielding. A single 10k pivot rotation/scale
update cost 135/95 ms respectively. Those large-transform timings are another
remaining smooth-editing limit, not 60 fps acceptance. Exact undo, collections,
hidden export exclusion and save/reload with world unloaded passed.

Fifty section load/evict cycles left no detail roots or detail leases, with a
stable warmed baseline of 22 geometries / 40 textures and post-GC heap of about
361.0-361.8 MiB. This includes retained overview/source caches. That cycle camera
did not exercise water capture; depth disposal/correctness has separate tests.

`instances-final/InstanceValidation.json` passed six synthetic cell/migration/
visibility/image cases (16/32/64 m, perspective/orthographic), three source-pose
image checks and 147 transformed/mirrored pose ray comparisons. Eight complete
builder image comparisons covered world on/off, perspective, orthographic,
selection and solid view. Less than 0.001% of channels differed by more than
3/255, within the recorded 0.1% tolerance. `depth-final/WaterDepthValidation.json`
records the expanded 44-case GPU depth suite.

`large-default-final/Acceptance.json` repeats all nine large-action checks after
the final cell/ID-allocation changes, including unique duplicate IDs and exact
save/export/undo comparisons. Final CPU timings were 9.4 ms select-all, 29 ms
marquee, 1.7 ms Ctrl-deselect, 1.0-1.8 ms warm snap and 124/92 ms pivot
rotation/scale. Duplication to 20k completed in 215 ms with yielding.
`normal-final-v2/AdapterValidation.json` covers
five normal-builder checks: 1k duplication/IDs, hide/delete/undo, localStorage
recovery, nonblank desktop/mobile canvases and static-NPC duplication/undo.
This is functional mobile coverage, not a mobile performance certification.
The existing expanded hotkey HUDs overlap on the narrow phone viewport; this
pass verifies a nonblank canvas, not a finished mobile layout. That UI issue is
separate from the desktop performance work and remains annotated for follow-up.

Map/navigation passed 12 checks. The cross-section journey saved, unloaded and
reloaded authored data exactly across `x3_y1`, `x4_y1` and `x3_y3`. Standalone
viewer regression loaded `x3_y1` (5,846 placements) and `x4_y3` (1,228 placements).
Pure project validation/serialization and world-streaming checks also pass.

Not all proposed optimizations were needed or implemented: camera-only snapshot
reuse, worker serialization, static-world matrix freezing and a new world-surface
index remain conditional follow-ups. Single GPU uploads/compiles are not
preemptible by the cooperative budget. Wide-view input/frame latency and 10k
simultaneous gizmo updates remain measured blockers to full performance sign-off.

Before release sign-off, rerun the unresolved performance gates and manually
check viewport/editing feel, placement contact and mixed game delivery. No
lower-resource hardware run or in-game visual approval is claimed.

## Follow-Up: Wide Views and Continuous Transforms

This pass supersedes the earlier wide-view and transform implementation notes,
but does not erase their measurements or the remaining manual review gates.

### Runtime Changes

- Water depth draws now use conservative receiver screen/depth bounds. Authored
  instance cells outside those bounds are omitted from the depth pass only.
  Color rendering, full mesh geometry, texture resolution, AA and drawing-buffer
  size remain unchanged. No LOD or scenery-distance reduction was introduced.
- Omitted geometry must be provably unable to affect a visible water/foam
  receiver. Unknown vertex deformation, near-plane crossings and custom render
  callbacks retain the original draw. Foreground depth blockers are retained.
  Helpers with depth testing disabled cannot write depth and are excluded from
  the optimized depth pass. See the
  [Khronos depth-mask reference](https://raw.githubusercontent.com/KhronosGroup/OpenGL-Refpages/main/gl4/glDepthMask.xml).
- Depth-only compacted instance buffers are cached independently of the normal
  color draw. Visibility changes, cell migrations and buffer growth invalidate
  them; store disposal releases both buffer sets.
- Direct transform math avoids temporary nested matrices and unnecessary Euler
  decomposition. Translation preserves rotation/scale exactly; scaling preserves
  rotation exactly. Canonical positive-scale yaw edits use a specialized path;
  mirrored, tilted-axis and near-gimbal cases retain general decomposition.
- Translation updates instance translation columns and the combined selection
  outline directly. Spatial cells rebuild only when their occupied range changes.
  During large gizmo gestures, derived spatial-index updates are deferred until
  release or the next spatial query. Authored state and visual bounds update
  immediately; saves and exports never depend on that deferred index.
- Transform frames refresh visible row coordinates without reconstructing
  collection statistics or the full inspector. An intersection observer avoids
  coordinate/text/layout work for off-screen Placed rows and refreshes their
  current coordinates as they scroll into view. Shader variants for editable
  objects and selection outlines are prepared while loading a project rather
  than on the first selection.

### Reproduction

All outputs below are ignored local files. Run GPU tests sequentially.
`TestTransformIntents.mjs` covers 300 mixed, signed-scale and near-gimbal actors;
`BenchmarkLargeTransforms.mjs` exercises continuous 10k translate/rotate/scale
gestures, verifies untouched channels and exact undo, and records release cost.
Its default six-target persistence fixture differs from the ten-row wide-view
benchmark fixture; do not compare their frame times as identical workloads.

```powershell
node tools/Web/TestTransformIntents.mjs --out _build/world-builder-m3/followup-intents-final --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
node tools/Web/BenchmarkLargeTransforms.mjs --world --headed --frames 120 --out _build/world-builder-m3/followup-transform-final --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
node tools/Web/BenchmarkWorldBuilder.mjs --milestone3 --counts 10000 --worlds true --repetitions 3 --frames 240 --headed --out _build/world-builder-m3/followup-wide-final --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

The continuous-transform harness waits for shader preparation before recording
gesture frames, but the wide-view harness still includes the first real click.
`--profile-clicks` records a CPU trace and any shader programs first compiled by
clicks. Frame sampling uses lightweight render counters, not a resource inventory
traversal. Reports keep raw frame/input values and the original acceptance limits.

### Follow-Up Validation

- `followup-depth-final/WaterDepthValidation.json`: 48 GPU pixel cases passed,
  including disabled-depth-test helpers, standard/log depth, perspective/ortho,
  alpha cutouts, river color and foam. The two extra depth-compaction image tests
  in `followup-instances-final/InstanceValidation.json` have zero differing
  channels while depth triangles fall from 1,200 to 72.
- `followup-instances-final/`: 2,000 signed/nonuniform transform matrix cases
  differ from the previous math by at most 1.56e-15; quaternion rotation results
  match exactly. Six cell/migration/visibility/disposal cases, component-origin
  translation, three NPC poses and 147 pose raycasts pass. Eight whole-builder
  image comparisons stay below 0.0007% differing channels, within the unchanged
  0.1% tolerance. These comparisons do not certify in-game material accuracy.
- `followup-intents-final/TransformIntents.json`: translation, yaw and scale
  edits on 300 mixed actors match the previous transform algorithm. Maximum
  rotation difference is 8.54e-7 degrees at a gimbal edge; scale/translate edits
  preserve every original rotation channel exactly. Mid-gesture spatial queries
  and drag release flush the deferred index; undo restores the exact snapshot.
- `followup-large-final/Acceptance.json`: all nine 10k action/persistence checks
  pass, pending the existing manual in-game gate. Select-all costs 10.1 ms CPU,
  marquee 31.6 ms, Ctrl-deselect 2 ms, warm snap 1.2-2.1 ms, duplicate-to-20k
  118 ms total with yielding. One rotation/scale action, including snapshot and
  release, costs 30.5/19.5 ms. Scrolling a previously off-screen Placed row after
  movement displays its current coordinates. Exact save/reload/export comparisons
  pass with hidden actors and collections and the world unloaded.
- `followup-normal-final/AdapterValidation.json`: standard builder duplication,
  hide/delete/undo, local autosave recovery, NPC editing and desktop/mobile
  nonblank-canvas checks pass. The pre-existing narrow-screen HUD overlap remains
  a separate UI limitation, not a passing mobile-layout or performance gate.
- Pure project document and world-streaming validation pass, including 23
  nondestructive invalid-project cases and 314 indexed sections.

### Continuous 10k Results

The final visible-browser, 120-frame-per-gesture run is
`followup-transform-visible-rows/Transforms.json`, with world detail loaded,
the six-target persistence fixture, 9,901 visible actors and all 10k selected.
Full-resolution color draws remain about 74.27 million triangles. This camera
does not need water depth capture; it is distinct from the wide-view water test.

| Gesture | Update CPU p95 | Frame p95 | Release/index flush |
| --- | --- | --- | --- |
| Move all 10k | 3.2 ms | 29.3 ms | 2.6 ms |
| Rotate all 10k | 9.9 ms | 41.7 ms | 6.0 ms |
| Scale all 10k | 10.6 ms | 37.5 ms | 2.5 ms |

The earlier final-math run before visible-row updates measured 54-63 ms frames
with the world loaded (`followup-transform-world/`). The same CPU/GPU buffer
hint experiment without profiling measured 58.3/62.5/50 ms
(`followup-transform-stream/`) and did not justify changing buffer usage; that
experiment was reverted. The off-screen DOM work was a substantial remaining
cost, not a reason to reduce model detail. The original world-disabled transform
baseline (`followup-transform-before/`) cost 116-121 ms CPU per update; it is a
CPU reference, not a matched world-enabled frame comparison.

Move-all now meets the 33.3 ms p95 frame target in this run. Full-selection
rotation and scale still miss it; do not label the entire 10k-smooth milestone
complete. No reduced-resource hardware or in-game sign-off is claimed.

### Final Wide-View Results

`followup-wide-final/Performance.json` records 27 visible-browser samples: three
repetitions of each view at 100, 1,000 and 10,000 placements, 240 orbit frames
per sample, world detail enabled, default 64 m cells and unchanged quality.

| 10k mixed view | Frame p95 across repetitions | Native click p95 |
| --- | --- | --- |
| Perspective full build | 29.2 ms | 66.2-71.0 ms |
| Close editing | 12.6-20.9 ms | 30.1-33.0 ms |
| Orthographic full build | 29.1-33.3 ms | 67.8-86.6 ms |

The close-view middle repetition is a slower outlier; it is retained in the
range, not discarded. The harness reports `performance_target_miss` because
one orthographic p95 is `33.30000000001746` rather than <= `33.3`. This is the
only frame/input violation in this report and is floating-point clock arithmetic;
the raw status and thresholds have not been rewritten. The real remaining
smoothness misses are the continuous full-selection rotate/scale cases above.

The 100-object controls remain 8.4 ms p95, and 1,000-object controls remain
12.5-12.6 ms, consistent with the earlier optimized small-scene controls.
The final full-build color sample submits 82,512,655 triangles; its depth draw
submits 16,255,890, compared with roughly 82 million previously. Color quality
and visible geometry are not reduced to achieve the depth-pass saving.

The multi-count run warms common shaders before the 10k case. Independent
cold 10k evidence is in `followup-click-prepared/`: native click p95 is 84.1 ms,
versus 136.5 ms in `followup-click-programs/`. No new shader programs were
compiled by the prepared test's clicks. The earlier profile identified a depth
shader and the selection-outline shader as the cold programs.

Final 10k authored restore was 611 ms, export 2.8-3.6 ms and awaited save
103-226 ms. Every measured export matched its baseline exactly. Fifty NPC
selection cycles held renderer resources at 892 geometries / 843 textures.
The image-test selection cycle independently held 246 / 729 for its smaller
fixture. These are resource-lifetime checks, not a total VRAM measurement.

Next targeted work is continuous all-selection rotate/scale submission and
outline/bounds updates, plus manual editing feel. Preserve this report and
camera/fixture distinctions when comparing further changes. The local server
and ignored review fixtures remain available; this pass does not publish a
release or change Blender packages, the game-export schema or project schema.
