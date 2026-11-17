# Curve Forge

A Blender 5.0+ extension combining mesh-edge conversion, interactive curve
thickness, unlimited corner bevels, control-point merging, and point sliding.

## Install

Drag **dist/curve_forge-1.0.0.zip** from your file manager into Blender,
then confirm **Install & Enable**. Keep the ZIP compressed.

Disable the separate **Edge to Curve** add-on before enabling this combined
extension. The extension keeps the original `bevel_curve_points` ID so it
updates previous Bevel Curve Points and Curve Tools installations and retains
their shortcuts.

Alternatively: **Edit → Preferences → Get Extensions → dropdown at top right
→ Install from Disk**, then choose the ZIP and enable the extension.

## Bevel Curve Points

1. Select a classic Curve object and enter **Edit Mode** with **Tab**.
2. Select corner control points, such as the corner of an L-shaped poly curve
   or a Bezier point with Vector handles. Select the point itself, not only its handles.
3. Press **Ctrl+B** in the 3D viewport, use **Right-click → Bevel Curve Points**,
   or press **F3** and search for it.
4. Move the mouse away from its starting position to increase the bevel radius;
   move back to decrease it. The curve updates as you move.
5. Scroll **up/down** to add/remove segments (and therefore control points).
6. **Left-click** or **Enter** to confirm; **Esc** or **right-click** to cancel.
7. Use **F9** to adjust the confirmed result, or **Ctrl+Z** to undo.

During the operation, hold **Shift** for precise mouse adjustment, or type a
number to set the amount exactly. **Backspace** edits the number; clear it
completely to return to mouse control. **M** toggles Round/Chamfer and **R**
toggles Radius/Offset. The viewport header shows the amount, segments, and shape; the status bar lists the controls.
Clearing numeric input resumes dragging from the last displayed value.

Also available in the curve right-click menu and the **Curve** menu in Edit Mode.
The **Ctrl+B** shortcut applies only in Curve Edit Mode; Blender's mesh bevel
shortcut in Mesh Edit Mode is unchanged.

**Radius** is the default amount type. On straight corners, it controls the
radius of the rounded corner, regardless of the corner angle. On curved
segments it is an approximation based on the tangents at the original corner.
**Offset** instead measures the distance along each side of the original curve.
Both use local curve units. Apply object scale for consistent world-space amounts.
The amount has no segment-length cap. Larger bevels can overlap neighboring
bevels; beyond a segment's endpoints, the curve is extended along its endpoint
tangents. Arc length uses a numerical approximation.

**Round** adds a smooth Bezier fillet, or sampled points on a poly spline.
Straight corners use the standard circular Bezier approximation; curved
or nonplanar corners use a tangent-continuous transition. **Chamfer** adds
a straight cut. **Segments** controls the number of pieces in the new bevel;
one Bezier segment already makes a smooth rounded corner. Increasing it on
a poly spline makes the sampled bevel smoother.

Every preview is calculated from the original curve. Reducing segments or
shrinking the radius does not stack bevel operations. Cancellation restores
the original datablock, topology, point selection, and attributes.
Rapid input is combined into at most 30 preview updates per second, and
confirmation always applies the latest value, including any pending input.

Open spline endpoints, hidden points, smooth points, zero-length edges, and
reversing cusps are skipped. Cyclic splines and multiple objects in Edit Mode
are supported. Radius, tilt, soft-body weights, material assignments, spline
settings, and untouched splines are preserved. Automatic handles adjacent to
a bevel become Free to preserve the existing curve shape after trimming.

This tool changes the curve path, rather than the thickness of its profile.
NURBS splines and the newer hair Curves object type are not supported.
Curves with shape keys, curve-data animation/drivers, or Hook modifiers are
rejected because adding points changes the indices those features depend on.

## Merge Points

In Curve Edit Mode, select at least two control points and press **M** to open
**Merge Curve Points**:

- **At Center** merges the selection into one point at its average position.
- **At Active** merges into the point selected last, keeping its position and
  point attributes. Select the destination point last with **Shift-click**.

