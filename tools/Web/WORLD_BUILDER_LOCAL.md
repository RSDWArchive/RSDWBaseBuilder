# Local World Builder

The world workspace attaches read-only overview and nearby world sections to the existing browser editor.
It is local-only and is not a deployed product or a change to the Blender add-on.

## Start and Test

From `E:\Github`, serve the sibling repos using the existing HTTP server, or:

```powershell
python -m http.server 8765 --protocol HTTP/1.1 --bind 127.0.0.1 --directory E:\Github
```

Open <http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1>.
Do not start another server if port 8765 is already serving this directory.
Without `?world=1`, a new project starts in Free Build with no world-data requests.
Both workspaces use the same project saves and recovery. Recovery restores the
saved workspace regardless of the query string. World (beta) is local-only.

The local config is `website/world/local-config.js`. The current catalog and
world must both be version `1.0.0.5`. Required generated inputs are:

- `_build/world-region/1.0.0.5/whole-world/WorldIndex.json`, `WorldShared.json`,
  section/spanning manifests, terrain and material textures.
- Sibling `RSDWModel/1.0.0.5/WebAssets/` models and textures.
- The existing generated `website/basebuilder-index.json` and builder assets.

No generation or pipeline stage changes are required for this integration.
Missing world files do not fall back to another version or a public dataset.
The existing Three.js/Draco dependencies still require their configured CDNs.

## Workspace Behavior

Choose **Free Build** for the grid or **World (beta)** for the whole-world overview.
Switching preserves all authored data, IDs, collections, anchor and undo, and
remembers independent cameras. Requests during editing wait until the gesture ends.
Free Build's **Plane Z** is an absolute centimeter height, not an actor offset.
World projects start at the whole-world overview. Click terrain or a section marker
to enter a build-scale view. The area filter and searchable **Locations** menu
also reach caves, vaults and isolated scenery without guessing section IDs.
**World Map** remembers your build camera; **Return to Build** restores it.
The turquoise map marker also returns to the authored build.

Nearby detail streams around the camera target in build view, with up to four
resident sections and one staged addition. The initial detail/retention radii are
260/400 m. Models/materials/textures are shared within the world layer, and shared
source placements/terrain are deduplicated across section boundaries. Existing
scenery is retained until replacement detail is usable. Status distinguishes
loading, failed and deferred sections. No visual-quality downgrade is applied.

**World Settings** contains the nearby-streaming checkbox, **Unload**,
**Load / Retry** and **Frame Section**. Unload suspends world context even when
the camera moves; Load / Retry explicitly resumes it. Turning off nearby streaming
keeps the current scenery and allows one explicitly chosen location to be loaded.
Overview tiles are navigation-only, never final placement surfaces. World context
never becomes selectable/exported build content. A section change during preview,
marquee or gizmo dragging waits for the gesture to finish. Layer switches affect
only the world. Previously annotated material approximations remain unchanged.

The local streaming policy lives in `website/world/world-streaming.js`. Its
estimated resource ceiling is initially 2.5 GiB for resident detail, not a claim
about actual driver/GPU memory. One dense destination can exceed the soft ceiling;
neighbors are then deferred rather than removing that destination or its contact
surface. The overview and authored assets have separate ownership. Resource and
coverage diagnostics are available only through the local debug entry.

Catalog drag, E preview and dragging existing objects use real terrain/static
scenery contacts, together with existing authored snapping and preview controls.
Water, foliage and transparent effects are not placement surfaces. Without a
contact, placement is blocked; there is no invisible zero-height fallback.
Numeric fields and gizmos remain usable while the world is unloaded.

Absolute UE centimeters remain the authored source of truth. Render origin is
fixed per document, stored in the project and shared by both layers. New documents
use zero; migrated documents retain their original render origin.
Import/Append Build offers **Original Location** (saved coordinates, no recentering)
or **Place Here** (whole-build preview at a terrain/scenery contact). Home/0 frames the map in overview, and authored content
in build view (nearby world if the build is empty). Clear clears only authored
objects and remains undoable.

