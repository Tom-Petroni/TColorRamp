# TColorRamp

TColorRamp est un node Nuke natif pour remapper la luminance d'une image via une rampe couleur editable directement en comp.

## Pourquoi TColorRamp

- Remap de luminance en couleur via color ramp
- Alpha preserve
- Workflow simple pour stylisation/lookdev comp
- Package Python + plugin natif

## Structure du repo

```text
TColorRamp/
  publish/        # payload a copier dans .nuke
  work/           # source rust/c++ + scripts de publication
  node.json
  VERSION
  CHANGELOG.md
```

## Prerequis

- Nuke SDK/headers accessibles
- Rust/Cargo
- Toolchain C++ compatible Nuke

## Compiler

Depuis la racine du repo:

```powershell
cd work
$env:NUKE_SOURCE_PATH = "C:/Program Files/Nuke16.0v6"
$env:PLATFORM_NAME = "windows"
cargo build --release -p tcolorramp-nuke
```

Publication binaire Windows (Nuke 16.0):

```powershell
cd work
.\scripts\publish_windows.ps1 -NukeVersion 16.0
```

## Installer dans Nuke

1. Copier `publish/TColorRamp` vers `C:/Users/<user>/.nuke/TColorRamp`
2. Dans `C:/Users/<user>/.nuke/init.py`, ajouter:

```python
import nuke
nuke.pluginAddPath(r"C:/Users/<user>/.nuke/TColorRamp")
```

3. Redemarrer Nuke

## Verification rapide

- Le menu `Nodes > TColorRamp` apparait
- Le binaire est present dans:
  `TColorRamp/bin/<nuke_version>/<os>/<arch>/`

## Licence

Usage commercial soumis a la licence du repo (`LICENSE` + `EULA.md`).
