# RSDWBaseBuilder Pipeline Handoff

This document is the orchestration contract for external tools or agents that
need to run the `RSDWBaseBuilder` pipeline as part of a larger multi-repo
update. It is intentionally shorter and more procedural than `DEVELOPERS.md`.

For human install/use notes, see `README.md`. For deeper developer context, see
`DEVELOPERS.md`.

## Purpose

`RSDWBaseBuilder` is the third step in the RSDW asset update chain:

1. `E:\Github\RSDWArchive` extracts game JSON, textures, and web datasets.
2. `E:\Github\RSDWModel` extracts and prepares importable model data.
3. `E:\Github\RSDWBaseBuilder` consumes those outputs and rebuilds the Blender
   extension asset library.

This repo does not run the Archive or Model pipelines. An external orchestrator
must run those first, then run this repo against the same game version.

## Upstream Dependencies

Default upstream repo locations:

- Archive root: `E:\Github\RSDWArchive`
- Model root: `E:\Github\RSDWModel`
- BaseBuilder root: `E:\Github\RSDWBaseBuilder`

The BaseBuilder pipeline expects the selected version to exist in both Archive
and Model outputs. If `--version` is omitted, the pipeline resolves the latest
shared Archive/Model version.

Required upstream data includes:

- Archive JSON output
- Archive texture output
- Archive item and BP data files
- RSDWModel static and skeletal model data
- RSDWModel `WebAssets\WebAssetManifest.json` for optimized PBR material builds

BaseBuilder owns its packaged snap metadata. During the BaseBuilder pipeline,
`tools\ModelData\BuildSnaps.py` scans the selected
`E:\Github\RSDWArchive\<version>\json` tree and refreshes
`addon\data\Snaps.json` before the extension is staged or the browser index is
built. RSDWArchive should not write this file directly.

Blender is resolved in this order:

1. `E:\Github\RSDWBaseBuilder\_local\blender-5.0.0-windows-x64\blender.exe`
2. `BLENDER_EXE`
3. Installed Blender versions under `C:\Program Files\Blender Foundation`

The `_local` Blender folder is ignored by Git and is local machine state.

## Canonical Commands

Run commands from `E:\Github\RSDWBaseBuilder`.

Target generation and early validation:

```powershell
python tools\UpdateAssetLibrary.py --version <game-version> --mode targets --dry-run
```

Smoke build:

```powershell
python tools\UpdateAssetLibrary.py --version <game-version> --mode smoke
```

Full release build, package, and portable Blender sync:

```powershell
python tools\UpdateAssetLibrary.py --version <game-version> --mode full --package --clean-stage --sync-portable-extension
```

Sync the currently staged extension into the selected portable Blender:

```powershell
python tools\UpdateAssetLibrary.py --mode sync-portable
```

Package the currently staged extension without rebuilding all assets:

```powershell
python tools\UpdateAssetLibrary.py --mode package-current --package
```

Force git commit planning for a partial run:

```powershell
python tools\UpdateAssetLibrary.py --version <game-version> --mode smoke --run-git-plan
```

Create the planned Git commits, and optionally push each batch:

```powershell
python tools\UpdateAssetLibrary.py --version <game-version> --mode full --package --git-commit-batches
python tools\UpdateAssetLibrary.py --version <game-version> --mode full --package --git-commit-batches --git-push-each
```

The normal project policy is direct commits and pushes to `main`. Do not create
or push orchestration branches for this repo unless the user explicitly changes
that policy.

## Pipeline Modes

`tools\UpdateAssetLibrary.py` is the orchestration entrypoint.

Current modes:

- `targets`: refreshes target manifests, catalog data, and target quality
  reports. With `--dry-run`, it does not build asset `.blend` files or package.
- `smoke`: builds a smoke target subset selected from
  `tools\AssetLibrary\asset_library_targets.json`.
- `full`: builds the full generated asset library.
- `sync-portable`: copies the existing staged extension into the configured
  portable Blender extension directory.