### Import Existing Builds

1. Choose a world location, then **Import**. Choose **Append** to keep existing builds,
   or **Import** to replace them after the import succeeds.
2. Choose a game-build JSON, then **Original Location** or **Place Here**.
   From the map, Place Here returns to the current build location first.
3. During Place Here, wheel rotates the entire build, R changes the rotation step,
   F flips it, Ctrl+wheel changes height, left click places, and Escape cancels.

The preview is instanced and moves as one rigid parent, not thousands of independently
updated placements. It uses the supplied anchor as pivot, or the visible geometry's
bottom-center if there is no anchor. Internal offsets, tilt and signed scales remain
intact. There is no individual snap/deformation of the prefab. An invalid surface
does not commit. Replacement cannot use soon-to-be-deleted objects as its surface.
Editing panels are locked during preview; cancel leaves the prior build unchanged.
Workspace changes can be queued. Both import choices also work in Free Build;
Place Here uses the free plane or visible authored geometry there.

**Place Build in World** moves the current document using the same whole-build
preview. It preserves IDs and collections and also moves hidden actors, while
showing only visible actors in the preview. Cancel is exact and commit is one undo
action. Switching workspaces alone never relocates the build.

Each imported file creates a named collection, including when appending. Collections
are retained by project saves, never by game JSON export. Existing global anchors are
retained on append; a source anchor is adopted only when there is no existing anchor.
Absent anchors are not invented. Appending assigns new piece IDs; invalid/nonpositive
IDs are repaired on import without stealing valid IDs. Missing mappings fail atomically.

Local verification: Grand Exchange (1,781 pieces), Looter Paradise 3 (12,316 pieces),
14,097 together. Both original-location exports and whole-build placement were tested,
including cancel, one-action undo, collections, world unload and project recovery.
Reports and screenshots: `_build/world-build-import/final/ImportTests.json`.
Source files and generated fixture exports are local only, not committed.

```powershell
python tools/AssetLibrary/TestCatalogRenames.py
python tools/Web/TestCatalogCompatibility.py
node tools/Web/TestBuildImport.mjs
node tools/Web/TestWorldBuildImport.mjs --file C:/Users/NZXT/Downloads/Grand_Exchange.json --file C:/Users/NZXT/Downloads/Looter_Paradise_3.json --out _build/world-build-import/final
```

The catalog join now recognizes same-folder `DA_...` to `BUILDPIECE_DA_...` data-asset
renames, preferring exact matches. This recovered Open Book and Broken Wooden Crate
as actual building pieces, plus 46 other renderable pieces (714 -> 762); no BP stand-ins.
The updated PieceDataMap resolves 48 additional classes. Existing browser target records
are retained unchanged; the decoration transform audit reports no mismatches. Nine other
catalog targets still lack usable metadata/meshes and are not silently substituted.
The existing Anima Orb icon exception was retained for target generation; no missing
icons were introduced by this fix. Blender libraries/dist were not rebuilt in this pass.
The standalone building-target tool also now defaults to `tools/ModelData/BPMap.json`,
matching the pipeline, so legacy torch/farm aliases are not dropped by manual regeneration.

## Save, Recover and Export

- **Project > Save Project** downloads `<name>.rsdwproject.json`, containing all
  authored placements (including hidden ones), IDs, collections, anchor, camera,
  render origin and requested world context. Map/build navigation and camera
  return locations are saved too; runtime residency is reconstructed on reopen.
  No model payloads are embedded.
- **Project > Open Project** validates and prepares all authored models before
  replacing the live build. Malformed data, missing targets or failed authored
  model loads retain the existing project. Missing/mismatched world context
  can leave authored work available without the world.
- **Project > New Project** starts a new local document. It does not delete
  previous stored project records. Download any project you need to keep.
- **Export Build** remains `rsdwtools.buildings.v1`, with the existing pitch/roll
  inversion, hidden-object exclusion and single-anchor rules. No project,
  collection or world-context fields leak into it.
