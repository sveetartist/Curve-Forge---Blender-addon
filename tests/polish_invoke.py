"""UI checks for modal cleanup, precise thickness, coalescing, and error recovery."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import traceback
from types import SimpleNamespace

import bpy

sys.dont_write_bytecode = True
bpy.context.preferences.use_preferences_save = False
bpy.context.preferences.view.show_splash = False
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('curve_forge_polish_invoke_test', root / '__init__.py',
                                            submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()
window = bpy.context.window_manager.windows[0]
area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
region = next(region for region in area.regions if region.type == 'WINDOW')
instances = {}
for cls, method in ((addon.CURVE_OT_bevel_selected_points, '_update_header'),
                    (addon.CURVE_OT_slide_points, '_update_header'),
                    (addon.MESH_OT_interactive_curve_extruder, 'update_status')):
    original = getattr(cls, method)
    def capture(self, *args, original=original, name=cls.bl_idname):
        instances[name] = self
        original(self, *args)
    setattr(cls, method, capture)


def event(kind, text='', x=None, y=None, **kwargs):
    return SimpleNamespace(type=kind, value='PRESS', unicode=text, shift=False, ctrl=False, alt=False,
                           mouse_x=region.x + 150 if x is None else x,
                           mouse_y=region.y + 250 if y is None else y, **kwargs)


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def create_curve():
    clean()
    data = bpy.data.curves.new('Polish UI curve', 'CURVE')
    spline = data.splines.new('BEZIER')
    spline.bezier_points.add(2)
    for index, co in enumerate(((-2, 0, 0), (0, 0, 0), (0, 2, 0))):
        point = spline.bezier_points[index]
        point.co = co
        point.handle_left_type = point.handle_right_type = 'VECTOR'
        point.select_control_point = index == 1
        point.select_left_handle = point.select_right_handle = False
    obj = bpy.data.objects.new('Polish UI curve', data)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    return obj


def assert_closed(operator):
    feedback = operator._feedback
    assert feedback.closed and feedback.timer is None
    assert feedback not in addon.interaction.ModalFeedback.active


def steps():
    obj = create_curve()
    original = obj.data
    baseline = addon.snapshot_splines(original)
    assert bpy.ops.mesh.interactive_curve_extruder('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    thickness = instances['mesh.interactive_curve_extruder']
    for character in '.25':
        thickness.modal(bpy.context, event('TEXTINPUT', character))
    assert abs(thickness.depth - 0.25) < 1e-6
    thickness.modal(bpy.context, event('MOUSEMOVE', x=region.x + 400))
    assert abs(thickness.depth - 0.25) < 1e-6
    # Backspace edits each digit, then resumes dragging at the last displayed value.
    thickness.modal(bpy.context, event('BACK_SPACE'))
    thickness.modal(bpy.context, event('BACK_SPACE'))
    thickness.modal(bpy.context, event('BACK_SPACE'))
    assert thickness.depth == 0 and thickness._numeric == ''
    thickness.modal(bpy.context, event('MOUSEMOVE', x=region.x + 410))
    assert abs(thickness.depth - 0.02) < 1e-6
    thickness.modal(bpy.context, event('R'))
    thickness.modal(bpy.context, event('F'))
    # Modal feedback must not install a cursor overlay.
    assert not hasattr(thickness._feedback, 'draw')
    yield
    assert thickness.modal(bpy.context, event('ESC')) == {'CANCELLED'}
    assert_closed(thickness)
    assert bpy.context.mode == 'EDIT_CURVE' and obj.data == original
    assert addon.snapshot_splines(original) == baseline
    yield
    print('PASS: thickness numeric entry, mouse resume, header/status feedback, and exact cancel')

    assert bpy.ops.curve.bevel_selected_points('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    bevel = instances['curve.bevel_selected_points']
    feedback = bevel._feedback
    now = [0.0]
    bevel._schedule.clock = lambda: now[0]
    for index in range(50):
        bevel.modal(bpy.context, event('MOUSEMOVE', x=bevel._mouse_origin[0] + index + 1,
                                      y=bevel._mouse_origin[1]))
    first_applied = bevel._schedule.applied
    assert first_applied[0] != bevel.width
    for _ in range(3):
        bevel.modal(bpy.context, event('WHEELDOWNMOUSE'))
    assert bevel.segments == 1
    now[0] = 0.04
    bevel.modal(bpy.context, event('TIMER', timer=feedback.timer))
    assert bevel._schedule.applied == (bevel.width, 1, bevel.shape, bevel.amount_type)
    for character in '.3':
        bevel.modal(bpy.context, event('TEXTINPUT', character))
    assert bevel._schedule.applied[0] != bevel.width
    assert bevel.modal(bpy.context, event('RET')) == {'FINISHED'}
    assert_closed(bevel)
    assert len(obj.data.splines[0].bezier_points) == 4
    assert abs(obj.data.splines[0].bezier_points[1].co.x + 0.3) < 1e-5
    yield
    print('PASS: rapid previews coalesce, timer applies latest settings, confirm flushes exact value and reduced segments')

    # Inject a failure after creating real temporary bevel geometry.
    obj = create_curve()
    original = obj.data
    baseline = addon.snapshot_splines(original)
    curve_names = set(bpy.data.curves.keys())
    assert bpy.ops.curve.bevel_selected_points('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    bevel = instances['curve.bevel_selected_points']
    bevel.modal(bpy.context, event('MOUSEMOVE', x=bevel._mouse_origin[0] + 20, y=bevel._mouse_origin[1]))
    preview = bevel._session.preview
    def fail(*args):
        preview(*args)
        raise ValueError('injected preview failure')
    bevel._session.preview = fail
    bevel._schedule.last_time = float('-inf')
    result = bevel.modal(bpy.context, event('WHEELUPMOUSE'))
    assert result == {'CANCELLED'}
    assert_closed(bevel)
    assert obj.data == original and bpy.context.mode == 'EDIT_CURVE'
    assert addon.snapshot_splines(original) == baseline
    assert set(bpy.data.curves.keys()) == curve_names
    yield
    print('PASS: bevel preview error restores original topology, attributes, selection, mode and timer')

    assert bpy.ops.curve.slide_points('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    slide = instances['curve.slide_points']
    for character in '.5':
        slide.modal(bpy.context, event('TEXTINPUT', character))
    assert abs(slide.factor - 0.5) < 1e-6
    # Clearing a one-digit value preserves that displayed factor until the next mouse delta.
    slide._numeric = '1'
    slide.factor = 1.0
    slide._apply()
    slide.modal(bpy.context, event('BACK_SPACE'))
    assert slide.factor == 1.0
    assert slide.modal(bpy.context, event('ESC')) == {'CANCELLED'}
    assert_closed(slide)
    assert addon.snapshot_splines(original) == baseline
    yield

    assert bpy.ops.curve.slide_points('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    slide = instances['curve.slide_points']
    apply = slide._apply
    def fail_slide(self):
        apply()
        raise ValueError('injected slide failure')
    cls = addon.CURVE_OT_slide_points
    previous = cls._apply
    cls._apply = fail_slide
    try:
        assert slide.modal(bpy.context, event('TEXTINPUT', '.')) == {'CANCELLED'}
    finally:
        cls._apply = previous
    assert_closed(slide)
    assert addon.snapshot_splines(original) == baseline
    yield
    print('PASS: slide numeric-to-mouse continuity, cancellation and preview error cleanup')

    assert bpy.ops.mesh.interactive_curve_extruder('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    thickness = instances['mesh.interactive_curve_extruder']
    apply = thickness._apply_settings
    def fail_thickness(self):
        apply()
        raise ValueError('injected thickness failure')
    cls = addon.MESH_OT_interactive_curve_extruder
    previous = cls._apply_settings
    cls._apply_settings = fail_thickness
    try:
        assert thickness.modal(bpy.context, event('R')) == {'CANCELLED'}
    finally:
        cls._apply_settings = previous
    assert_closed(thickness)
    assert addon.snapshot_splines(original) == baseline
    yield
    print('PASS: thickness preview error restores all curve settings and point attributes')

    assert bpy.ops.curve.bevel_selected_points('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    bevel = instances['curve.bevel_selected_points']
    bevel.modal(bpy.context, event('MOUSEMOVE', x=bevel._mouse_origin[0] + 20, y=bevel._mouse_origin[1]))
    feedback = bevel._feedback
    addon.unregister()
    assert feedback.closed and feedback.timer is None
    assert obj.data == original and addon.snapshot_splines(original) == baseline
    assert not addon.interaction.ModalFeedback.active
    yield
    print('PASS: disabling add-on during a preview cancels geometry and releases modal feedback/timer')


iterator = steps()


def run():
    try:
        with bpy.context.temp_override(window=window, area=area, region=region):
            next(iterator)
        return 0.2
    except StopIteration:
        result = {'passed': True}
    except Exception:
        result = {'passed': False, 'error': traceback.format_exc()}
        traceback.print_exc()
    path = Path(tempfile.gettempdir()) / 'curve_forge_polish_invoke.result.json'
    path.write_text(json.dumps(result), encoding='utf-8')
    print(f'Polish UI result: {path}')
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(run, first_interval=1.0)
