"""Native confirm/undo/redo and F9 popup: Blender --enable-event-simulate --python this_file.py."""
import importlib.util
import json
from math import pi
from pathlib import Path
import sys
import tempfile
import traceback

import bpy

sys.dont_write_bytecode = True
bpy.context.preferences.use_preferences_save = False
bpy.context.preferences.view.show_splash = False
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('curve_forge_thickness_invoke_test', root / '__init__.py',
                                            submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
data = bpy.data.meshes.new('Thickness source')
data.from_pydata([(0, 0, 0), (2, 0, 0), (2, 2, 0)], [(0, 1), (1, 2)], [])
source = bpy.data.objects.new('Thickness source', data)
bpy.context.collection.objects.link(source)
source.select_set(True)
bpy.context.view_layer.objects.active = source
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
source_name = source.name
window = bpy.context.window_manager.windows[0]
area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
region = next(region for region in area.regions if region.type == 'WINDOW')
mouse = (region.x + region.width // 2, region.y + region.height // 2)
instances = []
update = addon.MESH_OT_interactive_curve_extruder.update_status


def capture(self, context):
    if not instances:
        instances.append(self)
    update(self, context)


addon.MESH_OT_interactive_curve_extruder.update_status = capture


def key(kind, text='', ctrl=False):
    window.event_simulate(type=kind, value='PRESS', unicode=text, ctrl=ctrl, x=mouse[0], y=mouse[1])
    window.event_simulate(type=kind, value='RELEASE', ctrl=ctrl, x=mouse[0], y=mouse[1])


def steps():
    global mouse
    window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=mouse[0], y=mouse[1])
    key('ESC')
    yield
    bpy.ops.ed.undo_push(message='Before native thickness')
    assert bpy.ops.mesh.interactive_curve_extruder('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    yield
    for kind, text in (('ZERO', '0'), ('PERIOD', '.'), ('TWO', '2'), ('FIVE', '5')):
        key(kind, text)
    key('R', 'r')
    key('F', 'f')
    yield
    assert abs(instances[0].depth - 0.25) < 1e-6
    feedback = instances[0]._feedback
    key('RET')
    yield
    assert feedback.closed
    assert bpy.context.mode == 'OBJECT' and bpy.context.object.type == 'CURVE'
    assert abs(bpy.context.object.data.bevel_depth - 0.25) < 1e-6
    assert bpy.context.object.data.use_fill_caps
    assert bpy.context.window_manager.operators[-1].bl_idname == 'MESH_OT_interactive_curve_extruder'
    print('PASS: native thickness keyboard input and confirm')
    assert bpy.ops.screen.redo_last.poll()
    key('F9')
    yield
    bpy.ops.screen.screenshot(filepath=str(Path(tempfile.gettempdir()) / 'curve_forge_thickness_f9.png'))
    # The F9 popup is anchored at the cursor; Ctrl-click its first numeric row.
    scale = bpy.context.preferences.system.ui_scale
    popup_origin = mouse
    mouse = (mouse[0] + round(220 * scale), mouse[1] - round(50 * scale))
    window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=mouse[0], y=mouse[1])
    key('LEFTMOUSE', ctrl=True)
    yield
    key('A', 'a', ctrl=True)
    for kind, text in (('ZERO', '0'), ('PERIOD', '.'), ('FIVE', '5')):
        key(kind, text)
    key('RET')
    yield
    bpy.ops.screen.screenshot(filepath=str(Path(tempfile.gettempdir()) / 'curve_forge_thickness_f9_edited.png'))
    assert bpy.context.object.type == 'CURVE'
    assert abs(bpy.context.object.data.bevel_depth - 0.5) < 1e-6, bpy.context.object.data.bevel_depth
    assert len(bpy.data.objects) == 2
    assert abs(bpy.context.object.data.splines[0].points[0].tilt - pi / 4) < 1e-6
    mouse = (popup_origin[0] + round(70 * scale), popup_origin[1] - round(155 * scale))
    window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=mouse[0], y=mouse[1])
    yield
    key('LEFTMOUSE')
    yield
    bpy.ops.screen.screenshot(filepath=str(Path(tempfile.gettempdir()) / 'curve_forge_thickness_f9_mesh.png'))
    assert bpy.context.object.type == 'MESH'
    assert len(bpy.data.objects) == 2
    assert bpy.ops.screen.redo_last.poll()
    window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=mouse[0], y=mouse[1])
    yield
    key('LEFTMOUSE')
    yield
    assert bpy.context.object.type == 'CURVE'
    assert len(bpy.data.objects) == 2
    assert abs(bpy.context.object.data.bevel_depth - 0.5) < 1e-6
    key('ESC')
    yield
    print('PASS: editing depth through the real F9 popup replaces the result without duplicate objects or accumulating tilt')
    bpy.ops.ed.undo()
    assert bpy.context.mode == 'EDIT_MESH' and bpy.context.object.name == source_name
    yield
    bpy.ops.ed.redo()
    assert bpy.context.object.type == 'CURVE'
    assert abs(bpy.context.object.data.bevel_depth - 0.5) < 1e-6
    print('PASS: native thickness undo and redo after editing the F9 result')
    addon.unregister()


iterator = steps()


def run():
    try:
        with bpy.context.temp_override(window=window, area=area, region=region):
            next(iterator)
        return 0.3
    except StopIteration:
        result = {'passed': True}
    except Exception:
        result = {'passed': False, 'error': traceback.format_exc()}
        traceback.print_exc()
    path = Path(tempfile.gettempdir()) / 'curve_forge_thickness_invoke.result.json'
    path.write_text(json.dumps(result), encoding='utf-8')
    print(f'Thickness UI result: {path}')
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(run, first_interval=1.0)
