# Small World Region Reconstruction Plan

Status: local prototype implemented; structural build and terrain checks pass.
Visual refinement and matching in-game comparison remain acceptance gates. No
production pipeline, deployment, or build-export behavior has changed.

Implementation and local run commands: [World prototype guide](tools/World/README.md).

Next editor milestone: [Build in one world section](WORLD_BUILDER_MILESTONE_1_PLAN.md).
This separate plan covers authored-state isolation, project saving/recovery and
unchanged game exports. It is not yet implemented.

## Source Completion Pass

2026-10-16 continuation. **All 104 original white/pale/uniform candidates have
been source-inspected**, covering 58 effective materials and 27 shader families.
This closes the source review queue, not the in-game visual acceptance gate.
No builder/add-on schemas, production pipelines or published assets changed.

### Changes and Limits

- Enforce source-disabled diffuse, normal and emission branches, including
  ShellFur, NPC ghosts, SimpleGlass and character emission. Remove ghost opacity
  and AnimaDoor edge-smoke inputs incorrectly selected as diffuse. Existing
  cached GLTF maps are explicitly cleared when their source branch is disabled.
- Recover Dowdun's British-spelled `Colour Multiplier` through the established
  tint-only approximation. Do not infer missing shader brightness math.
- Use limited source-color proxies for texture-disabled fur (`MixColor`),
  ghosts (`Color A`), spectral cobbles (`ColourA`), AnimaDoor (`BaseColour`),
  and procedural checker materials (first checker color/roughness). These are
  not reconstructions of shell layers, caustics, animated masks or checker lines.
- SimpleGlass uses `TintGlass` and `OpacityMin` as a static minimum-opacity
  proxy. Fresnel opacity, reflection and refraction still need comparison.
- Kuldra backdrop, basin and swirl effects now use source `Opacity` scalars
  0.04 / 0.05 / 0.1. Their white flags clear, but color curves, layer masks,
  glow, animation and vertex motion remain unresolved. Reduced white coverage
  caused by transparency is not evidence of a fully correct shader.
- Kuldra tunnel source contains ground and wall BCR/NMM inputs plus a curve
  atlas. Cooked exports do not establish the floor/wall masks, segment UVs or
  curve sampling. No arbitrary ground-on-wall substitution was applied.
- Dune atlas inclusion was checked; the pale samples are not explained by
  accidentally omitted Umbral Sands landscape tiles. All 315 placements across
  six variants are recorded in `DuneCoverage.json`. Ten have no landscape XY
  overlap; 32 exceed 500 m horizontal span. The 9x9 AABB probes are diagnostics,
  not actual triangle coverage, height tests or Unreal RVT behavior. No geometry
  flattening, nearest-terrain stretching or arbitrary recoloring was introduced.

### Results

Whole-world rebuild: 330.4 seconds, all stages successful. The full material
scan renders **8,407 variants / 2,298 models with zero errors**. The original
104-candidate queue falls to **79 variants / 64 models**, with no new pixel
flags anywhere. Twenty-five candidates clear white/pale checks: 17 procedural
checker variants, three glass props, three Kuldra effects, one Dowdun effigy
and one spectral cobble variant. They remain manual-review pending.

Near-white flags: 29 -> 11; pale flags: 91 -> 66; uniform-texture flags stay at
13. Invisible-only flags: 3,443 -> 3,335. Overall pixel-flagged variants:
3,547 -> 3,414. Source flags rise by three because the glass approximations now
explicitly disclose their unreconstructed shader behavior. No automated metric
constitutes in-game approval.

The eight targeted section regressions pass with zero runtime errors, material
adapter mismatches, canvas warnings or HUD overflow. They include Outlying
Scenery, Kuldra, dense Ashenfall sections and Umbral Sands. This is not a new
314-section sweep. The subset loads 1,219 distinct models; the raw subset
report's `models.missing` means outside these eight sections, not failed loads.
The independent isolated scan renders every model.

The gallery retains all original 104 through **Source-inspected baseline**,
including cleared entries. **Source investigation** contains the per-material
manual checks, bound texture roles and missing expression-graph evidence.
Desktop/mobile checks pass with 48 -> 96 -> 104 pagination, searchable notes,
79 white-filter entries, no load errors and no horizontal overflow. Sample
desktop/mobile rendering and camera changes also pass.

All 92 Python tests, 17 JavaScript syntax checks and the three surface-settings,
pixel-metric and white-triage regression suites pass. Both repositories pass
`git diff --check`; explicit whitespace checks also cover the untracked
prototype source files. No changes have been committed or pushed.

Generated evidence: `_build/world-region/source-completion-pass/`, including
preserved before images/audit, `SourceCompletion.json`, `DuneCoverage.json`,
`SourceChanges.json`, `AuditComparison.json`, `SectionSummary.json` and
`Validation.json`. Current scene SHA-256:
`c01fb697aba1aeb272a003dd958971b54273fc81637f3e5f5cfaa5e00583144b`.

### Manual Verification Queue

Use the local material gallery, search the names below and select **Open in
World** for the sampled placement. Do not approve all instances from a single
isolated thumbnail. Source inspection remains distinct from the user's saved
"Verified against game" status.

| Search / filter | Evidence still needed |
| --- | --- |
| `SM_UMS_DuneShape_02`, `SM_UMS_DuneShape_03` | Compare terrain contact, large skirts, vertical deformation and blends at pale versus well-covered placements. `DuneCoverage.json` retains all placements for follow-up. |
| `SM_TunnelConnection_02`, `SM_Kuldra_Walls` | Floor/wall mask, segment UV and curve-atlas behavior; source inputs exist but their combination is unresolved. |
| `SM_KuldraBackdrop`, `SM_VFX_Bottom_Layer`, `SM_VFX_Swirls` | Whether these prototype effects are visible in-game, plus opacity, glow, color curves, masks and animation. Their new scalar-opacity proxies require comparison. |
| `M_NPC_Ghost`, `M_ShellFur` | Disabled texture branches are corrected; rim/glow, opacity masks, shell detail and final brightness are not reconstructed. |
| `M_Tool_ProcGrid`, `M_SimpleGlass` | First-checker-color and minimum-opacity proxies; verify final pattern, glass Fresnel/refraction and whether helper geometry is visible. |
| Source-inspected baseline | All 104 remain available, even the 25 that cleared flags. Review material-specific notes and preserve the user's manual verdict. |
| White / pale surfaces only | Remaining 79 are not all missing textures: pale source images, helpers, effects, one unassigned source slot and shader-dependent surfaces remain. No blanket darkening. |

The editor/NPC integration and measured optimization boundaries recorded below
remain unchanged; this pass does not add those features.

## Crystal and Dune Follow-Up

2026-10-16 continuation. The starting white/pale/uniform-texture queue contains
156 variants / 115 distinct models (not all are broken materials). Evidence is
preserved under `_build/world-region/crystal-dune-pass/before/` and
`BeforeAudit.json`. This pass remains local and does not change the builder,
Blender add-on, export schema or release pipeline.

- Crystals: source `Base` RGB, `Crystal Normal`, `Roughness` and `Metalic`
  provide a deliberately limited base-only proxy for both normal and fade
  masters. The packed `Crystal Mask` is NOT assigned as diffuse, emission or
  opacity. Source color distribution, bright tips/glow, concave/convex masks,
  subsurface, parallax and runtime fading remain pending in-game comparison.
- Kuldra heart base: recover named hard-wired `T_Heart_Base_BCC/NRM` inputs.
  Slime emission/subsurface still require comparison. The separate tunnel
  shader has floor/wall branches and remains open; applying its ground map to
  every wall would not be a verified reconstruction.
- Opaque stained glass: recover its named `BC/N` maps, retaining opaque and
  two-sided source properties. Stains, packed roughness and backlighting remain
  unverified. Do not turn this material into transparent glass by assumption.
