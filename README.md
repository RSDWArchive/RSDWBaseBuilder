# RSDW Base Builder

A Blender add-on that lets you design RuneScape: Dragonwilds bases visually
and load them into the game through the RSDW Dev Kit workflow.

Recommended Blender version: 5.0.0 or newer. This is what the local pipeline
builds and tests with.

## What It Does

- Browse generated Dragonwilds assets from Blender's Asset Browser: BP
  visuals, building pieces, and item visuals organized under `BP`,
  `Building Pieces`, and `Items`.
- Drag and drop assets into your scene to design a base.
- Snap building pieces together while you build.
- Save your design as a `.json` file the in-game companion mod reads.
- Load existing base `.json` files and edit them in Blender.

## Install

1. Download the latest `rsdw_base_builder-<version>.zip` from GitHub Releases.
2. Open Blender 5.0 or newer.
3. Go to `Edit > Preferences > Get Extensions > Install from Disk`.
4. Pick the `.zip` file you downloaded.
5. Enable the add-on if Blender does not enable it automatically.

## Quick Start

1. Open Blender.
2. In the 3D viewport, open the sidebar with `N` and choose the `RSDW Base
   Builder` tab.
3. Click `New Basebuilding File` and choose where to save the working file.
4. Open Blender's Asset Browser and choose `RSDW Base Builder` from the asset
   library dropdown.
5. Pick a category under `BP`, `Building Pieces`, or `Items`, then drag assets
   into the viewport.
6. When your base is ready, click `Export Building JSON` in the sidebar.

## Repository Layout

The public repo contains reproducible source and small metadata:

- `addon/` contains the Blender extension source, runtime `data/`, and
  `templates/basebuilding.blend`.
- `tools/` contains the repeatable Archive/Model-driven asset-library
  pipeline.
- `CatalogData/` contains small catalog metadata used by the pipeline.

Large local/runtime outputs are ignored by Git:

- `_local/blender-5.0.0-windows-x64/` is the configured portable Blender used
  by the pipeline.
- `_build/extension/` is the disposable staged extension with generated asset
  `.blend` files.
- `dist/` contains local release zips and package reports.
- `PipelineLogs/` and `PipelineRun.json` record local pipeline runs.

## Release Pipeline

The BaseBuilder pipeline consumes completed upstream outputs from
`E:\Github\RSDWArchive` and `E:\Github\RSDWModel`. It does not run those
upstream update pipelines itself.

```powershell
python tools\UpdateAssetLibrary.py --version 0.11.2.2 --mode targets --dry-run
python tools\UpdateAssetLibrary.py --version 0.11.2.2 --mode smoke
python tools\UpdateAssetLibrary.py --version 0.11.2.2 --mode full --package --clean-stage
python tools\UpdateAssetLibrary.py --mode sync-portable
```

The pipeline prefers `_local/blender-5.0.0-windows-x64/blender.exe`, then
`BLENDER_EXE`, then installed Blender versions. The release artifact is one
single Blender extension zip in `dist/`; publish that zip through GitHub
Releases rather than committing it to Git.

Use `--sync-portable-extension` on a full/package-current run, or
`--mode sync-portable` after a successful build, to replace the selected
portable Blender install at
`portable\extensions\user_default\rsdw_base_builder` with `_build\extension`.

Full and `package-current` runs also write an Archive-style Git commit batch
plan to `PipelineLogs\<timestamp>\GitCommitPlan.json` unless
`--skip-git-plan` is supplied. Use `--run-git-plan` to force planning on
targets/smoke runs.

## Development Notes

- Developer pipeline notes live in `DEVELOPERS.md`.
- Do not use Git LFS for this repo.
- Do not commit generated `.blend` assets, `_build/`, `dist/`, `_local/`, or
  pipeline logs.
- The old root asset folders were generated outputs and have been replaced by
  the reproducible asset-library pipeline.
