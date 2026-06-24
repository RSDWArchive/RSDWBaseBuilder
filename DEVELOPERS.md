# RSDW BaseBuilder Developer Notes

This repo is the public source repo and the local working repo for the Blender
asset-library pipeline. It replaces the old `RSDWBaseBuilderWorkspace` layout.

## Update Chain

BaseBuilder is the third step in the RSDW update chain:

1. `E:\Github\RSDWArchive` extracts game JSON, textures, and website datasets.
2. `E:\Github\RSDWModel` extracts and prepares importable model data.
3. `E:\Github\RSDWBaseBuilder` consumes those completed outputs and rebuilds
   the Blender asset library.

BaseBuilder does not run the Archive or Model pipelines. Run those first, then
run this repo's pipeline against the same game version.

## Repo Layout

Tracked public source:

- `addon/` is the Blender extension source root. It contains `__init__.py`,
  `blender_manifest.toml`, runtime `data/`, and `templates/basebuilding.blend`.
- `tools/` contains the asset-library update pipeline and worker scripts.
- `CatalogData/` contains small catalog metadata used to reconcile legacy
  building-piece catalog entries.
- `README.md` is user-facing install/use documentation.
- `DEVELOPERS.md` is this file.

Ignored local/generated state:

- `_local/blender-5.0.0-windows-x64/` is the configured portable Blender used
  for local builds.
- `_build/extension/` is the generated extension staging folder.
- `dist/` contains local release zips and package reports.
- `PipelineLogs/` contains timestamped pipeline logs.
- `PipelineRun.json` is the latest pipeline summary.

Do not use Git LFS. Generated `.blend` files and release `.zip` files stay out
of Git and are published through GitHub Releases.

## Blender Runtime

The pipeline resolves Blender in this order:

1. `E:\Github\RSDWBaseBuilder\_local\blender-5.0.0-windows-x64\blender.exe`
2. `BLENDER_EXE`
3. Installed Blender versions under `C:\Program Files\Blender Foundation`

The `_local` Blender directory is intentionally ignored. For a fresh local
checkout, copy the configured portable Blender into `_local/` or set
`BLENDER_EXE` to a compatible Blender 5.0+ executable with the required import
add-ons configured.

## Pipeline Commands

Target-only dry run:

```powershell
python tools\UpdateAssetLibrary.py --version 0.11.2.2 --mode targets --dry-run
```

Smoke build:

```powershell
python tools\UpdateAssetLibrary.py --version 0.11.2.2 --mode smoke
```

Full build and package:

```powershell
python tools\UpdateAssetLibrary.py --version 0.11.2.2 --mode full --package --clean-stage
```

Sync the currently staged extension into the configured portable Blender for
local testing:

```powershell
python tools\UpdateAssetLibrary.py --mode sync-portable
```

Useful options:

- `--archive-root` defaults to `E:\Github\RSDWArchive`.
- `--model-root` defaults to `E:\Github\RSDWModel`.
- `--extension-source-root` defaults to `addon/`.
- `--library-root` defaults to `_build/extension`.
- `--workers` controls concurrent Blender worker count.
- `--force` rebuilds already successful assets.
- `--limit` and `--only` restrict the target set for focused testing.
- `--material-mode optimized-pbr` is the default for smoke/full quality builds.
  It builds shared PBR material shards from RSDWModel WebAssets and links/falls
  back to them.
- Shared materials externalize texture files into `_MaterialTextures/` by
  default so the same texture data is not packed repeatedly into material
  shard `.blend` files.
- `--material-texture-limit-mb` defaults to `8.0` and transcodes larger
  externalized shared-material textures to JPEG for release-size control.
- `--material-texture-transcode-min-mb` defaults to `0.5`; supported
  externalized textures above that size are stored as release-friendly JPEGs.
- `--material-mode light` is only for fast debugging and is expected to produce
  weaker/untextured asset-library output.
- `--skip-shared-materials` skips shared material shard generation; workers can
  still build local fallback materials when `--material-mode fallback` is used.
- `--sync-portable-extension` installs the staged extension into the selected
  portable Blender after a full/package-current run.
- `--portable-extension-dir` overrides the installed extension directory. The
  target must still be under `portable\extensions\user_default`.
- Full and `package-current` runs write
  `PipelineLogs\<timestamp>\GitCommitPlan.json` by default.
- `--skip-git-plan` skips final Git commit batch planning.
- `--run-git-plan` or legacy `--git-plan` forces commit planning for
  targets/smoke runs.