- Textureless standard materials: use source constant color and PBR scalars.
  Pale source constants, including silver, are not missing texture errors.
- Dunes: the atlas was already bound. Diagnostic shader renders now measure
  atlas coverage versus our preview's `SandColourA`-derived fallback for each
  isolated view. This is not proof of Unreal's exact fallback shader math.
  No geometry, mask routing or arbitrary recoloring is introduced. A visible
  oversized skirt can be a missing-deformation issue, not a texture download.
- Every white/pale/uniform candidate receives source-backed triage in generated
  `WhiteMaterialReview.json` and the gallery's **White-material investigation**
  details. **White / pale surfaces only** separates these from invisible VFX.
  These classifications never mark a model approved against the game.

### Validated Results

Both world and sample builds completed. The whole-world rebuild took 338.1 s;
the full material scan took 322.9 s and rendered all **8,407 variants / 2,298
models with zero errors**. The white/pale/uniform-texture queue decreased from
156 variants / 115 models to **104 variants / 89 models**. Fifty-two variants
(26 models, 223 placements) cleared white/pale flags, with no newly flagged
variants. All 48 crystal variants cleared those pixel flags, but remain
base-only approximations pending in-game comparison.

Near-white flags fell from 49 to 29, pale flags from 143 to 91; the 13
uniform-texture and 3,443 invisible-effect flags are unchanged. Overall
pixel-flagged variants are now 3,547. None of these counts constitute manual
approval. Every remaining white candidate has source-backed triage; categories
overlap when a model has several materials:

| Review category | Variants |
| --- | ---: |
| Recovered texture already bound; compare surface/lighting | 68 |
| Shader reconstruction/reference required | 21 |
| Effects or transmission | 18 |
| Helper geometry | 7 |
| Source explicitly disables its texture branch | 3 |
| Dune projection/deformation | 2 |
| Source material slot is unassigned | 1 |
| Source uses constant color, not a diffuse texture | 1 |

Dune diagnostics sample one real placement per effective material variant,
from three views. `5cee218c81a37caf6b1f` (`SM_UMS_DuneShape_02`) has only
6.3-18.7% atlas coverage, with 81.3-93.7% preview fallback. The sampled
`6aaa5a2682c95ab39ff4` (`SM_UMS_DuneShape_03`) has no atlas coverage. Other
dune variants have substantial or complete coverage. This narrows the problem
to placement/atlas coverage and potentially deformation, not a blanket missing
diffuse map. It does not prove which Unreal deformation or blending operation
is missing. No dune geometry or fallback color was changed in this pass.

The eight targeted section checks pass, including Outlying Scenery, dense
Ashenfall sections, Dowdun Reach and Umbral Sands: zero runtime errors,
material-binding mismatches or canvas warnings. This is a regression subset,
not a new 314-section/9-area sweep; the prior complete sweep is recorded below.
The subset loaded 1,219 distinct models. Its raw `models.missing` list means
outside the selected subset, not failed loading; `SectionSummary.json`
distinguishes that explicitly. The separate isolated scan covers all models.

Validation also passes 86 Python tests, 17 JavaScript syntax checks and the
surface/PBR, pixel-metric and white-triage tests. Desktop/mobile sample and
gallery checks pass. The gallery renders all 104 white candidates through
48 -> 96 -> 104 pagination, with no horizontal overflow or page errors.
Repeated dune diagnostics leave ordinary render captures byte-identical.

Evidence: `_build/world-region/crystal-dune-pass/Validation.json`,
`AuditComparison.json`, `SectionSummary.json`, and before/after screenshots.
Current scan and per-candidate review evidence are in
`_build/world-region/visual-material-audit/VisualAudit.json` and
`WhiteMaterialReview.json`. Scene SHA-256:
`7da41ac8746d477051b9afe450f7427d2ec40a9f278ad3ca4e130419ba892d2a`.

### Next In-Game Checks

Use gallery search and **Open in World** to reproduce each sampled placement.
The gallery's saved review status is the user's approval, not an automated one.

| Search | Still needs comparison |
| --- | --- |
| `SM_UMS_DuneShape_02`, `SM_UMS_DuneShape_03` | Skirt extent, vertical deformation, terrain contact and color transitions at the bookmarked placement. Compare with well-covered dune variants before changing the shared adapter. |
| `Crystal Normal` | All 48 crystal variants: source green base versus final color distribution, bright tips, glow, subsurface, masks and fade. Clearing white pixels is not shader parity. |
| `SM_Kuldra_Heart_Base` | Recovered green/purple surface, normal strength, subsurface and emission. |
| `SM_CircularStainedGlass` | Recovered opaque stained-glass color, normals, roughness and backlighting; do not assume transparency. |
| `SM_TunnelConnection_02`, `SM_Kuldra_Walls` | Still unresolved floor/wall shader routing, wall atlas UVs, masks and animated veins. |
| White / pale surfaces filter | All remaining 104 candidates: verify pale source materials, inactive texture branches, helpers, effects and unassigned slots individually. No blanket recoloring. |

### Future Editor Integration

Direction recorded from the user's request, not implemented in this pass:

1. Keep three independently managed layers: streamed read-only world context,
   persistent authored placements, and optional location/NPC overlays. Section
   unload must never destroy user edits, undo history or autosave. Build export
   must serialize authored placements only, with existing anchor semantics.
2. Reuse the production builder's placement model, asset catalog, selection,
   snapping, gizmos, collections and `rsdwtools.buildings.v1` serializer through
   an integration boundary. Do not embed two applications with separate cameras
   or start a second set of transform/rotation rules. Both current viewers map
   UE centimeters to Three.js `(X,Z,Y)` meters; component transforms and actor
   export pitch/roll rules still need explicit regression tests at integration.
3. Pin Archive `website/data.config.json`, Model and this world to the same game
   version. Archive's `website/tools/LocationMap/LocationMapData.json` is the
   categorized input; `LocationData/LocationData.json` is a flat coordinate
   lookup, not an authoritative full actor transform/model definition. Resolve
   class, meshes, root offsets and rotation from Archive/BP data before placing
   3D NPCs. Deduplicate against world instances by source identity, not proximity.
4. Treat `DynamicAISpawnData/DynamicAISpawnData.json` separately: encounter
   volumes/candidate cells and conditions are possible spawn areas, not fixed
   simultaneous NPCs. Start with optional markers/areas; load a representative
   model only on demand. Source fixed spawn points are also not a live game save.
5. Preserve section/area selection and instanced static rendering. Current
   streaming uses a 520 m detail window and a 12-section metadata cache;
   explicitly selected sections can still be very dense. Before feature growth,
   benchmark cold/warm load, p95 frame time, input latency, draw calls, triangles,
   decoded texture/GPU memory and repeated unload/reload behavior in those areas.
6. Prioritize measured bottlenecks: incremental chunk replacement/shared-resource
   ownership, GPU/texture budgets and bounded cache eviction, distance LODs,
   compressed GPU textures where quality allows, spatial picking, then NPC
   animation update budgets. Compressed download bytes do not equal GPU memory.
   Keep selection/preview/picking responsive and authored edits persistent during
   streaming; compare export before/after. Do not reduce visual quality blindly.

Useful source contracts: Archive's `website/tools/LocationData/LocationData.md`
and `website/tools/DynamicAISpawnData/README.md`. They were inspected read-only;
no location data was regenerated or added to the world during this pass.

## White Surface Follow-Up

2026-10-16, continuing the full-model material audit. Local prototype only:

- `M_Withered` now uses its named `RockFractures` BCC surface input rather
  than an untextured white surface. The static approximation applies source
  `Tint`, roughness and metallic values. This affects nine variants / 88,171
  placements, including live Witherspine bubbles and spines. Fracture routing,
  presence/height masks, inner flow, outline emission, world-space normal
  behavior, refraction and animation are **not** reconstructed.
