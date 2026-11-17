"""Run without --background to verify dispatch in Blender's UI event loop."""
import importlib.util
import json
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

sys.dont_write_bytecode = True

# Keep this factory-startup UI test from writing personal preference changes.
bpy.context.preferences.use_preferences_save = False

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bevel_curve_invoke_test', root / '__init__.py',
                                            submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
curve = bpy.data.curves.new('Invoke Curve', 'CURVE')
spline = curve.splines.new('BEZIER')
spline.bezier_points.add(2)
for i, co in enumerate(((-1, 0, 0), (0, 0, 0), (0, 1, 0))):
    point = spline.bezier_points[i]
    point.co = co
    point.handle_left_type = point.handle_right_type = 'VECTOR'
    point.select_control_point = i == 1
    point.select_left_handle = point.select_right_handle = False
obj = bpy.data.objects.new('Invoke Object', curve)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')

# Capture the real Blender-created operator instance, leaving the real header
# and status UI update in place. Native event dispatch is not needed to verify
# the registered invocation or test subsequent event handling on that instance.
instances = []
update_header = addon.CURVE_OT_bevel_selected_points._update_header


def capture_header(self):
    if not instances:
        instances.append(self)
    update_header(self)


addon.CURVE_OT_bevel_selected_points._update_header = capture_header
window = bpy.context.window_manager.windows[0]
area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
region = next(region for region in area.regions if region.type == 'WINDOW')
baseline = set(bpy.data.curves.keys())


