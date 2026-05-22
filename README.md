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
cargo xtask --compile --nuke-versions 16.0 --target-platform windows --output-to-package --limit-threads
```

Exemples cibles:

- Linux: `--target-platform linux`
- macOS Intel: `--target-platform macos-x86-64`
- macOS Apple Silicon: `--target-platform macos-aarch64`

## Build CI GitHub

Le repo contient un workflow GitHub Actions (`.github/workflows/nuke-build.yml`) qui:

- build les versions Nuke 13.0 -> 17.0
- build Windows/Linux/macOS (x86_64 + arm64 quand disponible)
- genere un zip de release pret a copier dans `.nuke`

## Installer dans Nuke (utilisateur final)

1. Cloner le repo
2. Glisser `publish/TColorRamp` dans `C:/Users/<user>/.nuke/`
3. Redemarrer Nuke

Les binaires (`.dll`, `.so`, `.dylib`) sont versionnes dans `publish/TColorRamp/bin/...`.

Si ton setup Nuke ne charge pas automatiquement le dossier, ajoute en fallback dans `.nuke/init.py`:

```python
import nuke
nuke.pluginAddPath(r"C:/Users/<user>/.nuke/TColorRamp")
```

## Verification rapide

- Le menu `Nodes > TColorRamp` apparait
- Le binaire est present dans:
  `TColorRamp/bin/<nuke_version>/<os>/<arch>/`

## Licence

Usage commercial soumis a la licence du repo (`LICENSE` + `EULA.md`).