- Standard environment, ageing and emissive materials with non-default
  `Color Multiplier` values use a source-linear RGB tint-only proxy,
  applied once to the raw recovered texture. This includes tent fur,
  plaster, paving and candles. Alpha is not converted into opacity; emission
  remains independent. Specialized masters are excluded. Exact shader math,
  operation order, AO, wetness and lighting still need comparison. Direct
  `Brightness` multiplication made rune essence too pale in before/after
  comparison and was removed. Its source value remains annotated but unapplied.
- Kuldra vines recover their two named hard-wired BCC/NRM textures. Kuldra
  interiors recover `BCR` / `NM`, and masked ground rocks recover `BCA` / `NR`.
  Packed roughness, parallax, custom UVs, gradients and animated vein emission
  remain unverified. Hard-wired plugin texture references are canonicalized
  before native extraction, rather than assuming an export index.
- Audit cards now include searchable **In-game verification notes**, generated
  from the material descriptors on every build. Corrections and approximations
  remain separate from manual approval; every regenerated variant is pending.
- Scorned Wilderness crystals remain explicitly unresolved: they use Base,
  Base Var, Concave, Convex and Gradient colors plus packed masks, not a simple
  missing diffuse texture. No guessed tint or arbitrary replacement was added.

Final validation: both whole-world and small-region rebuilds succeed; 82 Python
tests, 15 JavaScript syntax checks and the surface/PBR and pixel-metric
regressions pass. The whole-world build took 330.3 s. The full render audit
checked 8,407 variants / 2,298 distinct models with zero final errors. Across
the source bindings and tint proxies, this pass affects 435 distinct models /
117,328 placements; these counts are coverage, not visual approval.

Compared with the preserved baseline, 120 variants (90,806 placements) cleared
white/pale flags, while one candelabra variant became newly pale-flagged:
`pale_low_chroma_surface` fell from 262 to 143 and `near_white_surface` from
55 to 49. Overall pixel-flagged variants fell from 3,718 to 3,599. Most remaining
pixel flags concern invisible/unsupported effects rather than opaque white
models. All 8,407 variants remain pending in-game comparison, including corrected
ones. Source-flagged variants are now 6,904; adding explicit approximation notes
can increase this count without introducing a missing texture.

The final browser sweep passes all 314 sections and all nine world/area
selections, covers all 2,298 models, and reports no missing models, runtime
errors or material-binding mismatches. The same 23 uniform-view warnings remain
annotated. Desktop/mobile sample and gallery checks pass, including pagination,
searchable review notes and the Kuldra-vine world bookmark. The gallery's only
non-blocking resource warning is the local server's absent `/favicon.ico`.

Evidence: `_build/world-region/color-material-pass/Validation.json` consolidates
the build, tests, audit comparison, section sweep and manual queue. The scene
SHA-256 is `ec6480e3c63f0a12c90583f0f00de1e3a5a2cf8886e066a032da3f607a891ceb`.
`BeforeAudit.json` and `before/` preserve the prior scan and representative
images. The final material scan plus two successful thumbnail-write retries
took 377.3 s; a local image-reader file lock caused those retries, not a model
load failure. The rejected brightness experiment and its interrupted audits
are preserved as superseded evidence, not accepted validation. Current results
are in `../visual-material-audit/VisualAudit.json` relative to that evidence
folder, and `sections-final/BrowserAudit.json` within it.

### Follow-Up Manual Checks

Use the material gallery's model search and **Open in World** bookmarks:

| Search | Verify against the game |
| --- | --- |
| `WitherSpine_Bubbles`, `WitherSpines` | Actual live color, fractures, brightness and outline/glow. The static colored surface is not an animated-shader reconstruction. |
| `Garou_Tent` | Dark base fur versus shell fur/hides; the white source texture plus brown multiplier is intentional source data, not evidence of a missing replacement image. |
| `Human_Ruins`, `Pavement`, `Candle` | Source tint under comparable lighting; brightness, ageing, AO and texture-channel interpretation remain open. |
| `Rune_Essence_Geyser`, `Sand_Pile` | Source Brightness can be 6 or 5.5. Direct multiplication was rejected by regression comparison; the shader operation remains unapplied pending game/reference evidence. |
| `Temple_Candelabra_01` | The one newly pale-flagged variant (`e038a99056bb01151d9e`) has an explicit Color Multiplier of `[2, 2, 2]`, not a missing texture. Its top view crosses the pale threshold after the source multiplier is applied. Confirm the intended lightness in-game; no arbitrary clamp or approval was applied. |
| Bones and Vault Guardian surfaces | Source textures are present but some surfaces remain pale. Compare their intended bone/metal coloration before treating a pixel flag as a defect or recoloring them. |
| `Kuldra`, `TunnelVines`, `GroundRockAlpha` | Recovered texture alignment, cutout edges, tint gradients, vein glow and surface contact. |
| `SW_Crystal` | Still unresolved procedural color/masks/glow/fade. White is not approved or automatically classified as intentional. |
| `UMS_DuneShape`, shoreline and foam | Earlier annotations remain open, including the white dune in the small-region overview; this pass does not fix dune deformation or establish terrain/water parity. |

## Section Loading and Visual Audit Implementation

2026-10-16 implementation, following the research below:

- Whole-world and area overviews now include clickable section navigation
  markers. Non-terrain groups open on a populated, non-helper section instead
  of silently opening with zero models. Area Overview returns to the broader
  bounds; loaded placements, blockouts and deferred sections are distinguished.
  Distant scenery is still streamed, not all kept resident simultaneously.
- Generated sections include visible-content bounds, layer counts and explicit
  classification provenance. `Outlying Scenery` remains the no-landscape
  fallback name; it is not presented as a verified gameplay biome. Seventeen
  helper-only sections are omitted from overview markers but remain selectable.
- Restored the primary base-color mapping for the `M_Rock` family (16,725
  placements), the enabled virtual base/normal branch on four WitherSpine
  materials (710 placements), and campfire ash BCO/NR inputs (113 placements).
  These fixes do not claim reconstruction of moss, RVT, wetness or deferred
  decal shader behavior. The cave-rock before/after uses the same placement and
  preserves its silhouette.
- The new audit also caught legacy dungeon `Albedo00` and character
  `BaseColor Map` aliases falling back to default blend/subsurface masks.
  Corrected both source families, including character `UseVT` branch selection
  and `HasOpacity` alpha testing, with independent mapping checks. Remaining
  tint, layer, UV and character effects are explicitly unverified.
- Every build generates `VisualAuditIndex.json`. Validation checks its scene
  fingerprint and exact active-variant coverage, and rejects required material
  conversion gaps. Independent source-intent checks prevent the confirmed rock,
  virtual-texture and decal alias errors from being accepted as correct roles.
- `AuditWorldMaterials.mjs` renders all 8,407 active mesh/material variants from
  three views using actual shader alpha as the object mask. It records source
  warnings, runtime bindings, flat textures and white/pale/invisible candidates.
  The searchable local gallery includes bookmarks and fingerprint-scoped,
  browser-local review choices. Every generated row starts with manual review
  pending; white pixels alone never trigger automatic recoloring.
- The browser sweep now covers whole-world and all area-group selections as
  well as individual sections. Review links load the target section directly
  before applying the bookmark, with explicit helper visibility where needed.