- Shared autosave uses IndexedDB `RSDWBaseBuilder.Projects.v1` and Project.v2.
  Project.v1 world files and old free localStorage saves migrate without deleting
  the originals. Recovery offers distinct current/previous and legacy candidates.
  Migration is atomic and restartable. `Saved` means its transaction completed. An edit
  interrupted before that point is not guaranteed recoverable.
- Startup offers the latest project or its previous committed revision. A
  failed recovery does not replace the recovery pointer with an empty project.
- Storage/revision failures remain visible. **Save Project** is still available
  as a download; **Save Copy** creates a new local project identity after a
  two-tab revision conflict. Neither tab may silently overwrite the other.
- `localhost`, `127.0.0.1`, different ports and different browser profiles have
  separate storage. Continue using the same URL/profile for autosave recovery.

Reference GLB/GLTF import is disabled only in world mode because those files are
not yet part of the project document. In Free Build, imported references display
an explicit not-saved warning; re-import them after reopening. Undo history is session-local: section
changes preserve it, but project open/reload starts fresh history. Catalog
migration, cloud saves and world/NPC editing are not included. Verified additive catalog
updates are the exception: the web-index generator records compatible prior identities
only if every prior target and its referenced snap data is unchanged. This allows existing
world projects to recover after adding these missing mappings, and updates their catalog
identity on the next save. Changes to existing visuals/exports/snaps or game version still
require explicit migration. The generator needs Node.js to match browser JSON hashing.
Older Milestone 1
projects open at their saved build camera; game JSON is unchanged. Exports include
all eligible authored objects even when their surrounding sections are unloaded.

**Export Build** asks for delivery intent and remembers the choice. **Saved World
Location** keeps absolute game coordinates: use RSDWTools **Deliver Build**.
**Place Using Anchor** exports the same source JSON: use **Deliver via Preview**
to reposition it with the native anchor. The browser cannot choose the delivery
route in the companion app for you. Anchor delivery requires a visible anchor.
Captures without a game version remain version-unverified. In-game exact delivery
and persistence are pending, not established by browser round trips.

Milestone 4 verification commands (local server required):

```powershell
node tools/Web/TestProjectDocument.mjs
node tools/Web/TestProjectStore.mjs
node tools/Web/TestGameDeliveryComparison.mjs
node tools/Web/TestUnifiedWorkspace.mjs
node tools/Web/BuildDeliveryVerificationPack.mjs
```

Results: `_build/world-builder-m4/acceptance-final/Acceptance.json`, storage report and
`game-verification/README.md`. The pack includes upright building types, a crafting
station, item and BP actor, projects and canonical expectations. Verify actor-root
captures before and after game save/reload using `VerifyGameDelivery.mjs`.
Use a backed-up test save, wait for paced queues and keep a traceable list of spawned
actors. Mathematical below-zero fixtures need a manually confirmed safe location.

## Automated Checks

With Playwright and sharp available to Node (set `NODE_PATH` to the local runtime
dependencies if needed):

