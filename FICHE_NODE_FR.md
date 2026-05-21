# Fiche Node - TColorRamp

## Resume

TColorRamp est un node Nuke natif (C++/Rust bridge) pour remapper la luminance via une rampe couleur editable.

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

1. Copier `publish/TColorRamp` dans `C:/Users/<user>/.nuke/TColorRamp`
2. Ajouter dans `C:/Users/<user>/.nuke/init.py`:

```python
import nuke
nuke.pluginAddPath(r"C:/Users/<user>/.nuke/TColorRamp")
```

3. Relancer Nuke

## Verification

- Verifier la presence de `Nodes > TColorRamp`
- Verifier que le binaire existe dans `TColorRamp/bin/<nuke_version>/<os>/<arch>/`