Previous verification checkpoint: 72 Python tests, JavaScript syntax checks, the
pixel-metric regressions and 36 fingerprint-matched GPU depth/alpha/foam cases
pass. The final full-world rebuild completed in 341.1 s with all stages
successful: 314 sections, 871,578 unique browser placements and zero required
material-conversion gaps. The final isolated render scan covered every one of
the 8,407 variants / 2,298 distinct models with zero runtime errors. The final
section sweep passes all nine world/area selections and all 314 sections, with
all 2,298 models covered and no missing models or material-binding failures.
Its 23 uniform-view warnings remain annotated below, not treated as visual
approval. Desktop/mobile navigation, marker clicks, helper links and gallery
search/pagination/review persistence also pass. The small-region rebuild passes.

The final material scan took 360.8 s using four isolated browser workers.
Its 3,718 pixel-flagged variants are candidates, not 3,718 confirmed broken
models; unsupported effects, intentional pale surfaces and source defaults can
all trigger the checks. There are 6,895 variants with source review notes, with
overlap between these sets. All 8,407 remain pending in-game comparison.
The default-color source check now identifies one material shared by three
Garou tent variants. No texture-resolution reduction or guessed recoloring was
used. Existing instancing and bounded section streaming remain in place;
these concurrent audit runs are not a clean interactive-FPS benchmark.

### Manual Verification Queue

All of the following remain open, including the user's provisionally positive
shoreline feedback. Automated completion is not visual approval:

| Area | What remains to verify |
| --- | --- |
| Rock, limestone and moss | Primary maps restored; exact detail/moss blending, curvature and wetness remain approximate. Compare both dry and mossy variants. |
| Dead WitherSpines | Correct enabled texture branch; compare color, normals and landscape contact in-game. |
| Campfire ash | Static surface color/alpha/normal restored; deferred projection, coplanar contact and emission still need comparison. |
| Legacy dungeon and character surfaces | Verify primary maps on dungeon walls/columns, the Parcel Pete hat and burnt Moon Garou. Layer tint/UV behavior and dye/character effects are not reconstructed. Garou tent base-fur tint is addressed in the follow-up above, not manually approved. |
| Paving, sand and candles | Pale pixels are candidates, not confirmed defects. The follow-up applies a scoped source color proxy; exact brightness, intentional pale materials and in-game lighting still need comparison. |
| Proxy/grid materials, tunnel vines and crystals | Vine surface maps are addressed in the follow-up, with shader effects pending. Proxy/grid and procedural crystal materials remain unresolved. Do not classify them as intentional white or hide them automatically. |
| Visually blank sections | `x4_y10`, `x4_y11`, `x5_y11`, `x6_y10` and `x6_y11` contain the same `MI_FuzanFog` volume, whose hardwired shader is unmapped and isolated render is invisible. These are not failed model downloads. `x-9_y0` shows a small Sand Vault terrain patch at the cell boundary; `x-9_y4` retains only two triangles after the source visibility mask. Compare those source holes/framing in-game. Other uniform screenshots primarily show helper-only sections with Blockouts disabled. |
| Terrain, shoreline and foam | Compare `x1_y3` shallow banks and `x1_y1` waterfall foam against matching game views. |
| Oasis and dunes | `x4_y3`: source dune deformation remains unreconstructed; do not mark it fixed on the strength of a material audit. The large white surface at the left of the small-region overview was traced by raycast to `SM_UMS_DuneShape_02.2` / `MI_UMS_Dunes`, not an untextured rock. Its missing texture roles and deformation are already flagged in the gallery. |

Review gallery: `_build/world-region/visual-material-audit/index.html`.
Final result summary: `_build/world-region/ImplementationValidation.json`.
Final section sweep: `_build/world-region/browser-audit-alias-final/BrowserAudit.json`.
Final scene fingerprint:
`92b6d19fa319fceafe7975bee6ab699e0c784f681e2f6024bd2d0a45debe0a9d`.
Preserved baseline and targeted before/after images:
`_build/world-region/visual-material-audit-test/`.
The intermediate browser sweep in `browser-audit-materials/` was deliberately
stopped after nine group checks and 163 sections to rebuild the additional
confirmed fixes; its report is explicitly marked incomplete, not a full pass.

## Manual Review Status and Next Pass

2026-10-16: the user reports that the latest shoreline/foam pass looks good as
far as they can tell, but explicitly requests another manual verification pass.
Record this as **provisional feedback, not in-game visual-parity approval**.
These checks remain open:

- [ ] Terrain transitions and shoreline depth/color, including `x1_y3`.
- [ ] Waterfall foam masks, opacity and placement in `x1_y1`.
- [ ] Oasis shoreline and dune silhouette in `x4_y3`; dune deformation is still
  unreconstructed, not a completed fix awaiting sign-off.
- [ ] Other sections after the loading and per-model material audits below.

Use matching in-game screenshots plus Save View bookmarks for these checks.
Keep source/build fingerprints with results, and reopen affected approvals when
a material family, terrain bake or geometry conversion changes.

### Research Findings

Read-only reproduction against the current 1.0.0.5 build:

- Selecting **Outlying Scenery / All sections** frames 219 sections at about
  29,063 m from the orbit target. `world-browser.js` disables detailed models at
  distances of 1,500 m or greater unless a single section is selected. The result
  is zero model placements, six overlapping overview terrain meshes and no
  network/runtime errors. This is a streaming/framing policy gap, not evidence
  that the models failed extraction.
- Selecting `x-4_y2` directly loads 6,762 placements (including spanning objects)
  and displays the interior. The existing 314-section sweep selects individual
  sections only, so it does not exercise the failing whole-area selection path.
- `Outlying Scenery` is a terrain-derived fallback label, not a verified biome:
  `world_sections.py` assigns it whenever a cell contains no landscape tiles.
  Its section files include 18,884 unique placements, including vault geometry;
  17 sections contain only helpers that are intentionally hidden by default.
  Section totals overlap and must not be summed as unique world placements.
- A visibly white `SM_Cave_Floor_03` uses `MI_CaveRocks_v2`. Its loaded color map
  is `T_Default_Gray_D`, selected from `Detail Albedo`, despite `Use Detail Layer`
  being false and `Rock BaseColor` referencing `T_Cave_Rock_v2_BCC`. The role
  resolver recognizes other rock color aliases but misses `Rock BaseColor`.
  The material currently reports `no_detected_gap`: matching a generated role
  is not independent confirmation that the role was correctly inferred.
- The same role-selection scan flags 14 rock-family material candidates.
  Enabled moss/detail variants require branch/blend analysis, not a blanket
  replacement with a single base map. The two cave-rock materials alone report
  7,175 and 782 affected placements respectively.
- Current coverage is 2,298 distinct meshes, 8,407 active asset variants and
  4,587 effective materials. Of those materials, 3,837 need review; many are
  unreconstructed effects, not confirmed missing textures. The browser sweep's
  near-white warning triggers above 80% of the entire canvas, which misses small
  white objects and cannot judge occluded models.

Evidence: `_build/world-region/loading-research/Research.json`, including source
hashes, scene fingerprint, runtime metrics and the rock-role candidates;
`outlying-group.png` and `outlying-individual.png` capture the reproduction.
No renderer, material generator or pipeline behavior changed in this research
pass. The previous structural success remains valid within its limited scope.

### Recommended Implementation Order

1. **Loading coverage:** test whole-world, every area group and every section;
   distinguish expected, loaded, deferred, intentionally hidden and failed
   placements. Improve non-terrain framing and provide a budgeted mesh overview
   or section navigation so distant content does not silently disappear. Audit
   fallback classification using source-level provenance before renaming areas.
2. **Material correctness:** audit each mesh plus effective material assignment,
   not just each mesh name. Add material-family role/branch checks independent
   of inferred output roles, starting with the confirmed cave-rock case. Render
   isolated multi-view previews with consistent lighting and object masks;
   flag default textures, unexpectedly uniform/near-white surfaces, missing
   maps and excessive emission. Treat white pixels as review evidence, not an
   automatic recoloring instruction. Retain an intentional-white allowlist with
   source evidence or manual approval.