Both modes are also available in the curve right-click menu, the **Curve**
menu and **F3** search for **Merge Curve Points**.
Use **F9** to change the merge mode or **Ctrl+Z** to undo.

Select points within one Bezier or poly spline, or select one endpoint in each
of two open splines of the same type to join them into a single spline. Joined
splines use the active spline's settings for At Active and the first spline's
settings for At Center. Merge works on one curve object at a time. Hidden points
and points with only their handles selected are excluded. Untouched splines,
curve materials, and linked users of the curve datablock are preserved.

## Slide Curve Points (G, G)

In Curve Edit Mode, select Bezier or poly control points and press **G**, then
**G** again to slide them along their original neighboring curve segments.
Turn proportional editing off for double-G; when it is on, G keeps Blender's
native proportional move. The direct Slide Curve Points command moves the selection.
Moving the mouse towards either neighbor chooses that side of the curve.
Bézier points follow the curved segment, rather than the straight chord.

- **Shift** gives precise movement; **Ctrl** snaps to 10% increments.
- Type a factor such as **0.5** to travel halfway towards the next point, or
  **-0.5** towards the previous point. **Backspace** edits the amount.
- **C** toggles clamping at neighboring points; **Alt** temporarily disables
  it. Unclamped movement extends along the segment's endpoint tangent.
- **Left-click / Enter** confirms; **Esc / right-click** restores the original
  points and handles. **Ctrl+Z** undoes a confirmed slide.

Also available as **Slide Curve Points** in the Curve menu, right-click menu,
and **F3** search. **F9** adjusts the factor and clamping.
Open endpoints and cyclic splines are supported; hidden points and zero-length
paths are skipped. Sliding moves existing control points and translates their
handles, so the curve shape updates without changing topology or attributes.
Shape-key curves and NURBS splines use Blender's regular move tool for **G**;
sliding is available for Bezier and poly splines without shape keys.

The first **G** starts a free curve-point move, with **X/Y/Z** axis constraints,
**Shift+X/Y/Z** plane constraints, numeric input, **Shift** precision, and **Ctrl**
increments. Repeating an axis key switches between global, local, and free
movement. The second **G** starts sliding from the original point positions.
Curve Forge's G binding applies only in Curve Edit Mode; mesh slide is unchanged.

## Custom Shortcuts

Open **Edit → Preferences → Add-ons → Curve Forge** and expand the
add-on to edit its **Bevel Curve Points**, **Merge Curve Points**, and
**Move / Slide Curve Points** shortcuts.
Click the key field and press your preferred shortcut; expand its row to change
Ctrl, Shift, Alt, or other event settings. Defaults are **Ctrl+B** for bevel and
**M** for the merge menu, and **G** for move / slide. Changing the move key also
changes the key to press twice for sliding. Blender saves the changes in its user keymap; save
preferences if automatic saving is disabled.

Turn off **Use Curve Forge Move / Slide shortcut** to restore Blender's native
**G** with the default keymap. The preference retains your custom move/slide
binding when you turn it back on. **Slide Curve Points** remains available in
the menus and F3 search.

You can also find these bindings in **Preferences → Keymap**. They apply only
in Curve Edit Mode. During an active bevel operation, **M** still toggles its
Round/Chamfer shape.

## Edge to Thick Curve

Select mesh edges in Edit Mode and choose **Edge → Edge to Thick Curve**,
use the right-click menu in Edge Select mode, or open **N → Curve → Curve Forge**.
The tool copies selected visible edges into a new curve; the source mesh,
its edge selection, and its modifiers are preserved. Object transforms and
material slots are copied to the new curve.

For an existing curve in Object or Edit Mode, use **Adjust Curve Thickness**
in the Curve menu (Edit Mode) or its right-click menu.

