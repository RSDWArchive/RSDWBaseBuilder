# Local World Reconstruction

This opt-in viewer reconstructs the packaged world from dataset **1.0.0.5**, or
loads the original small-region sample. It
does not modify the production builder, its JSON format, add-on, or normal
release pipelines. No world data is published. Generated files remain ignored.

The existing BaseBuilder now also has a separate local-only `?world=1` workspace
for authoring against one section. See [World Builder local testing](../Web/WORLD_BUILDER_LOCAL.md).
The standalone viewer below remains available; both hosts share the material,
water/depth and asset-rendering adapters under `website/world/`.

### Current Source Completion Pass

All **104 baseline candidates / 58 materials / 27 shader families** have been
source-inspected. This is completion of the source-data review, not in-game
visual approval. The whole-world and sample builds pass. The full render audit
covers **8,407 variants / 2,298 models with zero errors**. White/pale/uniform
candidates decreased to **79 variants / 64 models**, with no new pixel flags.
Validation also passes 92 Python tests, 17 JS syntax checks, three JS regression
suites, eight targeted section loads and desktop/mobile gallery/sample checks.
This section subset is not a fresh full-world section sweep.

Confirmed fixes enforce disabled diffuse/normal/emission branches, prevent
opacity/smoke inputs being treated as diffuse, and recover the named Dowdun
`Colour Multiplier`. Limited source-color and opacity proxies improve checker
materials, ghost/fur surfaces, glass, spectral cobbles and Kuldra effects.
They do not reconstruct their specialized shader graphs. In particular, Kuldra
effects clearing white flags after applying source opacity is not shader parity.

The gallery's **Source-inspected baseline** filter retains all 104 candidates,
including cleared ones. Expand **Source investigation** for the material-specific
manual checks. All remain pending in-game verification. Kuldra tunnel floor/wall
routing and dune deformation still need reference evidence; neither is guessed.