3. **Review workflow:** generate contact sheets and a ranked queue by affected
   placement count, sections and confidence. Link each issue to source material,
   affected variants and an in-world bookmark. Fix supported material families,
   rerun all affected variants, and retain `manual_review_pending` separately
   from automated load/mapping success. Unrecovered shaders remain explicit.
4. **Measured optimization:** establish network, decode/upload, draw-call and
   GPU-memory baselines first. Improve shared-resource reuse, bounded loading,
   cancellation and eviction, then distance-appropriate mesh/texture detail.
   Keep full detail available near the camera and compare against the corrected
   visual baseline. Do not use blanket texture downscaling to hide shader bugs
   or solve the current terrain-only streaming gap.

## Shoreline and Foam Checkpoint

Follow-up on 2026-10-16 (supersedes the water limitations below where noted):

- Added an on-demand opaque-scene depth pass, including source alpha cutouts and
  instance transforms. Standard/logarithmic depth and perspective/orthographic
  cameras are supported. Render statistics include the extra pass; idle views
  do not continuously redraw.
- Added shallow/deep color and opacity blending for the legacy river material
  using its source centimeter distances. Eighteen modern water variants with
  enabled PDO now use a linear shoreline-fade surrogate. This is not Unreal's
  recovered PDO equation or physical SingleLayerWater transmission. Fifty-eight
  other water variants retain their prior surface behavior.
- Recovered static foam masks for 21 material variants across 310 placements,
  including source opacity, texture channels, tiling, enabled constant color and
  depth fade. This fixes untextured effect planes, not the entire particle graph.
  Shape/radial masks, UV distortion, runtime interaction, day/night and animation
  still need comparison; no universal white shoreline band was invented.
- Made dune deformation a specific audit issue with source function references
  and grounding/flattening parameters. The five dune meshes affect 315 placements.
  All 28 referenced material functions exist in the archive, but none retains
  MaterialExpression exports. Geometry is unchanged: an arbitrary flattening
  rule would risk damaging all 315 placements.
- Focused validation: 63 Python tests and 36 GPU pixel cases pass. GPU cases cover
  source-style river/foam blending, both depth encodings, alpha-cutout holes,
  translated instances, background pixels, resize and disabled-effect skipping.
  The 4,011-placement sample rebuild passes; desktop/mobile interaction checks
  have no material-adapter errors, no page overflow and no idle redraws.
- Final whole-world rebuild passes every stage in 789.8 s, including a fresh
  terrain bake. Section coverage remains 871,578 placements across 314 sections.
  The 17,133 runtime dependencies total about 3.09 GiB. The material audit has
  zero required conversion gaps; 3,837 material instances remain in review.
- The final fingerprint-matched browser sweep passes 314/314 sections and covers
  all 2,298 distinct models, with zero browser/network errors or supported
  adapter mismatches. The same 23 known uniform-frame warnings remain, with no
  new warnings. Returning to the world overview releases detail resources;
  its 574 terrain geometries and 578 textures include two persistent depth-pass
  textures. All eight world-bounds corners fit the mobile camera frustum.

Current evidence: `_build/world-region/shoreline-validation/`, including
`BuildValidation.json`, `WaterDepthValidation.json`, `DuneSourceReview.json`,
`SampleValidation.json`, `WorldInteractionValidation.json` and
`CloseupValidation.json` (source placement IDs and camera bookmarks).
The full sweep is `_build/world-region/browser-audit-shoreline/BrowserAudit.json`.
Build logs: `shoreline-build.log` and `shoreline-sample.log`.

Manual comparison boundary: review the Umbral Sands oasis in `x4_y3` first,
particularly the dune silhouette over the water. Then compare a shallow river
bank in `x1_y3` and waterfall foam in `x1_y1`. Matching in-game screenshots and
the viewer's Save View bookmark will distinguish source shader omissions from
intentional art direction. Structural/audit success does not certify these
areas as visually complete. Runtime RVT-height inputs or an original shader
graph would be needed for exact dune deformation; a static proxy would need
reference-guided validation.

## Water and Terrain Feature Checkpoint

Additional refinement on 2026-10-16:

- Blended valid, explicit feature-array ranges with their painted coverage on
  173 of 574 terrain tiles (212 feature blends). This is a static approximation,
  not recovered Unreal height/noise shader logic. Nine tiles retain unresolved
  feature ranges instead of selecting unrelated texture slices.
- Preserved fine visibility-hole triangles in overview terrain on 261 tiles;
  cave openings no longer get filled by a coarse quad. This costs more overview
  triangles, about 5.74 million in the whole-world frame, than the earlier coarse
  mesh. Hole-free tiles still use the coarse grid.
- Added a source-controlled static adapter for 77 water material instances:
  normal maps and dual-normal strengths, roughness, UV/world scales, color and
  enabled flat-color emission. SingleLayerWater opacity is not treated as alpha.
  Water color/transmission and combined normals remain explicit approximations.
- Restored 16 real water-plane asset variants that had been incorrectly hidden
  because their mesh lived in a blockout folder. Water classification now uses
  its master material, so unrelated foam/waterfall maps are not stripped.
- A close-up found dark swamp slabs were scene-capture-only lighting cubes.
  Inventory now honors `bVisibleInSceneCaptureOnly`, including template
  inheritance and per-instance overrides, excluding 51 source components.
  Their scene-capture/indirect-lighting contribution is not reconstructed.
- All 59 focused Python tests pass, including feature blending, overview holes,
  water branch semantics and capture-only visibility regression cases.
- Whole-world and sample rebuilds pass every stage. The final resumed world
  rebuild took 360.6 s, reusing verified terrain and native resources; the sample
  took 17.1 s. These are cached build timings, not cold-build estimates. The
  final world has 871,578 browser placements, 314 sections and 2,298 distinct
  models, with 17,131 runtime dependencies totaling about 3.09 GiB.
- Final desktop/mobile framing, sample orbit and road toggles, water close-ups,
  detail-resource release and zero-frame idle rendering pass. The swamp
  before/after capture confirms the dark lighting slabs are gone. Bookmarks and
  source placement identities are retained for later in-game comparison.
- The final fingerprint-matched browser sweep passed 314/314 sections and loaded
  2,298/2,298 distinct models in 450.4 s. No browser/network errors or supported
  material-adapter mismatches were found. The same 23 previously investigated
  uniform-frame warnings remain; no new warnings were introduced. This is not
  approval of in-game visual parity.

Current build and interaction evidence under `_build/world-region/`:

- `WaterFeatureFinalBuildValidation.json` and `WaterFeatureInteractionValidation.json`.
- `browser-audit-water-final/BrowserAudit.json` and per-section screenshots.
- `WaterShaderValidation.json` (world/mesh UV, instancing and tangent variants).
- `water-feature-visibility-build.log` and `water-feature-visibility-sample.log`.
- `water-final-*.png`, plus desktop/mobile overview and sample captures.

The final material audit has zero required conversion gaps. Of 4,587 active
material instances, 3,837 still require shader/tint review. The higher review
count than the preceding checkpoint reflects newly recognized water
approximations, not new missing textures. No production pipeline, shared
WebAssets, Archive data, Blender add-on or build-export schema changed.

Remaining terrain review: 15 tiles have clamped biome ranges, 93 assumed ranges,
and 222 still contain active unmodeled paint channels; these counts overlap.
Close-up water checks show static dune geometry overlapping parts of the oasis.
Dune grounding/displacement, RVT, depth-aware shorelines, foam, refraction and
animated water remain unimplemented or approximate. Matching in-game captures
are still needed for visual acceptance.

## Terrain and Material Refinement Checkpoint

Follow-up pass on 2026-10-16, after the initial whole-world checkpoint below:

- Corrected absent terrain paint channels, vertex-aligned mask interpolation,
  linear-light color/tint blending and footprint-filtered texture sampling.
  An unpainted base layer no longer dilutes another painted sub-biome.
- Preserved explicit source `SRGB=false` color textures. Terrain uses their
  linear values directly; browser mesh color/emissive derivatives are encoded
  to sRGB. The audit records this correction on 31 active mesh materials.
- Reconstructed shared lighting normals for 114,513 coincident terrain samples
  within their landscape GUID, and reused them for coarse overview terrain.
  Source height decoding and the existing height-boundary approximation are
  unchanged. Normal-map derivatives now use lossless WebP encoding.
- Rebuilt all 574 terrain components and both the whole world and original
  sample. The final verified resumed whole-world run completed in 322.7 s,
  reused verified terrain bakes, and passed every pipeline stage. This is not
  a cold-build timing. Its 17,136 runtime dependencies total about 3.08 GiB.
- All 50 focused Python tests pass. The new browser sweep passed 314/314
  sections and loaded 2,298/2,298 distinct models in 454.5 s, with no browser,
  network or supported material-adapter errors. The report retains scene/viewer
  fingerprints; this is a loading and binding audit, not in-game parity approval.
- Investigated all 23 uniform-canvas warnings. The previous 22 cases remain;
  the additional `x-9_y0` warning is a small visible Sand Vault terrain patch
  whose sampled colors changed from three quantized colors to two. Its second
  terrain tile is fully visibility-masked, and its four cube placements are
  hidden helpers. Before/after captures show the same visible terrain footprint.
- Desktop/mobile framing, nonblank rendering, sample orbit, road toggles,
  supported material bindings and idle rendering pass the interaction checks.
  The server remains local-only; no production or shared WebAssets changed.

Current validation artifacts under `_build/world-region/`:

- `browser-audit-terrain/BrowserAudit.json` and section screenshots.
- `TerrainMaterialInteractionValidation.json` and sample/world captures.
- `terrain-material-build-verified.log` and `terrain-material-sample.log`.
- `1.0.0.5/whole-world/source-data/TerrainReport.json` and `MaterialAudit.json`.

Remaining visual work is explicit: 15 terrain tiles have clamped biome-array
ranges, 93 use assumed ranges, and 276 have active paint channels whose shader
equations are not reconstructed. These counts overlap. Four-meter world-texture
tiling, RVT, slope/height/noise blending, water and procedural effects remain
approximations. The material audit has zero required conversion gaps, but 3,781
of 4,591 active material instances still require shader/tint review. Matching
in-game captures are still needed before claiming visual parity.

## Whole-World Checkpoint

The user authorized expansion beyond the original sample on 2026-10-16. The
opt-in build now inventories all packaged, non-HLOD `L_World` cells in 1.0.0.5.

- 314 spatial sections, 574 terrain components, 871,629 browser placements and
  2,298 distinct active models. Another 4,118 road-spline placements are baked
  into the terrain rather than rendered twice.
- Whole-world/biome views stream a local detail window. Individual-section mode
  loads the complete chosen section. The original sample remains the default.
- Exact source-identity coverage, dependency, hierarchy, transform and road
  projection checks pass. Generated per-section, per-model and material audits
  retain outstanding shader questions rather than approving them automatically.
- Whole-world fixes include plugin/case-sensitive source recovery, cave terrain
  layer mapping, source-controlled emission/blend modes, case-insensitive
  inherited material parameters, projected dune color, blockout visibility,
  full-height section framing and bounded detail-resource lifetime. Background
  mountains now use their source base tint instead of the cached white fallback.
- `AuditWorldPreview.mjs` provides a repeatable full-section browser sweep with
  screenshots, canvas checks, material-adapter checks and incremental results.
  The final 2026-10-16 sweep passed **314/314 sections** and loaded **2,298/2,298
  distinct models**, with zero browser/network errors, missing models, toolbar
  overflow or supported-adapter mismatches. It completed in 426.5 s. Its scene,
  viewer and audit-tool hashes are retained in `BrowserAudit.json`.
  Interrupted earlier sweeps do not count as completion.
- All 22 uniform-canvas warnings were investigated: 16 helper-only sections,
  five cells overlapping the source additive `M_SurroundingFog` volume (its
  procedural fog is not reproduced), and one nearly visibility-masked Sand
  Vault terrain component with only two surviving triangles. These are retained
  for review, not counted as proof of missing geometry or textures.
- The densest section loaded 90,541 placements in 8.6 s during this local sweep.
  The slowest section took 19.5 s; maximum sampled JavaScript heap was 449 MiB
  (not total browser/GPU memory). These are local observations, not device-wide
  performance guarantees.
- The static terrain boundary reconstruction adjusts 556 coincident boundary
  positions within their landscape GUID. This is an explicit approximation of
  Unreal's runtime patching, not verified height parity. Its original differences
  remain recorded in `source-data/TerrainReport.json`.
- Full source material audit: 4,591 active material instances. No unresolved
  required conversion gaps remain; 3,782 instances still need shader/tint review.
  Instance counts are not counts of distinct shader implementations.
- The rebuilt output validates 17,136 runtime dependencies (about 3.02 GiB of
  model/terrain payload, loaded on demand). The resumed full build took 339.5 s
  on this machine; this is not a cold-build or browser-load measurement.
- Local serving uses persistent HTTP/1.1 connections. The exhaustive sweep
  exposed connection exhaustion with the previous HTTP/1.0 server; the launcher
  now avoids creating a separate connection for every asset request.
- Desktop/mobile controls, section isolation, orbit, bounds, road toggles,
  return-to-overview resource disposal and idle rendering pass regression checks.
  The original 4,011-placement sample still loads with no browser errors or
  supported-adapter mismatches. All 34 focused Python tests pass.
- No production pipeline, website deployment, Blender add-on, upstream Archive
  content, shared Model WebAssets, or build JSON format was modified.

Local review URL:
<http://127.0.0.1:8765/RSDWBaseBuilder/tools/World/preview/index.html?world=1>

Outputs: `_build/world-region/1.0.0.5/whole-world/`. Browser sweep results and
captures: `_build/world-region/browser-audit/`. **Visual acceptance remains
pending**, especially landscape blending/boundaries, procedural effects, water,
lighting and unsupported shader behavior. Whole-world structural completion is
not a claim that every model looks identical to the game.

## Original Sample Checkpoint

- Built locally: 8 terrain components and 4,011 static placements from 21 source
  packages (1,460 foliage, 408 building, 64 road, 2,079 scenery placements).
- Source resolution and dependency validation passed. Terrain borders match with
  zero height delta; an independent CUE landscape probe matched 16,129 vertices
  within 0.000382 cm. Twenty-one focused Python tests pass.
- Browser checks passed for loading, layer toggles, coordinate round trip, orbit,
  nonblank canvas pixels, and desktop/mobile layout. No observed console errors.
  Settled idle rendering produced zero additional frames.
- Local headless Chrome observations: about 6.0 s first load, 4.4 s warm reload,
  16.7 ms median / 16.8 ms p95 during a short orbit at 1600x1000. Payload is about
  137.9 MiB after the rune material recovery. These are short local measurements,
  not general device guarantees.
- Cached regeneration completed in 23.1 s with no native resources re-exported.
- Source lives only in new opt-in `tools/World/` folders in Model/BaseBuilder.
  Archive is unchanged. Nothing has been committed, published, or added to the
  normal release pipeline.
- The foliage pass fixes unintended constant-white emission on 901 placements,
  retains enabled flower glow, and honors source cutout/vertex-mask semantics.
  The whole-region browser audit found no missing plant base-color maps or
  emission remaining on source-disabled foliage. See
  `_build/world-region/MaterialValidation.json` and the before/after plant captures.