- `--git-plan-output` writes the commit plan to an explicit path.
- `--git-commit-batches` creates the planned commits; `--git-push-each` also
  pushes each created batch.

## What The Pipeline Builds

The generated asset library is staged under `_build/extension/` and packaged
from there. The generated top-level asset groups are:

- `BP/`
- `Building_Pieces/`
- `Items/`

`blender_assets.cats.txt` is generated into `_build/extension/`, not committed
at repo root. Blender displays the catalogs as `BP`, `Building Pieces`, and
`Items`.

The full pipeline also refreshes source-side manifests under `tools/`, such as:

- `CatalogData\_catalog.json`
- `CatalogData\_catalog_disk.json`
- `addon\data\PieceDataMap.json`
- `tools\AssetLibrary\asset_library_targets.json`
- `tools\AssetLibrary\catalog_asset_targets.json`
- `tools\AssetLibrary\catalog_reconciliation.json`
- `tools\ModelData\BPMap.json`
- `tools\ModelData\MaterialInventory.json`

Review these generated manifests before committing because they describe the
current upstream Archive/Model inputs.

## Asset Quality Rules

The asset-library pipeline has explicit preview and material expectations:

- Item previews come from `properties.Icon` in `ItemData.json`, resolved against
  the selected Archive texture root.
- Building-piece previews come from the referenced building-piece JSON
  `Properties.DisplayIcon`.
- BP assets normally do not have authoritative UI icons. They should ship
  without a custom placeholder preview so Blender's asset browser can generate
  its normal 3D object thumbnail on load.
- Pipeline-generated targets must not use category fallback icons. The old
  category fallback remains only for legacy direct script runs without a target
  manifest.
- Smoke/full builds should use MI-derived materials. A material can be valid
  with texture images or with scalar/vector color parameters only, depending on
  what the source MI actually contains.

Quality reports are written under each run's `PipelineLogs\<timestamp>\` folder:

- `asset_target_quality_report.json` verifies icon coverage and preview intent
  immediately after target generation.
- `asset_quality_report.json` verifies built preview sources and materialized
  slot counts after the Blender workers finish.
- `_build\extension\_Materials.manifest.json` summarizes shared material shards,
  built/empty material counts, and externalized texture counts.

## Expected Validation

For game version `0.12.0.0`, the current target generation should produce:

- 3,528 generated assets total
- 1,678 BP assets
- 771 building-piece assets
- 1,079 item assets
- 13 unresolved model-ref records across 3 unique unresolved model refs

The validation stages should report:

- asset build: `3528 ok, 0 failed`
- metadata verification: `3528 ok, 0 failed`
- asset target quality: all `771` building pieces and `1078` of `1079` item
  targets have resolved authoritative icons; `ITEM_AnimaOrb` is the known
  allowed missing item icon; BP targets use generated preview mode
- asset quality: item/building-piece assets use custom icons, BP assets use
  Blender default/generated previews, and fallback material mode reports
  materialized slots
- Git file-size audit: no generated file over the configured limit
- package: one `dist\rsdw_base_builder-<addon-version>.zip`
- optional portable sync: installed extension has the same file count/layout as
  `_build\extension`
- Git commit plan: one `PipelineLogs\<timestamp>\GitCommitPlan.json` with no
  blocked oversized paths

The release zip can be larger than 100 MB. That is fine because it is a GitHub
Release artifact, not a committed source file.

## Git Hygiene

Before committing, check:

```powershell
git status --short --ignored
python tools\PlanGitCommits.py analyze
git ls-files | Select-String -Pattern '^_local/|^_build/|^dist/|^PipelineLogs/|^PipelineRun\.json'
git diff --cached --name-status
```

Expected hygiene:

- `_local/`, `_build/`, `dist/`, `PipelineLogs/`, and `PipelineRun.json` show as
  ignored.
- No generated release zip is staged.
- No generated asset `.blend` files are staged.
- `tools\PlanGitCommits.py analyze` reports zero blocked oversized paths.
- No old root asset folders are tracked.
- `addon/templates/basebuilding.blend` is tracked because it is the small
  starter template, not a generated asset-library file.

## Troubleshooting

- If Blender is not found, populate `_local/` or set `BLENDER_EXE`.
- If metadata verification fails, inspect
  `PipelineLogs\<timestamp>\asset_metadata_report.json`.
- If packaging fails, inspect `PipelineLogs\<timestamp>\11_package.log`.
- If target counts change after upstream updates, confirm `RSDWArchive` and
  `RSDWModel` were both updated to the same version before assuming the
  BaseBuilder pipeline is wrong.