| Input | Action |
| --- | --- |
| Move mouse left/right | Adjust thickness |
| Shift + mouse movement | Fine-tune thickness |
| Type a number / Backspace | Set an exact depth in local curve units / edit the number |
| Scroll wheel | Adjust bevel resolution |
| S | Toggle smooth/flat shading |
| F | Toggle end caps |
| R | Add 45 degrees of tilt to all curve points, including Bezier points |
| A | Convert to mesh and finish |
| Left click / Enter | Confirm and select the curve in Object Mode |
| Right click / Esc | Cancel and restore the original selection and mode |

Mouse sensitivity is 0.002 curve units per pixel, or 0.0004 with Shift.
Typed input pauses mouse adjustment; clearing the number resumes dragging at
the last displayed depth. The viewport header shows depth, resolution, caps,
shading, and tilt, with detailed controls in the status bar.
Cancelling a new curve removes the generated object and its data. Cancelling
an existing-curve adjustment restores thickness, resolution, caps, tilt,
each spline's shading, dimensions, and fill mode.

After confirming, use **F9** to edit depth, resolution, caps, shading, tilt
offset, or **Convert to Mesh**. Redo recreates the result from the original
source, so it does not duplicate objects or accumulate tilt. **Keep Original**
shading preserves mixed smooth/flat splines. Tilt offset is relative to the
original points. **Convert to Mesh** can be switched back off in F9.
Depth is a profile radius in local curve units; unit suffixes are not supported.

After confirming a new curve, enter Edit Mode to bevel or merge its points.
The thickness tool keeps the original `mesh.interactive_curve_extruder`
operator ID for existing custom bindings.

## Project Layout

- `__init__.py`: one registration and unregistration flow for all tools.
- `bevel.py`, `geometry.py`: interactive bevel and curve geometry.
- `merge_operators.py`, `merge.py`: merge operators and point geometry.
- `slide.py`, `slide_geometry.py`: curve grab and slide operators and path geometry.
- `edge_to_curve.py`: mesh-edge conversion and interactive thickness.
- `common.py`: shared curve data and selection helpers.
- `ui.py`: menus and shortcut preferences.
- `interaction.py`: shared numeric entry, preview scheduling, and modal cleanup.
- `tests/`: geometry, Blender integration, and UI invocation checks.
- `dist/`: the current installable ZIP; previous ZIPs are archived in `dist/old/`.
  This directory is excluded from extension contents.

## Development

Build and validate using Blender's extension commands:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' --factory-startup --command extension validate
& 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' --factory-startup --command extension build --output-filepath dist/curve_forge-1.0.0.zip
```

Run the geometry tests with `python -m unittest discover -s tests`.
Run Blender integration tests with `blender --background --factory-startup --python tests/blender_integration.py`.
Run edge/thickness integration tests with `blender --background --factory-startup --python tests/edge_integration.py`.
Run slide integration tests with `blender --background --factory-startup --python tests/slide_integration.py`.
Run thickness redo checks with `blender --background --factory-startup --python-exit-code 1 --python tests/polish_integration.py`.
Run the UI invocation check with `blender --factory-startup --python tests/modal_invoke.py`;
it tests both modal tools in Blender's UI event loop and then closes that test
instance. The result JSON is written to the system temporary directory.
Run the actual double-G keyboard check with
`blender --factory-startup --enable-event-simulate --python tests/slide_invoke.py`;
its result is `curve_forge_slide_invoke.result.json` in the system temporary directory.
Run modal cleanup, preview scheduling, numeric input, and injected-error UI checks with
`blender --factory-startup --python tests/polish_invoke.py`; inspect
`curve_forge_polish_invoke.result.json` in the system temporary directory.
Run native thickness confirm/undo/redo and F9 editing checks with
`blender --factory-startup --enable-event-simulate --python tests/thickness_invoke.py`;
inspect `curve_forge_thickness_invoke.result.json` in the system temporary directory.
UI result JSON must contain `"passed": true`; a successful Blender exit alone
does not indicate that the UI assertions passed. Validate on both Blender 5.0 and 5.2.

License: GPL-3.0-or-later, see LICENSE. Includes the Edge to Curve tool by ArtVit.