- A separate white dune surface uses an unsupported texture-array shader.
  It remains explicitly reported for the next shader pass, not hidden as a
  completed material conversion.
- The rune essence pass restores missing base color and fixes color-as-emission
  bindings on three models / 12 placements, using the original hard-wired maps.
  `MaterialAudit.json` now checks 114 active materials across 156 models on every
  build, ranks gaps/review items, records affected placements and sample locations,
  and separates locally corrected bindings from unresolved shader behavior.
  This audit is not an automatic in-game visual-parity test.

**Not yet accepted:** terrain/material approximation and unsupported shader
surfaces still require visual review. Matching in-game captures have not been
provided, so actor placement/rendering parity is not asserted. The user has now
authorized a whole-world structural build and audit; visual acceptance remains
separate. See the World prototype guide for the opt-in whole-world commands,
streamed section loading and per-model/per-section audit outputs.

Local captures and browser measurements are in `_build/world-region/`;
`BrowserValidation.json` records the smoke checks. Build/coverage reports are in
the versioned output directory listed below. Restart the local server with the
guide's command after a reboot; the generated region does not need rebuilding.

## Goal

Reconstruct one recognizable surface region of Dragonwilds in a local Three.js
viewer, including terrain, trees, existing buildings or ruins, and roads. Prove
placement accuracy and the terrain conversion path before attempting the whole
world or integrating world scenery into the production BaseBuilder editor.

The result is a static visual reconstruction of packaged content, not a live
save, a playable game, or an exact reproduction of Unreal's rendering.

## Initial Region

Pin the first run to game dataset `1.0.0.5` in both Archive and Model. Do not
silently switch to the newest dataset during implementation.

Use `fellhollow-road-ruins` as the prototype identifier. The initial candidate is:

| Field | Value |
| --- | --- |
| Runtime cell | `AH1KHVYOKGH2CP54XNL3JAWTA` |
| Runtime grid | `MainGrid` |
| Center in UE centimeters | X `239400`, Y `-12600` |
| Nominal XY bounds in UE centimeters | X `226800..252000`, Y `-25200..0` |
| Nominal size | 252 m by 252 m |
| Source | `RSDragonwilds/Content/Maps/World/L_World/_Generated_/AH1KHVYOKGH2CP54XNL3JAWTA.json` |

A read-only survey found 2,979 exports, 949 serialized instance entries, tree
mesh references, and castle/ruin architecture in this cell. Of 108 directly
referenced mesh package paths, 106 resolve to existing Model web assets. The
remaining paths are an Engine plane and a map-local reference needing object
resolution. These are candidate-selection observations, not completeness totals.

There are 76 spline components, but only 39 have an explicit mesh reference.
Those include paving meshes and `SM_PathDecalPlane`; audio-only spline components
must not be mistaken for missing roads.

The candidate cell contains no landscape components itself. Terrain must be
collected from the main world package and any other intersecting source cells.
A single cell file is therefore not the region's complete dependency set.

At the first validation gate, confirm that this is a coherent outdoor sample
containing all four target categories. If not, select another candidate before
expanding the build. Do not claim an official landmark name without confirming it.

## Scope and Boundaries

- Include intersecting terrain tiles, visible static scenery, trees/foliage,
  relevant Blueprint visuals, building assemblies, and mesh-bearing road splines.
- Start with a 25 m dependency halo around the nominal region. Retain complete
  actors/assemblies crossing the boundary; enlarge the dependency set when their
  bounds require it. Keep the primary inspection area at the nominal bounds.
- Resolve always-loaded content and all relevant runtime grids, not just the
  candidate MainGrid cell. Exclude HLOD substitutes from the full-detail baseline.
- Keep terrain holes, cave entrances, and below-ground content explicitly
  classified. Do not flatten holes or accidentally display cave scenery as surface
  scenery. Deeper interior exploration is outside this milestone.
- Exclude AI, quests, audio playback, gameplay simulation, live procedural
  generation, weather, dynamic destruction, and player-built/save-specific state.
- No Blender library rebuild, add-on release, public deployment, full-world
  export, or automatic Git commit/push is part of this milestone.
- Do not change `rsdwtools.buildings.v1`, build export behavior, or editor autosaves.

## Ownership

### RSDWArchive

Consume its versioned JSON and original shared Retoc packages read-only during
the prototype. Use full object references, attachment data, Blueprint templates,
landscape metadata, material overrides, and instance transforms as source inputs.

Do not use the filtered, position-only `LocationData.json` as the scene manifest.

The research identified a texture naming collision in
`tools/CueExtract/RsdwArchiveExtract/Program.cs`: map-embedded textures with the
same leaf name share an output path. For example, the main world package contains
187 distinct `Heightmap_0` exports. Do not trust the existing loose heightmap PNGs
as a complete terrain source.

For this prototype, recover required terrain data directly from Retoc with
identity-safe outputs. A durable Archive naming change is a separate upstream
follow-up with a compatibility plan; do not rename its public texture corpus here.

### RSDWModel

Own new opt-in tools under `tools/World/` for region dependency resolution,
source conversion, and scene-manifest generation. Reuse existing WebAssets for
ordinary models and existing CUE4Parse/Blender conversion helpers where suitable.

Use a small dedicated CUE world-export wrapper for landscapes, object-specific
textures, embedded meshes, and any spline baking that requires original packages.
Try the existing CUE4Parse LandscapeExporter first, but treat compatibility with
this game's cooked terrain as unproven until the terrain gate passes. Do not
modify the shared CUE4Parse checkout without a concrete reproduced incompatibility.

### RSDWBaseBuilder

Keep the region configuration, this plan, and a local inspection viewer. Proposed
source paths are `tools/World/regions/` and `tools/World/preview/`, outside the
production `website/` deployment tree. Reuse the existing Three.js version,
loaders, visual theme, and camera conventions without coupling the prototype
to the editor's placement, selection, or export state.

Keep generated output under this repo's already-ignored `_build/world-region/`.
An explicitly supplied output path is the only cross-repo write destination.

## Implementation Stages

### 1. Freeze Inputs and Resolve the Region

- Record game version, source revisions/hashes, matching usmap, CUE4Parse revision,
  region bounds, and asset roots in the run report.
- Build an object reference resolver using package path plus export/Outer identity.
  Never identify a mesh, texture, or component solely by its leaf name. Export
  indices are version-bound and must not be reused across datasets.
- Normalize `/Game`, `/Engine`, and GameFeature mount paths consistently.
- Index runtime cell bounds and collect dependencies from intersecting cells,
  the main package, Blueprint templates, packed assemblies, and attached objects.
  Reading a large package to resolve dependencies is acceptable; exporting every
  object in it is not.
- Produce a categorized inventory of terrain, trees, buildings, roads, helpers,
  HLODs, unresolved references, and deliberately excluded systems.
- Classify audio splines, collision helpers, RVT-only geometry, and hidden source
  components instead of treating every serialized component as visible scenery.

Gate 1: freeze the region and confirm its source set covers terrain, trees,
architecture, and at least one actual visible road/paving section.

### 2. Prove Terrain Extraction First

- Select the landscape components intersecting the region using their transformed
  extents, section bases, landscape GUIDs, and root transforms.
- Recover each required heightmap and weightmap from the original package using
  its complete object identity. Distinct identically named textures must produce
  distinct outputs, with a manifest mapping source objects to files.
- Preserve packed height channels, source precision, layer weights, and linear
  data semantics. Do not resize, color-correct, use lossy WebP, or apply sRGB
  conversion to terrain data textures before decoding.
- Generate terrain geometry with correct scale, component offsets, tile borders,
  normals, and visibility holes. Keep original height/weight data for validation.
- Render a diagnostic terrain-only view before spending time on scene assembly.

