# Repository Guidelines

## Project Structure & Module Organization

Curve Forge is a Python extension for Blender 5.0+. Source modules live at the repository root:

- `__init__.py` registers operators, menus, and shortcuts.
- `bevel.py`, `merge_operators.py`, `slide.py`, and `edge_to_curve.py` implement tools.
- `geometry.py`, `merge.py`, and `slide_geometry.py` contain geometry logic.
- `common.py`, `interaction.py`, and `ui.py` provide shared data helpers, modal interaction, and interface components.

`tests/` contains unit, Blender integration, and UI checks. `promo/` holds promotional scenes and images. `dist/` contains generated installation ZIPs. `blender_manifest.toml` defines extension metadata and the explicit build file list; update that list when adding runtime modules.

## Build, Test, and Development Commands

Run commands from the repository root with Blender on `PATH`, or substitute its full executable path:

```powershell
python -m unittest discover -s tests
blender --factory-startup --command extension validate
blender --factory-startup --command extension build --output-filepath dist/curve_forge-1.1.0.zip
blender --background --factory-startup --python-exit-code 1 --python tests/blender_integration.py
```

These run unit tests, validate the extension, build the installation archive, and run Blender integration checks. Match the archive version to the manifest. Install the ZIP through Blender's Install from Disk workflow for manual testing.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, and descriptive module names. Follow neighboring code for wrapping and quotation style. Keep geometry calculations separate from operators and UI. Preserve SPDX license headers and Blender class prefixes such as `CURVE_OT_` and `VIEW3D_PT_`. No formatter or linter configuration is included.

## Testing Guidelines

Unit tests use `unittest` and `test_*.py` filenames. Add regression coverage for geometry and interaction changes. Run the relevant `*_integration.py` and `*_invoke.py` scripts documented in `README.md`. UI checks require a graphical Blender instance; verify their temporary result JSON contains `"passed": true`. Test on Blender 5.0 and 5.2. No coverage threshold is configured. Check cancellation, undo/redo, selection, and attribute preservation for modal changes.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout, so no existing commit convention could be verified. Use concise imperative subjects, such as `Fix slide cancellation restoring handles`. Describe the behavior changed, validation performed, and supported Blender versions tested. Link relevant issues and include screenshots or recordings for visible UI or interaction changes.