- `package-current`: stages runtime files, audits generated file sizes,
  packages the current staged extension, and runs git planning by default.

Default mode is `smoke`.

Default material mode is `optimized-pbr`. Available material modes are:
`optimized-pbr`, `light`, `fallback`, `base-color`, and `none`.

For `targets`, `smoke`, and `full`, the main stage order is:

1. Refresh `tools\ModelData\BPMap.json`
2. Refresh `addon\data\PieceDataMap.json` from the runtime building catalog
3. Refresh `addon\data\Snaps.json` from the selected Archive JSON tree
4. Prepare extension stage when required, after runtime data has been refreshed
5. Reconcile building-piece catalog data
6. Build building-piece targets
7. Build unified asset targets
8. Verify target quality
9. Write `blender_assets.cats.txt`
10. Build the browser web index from target data and refreshed snap data
11. Build material inventory
12. Build shared materials when material mode requires them
13. Build generated asset `.blend` files
14. Bake generated previews for BP assets unless skipped; this also writes
    browser BP preview WebPs
15. Rebuild the browser web index so generated BP preview paths are included
16. Verify Blender asset metadata
17. Verify built asset quality
18. Audit generated file sizes for Git safety
19. Optionally package the extension
20. Optionally sync the portable Blender extension
21. Optionally write or execute the Git commit plan

## Inputs and Outputs

Tracked source/config files that may be refreshed by the pipeline:

- `CatalogData\_catalog.json`
- `CatalogData\_catalog_disk.json`
- `addon\data\PieceDataMap.json`
- `addon\data\Snaps.json`
- `tools\AssetLibrary\asset_library_targets.json`
- `tools\AssetLibrary\catalog_asset_targets.json`
- `tools\AssetLibrary\catalog_reconciliation.json`
- `tools\ModelData\BPMap.json`
- `tools\ModelData\MaterialInventory.json`
- `website\basebuilder-index.json`
- `website\previews\<version>\bp\*.webp`

Ignored generated outputs:

- `_build\extension\`
- `_build\AssetLibraryProgress.<version>.json`
- `_build\GeneratedPreviewProgress.<version>.json`
- `dist\`
- `PipelineLogs\`
- `PipelineRun.json`

Important generated reports:

- `PipelineRun.json`
- `PipelineLogs\<timestamp>\asset_target_quality_report.json`
- `PipelineLogs\<timestamp>\asset_metadata_report.json`
- `PipelineLogs\<timestamp>\asset_quality_report.json`
- `PipelineLogs\<timestamp>\generated_preview_report.json`
- `PipelineLogs\<timestamp>\git_file_size_audit.json`
- `PipelineLogs\<timestamp>\GitCommitPlan.json`
- `PipelineLogs\<timestamp>\portable_extension_sync.json`
- `_build\extension\_Materials.manifest.json`
- `dist\rsdw_base_builder-<addon-version>.zip`
- `dist\rsdw_base_builder-<addon-version>.package_report.json`

The release artifact is the single zip under `dist\`. Publish that zip through
GitHub Releases or the larger orchestrator release system. Do not commit it.

## Success Criteria

An orchestration run should treat the BaseBuilder step as successful only when:

- `python tools\UpdateAssetLibrary.py ...` exits with code `0`.
- `PipelineRun.json` exists and its stages are successful or intentionally
  skipped.
- `PipelineRun.json` points at the current `PipelineLogs\<timestamp>\` folder.
- `asset_target_quality_report.json` has no blocking icon or target errors.
- `addon\data\Snaps.json` has been regenerated from the selected Archive JSON
  tree before staging/package work.
- `website\basebuilder-index.json` contains no local absolute paths and points
  at browser BP previews after a full, non-limited build. Its embedded snap
  metadata should reflect the refreshed `addon\data\Snaps.json`.
- `asset_metadata_report.json` and `asset_quality_report.json` pass for build
  modes that generate assets.
- `git_file_size_audit.json` has no oversized generated source files.
- A packaged release run produces `dist\rsdw_base_builder-<addon-version>.zip`.
- A portable sync run reports matching copied file counts and bytes in
  `portable_extension_sync.json`.
- The final Git commit plan has no blocked paths before commit creation.

For game version `0.12.0.0`, the known target summary after refreshing the
runtime building catalog is:

- 3,528 generated assets total
- 1,678 BP assets
- 771 building-piece assets
- 1,079 item assets

Target counts may legitimately change after upstream game updates. When they
change, confirm Archive and Model were both updated to the same version before
treating the BaseBuilder step as broken.

## Failure Recovery

Use the log paths in `PipelineRun.json` first. Each pipeline stage writes a
dedicated log under `PipelineLogs\<timestamp>\`.

Common recovery choices:

- If Blender cannot be found, install/copy the portable Blender under `_local\`
  or set `BLENDER_EXE`.
- If target generation fails, rerun or inspect the Archive and Model upstream
  pipelines for the same version.
- If only a few asset builds failed, inspect `08_asset_build.log`, then rerun
  with `--force` or a focused `--only <target-id>` command.
- If generated previews are the only failing stage, inspect
  `08b_generated_previews.log`; use `--skip-generated-previews` only for local
  diagnosis, not for release builds.
- If browser BP thumbnails are missing or blank, inspect
  `08b_generated_previews.log` and `08c_browser_web_index.log`. Full,
  non-limited release builds require BP preview WebPs before the final browser
  index is accepted.
- If packaging fails, inspect `11_package.log` and the package report.
- If portable sync fails, verify the target is under
  `portable\extensions\user_default\rsdw_base_builder`.
- If Git planning blocks a path, do not force-add the generated output. Fix the
  ignore/source split or release packaging path.

## Git and Release Policy

Commit source, small pipeline metadata, and website browser assets only. Do not
commit generated Blender asset libraries, release zips, pipeline logs, or local
Blender runtimes.

Ignored paths that should stay out of Git:

- `_local\`
- `_build\`
- `dist\`
- `PipelineLogs\`
- `PipelineRun.json`

Before creating commits, check:

```powershell
git status --short --ignored
python tools\PlanGitCommits.py analyze
git diff --cached --name-status
```

Current branch policy:

- Work on `main`.
- Commit directly to `main`.
- Push `main` to `origin/main`.
- Do not create extra branches or push auxiliary branches as part of the normal
  pipeline.

## Orchestrator Contract

Minimal machine-facing contract for a larger pipeline:

```yaml
repo: 'E:\Github\RSDWBaseBuilder'
depends_on:
  - 'E:\Github\RSDWArchive'
  - 'E:\Github\RSDWModel'
entrypoint: 'python tools\UpdateAssetLibrary.py'
version_argument: '--version <game-version>'
canonical_full_command: >
  python tools\UpdateAssetLibrary.py --version <game-version> --mode full --package --clean-stage --sync-portable-extension
default_mode: 'smoke'
default_material_mode: 'optimized-pbr'
success_files:
  - 'PipelineRun.json'
  - 'addon\data\Snaps.json'
  - 'PipelineLogs\<timestamp>\asset_target_quality_report.json'
  - 'PipelineLogs\<timestamp>\asset_metadata_report.json'
  - 'PipelineLogs\<timestamp>\asset_quality_report.json'
  - 'PipelineLogs\<timestamp>\git_file_size_audit.json'
  - 'website\basebuilder-index.json'
  - 'website\previews\<version>\bp\*.webp'
release_artifact: 'dist\rsdw_base_builder-<addon-version>.zip'
ignored_outputs:
  - '_local\'
  - '_build\'
  - 'dist\'
  - 'PipelineLogs\'
  - 'PipelineRun.json'
commit_policy:
  branch: 'main'
  push_target: 'origin/main'
  commit_generated_outputs: false
```