Evidence: `_build/world-region/source-completion-pass/SourceCompletion.json`,
`DuneCoverage.json`, `AuditComparison.json`, `SectionSummary.json` and
`Validation.json`. The dune report accounts for all 315 placements / 6 variants.
Its 9x9 world-XY bounding-box probes are not visible-triangle coverage or height
tests. Ten placements have no landscape XY overlap; 32 exceed 500 m horizontal
span. See [source completion and manual checks](../../WORLD_REGION_PROTOTYPE_PLAN.md#source-completion-pass).

To repeat the source review, preserve `WhiteMaterialReview.json` as a baseline
before rebuilding/rerendering. After the **full** render audit completes, run
from `E:\Github\RSDWModel` (replace the baseline/output paths for a new pass):

```powershell
python tools\World\AuditWhiteCandidates.py --root ..\RSDWBaseBuilder\_build\world-region\1.0.0.5\whole-world --archive-root ..\RSDWArchive\1.0.0.5\json --baseline ..\RSDWBaseBuilder\_build\world-region\source-completion-pass\BeforeWhite.json --audit ..\RSDWBaseBuilder\_build\world-region\visual-material-audit\VisualAudit.json --out ..\RSDWBaseBuilder\_build\world-region\source-completion-pass\SourceCompletion.json --annotate-gallery
python tools\World\AuditDuneCoverage.py --root ..\RSDWBaseBuilder\_build\world-region\1.0.0.5\whole-world --out ..\RSDWBaseBuilder\_build\world-region\source-completion-pass\DuneCoverage.json
```

The completion tool refuses a partial audit or scene mismatch, accounts for
cleared candidates, and fails for unclassified families, missing candidates,
confirmed role gaps, missing bound files or render errors. Source dependencies
and texture samples are recorded independently of rendered pixel metrics.
`--annotate-gallery` attaches review notes to generated JSON only; rerendering
the audit replaces those annotations, so rerun source completion afterward.
These are opt-in prototype tools, not new production pipeline stages.

### Previous Crystal/Dune Pass

Crystals now have an explicitly limited source Base-color/normal/PBR proxy;
packed masks, gradient/glow, subsurface and fade are still unverified. Named
Kuldra heart-base and opaque stained-glass maps are recovered, and textureless
standard materials use source color/PBR constants. No production WebAssets are
rewritten. Dune diagnostics measure the visible terrain-atlas versus pale
fallback fraction; deformation is not invented.

The material audit emits `WhiteMaterialReview.json` for every remaining white,
pale or uniform-texture candidate, with source-family evidence and manual review
status. The gallery adds **White / pale surfaces only** and expandable
**White-material investigation** notes. Invisible-only effects remain separate.
Run `node tools/World/TestWhiteTriage.mjs` alongside the existing metric tests.
Current evidence: `_build/world-region/crystal-dune-pass/`.
See [follow-up and future editor boundaries](../../WORLD_REGION_PROTOTYPE_PLAN.md#crystal-and-dune-follow-up).

The completed scan renders **8,407 variants / 2,298 models with zero errors**.
White/pale/uniform candidates decreased from 156 to 104 (89 distinct models),
with no newly flagged variants. All 48 crystal variants clear the white/pale
pixel checks, but glow, gradients and fade remain manual checks. The sampled
pale dunes expose 81-100% preview fallback in their isolated views; other dune
variants have good atlas coverage. This is diagnostic evidence, not a dune
deformation fix or proof of Unreal's exact fallback shader math.

Both builds, 86 Python tests, 17 JS syntax checks, three JS regression suites,
eight selected section regressions, and desktop/mobile gallery checks pass.
The eight-section subset is not a repeat of the prior full-world section sweep.
Final results: `_build/world-region/crystal-dune-pass/Validation.json` and
[manual comparison queue](../../WORLD_REGION_PROTOTYPE_PLAN.md#next-in-game-checks).

### Previous White-Surface Pass

The local renderer restores the named Witherspine `RockFractures` input,
Kuldra vine BCC/NRM references, Kuldra interior BCR/NM inputs, and masked
ground-rock BCA/NR inputs. Witherspine Tint/roughness/metallic and non-default
standard-environment Color Multiplier values are source-driven
static proxies, not reconstructed cooked shader graphs. Linear RGB values are
assigned once against raw recovered textures; tint alpha is not opacity and
cached GLTF tint is not multiplied a second time.
Brightness remains annotated but unapplied: directly multiplying the source
value made rune essence too pale during the regression pass. Its shader math
needs in-game/reference evidence before it is enabled.

`VisualAuditIndex.json` includes material-specific `review_notes`. The audit
gallery exposes them under **In-game verification notes**, including remaining
crystal masks, live Witherspine effects, ageing, packed channels, parallax and
wetness. A corrected texture binding never marks a model visually approved.
The follow-up evidence and before/after images live under the ignored
`_build/world-region/color-material-pass/` directory. See the root prototype
plan for the manual comparison queue. `node tools/World/TestSurfaceSettings.mjs`
checks the color/PBR adapter independently of browser screenshots.

The completed follow-up passes 82 Python tests, all 314 section loads and all
nine world/area selections. The material scan covers 8,407 variants / 2,298
models with zero final errors. Pale-surface flags fell from 262 to 143; this is
an audit improvement, not in-game approval. Consolidated results and the
remaining manual checks: `_build/world-region/color-material-pass/Validation.json`
and [White Surface Follow-Up](../../WORLD_REGION_PROTOTYPE_PLAN.md#white-surface-follow-up).

## Run Locally

Prerequisites: matching Archive JSON and Model WebAssets/index, original Retoc
packages with one matching usmap, the shared CUE4Parse checkout, Python with
`RSDWModel/tools/World/requirements.txt`, and .NET 8. The viewer uses the existing
Three.js 0.184.0 CDN pattern and Google's Draco decoder, so its first load needs
internet access. Geometry and recovered textures are served from localhost.

From `E:\Github\RSDWModel`:

```powershell
python tools\World\BuildWorldRegion.py --version 1.0.0.5 --region-config ..\RSDWBaseBuilder\tools\World\regions\fellhollow-road-ruins.json --out-root ..\RSDWBaseBuilder\_build\world-region\1.0.0.5\fellhollow-road-ruins --mode build --resume
```

Use `--mode plan` for the inventory without conversion, or `--mode validate` to
check existing outputs. The region config and Model index must match `--version`.
Resume caches native recovery by source identity, cooked-package metadata,
mapping hash, exporter source hash, and CUE revision. Terrain/color/manifest
assembly checks its own terrain cache; unchanged terrain bakes may be reused,
while material/road/manifest assembly reruns. A forced `--mode build` without
`--resume` recovers sources again.

## Whole World and Sections

The whole-world expansion is opt-in and remains separate from production.
From `E:\Github\RSDWModel`:

```powershell
python tools\World\BuildWorld.py --version 1.0.0.5 --out-root ..\RSDWBaseBuilder\_build\world-region\1.0.0.5\whole-world --mode build --resume
```

Use `--mode inventory` for source discovery only, or `--mode validate` to check
the existing full output. `--workers` defaults to 8; native batches use up to 8
separate processes. Resume validates source metadata, exporter code and cached
outputs. Verified terrain bakes are reused independently of mesh-material fixes.
Allow substantial disk headroom: the build refuses to start below 12 GiB free
and native recovery stops below 8 GiB. Those are safety thresholds, not total
storage estimates. A failed run can be resumed without discarding successful
native batches.

Open <http://127.0.0.1:8765/RSDWBaseBuilder/tools/World/preview/index.html?world=1>.
The original sample is still the default page. Whole-world mode provides:

- Whole-world terrain overview, or a biome/individual spatial section selection.
- Approximately 504 m square sections generated from source bounds, not a
  hand-maintained map list. Biome labels are inferred from landscape materials.
- Coarse terrain at long distance; full-detail terrain and instanced static
  scenery near the camera's orbit target when the camera is within 1.5 km.
- A 520 m wide detail window, refreshed after navigation settles. Selecting
  "all" enables world-wide streaming; it does **not** keep every model resident.
- Selecting an individual section loads that complete section,
  without clipping it to the quantized camera window.
- Distant views show clickable, screen-sized section markers. These are
  navigation targets, not rendered replacement geometry or loaded placements.
  Area Overview returns to the selected area's bounds. Status distinguishes
  loaded placements, blockouts and deferred sections.
- Areas without landscape tiles start on their most populated non-helper
  section. `Outlying Scenery` is a fallback classification for cells without
  landscape tiles, including some vault interiors, not a verified biome name.
- Stable source identities deduplicate models crossing section boundaries.
  Unloaded detail releases geometry, textures and instance buffers.
- The Blockouts layer is off by default for inspection. It retains basic shapes
  with default/debug/blackout materials and explicit level-design blockout meshes;
  developer `Prototype` resources also live here. Basic shapes with real ground
  materials remain visible. Meshes assigned a recognized water material also
  remain visible: the game reuses a `BlockoutMeshes/SM_BO_Water_Plane` mesh for
  real water. Nothing is deleted.

The scope is the packaged `L_World` static environment, including surface and
cave landscapes, not menus, server startup maps, HLOD substitutes, live actors,
gameplay, weather, or animated effects. Recognized fog/aurora volume shaders are
explicitly excluded rather than displayed as opaque white geometry. Other
unsupported procedural shaders remain recorded in the material review queue.

Additional outputs in `whole-world/`:

| File | Meaning |
| --- | --- |
| `WorldIndex.json` | Section names, inferred biomes, bounds, counts and identity digests |
| `WorldShared.json` | Shared model/material descriptors and coarse terrain |
| `sections/*.json` | Independently loadable section placement and terrain manifests |
| `SpanningPlacements.json` | Very large geometry shared across section boundaries |
| `SectionAudit.json` | Per-section model/material inventory and outstanding review status |
| `SectionValidation.json` | Exact placement and terrain identity coverage checks |
| `ModelAudit.json` | Distinct model review queue, material references and affected counts |
| `MaterialSources.json` | Full inherited source parameters for diagnostic comparison |
| `VisualAuditIndex.json` | Every active mesh/material variant, source flags and one reproducible placement |

Structural validation is not visual approval. A section marked
`built_pending_visual_review` is available to inspect, not certified identical
to Unreal. Material arrays, RVT, procedural VFX, water and landscape shading may
still require dedicated adapters. Every distinct model and every section is
covered by the generated audits; screenshots sample rendered areas only.

### Isolated Material Review

The scene builder now generates `VisualAuditIndex.json` on every build. Structural
validation checks its scene fingerprint and exact active variant coverage, and
fails on required material conversion gaps. This remains an opt-in world tool,
not part of the production base-builder release pipeline.

From `E:\Github\RSDWBaseBuilder`, with Playwright and Sharp available to Node:

```powershell
node tools\World\AuditWorldMaterials.mjs --out _build/world-region/visual-material-audit --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe" --workers 3 --resume
node tools\World\AuditWorldPreview.mjs --out _build/world-region/browser-audit-materials --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
node tools\World\TestPixelMetrics.mjs
```

The material audit uses the actual preview renderer and effective component
overrides, including native geometry, instancing, transparency and alpha cuts.
Three isolated views retain the source placement transform but normalize camera
framing and lighting. Rendered alpha supplies the object mask; background pixels
do not contribute to white/pale-surface statistics. Uniform base textures,
source defaults, unsupported branches and runtime mapping errors are separate
signals. A white pixel is not an automatic material defect.

`--limit N` supports smoke checks; `--assets id,id` restricts variants. `--workers`
accepts 1-6 contexts and defaults to 3. `--resume` requires identical source,
renderer and scene fingerprints and existing preview files. `--root` selects
the local index; a custom `--url` must serve the same scene, or the audit fails.

Outputs are ignored: `VisualAudit.json`, three-view WebP contact sheets under
`previews/`, and `index.html`, a searchable local review gallery. The report
retains model/material identities, affected placement counts, source flags,
runtime bindings, pixel measurements and in-world camera bookmarks. All rows
remain `manual_review_pending`; a completed scan is not in-game approval.
Gallery review choices are browser-local and keyed to the audit fingerprint,
so a changed build does not inherit stale approval. Keep important user
verification notes in `WORLD_REGION_PROTOTYPE_PLAN.md` as well.

The browser sweep now tests all area-group selections and their overview
navigation before its per-section checks. This closes the earlier coverage gap
where individual sections passed while Outlying Scenery / All sections loaded
zero meshes. Environment-dependent terrain projection, water, particles and
dune deformation still need in-world review rather than isolated thumbnails.

The rock adapter selects the explicit `Rock BaseColor` and `Rock Normal` maps
instead of a default detail-layer albedo. An independent source-intent audit
checks that primary mapping. Optional moss/detail blending, curvature, wetness
and landscape blending remain documented approximations, even after the primary
map is restored.

The enabled `Is VT` branch on standard environment materials now resolves
`Virtual BaseColor` and the appropriate virtual normal input rather than the
inactive regular white/flat defaults. Campfire-ash mesh decals recover their
`BCO` color/alpha and `NR` normal inputs when `Use R as Alpha` is false. These
are static surface reconstructions: virtual streaming/RVT blending, deferred
decal projection and the unrecovered decal emission connection are not claimed
as reproduced. Their source branches have independent audit checks and tests.

The legacy `M_Master` family now selects `Albedo00` / `Normal00` instead of
incidental white blend masks. `M_Character_Standard` selects `BaseColor Map` /
`Normal`, or their explicitly enabled `UseVT` alternatives, instead of a
subsurface mask. Its `HasOpacity` switch controls alpha testing. Layer/tint
blends, custom UV behavior, dye and character effects remain review items;
these surface bindings do not claim full reconstruction of either shader.

Review links request an explicit section before applying a camera bookmark, so
large isolated assets do not disappear behind the distance-based overview
policy. Helper-only review links explicitly enable the Blockouts layer.

### Landscape Boundaries

The full scan found mismatched raw heights at some shared landscape boundaries.
Unreal performs [runtime edge/corner patching](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Landscape/ULandscapeHeightmapTextureEdgeFi-).
This prototype uses a deterministic shared-height average within the same
landscape GUID as a **static approximation**, not a byte-for-byte port of that
shader/streaming implementation. `TerrainReport.json` retains the raw maximum
delta, affected source components and reconstructed boundary positions. Separate
landscape GUIDs are never blended. The independent CUE probe compares raw
decoded heights before this reconstruction. These adjusted boundaries need
particular attention during in-game comparison.

Full-detail terrain now shares area-weighted lighting normals across coincident
edges within each landscape GUID. The overview samples those same normals,
instead of calculating unrelated normals on each coarse tile. This removes an
additional source of lighting seams without changing the source height decode.
Overview tiles containing visibility holes retain the original visible
triangles; sampling one corner of a coarse quad could otherwise fill an opening.
Hole-free tiles still use the smaller coarse grid.

### Terrain Color Reconstruction

The color bake uses zero for absent painted layers. A base-layer fallback is
used only where the entire relevant weight group is unpainted; it is not mixed
into another painted sub-biome. Paint masks are interpolated at terrain vertex
coordinates, retaining their edge samples. Color textures are filtered to the
bake's pixel footprint, sampled bilinearly, blended/tinted in linear light, and
encoded back to sRGB. Each source texture's `SRGB` flag is retained: explicitly
linear color textures are not gamma-decoded a second time. Mesh color/emissive
textures with that flag are encoded to sRGB for the browser while preserving
alpha, and listed in their descriptor's `linear_color_sources` field.
Road compositing uses the same color convention. This
matches the [glTF color-space contract](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#textures).
Generated mesh normal maps use lossless WebP encoding after the existing
resolution limit, avoiding color-compression artifacts in vector data.

`source-data/TerrainReport.json` (also embedded in `WorldRegionReport.json`)
records `normal_reconstruction` and each tile's `samples[].color_bake`:

- Active paint layers not yet represented by the static color bake.
- Unpainted fallback coverage and missing level/sub-biome masks.
- Assumed biome ranges and ranges exceeding the source texture-array size.
- Approximate feature-paint blends and unresolved feature ranges.
- Filtering, color-space and tiling policy.

The 4 m texture period is still an approximation. Cooked material functions
retain parameters but not their editable expression connections, so parameter
names alone do not establish the exact UV, slope, height-blend, noise or feature
paint equations. Valid explicit `BiomeA/B_Feature` ranges now use their painted
`Param_FeatureA/B` coverage as a normalized overlay, with the existing level
mask interpolating within each range. This is an auditable static approximation,
not a recovered height-blend graph. Negative, absent or out-of-bounds feature
ranges are not guessed or clamped into unrelated slices. Those omissions remain
review items, not silently certified fixes.

### Water Surfaces

Water is identified by the actual `M_Water`, `M_Water_Translucent` or
`M_Water_River` master, not a folder name. Foam and waterfall effects are no
longer stripped of their cached surface maps by the water fallback. Shipped
water planes remain visible even when their mesh lives in a blockout folder.

The static adapter restores source normal maps, two normal-layer strengths,
roughness, and river UV scales. Non-river normals use source scale values as
world-space periods in centimeters; that interpretation and the combined normal
formula are still approximations of the unavailable graph. Normal sampling is
frozen at time zero, so the viewer continues to sleep while idle.

Flat color and flat-color emission are used only when their source switches
enable them. Otherwise a scattering/(scattering+absorption) color proxy is used,
or the older river master's deep-water color/tint. This is not depth-aware
transmission. SingleLayerWater's source opacity is not mapped to alpha: it
controls surface/volume mixing in Unreal, as described in
[Epic's water shading documentation](https://dev.epicgames.com/documentation/en-us/unreal-engine/single-layer-water-shading-model-in-unreal-engine).
Translucent variants retain their source opacity. Source roughness is clamped
to the renderer's 0..1 range.

`settings.water` records applied values, the color method and unsupported enabled
switches. Both build-time and browser audits check the supported surface
bindings. A scene-depth pass now blends water into opaque surroundings, retaining
alpha-cutout foliage and instanced transforms. The older river master uses its
shallow/deep colors, opacity and centimeter depth distances. Modern water with
`UsePDO?` enabled uses `PDOBlend / 100` as a linear edge-fade distance: an explicit
**preview approximation**, not the recovered pixel-depth-offset equation or
Unreal's SingleLayerWater pass. Its source surface/volume opacity stays separate.
The depth pass supports both the sample camera and whole-world logarithmic depth,
resizes with the viewport, and runs only on dirty frames with a visible affected
surface. It costs an additional opaque-scene render on those frames; idle views
still sleep. See [Epic's depth-fade description](https://dev.epicgames.com/documentation/en-us/unreal-engine/depth-material-expressions-in-unreal-engine).

Foam instances using `M_VFX_Master_TransSimple` now recover the `TexA` mask as
lossless linear data, source channel weights/tiling, opacity and enabled constant
color. This is a static subset, not the complete VFX graph: radial/shape masks,
UV distortion, particle inputs, time, day/night and glow are still unverified.
It does not invent a white foam band around every body of water. Dynamic water
interaction foam requires runtime data that the static archive does not contain.
Refraction, caustics, cloudy/oily water, duckweed and River/Lake of Souls effects
also remain review items; the presence of masks/normals is not visual approval.

The focused GPU regression check exercises depth decoding, translated instances,
alpha-cutout holes, background pixels, resize, river blending and foam masks:

```powershell
node tools\World\AuditWaterDepth.mjs --out _build\world-region\shoreline-validation --chrome "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

It uses Playwright, with the same `NODE_PATH` setup as the section audit below.

Scene-capture-only components are excluded during inventory, including inherited
template flags with per-instance overrides. This removes swamp lighting cubes
that otherwise render as dark slabs above the water. They are not visible in the
normal game view, per
[Epic's component visibility contract](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/UPrimitiveComponent).
Their exclusion reason is retained in `RegionPlan.json`; this does not recreate
their indirect illumination or scene-capture contribution.

Close-up inspection still finds static dune geometry overlapping parts of oasis
water. The dune source has grounding/flattening parameters, but the cooked graph
does not establish their exact displacement equations. `settings.deformation_review`
and the `dune_deformation_unreconstructed` audit issue retain the source RVT/sand
function references and relevant parameters. Five distinct dune meshes occur in
315 placements in this dataset. Their geometry is deliberately not flattened from
parameter names alone. Matching in-game views are now needed to establish the
correct shoreline silhouette and acceptable static deformation approximation.

### Start the Local Viewer

From `E:\Github\RSDWBaseBuilder`:

```powershell
powershell -ExecutionPolicy Bypass -File tools\World\StartWorldPreview.ps1
```

Open <http://127.0.0.1:8765/RSDWBaseBuilder/tools/World/preview/index.html>.
Use `-Port 8766` if needed. The hidden server binds only to loopback and serves the
shared `E:\Github` root, allowing access to both repos. It prints its process ID;
stop it with `Stop-Process -Id <printed-id>`. A computer restart stops the server.
HTTP/1.1 keeps connections alive during large section sweeps instead of opening
a new local connection for every texture. The launcher requires a Python runtime
with `http.server --protocol` support (verified locally with Python 3.13).

## Inspection

- Left/middle drag orbits, right drag pans, wheel zooms; Home or 0 reframes.
- The view selector provides oblique, overhead, and road-level starting views.
- Layer checkboxes isolate terrain, foliage, buildings, roads, and scenery.
- Roads includes physical paving plus the terrain-baked contribution of RVT
  splines. Turning it off restores the unbaked terrain color.
- Save View downloads a UE-coordinate camera bookmark and puts it in the URL
  hash. Reopening that URL restores the viewpoint.
- `window.worldRegionDebug.metrics()` reports local loading/render measurements.
  The viewer renders on changes, not continuously while idle. FPS samples reflect
  active rendering; they are not a promise of performance on other hardware.
- `window.worldRegionDebug.auditMaterials()` checks loaded mesh sections against
  the material descriptors. `adapter_mismatches` identifies failed application
  of supported source rules; unadapted shader differences are `needs_review`.

## Outputs and Validation

All generated files are in
`_build/world-region/1.0.0.5/fellhollow-road-ruins/`:

| File | Meaning |
| --- | --- |
| `PipelineRun.json` | Current run/mode and persisted stage status; only `success` is completion |
| `RegionPlan.json` | Source inventory, identities, transforms, exclusions and provenance |
| `WorldRegion.json` | Browser manifest, rebased at render time, canonical UE matrices retained |
| `WorldRegionReport.json` | Coverage, dependencies, approximations, source-controlled material settings, unsupported texture roles and structural validation |
| `MaterialAudit.json` | Ranked per-material diagnostics for active mesh sections, affected models/placement counts, and sample UE locations |
| `source-data/native/NativeExport.json` | Identity-safe original-source recovery results |
| `source-data/TerrainReport.json` | Border checks, packed-height samples, independent native probe comparison |

An abrupt termination leaves a `running` stage, not a new success. Read the run's
mode: a successful inventory/validation alone does not mean a fresh build.
The build rejects missing visible geometry, unresolved attachment hierarchies,
invalid transforms, missing dependencies, terrain seams over 1 cm, and RVT roads
that reach no terrain. Materials with unavailable optional parent defaults are
listed in the report; they do not silently count as exact rendering.
Every build regenerates the material audit. Validation rejects a missing audit
or one whose scene hash does not match. The audit's material warnings remain
nonfatal and are distinct from structural validation success.

The audit compares effective section materials (including component overrides)
with inherited Archive parameters, hard-wired texture references, and Model's
glTF bindings/texture provenance. Unused material slots and terrain-baked road
planes are excluded; terrain uses its own report. Results distinguish:

- `conversion_gap`: a required descriptor or mapped texture cannot be provided.
- `needs_review`: unknown shader connections, unverified tint/brightness, missing
  source defaults, or a parameter-derived texture difference needing shader review.
- `corrected_in_preview`: a cached-model mismatch repaired by the local adapter.
- `no_detected_gap`: these checks found nothing; this does not certify visual parity.

Inspect individual issues as well as each material's highest-priority status:
the rune material, for example, has corrected texture bindings but still needs
review for omitted animation. Sample positions identify a placement to inspect,
not a guaranteed useful camera viewpoint. The audit does not guess textures for
unknown shaders or treat deliberately untextured/constant-color materials as broken.

Tests from Model: `python -m unittest discover -s tools\World\tests -v`.
Viewer syntax: `node --check tools/World/preview/world.js` from BaseBuilder.

### Whole-World Browser Audit

With the localhost server running and Playwright available to Node (installed
locally or through `NODE_PATH`), run from BaseBuilder:

```powershell
node tools\World\AuditWorldPreview.mjs --out _build\world-region\browser-audit --chrome "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

This sequentially visits every section, verifies complete section loading,
checks material adapters and browser/network errors, reads canvas pixels, and
saves one screenshot per section with an incremental `BrowserAudit.json`. A full
sweep also verifies that every distinct indexed model was loaded at least once.
`--sections x2_y1,x6_y0` narrows a diagnostic run. `--resume` reuses passed results
only when the world scene, viewer and audit-tool fingerprints match. The headless test
browser is closed afterward. Near-white or uniform images are review warnings,
not automatic proof of missing textures. These checks do not compare against
in-game screenshots or establish visual parity.

The earlier 2026-10-16 water/terrain-feature pass passed all 314 section loads and
covered all 2,298 distinct indexed models without browser/network errors or
supported-adapter mismatches. Its report and captures are under
`_build/world-region/browser-audit-water-final/`. All 59 focused Python tests pass.
Desktop/mobile and sample interaction results are recorded in
`_build/world-region/WaterFeatureInteractionValidation.json`; water close-ups
include source placement IDs and UE-coordinate camera bookmarks. Final build
and audit counts are in `WaterFeatureFinalBuildValidation.json` in that folder.
The world and sample were both rebuilt after the capture-only visibility fix.

The 23 uniform-frame warnings comprise 16 helper-only sections, five sections
overlapping an unreconstructed additive fog volume, one nearly visibility-masked
terrain component, and one small visible Sand Vault terrain patch (`x-9_y0`).
The latter still renders the same footprint as before; the updated bake changed
its sparse sampled palette from three quantized colors to two. These warnings
are retained, not interpreted as missing geometry. No new warnings were introduced
by the water/terrain-feature pass. Source material review
warnings remain separate from these successful loading checks. Full results
and remaining terrain limitations:
[refinement checkpoint](../../WORLD_REGION_PROTOTYPE_PLAN.md#water-and-terrain-feature-checkpoint).

## Current Limitations

The foliage material pass honors inherited Unreal `CanBeEmissive` switches,
alpha-cutout overrides, and two-sided flags. It removes unintended constant-white
emission from 901 placements in the current region (ferns, small plants, peace
lilies, water lettuce and foxgloves), while retaining source-enabled emissive
maps on flowers. Vertex channels used by foliage shaders are no longer applied
as literal RGB/alpha tint; source-enabled red-channel AO affects indirect light.
These corrections run during every prototype build and do not rewrite Model's
shared WebAssets. `material_rendering` in the quality report audits the settings.

The rune essence pass restores the hard-wired `M_VFX_GeyserStones` maps on three
models / 12 placements. The cached glTF omitted base color and assigned the BCC
color texture to emission; the prototype now uses the original BCC, NRM and E
textures in their respective channels. Purple geyser illumination is retained.
This is a static material approximation; shader-driven rotation/glow animation
is not reproduced. Model's shared WebAssets and production pipelines are unchanged.

The broader pass resolves material parameter names case-insensitively so child
emission overrides win. Explicit `BaseColor` parameters outrank moss/overlay
filename guesses. Dowdun ageing surfaces and baked mechanised traps receive
their source base/normal maps locally, as do Dreamstone and vertex-painted rock
surfaces. Layered moss, packed shader behavior and UV animation remain explicit
approximations. Optional duckweed is not treated as water's base texture.
Disabled fur texture branches and
constant-white mountain defaults are not reported as missing diffuse maps.
Background mountains use their source `Color Base` tint rather than the cached
white fallback; their multi-channel splat/contrast blend still needs review.

This is a structural reconstruction, not Unreal rendering parity. Terrain color
uses original biome arrays/weights with an approximate blend. Rock base color is
world-projected; full moss, wind, wetness, water, lighting, and animated shader
effects are not reproduced. Regional water uses the static adapter above; global ocean-mask
planes and recognized atmosphere/VFX helpers are explicitly excluded and reported.
The `MI_UMS_Dunes` and mesh-assigned landscape shaders can receive a
world-projected atlas when compatible landscape tiles and texture-gap metadata
are available. This is conditional, not a blanket white-surface fix: the small
region's `SM_UMS_DuneShape_02.2` remains flagged for its pale/white surface and
unreconstructed deformation. Atlas shading remains an approximation of Unreal
RVT/array sampling; procedural normals, grain and shader blending still need
review. Source switches
and static texture maps do not reproduce
animated proximity glow, subsurface scattering, or full landscape blending.

The chosen region crosses a cliff edge. The eastern side is not a missing flat
floor, and retained large boundary-crossing cliff meshes can extend beyond the
nominal 252 m square. Complete intersecting terrain components are retained.
Camera presets are inspection starting points, not confirmed in-game bookmarks.

**In-game parity is still pending.** Compare matching overhead, road-level and
oblique captures using saved source coordinates before accepting visual parity.
The user has authorized whole-world expansion while this comparison remains
open. Browser-only checks cannot establish parity.

Source ownership and acceptance gates: [prototype plan](../../WORLD_REGION_PROTOTYPE_PLAN.md).