```powershell
node tools/Web/TestProjectDocument.mjs
node tools/Web/TestWorldStreaming.mjs
node tools/Web/TestWorldBuilderStreaming.mjs --out _build/world-builder-m2/acceptance-final --cycles 2
node tools/Web/TestWorldBuilderJourney.mjs
node tools/Web/AuditWorldBuilderAreas.mjs
node tools/Web/BenchmarkWorldBuilder.mjs --out _build/world-builder-m2/performance --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe" --streaming --stress
node tools/Web/BenchmarkWorldBuilder.mjs --out _build/world-builder-m2/performance-four --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe" --four-sections
node tools/Web/TestWorldBuilder.mjs --out _build/world-builder-m2/editor-acceptance --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe" --cycles 50
node tools/World/AuditWorldPreview.mjs --sections x3_y1,x4_y3 --out _build/world-builder-m2/preview-regression --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

Tests use isolated temporary browser profiles, not the user's autosave. The
local-only `?world=1&debug=1` entry exposes diagnostic hooks used by these tests.
Generated fixtures, downloads, screenshots and reports stay under ignored
`_build/world-builder-m1/` or `_build/world-builder-m2/`; do not commit them.

The benchmark records 100/1,000 instanced authored pieces, cold/warm section
loads, orbit frame intervals, selection-to-next-frame latency, surface raycasts,
export/save timing, long tasks, scene draw calls and resource counts. Its elevated
synthetic grid keeps all test pieces visible instead of burying them in terrain.
It also measures the normal builder as a baseline. It is a local headless Chrome
measurement, not a guarantee for every GPU, viewport or section.
Run performance measurements alone, after other headless browser tests finish.
`AuditWorldBuilderAreas.mjs --sections x4_y0,x-4_y2 --out <ignored-directory>`
can isolate a dense destination instead of rerunning every area.

The final local reports are `performance-tuned/Performance.json` and
`performance-four/Performance.json`. The primary 100/1,000-object checks passed
the provisional frame/selection targets; the 10,000-object stress case saved and
exported correctly but was not smooth (about 83 ms frame / 208 ms selection p95).
The milestone plan records the full measurements and remaining optimization work.
Dense scenery can take tens of seconds to settle on a first visit; status reports
loading/deferred detail while the overview remains available.

## Manual Gate

### Milestone 3 Local Performance Test

Open `http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1&milestone=3`.
The normal project controls and formats are unchanged. Open a generated
`sample-10000.rsdwproject.json` through **Project > Open Project**; it is not a
game-build import. Use **0** to frame, resume world detail, edit, save, unload
sections, reload, and export. The fixture is elevated above terrain intentionally
so the full 10k build can be measured without burying objects.

The repeatable benchmark writes those samples and measurements to its `--out`
directory. Run browser measurements sequentially, never in competing browsers:

```powershell
node tools/Web/BenchmarkWorldBuilder.mjs --milestone3 --counts 100,1000,5000,10000 --fixture mixed --repetitions 3 --frames 240 --out _build/world-builder-m3/acceptance-rerun --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
node tools/Web/TestInstanceRendering.mjs --builder --out _build/world-builder-m3/instances-final --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
node tools/World/AuditWaterDepth.mjs --out _build/world-builder-m3/depth-final --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
node tools/Web/TestWorldBuilder.mjs --large --cycles 50 --out _build/world-builder-m3/editor-final --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
node tools/Web/TestWorldBuilderStreaming.mjs --out _build/world-builder-m3/navigation-final
node tools/Web/TestWorldBuilderJourney.mjs --out _build/world-builder-m3/journey-final
node tools/Web/TestBuilderAdapter.mjs --out _build/world-builder-m3/normal-rerun --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

The default authored cell size is 64 m. Use `--backend legacy` for a diagnostic comparison, `--cell 16`, `32` or `64`
for cell-size measurements, `--fixture repeated` or `legacy` for narrower
fixtures, and `--headed` for a visible browser run. `--section`, `--views` and
`--worlds` can isolate a dense section or camera scenario. Those are benchmark
controls, not new user modes. Failed gates must be reported, not hidden by
choosing easier fixtures. See the Milestone 3 plan for current evidence and
remaining acceptance work.

Current status: functional/save/export and image checks pass, including the
prior 50 section disposal cycles. The follow-up reduces wide world views to
about 29-33 ms p95 and moving all 10k to 29.3 ms in the visible-browser tests.
Whole-selection rotation/scale still miss the 33.3 ms target at 41.7/37.5 ms.
The wide-view report retains a strict floating-point threshold flag; see the
Milestone 3 follow-up results for exact values, comparisons and limitations.
Treat this as a local test build, not a finished 10k-smooth release. For the
latest persistence fixture, open
`_build/world-builder-m3/followup-large-final/10k-review.rsdwproject.json`.
It includes hidden actors and custom collections; keep your own project saved
before opening it. No test fixture is loaded automatically into your browser.

