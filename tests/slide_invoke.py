"""Real G-G event dispatch: Blender --enable-event-simulate --python this_file.py."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import traceback
from types import SimpleNamespace

import bpy
from bpy_extras import view3d_utils
from mathutils import Quaternion, Vector

sys.dont_write_bytecode = True
bpy.context.preferences.use_preferences_save = False
bpy.context.preferences.view.show_splash = False
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('curve_forge_slide_invoke_test', root / '__init__.py',
                                            submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
curve = bpy.data.curves.new('G-G curve', 'CURVE')
curve.dimensions = '3D'
spline = curve.splines.new('BEZIER')
spline.bezier_points.add(2)
for i, co in enumerate(((-2, 0, 0), (0, 0, 0), (0, 2, 0))):
    point = spline.bezier_points[i]
    point.co = co
    point.handle_left_type = point.handle_right_type = 'VECTOR'
    point.select_control_point = i == 1
    point.select_left_handle = point.select_right_handle = False
obj = bpy.data.objects.new('G-G object', curve)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
window = bpy.context.window_manager.windows[0]
area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
region = next(region for region in area.regions if region.type == 'WINDOW')
view = area.spaces.active.region_3d
view.view_rotation = Quaternion((1, 0, 0, 0))
view.view_location = Vector((0, 0, 0))
view.view_distance = 10
view.view_perspective = 'ORTHO'
instances = []
invoke_events = []
original_invoke = addon.CURVE_OT_grab_or_slide.invoke


def capture_invoke(self, context, event):
    invoke_events.append((event.type, event.value, context.area.type, context.mode))
    return original_invoke(self, context, event)


addon.CURVE_OT_grab_or_slide.invoke = capture_invoke
update_header = addon.CURVE_OT_grab_or_slide._update_header


def capture(self):
    if not instances:
        instances.append(self)
    update_header(self)


addon.CURVE_OT_grab_or_slide._update_header = capture
stage = 0
mouse = None
baseline = None


def key(kind, text=''):
    window.event_simulate(type=kind, value='PRESS', unicode=text, x=mouse[0], y=mouse[1])
    window.event_simulate(type=kind, value='RELEASE', x=mouse[0], y=mouse[1])


def move(x, y):
    global mouse
    mouse = (round(x), round(y))
    window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=mouse[0], y=mouse[1])


def finish(passed, error=None):
    path = Path(tempfile.gettempdir()) / 'curve_forge_slide_invoke.result.json'
    path.write_text(json.dumps({'passed': passed, 'error': error}), encoding='utf-8')
    print(f'Slide UI result: {path}')
    bpy.ops.wm.quit_blender()


def run():
    global stage, baseline
    try:
        with bpy.context.temp_override(window=window, area=area, region=region):
            if stage == 0:
                baseline = addon.snapshot(bpy.context.object.data.splines[0])
                bpy.ops.ed.undo_push(message='Before G-G slide')
                screen = view3d_utils.location_3d_to_region_2d(region, view, Vector((0, 0, 0)))
                move(region.x + screen.x, region.y + screen.y)
                key('ESC')
            elif stage == 1:
                key('G', 'g')
            elif stage == 2:
                assert instances and instances[0].operation_mode == 'GRAB', (
                    'G did not invoke the curve move handler',
                    [operator.bl_rna.identifier for operator in window.modal_operators],
                    [(item.idname, item.type, item.active) for item in bpy.context.window_manager.keyconfigs.user.keymaps['Curve'].keymap_items if item.type == 'G'],
                    mouse, (region.x, region.y, region.width, region.height), bpy.context.mode, invoke_events,
                    [operator.bl_rna.identifier for operator in bpy.context.window_manager.operators][-10:])
                move(mouse[0] + 20, mouse[1] + 10)
            elif stage == 3:
                assert Vector(addon.snapshot(bpy.context.object.data.splines[0])[1]['co']).length > 0
                key('G', 'g')
            elif stage == 4:
                assert instances[0].operation_mode == 'SLIDE', 'Second G did not switch to slide'
                assert addon.snapshot(bpy.context.object.data.splines[0]) == baseline
                endpoint = view3d_utils.location_3d_to_region_2d(region, view, Vector((0, 1, 0)))
                delta = endpoint - instances[0]._anchor
                move(mouse[0] + delta.x, mouse[1] + delta.y)
            elif stage == 5:
                assert abs(instances[0].factor - 0.5) < 0.02
                co = Vector(addon.snapshot(bpy.context.object.data.splines[0])[1]['co'])
                assert abs(co.x) < 1e-5 and abs(co.y - 1.0) < 0.04
                key('RET')
            elif stage == 6:
                assert instances[0]._closed
                assert bpy.context.mode == 'EDIT_CURVE'
                bpy.ops.ed.undo()
                assert addon.snapshot(bpy.context.object.data.splines[0]) == baseline
                instances.clear()
            elif stage == 7:
                key('G', 'g')
            elif stage == 8:
                assert instances and instances[0].operation_mode == 'GRAB', (
                    'G after undo', invoke_events, bpy.context.mode,
                    [operator.bl_rna.identifier for operator in window.modal_operators],
                    [(item.idname, item.type, item.active) for item in bpy.context.window_manager.keyconfigs.user.keymaps['Curve'].keymap_items if item.type == 'G'],
                    window.screen == area.id_data, window.as_pointer(), bpy.context.window_manager.windows[0].as_pointer())
                repeated = SimpleNamespace(type='G', value='PRESS', is_repeat=True,
                                           alt=False, ctrl=False, shift=False, unicode='g')
                instances[0].modal(bpy.context, repeated)
                assert instances[0].operation_mode == 'GRAB'
                key('G', 'g')
            elif stage == 9:
                assert instances[0].operation_mode == 'SLIDE'
                for kind, text in (('ZERO', '0'), ('PERIOD', '.'), ('SEVEN', '7')):
                    key(kind, text)
            elif stage == 10:
                co = Vector(addon.snapshot(bpy.context.object.data.splines[0])[1]['co'])
                assert abs(co.y - 1.4) < 1e-5
                key('ESC')
            elif stage == 11:
                assert addon.snapshot(bpy.context.object.data.splines[0]) == baseline
                config = bpy.context.window_manager.keyconfigs
                config.update()
                item = next(item for item in config.user.keymaps['Curve'].keymap_items if item.idname == 'curve.grab_or_slide')
                item.type = 'H'
                config.update()
                instances.clear()
                key('H', 'h')
            elif stage == 12:
                assert instances and instances[0].operation_mode == 'GRAB'
                key('H', 'h')
            elif stage == 13:
                assert instances[0].operation_mode == 'SLIDE'
                key('ESC')
            elif stage == 14:
                assert addon.snapshot(bpy.context.object.data.splines[0]) == baseline
                print('PASS: actual G, G dispatch; free grab; original-path slide; confirm/undo; numeric input; exact cancel; customized double key')
                bpy.context.scene.tool_settings.use_proportional_edit = True
                instances.clear()
                key('H', 'h')
            elif stage == 15:
                assert not instances
                operators = [(operator.bl_rna.identifier, operator.properties.bl_rna.identifier, operator.name)
                             for operator in window.modal_operators]
                assert any(properties == 'TRANSFORM_OT_translate' for _, properties, _ in operators), operators
                key('ESC')
            elif stage == 16:
                bpy.context.scene.tool_settings.use_proportional_edit = False
                assert addon.snapshot(bpy.context.object.data.splines[0]) == baseline
                print('PASS: proportional G delegates to the native move tool')
                config = bpy.context.window_manager.keyconfigs
                item = next(item for item in config.user.keymaps['Curve'].keymap_items if item.idname == 'curve.grab_or_slide')
                item.type = 'G'
                config.update()
                entry = bpy.context.preferences.addons.new()
                entry.module = spec.name
                entry.preferences.use_move_slide = False
                config.update()
                assert addon.ui.shortcut_label(bpy.context, 'curve.grab_or_slide') == 'Unassigned'
                instances.clear()
                key('G', 'g')
            elif stage == 17:
                assert not instances
                assert any(operator.properties.bl_rna.identifier == 'TRANSFORM_OT_translate'
                           for operator in window.modal_operators)
                key('ESC')
            elif stage == 18:
                entry = bpy.context.preferences.addons[spec.name]
                config = bpy.context.window_manager.keyconfigs
                _, item = addon.ui.effective_binding(bpy.context, 'curve.grab_or_slide')
                item.type = 'H'
                config.update()
                entry.preferences.use_move_slide = True
                config.update()
                assert addon.ui.shortcut_label(bpy.context, 'curve.grab_or_slide') == 'H'
                entry.preferences.use_move_slide = False
                addon.unregister()
                addon.register()
                config.update()
                assert addon.ui.shortcut_label(bpy.context, 'curve.grab_or_slide') == 'Unassigned'
                entry.preferences.use_move_slide = True
                config.update()
                assert addon.ui.shortcut_label(bpy.context, 'curve.grab_or_slide') == 'H'
                print('PASS: preference restores native G, retains remapping, and survives re-registration')
                bpy.context.preferences.addons.remove(entry)
                addon.unregister()
                finish(True)
                return None
        stage += 1
        return 0.2
    except Exception:
        error = traceback.format_exc()
        traceback.print_exc()
        finish(False, error)
        return None


bpy.app.timers.register(run, first_interval=1.0)