Gate 2: terrain is nonflat, correctly sized and positioned, has no conversion
seams, and has samples traceable to source height values. If the exporter cannot
produce valid terrain, stop and report the incompatibility rather than substituting
a flat floor or a distant HLOD and calling terrain complete.

### 3. Assemble Scenery and Roads

- Resolve inherited component properties before composing actor, attachment,
  component, and per-instance transforms. Account for absolute-transform flags,
  translated instance-space origins, sockets when used, and packed assemblies.
- Use UE space as the source of truth and one tested conversion module for browser
  axes/units. Do not apply BaseBuilder's user-JSON pitch/roll corrections blindly
  to cooked component matrices or quaternions.
- Keep canonical world coordinates in the manifest; render relative to the region
  origin to reduce large-coordinate precision problems.
- Reuse existing Model glTF assets. Convert missing visible meshes by exact
  reference, including non-`SM_` names and embedded exports. Report unresolved
  visible geometry instead of silently dropping it.
- Apply component material overrides. Distinguish assets by geometry plus material
  configuration when batching; sharing a mesh does not imply identical materials.
- Reproduce mesh-bearing spline deformation using positions, tangents, forward
  axis, roll, scale, and offsets. Prefer the existing source conversion logic to
  a separate approximation. Plain undeformed meshes are diagnostic only.
- Render physical paving as geometry. For RVT/decal-only road surfaces, bake the
  relevant static contribution into terrain textures or a compatible projected
  surface treatment. Respect `Never` main-pass flags and avoid double-rendering
  both the source road planes and their baked contribution.
- Produce a recognizable textured terrain blend from source layer weights and
  material inputs. Any shader approximation must be named in the quality report.
  A gray terrain diagnostic does not pass the final visual gate.

Gate 3: terrain, trees, architecture, and roads appear together without duplicate
HLODs, systematic floating/sinking, mirrored placement, or straightened roads.

### 4. Build the Local Inspection Viewer

- Provide an isolated viewport with orbit/pan/zoom, frame-region, and basic layer
  toggles for terrain, trees, buildings, roads, and diagnostic bounds.
- Include a readable source-world coordinate display and reproducible camera
  bookmarks for comparing with in-game views. Use existing theme assets; no new
  marketing page or production navigation entry is needed.
- Instance repeated static scenery by compatible geometry/material groups and
  cull at sensible spatial boundaries. Reuse textures and model caches.
- Show loading phases and errors. Record load timings, draw calls, triangles,
  frame timing, and available memory indicators rather than relying on feel alone.
- Keep source/generated data local by default. Serve from a shared local HTTP
  root that can access both repos; production raw-GitHub loading is not required.

Gate 4: the region can be loaded, navigated, reframed, and visually inspected
without changes to the production builder.

## Proposed Outputs and Interface

The filenames and commands below are implemented as opt-in prototype tools.

Output root:
`E:\Github\RSDWBaseBuilder\_build\world-region\1.0.0.5\fellhollow-road-ruins\`

| Output | Purpose |
| --- | --- |
| `RegionPlan.json` | Frozen bounds, version, source packages, dependencies, and exclusions |
| `WorldRegion.json` | Versioned prototype scene manifest with asset refs and UE transforms |
| `assets/` | Newly converted terrain, splines, missing meshes, and preview textures |
| `source-data/` | Identity-safe lossless terrain data and source-to-output mapping |
| `WorldRegionReport.json` | Coverage, conversion warnings, timings, sizes, and validation results |
| `PipelineRun.json` | Stage status for this prototype only |

The scene manifest should contain stable source identities, asset/material refs,
full transforms or matrices, layer classification, bounds, region origin, and
provenance. Keep local absolute filesystem paths out of browser-facing manifests;
configure HTTP asset roots separately. Do not embed or duplicate Model's entire
WebAssets corpus.

Model entrypoint:

```powershell
# From E:\Github\RSDWModel.
python tools\World\BuildWorldRegion.py --version 1.0.0.5 --region-config ..\RSDWBaseBuilder\tools\World\regions\fellhollow-road-ruins.json --out-root ..\RSDWBaseBuilder\_build\world-region\1.0.0.5\fellhollow-road-ruins --mode plan
```

Support `--mode build`, `--mode validate`, and `--resume` on the same entrypoint.
Plan mode must not run heavyweight conversion. Resume must invalidate cached
outputs when source identity, version, conversion settings, or tool revision changes.
Parallelize independent conversions with a bounded, memory-aware worker pool.

Keep this entrypoint opt-in. Do not add it to normal Archive, Model, BaseBuilder,
or MasterPipeline releases until the prototype is accepted.

## Validation and Acceptance

### Automated Checks

- Reference resolution handles duplicate names, embedded exports, plugin mounts,
  inherited properties, and attachment chains without ambiguity or cycles.
- Transform fixtures cover yaw/pitch/roll, nonuniform/negative scale, translated
  foliage origins, and local region rebasing. Preserve source handedness and winding.
- Terrain fixtures cover packed height precision, UV tile offsets, adjacent borders,
  layer weights, and holes. Never treat geometric data textures as display images.
- Verify every required source has an output or an explicitly reviewed exclusion;
  missing visible terrain, trees, buildings, or road segments fail validation.
- Exclude HLOD/full-detail duplication, invalid bounds/transforms, broken asset URLs,
  missing render textures, and unexpected unclassified conversion failures.
- Repeating a build must give the same scene content apart from timestamps/timings.

### Visual Checks

Compare at least three matching in-game/viewer viewpoints: overhead, ground-level
along a road, and oblique across a building/tree/terrain intersection. Ask the user
for reference captures if none are available. Do not claim in-game parity from
browser screenshots alone.

Inspect terrain silhouette, tree bases, building roots, road curvature and contact,
terrain tile borders, cave openings, missing objects, and accidental helper meshes.
Use source precision for numerical checks; initial transform tolerances are 1 cm
position, 0.01 degree orientation, and 0.0001 scale where source precision permits.

### Performance Checks

Record cold and warm local loads, payload size, longest UI stall, draw calls,
frame timings, and memory growth on the test workstation. The initial target is
at least 30 FPS during ordinary orbiting at a documented desktop resolution,
with progress feedback during loading and no unbounded cache growth on reload.
Measure before adding further optimization or changing visual quality.

### Completion Gate

The prototype passes when all four categories are recognizable, structurally
correct, independently inspectable, and have explained coverage; numerical and
visual checks pass; and remaining material/render differences are explicitly
accepted. Stop for review at that point. Do not automatically expand to the whole
world or publish the prototype.

The handoff should include the local test URL, reproducible commands, region/run
reports, comparison captures, known limitations, and the proposed next step.

## Source References

- Archive world: `E:\Github\RSDWArchive\1.0.0.5\json\RSDragonwilds\Content\Maps\World\L_World.json`
- Archive location compiler: `E:\Github\RSDWArchive\website\tools\LocationData\CompileLocationData.py`
- Archive map bounds compiler: `E:\Github\RSDWArchive\website\tools\MapData\CompileMapData.py`
- Original packages: `E:\Github\Retoc\RSDragonwilds\1.0.0.5`
- Model inventory/index: `E:\Github\RSDWModel\website\model-index.json`
- Model extractor: `E:\Github\RSDWModel\tools\CueExtract\RsdwCueExtract\Program.cs`
- Landscape conversion: `E:\Github\CUE4Parse\CUE4Parse-Conversion\Landscape\LandscapeExporter.cs`
- BaseBuilder component assembly: `tools/AssetLibrary/BuildAssetLibraryTargets.py`
- Existing pipeline boundaries: [PIPELINE_HANDOFF.md](PIPELINE_HANDOFF.md) and [DEVELOPERS.md](DEVELOPERS.md)