The follow-up also includes `TestTransformIntents.mjs` and
`BenchmarkLargeTransforms.mjs`. The latter accepts `--world`, `--headed`,
`--frames`, `--fixture` and optional `--profile`; it measures continuous gizmo
edits, not just one transform event. Use the commands in the milestone plan.
Generated fixtures and diagnostic profiles remain ignored under `_build/`.

### In-Game and Editing Review

Use `manual-review.rsdwproject.json` and `manual-review-building.json` in the acceptance output
for the mixed foundation/wall/floor/roof/item/BP comparison. Open the project,
Load its section if unloaded, and use 0 to frame. The separate `sample.*` fixture
also exercises hidden items: those remain in that project and are deliberately
absent from its game export.

`_build/world-builder-m2/cross-section/cross-section.rsdwproject.json` is the
separate three-section persistence fixture, with a corresponding game export.
Its objects are deliberately far apart; use the mixed sample for a compact
visual/game-delivery comparison.

Check placing/snapping on terrain, save/reload, collections, unload/reload and
both camera projections. Deliver the game JSON through the existing tool and
verify anchor-relative position, rotation and scale. Absolute-location delivery
still depends on that tool's existing anchor/delivery behavior.

In-game transform/location verification remains pending user review. Existing
material, shoreline, dune and Kuldra approximations retain their prior manual
annotations in the world audit; this milestone does not certify visual parity.

See [Milestone 1](../../WORLD_BUILDER_MILESTONE_1_PLAN.md),
[Milestone 2](../../WORLD_BUILDER_MILESTONE_2_PLAN.md),
[Milestone 3 results](../../WORLD_BUILDER_MILESTONE_3_PLAN.md) and the
[world reconstruction/audit guide](../World/README.md) for the full contracts.

The implemented [Milestone 4](../../WORLD_BUILDER_MILESTONE_4_PLAN.md) provides one
Free/World workspace and shared saves locally. Its exact-location in-game delivery
acceptance gate is still pending; browser tests are not live-game verification.

### Wide-View Follow-Up

Refresh the local builder at
`http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1&milestone=4&wideView=20261017`.
Your existing project/recovery format is unchanged. No benchmark scene is opened
automatically, and the tests use isolated browser profiles rather than your saves.

The final 10k mixed/world benchmark passes frame/input targets in all 18 samples:
wide perspective p95 20.9-25 ms, wide orthographic p95 25 ms, close p95 8.4-8.5 ms.
Perspective/orthographic before-after screenshots are pixel-identical. This pass
reuses transform/culling work across depth/color passes and coalesces overlapping
background saves, without lowering geometry, texture or rendering quality.
See the Milestone 4 follow-up for hardware, buffer dimensions, evidence and limits.
Continuous rotate/scale-all and lower-resource hardware gates remain separate.

```powershell
node tools/Web/BenchmarkWorldBuilder.mjs --milestone3 --counts 1000,10000 --worlds true --views full,close,orthographic --frames 240 --repetitions 3 --render-origin 176400,75600,0 --viewport-height 1060 --out _build/world-builder-wide/final-performance --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
node tools/Web/TestWideViewRendering.mjs --source _build/world-builder-wide/baseline/source
node tools/Web/TestAutosaveScheduling.mjs
node tools/World/AuditWaterDepth.mjs --url http://127.0.0.1:8765/RSDWBaseBuilder/website/world/ --out _build/world-builder-wide/depth --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
node tools/Web/TestUnifiedWorkspace.mjs --out _build/world-builder-wide/workspaces
```

`ProfileWideView.mjs --profile --out <ignored-directory>` records CPU profiles
and depth/color timings. Add `--snapshot` **before** an optimization to retain the
source used by image and profiling comparisons; `--source <snapshot-directory>`
runs that source with the same fixture/data without reverting the worktree.
The initial snapshot is local ignored evidence, not a required shipped asset.
Run all GPU browser checks sequentially. Do not overwrite a comparison snapshot
with the optimized source or treat a diagnostic profile as a release benchmark.