def run():
    try:
        keyconfigs = bpy.context.window_manager.keyconfigs

        def mesh_bindings():
            return tuple(
                (config.name, item.idname, item.type, item.value,
                 item.ctrl, item.shift, item.alt, item.oskey, item.active)
                for config in keyconfigs
                for keymap in config.keymaps if keymap.name == 'Mesh'
                for item in keymap.keymap_items
            )

        native_bevel = [item for item in keyconfigs.default.keymaps['Mesh'].keymap_items
                        if item.idname == 'mesh.bevel' and item.type == 'B'
                        and item.value == 'PRESS' and item.ctrl
                        and not item.shift and not item.alt and not item.oskey]
        assert native_bevel and all(item.active for item in native_bevel)
        baseline_mesh = mesh_bindings()
        assert len(addon.addon_keymaps) == 3
        keymap, item = addon.addon_keymaps[0]
        assert keymap.name == 'Curve' and keymap.space_type == 'EMPTY'
        assert keymap.region_type == 'WINDOW'
        assert item.idname == 'curve.bevel_selected_points'
        assert item.type == 'B' and item.value == 'PRESS' and item.ctrl
        assert not item.shift and not item.alt and not item.oskey and not item.any
        merge_keymap, merge_item = addon.addon_keymaps[1]
        assert merge_keymap == keymap
        assert merge_item.idname == 'curve.merge_points_menu'
        assert merge_item.type == 'M' and merge_item.value == 'PRESS'
        assert not merge_item.ctrl and not merge_item.shift and not merge_item.alt
        slide_keymap, slide_item = addon.addon_keymaps[2]
        assert slide_keymap == keymap and slide_item.idname == 'curve.grab_or_slide'
        assert slide_item.type == 'G' and slide_item.value == 'PRESS' and not slide_item.any
        assert not slide_item.ctrl and not slide_item.shift and not slide_item.alt
        addon.unregister()
        assert not addon.addon_keymaps
        assert not any(item.idname == 'curve.bevel_selected_points'
                       for keymap in keyconfigs.addon.keymaps for item in keymap.keymap_items)
        assert mesh_bindings() == baseline_mesh
        addon.register()
        assert len(addon.addon_keymaps) == 3
        assert sum(item.idname == 'curve.bevel_selected_points'
                   for keymap in keyconfigs.addon.keymaps for item in keymap.keymap_items) == 1
        assert mesh_bindings() == baseline_mesh
        print('PASS: Ctrl+B is scoped to Curve, unregister removes it, re-enable adds one binding, Mesh keymaps unchanged')

        keyconfigs.update()
        user_keymap = keyconfigs.user.keymaps['Curve']
        custom = next(item for item in user_keymap.keymap_items
                      if item.idname == 'curve.merge_points_menu')
        custom.type = 'J'
        custom.ctrl = True
        custom.shift = True
        # Preferences must display the effective user keymap, not its defaults.
        import rna_keymap_ui
        draw_kmi = rna_keymap_ui.draw_kmi
        shown = []
        rna_keymap_ui.draw_kmi = lambda _, kc, km, item, layout, level: shown.append(item)
        layout = SimpleNamespace(label=lambda **kwargs: None, prop=lambda *args: None,
                                 context_pointer_set=lambda *args: None)
        try:
            addon.BevelCurvePreferences.draw(SimpleNamespace(layout=layout), bpy.context)
        finally:
            rna_keymap_ui.draw_kmi = draw_kmi
        assert len(shown) == 3
        assert shown[1] == custom and shown[1].type == 'J'
        addon.unregister()
        addon.register()
        keyconfigs.update()
        custom = next(item for item in keyconfigs.user.keymaps['Curve'].keymap_items
                      if item.idname == 'curve.merge_points_menu')
        assert custom.type == 'J' and custom.ctrl and custom.shift
        custom.type = 'M'
        custom.ctrl = custom.shift = False
        assert mesh_bindings() == baseline_mesh
        print('PASS: customizable merge shortcut is displayed in preferences and survives re-enable')

        with bpy.context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.curve.bevel_selected_points.poll()
            result = bpy.ops.curve.bevel_selected_points('INVOKE_DEFAULT')
            assert result == {'RUNNING_MODAL'}, result
            operator = instances[0]
            assert operator.width == 0
            x, y = operator._mouse_origin
            move = SimpleNamespace(type='MOUSEMOVE', value='NOTHING', mouse_x=x + 30, mouse_y=y,
                                   shift=False, unicode='')
            assert operator.modal(bpy.context, move) == {'RUNNING_MODAL'}
            assert operator.width > 0
            assert obj.data != curve
            old_segments = operator.segments
            wheel = SimpleNamespace(type='WHEELDOWNMOUSE', value='PRESS', unicode='')
            assert operator.modal(bpy.context, wheel) == {'RUNNING_MODAL'}
            assert operator.segments == old_segments - 1
            cancel = SimpleNamespace(type='ESC', value='PRESS')
            assert operator.modal(bpy.context, cancel) == {'CANCELLED'}
            assert obj.data == curve
            assert set(bpy.data.curves.keys()) == baseline
            assert bpy.context.mode == 'EDIT_CURVE'
            # Make the middle point genuinely active using Blender's viewport
            # selection operator, then select all without replacing that active.
            area.spaces.active.region_3d.view_perspective = 'ORTHO'
            location = view3d_utils.location_3d_to_region_2d(
                region, area.spaces.active.region_3d, obj.matrix_world @ Vector((0, 0, 0)))
            assert location is not None
            bpy.ops.curve.select_all(action='DESELECT')
            result = bpy.ops.view3d.select(location=(round(location.x), round(location.y)))
            assert 'FINISHED' in result, result
            destination = addon.active_point_position(bpy.context)
            assert destination is not None and destination.length < 1e-5
            bpy.ops.curve.select_all(action='SELECT')
            cursor = bpy.context.scene.cursor.location.copy()
            bpy.ops.ed.undo_push(message='Before active merge')
            assert bpy.ops.curve.merge_selected_points(merge_type='ACTIVE') == {'FINISHED'}
            bpy.ops.ed.undo_push(message='After active merge')
            assert bpy.context.scene.cursor.location == cursor
            bpy.ops.object.mode_set(mode='OBJECT')
            points = obj.data.splines[0].bezier_points
            assert len(points) == 1 and points[0].co.length < 1e-5
            print('PASS: active merge uses the clicked middle point, not the last point in spline order')
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.ed.undo()
            # F9-style re-execution with captured source indices restores the
            # same target even though changing modes clears native active state.
            assert bpy.ops.curve.merge_selected_points(merge_type='ACTIVE',
                                                      active_spline_index=0, active_point_index=1) == {'FINISHED'}
            bpy.ops.object.mode_set(mode='OBJECT')
            points = bpy.context.object.data.splines[0].bezier_points
            assert len(points) == 1 and points[0].co.length < 1e-5
            print('PASS: redo preserves the active merge target')
            assert not bpy.ops.curve.bevel_selected_points.poll()
            assert not bpy.ops.curve.merge_selected_points.poll()
            assert not bpy.ops.curve.merge_points_menu.poll()
            bpy.ops.mesh.primitive_cube_add()
            bpy.ops.object.mode_set(mode='EDIT')
            assert bpy.context.mode == 'EDIT_MESH'
            assert not bpy.ops.curve.bevel_selected_points.poll()
            assert not bpy.ops.curve.merge_selected_points.poll()
            assert not bpy.ops.curve.merge_points_menu.poll()
            assert bpy.ops.mesh.bevel.poll()
            assert mesh_bindings() == baseline_mesh
            print('PASS: curve bevel unavailable in Object/Mesh Edit Mode; native mesh bevel available')
            # Verify the integrated Edge to Curve operator enters its actual
            # modal loop, cancels cleanly, then confirms a curve usable by the
            # existing bevel and merge tools.
            source = bpy.context.object
            thick_instances = []
            update_thickness_status = addon.MESH_OT_interactive_curve_extruder.update_status

            def capture_thickness(self, context):
                if not thick_instances:
                    thick_instances.append(self)
                update_thickness_status(self, context)

            addon.MESH_OT_interactive_curve_extruder.update_status = capture_thickness
            before_curves = set(bpy.data.curves.keys())
            before_meshes = set(bpy.data.meshes.keys())
            assert bpy.ops.mesh.interactive_curve_extruder('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
            thickness = thick_instances[0]
            assert thickness.curve_obj.type == 'CURVE' and thickness.curve_obj != source
            assert thickness.modal(bpy.context, SimpleNamespace(type='ESC', value='PRESS')) == {'CANCELLED'}
            assert bpy.context.mode == 'EDIT_MESH' and bpy.context.object == source
            assert set(bpy.data.curves.keys()) == before_curves
            assert set(bpy.data.meshes.keys()) == before_meshes
            thick_instances.clear()
            assert bpy.ops.mesh.interactive_curve_extruder('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
            thickness = thick_instances[0]
            move = SimpleNamespace(type='MOUSEMOVE', value='NOTHING',
                                   mouse_x=thickness.last_mouse_x + 50, shift=False)
            assert thickness.modal(bpy.context, move) == {'RUNNING_MODAL'}
            assert thickness.curve_obj.data.bevel_depth > 0
            assert thickness.modal(bpy.context, SimpleNamespace(type='LEFTMOUSE', value='PRESS')) == {'FINISHED'}
            assert bpy.context.mode == 'OBJECT' and bpy.context.object.type == 'CURVE'
            assert source.type == 'MESH'
            bpy.ops.object.mode_set(mode='EDIT')
            assert bpy.ops.curve.bevel_selected_points.poll()
            assert bpy.ops.curve.merge_selected_points.poll()
            assert bpy.ops.mesh.interactive_curve_extruder.poll()
            assert mesh_bindings() == baseline_mesh
            print('PASS: edge-to-curve modal cancel/confirm and shared Curve Tools workflow')
        addon.unregister()
        result = {'passed': True}
        print('PASS: registered INVOKE_DEFAULT enters modal, real instance previews, wheel adjusts, cancel restores')
    except Exception:
        result = {'passed': False, 'error': traceback.format_exc()}
        traceback.print_exc()
    result_path = Path(tempfile.gettempdir()) / 'curve_tools_modal_invoke.result.json'
    result_path.write_text(json.dumps(result), encoding='utf-8')
    print(f'UI test result: {result_path}')
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(run, first_interval=1.0)
