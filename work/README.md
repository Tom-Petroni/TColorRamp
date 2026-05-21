# TColorRamp

TColorRamp is a standalone Nuke node extracted from the TNoise color ramp workflow.

## What it does

- Reads RGB from input
- Computes Rec.709 luminance per pixel
- Remaps that luminance through a user-editable color ramp
- Outputs remapped RGB while preserving alpha

## Repository layout

- `crates/tcolorramp-nuke/src/tcolor_ramp.cpp`: native Nuke node implementation
- `TColorRamp/_python_color_ramp.py`: inline ramp editor (PySide)
- `TColorRamp/_plugin_loader.py`: binary discovery and loading
- `TColorRamp/menu.py`: node menu registration

## Build

The native plugin requires Nuke SDK headers and `DDImage`.
If `NUKE_SOURCE_PATH` is missing, the Rust crate still builds for sanity checks,
but the output is not a loadable Nuke node binary.

PowerShell example:

```powershell
$env:NUKE_SOURCE_PATH = "C:/Program Files/Nuke16.0v6"
$env:PLATFORM_NAME = "windows"
cargo build --release -p tcolorramp-nuke
```

## Install binary into package

TColorRamp expects a packaged binary at:

- `TColorRamp/bin/<NUKE_MAJOR.MINOR>/windows/x86_64/TColorRamp.dll`
- `TColorRamp/bin/<NUKE_MAJOR.MINOR>/linux/x86_64/libTColorRamp.so`
- `TColorRamp/bin/<NUKE_MAJOR.MINOR>/macos/<arch>/libTColorRamp.dylib`

Windows example (Nuke 16.0):

```powershell
.\scripts\publish_windows.ps1 -NukeVersion 16.0
```

Current packaged binary in this repo:

- `TColorRamp/bin/16.0/windows/x86_64/TColorRamp.dll`

## Enable in Nuke

Add this repository root to your Nuke plugin path.
`init.py` will register `TColorRamp/` automatically.

A `TColorRamp` menu and node entry will appear in the Nodes toolbar.
