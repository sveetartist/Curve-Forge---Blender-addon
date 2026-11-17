"""Run with Blender --background --factory-startup --python this_file.py."""
import importlib.util
import sys
sys.dont_write_bytecode = True
from pathlib import Path
from types import MethodType, SimpleNamespace

import bpy
from mathutils import Vector

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bevel_curve_test', root / '__init__.py',
                                            submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()
assert addon.draw_menu in bpy.types.VIEW3D_MT_edit_curve_context_menu.draw._draw_funcs
print('PASS: registered in Curve Edit Mode right-click context menu')


def clean():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def create_curve(kind='BEZIER', cyclic=False):
    curve = bpy.data.curves.new('Test Curve', 'CURVE')
    curve.dimensions = '3D'
    spline = curve.splines.new(kind)
    coords = [(-1, 0, 0), (0, 0, 0), (0, 1, 0)]
    if cyclic:
        coords = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    collection = spline.bezier_points if kind == 'BEZIER' else spline.points
    collection.add(len(coords) - 1)
    for i, (point, co) in enumerate(zip(collection, coords)):
        if kind == 'BEZIER':
            point.co = co
            point.handle_left_type = point.handle_right_type = 'VECTOR'
            point.select_control_point = cyclic or i == 1
            point.select_left_handle = point.select_right_handle = False
        else:
            point.co = (*co, 1)
            point.select = cyclic or i == 1
        point.radius = i + 1
        point.tilt = i * 0.1
    spline.use_cyclic_u = cyclic
    spline.resolution_u = 17
    obj = bpy.data.objects.new('Test Object', curve)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def close(a, b):
    assert (Vector(a) - Vector(b)).length < 1e-5, (tuple(a), b)


clean()
obj = create_curve()
extra = obj.data.splines.new('POLY')
extra.points.add(1)
extra.points[0].co = (4, 0, 0, 1)
extra.points[1].co = (4, 1, 0, 1)
obj.data.bevel_depth = 0.04
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.bevel_selected_points(width=0.2, segments=1) == {'FINISHED'}
assert bpy.context.mode == 'EDIT_CURVE'
bpy.ops.object.mode_set(mode='OBJECT')
points = obj.data.splines[0].bezier_points
assert len(points) == 4
close(points[1].co, (-0.2, 0, 0))
close(points[2].co, (0, 0.2, 0))
assert abs(points[1].radius - 1.8) < 1e-5
assert abs(points[2].radius - 2.2) < 1e-5
assert obj.data.splines[0].resolution_u == 17
assert abs(obj.data.bevel_depth - 0.04) < 1e-6
assert len(obj.data.splines) == 2
close(obj.data.splines[1].points[0].co[:3], (4, 0, 0))
print('PASS: Bezier trim, attributes, profile and untouched spline')

for kind in ('BEZIER', 'POLY'):
    for width in (0.75, 1.0, 25.0):
        clean()
        obj = create_curve(kind)
        bpy.ops.object.mode_set(mode='EDIT')
        assert bpy.ops.curve.bevel_selected_points(width=width, segments=1) == {'FINISHED'}
        bpy.ops.object.mode_set(mode='OBJECT')
        spline = obj.data.splines[0]
        points = spline.bezier_points if kind == 'BEZIER' else spline.points
        assert len(points) == 4
        close(points[1].co[:3], (-width, 0, 0))
        close(points[2].co[:3], (0, width, 0))
print('PASS: unlimited Bezier/poly radius, including amounts above segment length and 10 units')

clean()
obj = create_curve('POLY', True)
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.bevel_selected_points(width=10, segments=4) == {'FINISHED'}
bpy.ops.object.mode_set(mode='OBJECT')
assert len(obj.data.splines[0].points) == 28
assert obj.data.splines[0].use_cyclic_u
close(obj.data.splines[0].points[4].co[:3], (10, 0, 0))
print('PASS: cyclic poly curve, adjacent corners, unlimited width')

clean()
first = create_curve()
second = create_curve('POLY')
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.bevel_selected_points(width=0.1, segments=2, shape='CHAMFER') == {'FINISHED'}
bpy.ops.object.mode_set(mode='OBJECT')
assert len(first.data.splines[0].bezier_points) == 5
assert len(second.data.splines[0].points) == 5
close(second.data.splines[0].points[2].co[:3], (-0.05, 0.05, 0))
print('PASS: multi-object Edit Mode and chamfer')

clean()
obj = create_curve()
for point in obj.data.splines[0].bezier_points:
    point.select_control_point = False
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.bevel_selected_points() == {'CANCELLED'}
assert bpy.context.mode == 'EDIT_CURVE'
bpy.ops.object.mode_set(mode='OBJECT')
assert len(obj.data.splines[0].bezier_points) == 3
print('PASS: no selection cancels without changing topology')

clean()
obj = create_curve()
obj.shape_key_add(name='Basis')
obj.shape_key_add(name='Key')
bpy.ops.object.mode_set(mode='EDIT')
try:
    bpy.ops.curve.bevel_selected_points()
except RuntimeError as exc:
    assert 'shape keys' in str(exc)
else:
    raise AssertionError('Expected shape-key rejection')
assert bpy.context.mode == 'EDIT_CURVE'
bpy.ops.object.mode_set(mode='OBJECT')
assert len(obj.data.splines[0].bezier_points) == 3
print('PASS: shape keys protected')

clean()
obj = create_curve()
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.ed.undo_push(message='Before bevel')
assert bpy.ops.curve.bevel_selected_points(width=0.2, segments=1) == {'FINISHED'}
bpy.ops.ed.undo_push(message='After bevel')
bpy.ops.ed.undo()
bpy.ops.object.mode_set(mode='OBJECT')
obj = bpy.context.object  # Undo replaces data; discard stale RNA references.
assert len(obj.data.splines[0].bezier_points) == 3
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.ed.redo()
bpy.ops.object.mode_set(mode='OBJECT')
obj = bpy.context.object
assert len(obj.data.splines[0].bezier_points) == 4
close(obj.data.splines[0].bezier_points[1].co, (-0.2, 0, 0))
print('PASS: undo restores original topology, redo restores bevel')

# Exercise the preview backend with real curve data. Segment decreases need
# deletion, which the curve-point RNA collections cannot do directly.
clean()
obj = create_curve()
original = obj.data
original_values = addon.snapshot(original.splines[0])
original_names = set(bpy.data.curves.keys())
bpy.ops.object.mode_set(mode='EDIT')
session = addon.BevelSession(bpy.context)
for width, segments in ((0.1, 2), (25.0, 8), (0.05, 1), (0.0, 1), (0.2, 4)):
    session.preview(width, segments, 'ROUND', 'RADIUS')
    assert bpy.context.mode == 'EDIT_CURVE'
    bpy.ops.object.mode_set(mode='OBJECT')
    assert len(original.splines[0].bezier_points) == 3
    assert addon.snapshot(original.splines[0]) == original_values
    points = obj.data.splines[0].bezier_points
    assert len(points) == (segments + 3 if width > 0 else 3)
    if width > 0:
        close(points[1].co, (-width, 0, 0))
    bpy.ops.object.mode_set(mode='EDIT')
session.finish()
assert obj.data == original
assert set(bpy.data.curves.keys()) == original_names
bpy.ops.object.mode_set(mode='OBJECT')
assert addon.snapshot(original.splines[0]) == original_values
print('PASS: repeated previews, decreasing segments, zero width and exact cancel')

clean()
first = create_curve()
original = first.data
linked = bpy.data.objects.new('Linked user', original)
bpy.context.collection.objects.link(linked)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.ed.undo_push(message='Before modal bevel')
session = addon.BevelSession(bpy.context)
session.preview(0.15, 6, 'ROUND', 'RADIUS')
session.preview(0.25, 2, 'CHAMFER', 'OFFSET')
assert linked.data == original
session.finish(commit=True)
assert first.data == original and linked.data == original
bpy.ops.ed.undo_push(message='After modal bevel')
bpy.ops.object.mode_set(mode='OBJECT')
assert len(original.splines[0].bezier_points) == 5
close(original.splines[0].bezier_points[1].co, (-0.25, 0, 0))
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.ed.undo()
bpy.ops.object.mode_set(mode='OBJECT')
assert len(bpy.context.object.data.splines[0].bezier_points) == 3
print('PASS: preview confirm commits once, preserves linked data and supports undo')

# Drive the actual modal method with synthetic events, checking that wheel,
# precision, typing, confirm, and cancel route to the tested preview backend.
class RecordedSession:
    changed = 1
    clamped = 0

    def __init__(self):
        self.calls = []
        self.finished = None

    def preview(self, *args):
        self.calls.append(args)

    def finish(self, commit=False):
        self.finished = commit


def modal_operator():
    operator = SimpleNamespace(width=0.0, segments=4, shape='ROUND', amount_type='RADIUS',
                               _session=RecordedSession(), _mouse_origin=(10, 10),
                               _last_distance=0.0, _numeric='', _drag_amount=0.0,
                               _units_per_pixel=0.01, cleaned=False, _closed=False,
                               _schedule=addon.bevel.PreviewSchedule())
    for name in ('_modal', '_preview'):
        setattr(operator, name, MethodType(getattr(addon.CURVE_OT_bevel_selected_points, name), operator))
    operator.report = lambda *args: None
    operator._update_header = lambda: None
    operator._cleanup = lambda: setattr(operator, 'cleaned', True)
    operator.cancel = lambda context: (operator._session.finish(), operator._cleanup())
    return operator


def event(kind, value='PRESS', x=10, y=10, shift=False, text=''):
    return SimpleNamespace(type=kind, value=value, mouse_x=x, mouse_y=y, shift=shift, unicode=text)


operator = modal_operator()
modal = addon.CURVE_OT_bevel_selected_points.modal
assert modal(operator, None, event('MOUSEMOVE', 'NOTHING', x=30)) == {'RUNNING_MODAL'}
assert abs(operator.width - 0.2) < 1e-6
modal(operator, None, event('WHEELUPMOUSE'))
assert operator.segments == 5
modal(operator, None, event('WHEELDOWNMOUSE'))
assert operator.segments == 4
modal(operator, None, event('MOUSEMOVE', 'NOTHING', x=40, shift=True))
assert abs(operator.width - 0.21) < 1e-6
for text in '0.35':
    modal(operator, None, event('ZERO', text=text))
assert abs(operator.width - 0.35) < 1e-6
modal(operator, None, event('MOUSEMOVE', 'NOTHING', x=200))
assert abs(operator.width - 0.35) < 1e-6  # Typed amount ignores mouse movement.
for _ in range(4):
    modal(operator, None, event('BACK_SPACE'))
assert operator._numeric == '' and operator.width == 0
modal(operator, None, event('MOUSEMOVE', 'NOTHING', x=201))
assert abs(operator.width - 0.01) < 1e-6  # Continues at the last displayed numeric value.
for text in '0.35':
    modal(operator, None, event('ZERO', text=text))
modal(operator, None, event('M'))
modal(operator, None, event('R'))
assert operator.shape == 'CHAMFER' and operator.amount_type == 'OFFSET'
assert modal(operator, None, event('LEFTMOUSE', 'RELEASE')) == {'RUNNING_MODAL'}
assert modal(operator, None, event('LEFTMOUSE')) == {'FINISHED'}
assert operator._session.calls[-1] == (0.35, 4, 'CHAMFER', 'OFFSET')
assert operator._session.finished is True and operator.cleaned
for cancel_type in ('ESC', 'RIGHTMOUSE'):
    operator = modal_operator()
    assert modal(operator, None, event(cancel_type)) == {'CANCELLED'}
    assert operator._session.finished is False and operator.cleaned
print('PASS: mouse, wheel, precision, numeric input, shape, confirm and cancel events')

for kind in ('BEZIER', 'POLY'):
    clean()
    obj = create_curve(kind)
    original = obj.data
    points = original.splines[0].bezier_points if kind == 'BEZIER' else original.splines[0].points
    for i, point in enumerate(points):
        if kind == 'BEZIER':
            point.select_control_point = i < 2
        else:
            point.select = i < 2
    untouched = original.splines.new('NURBS')
    untouched.points.add(3)
    for i, point in enumerate(untouched.points):
        point.co = (4, i, 1, 0.5 + i * 0.1)
        point.weight = 0.2 + i * 0.1
        point.select = False
    untouched.order_u = 3
    untouched.use_cyclic_u = True
    untouched.resolution_u = 19
    baseline = addon.snapshot_splines(original)[1]
    linked = bpy.data.objects.new('Merge linked user', original)
    bpy.context.collection.objects.link(linked)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.ed.undo_push(message='Before merge')
    assert bpy.ops.curve.merge_selected_points(merge_type='CENTER') == {'FINISHED'}
    bpy.ops.ed.undo_push(message='After merge')
    assert bpy.context.mode == 'EDIT_CURVE'
    bpy.ops.object.mode_set(mode='OBJECT')
    assert obj.data == original and linked.data == original
    spline = original.splines[0]
    points = spline.bezier_points if kind == 'BEZIER' else spline.points
    assert len(points) == 2
    close(points[0].co[:3], (-0.5, 0, 0))
    assert abs(points[0].radius - 1.5) < 1e-5
    assert addon.snapshot_splines(original)[1] == baseline, (addon.snapshot_splines(original)[1], baseline)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.ed.undo()
    bpy.ops.object.mode_set(mode='OBJECT')
    spline = bpy.context.object.data.splines[0]
    assert len(spline.bezier_points if kind == 'BEZIER' else spline.points) == 3
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.ed.redo()
    bpy.ops.object.mode_set(mode='OBJECT')
    spline = bpy.context.object.data.splines[0]
    assert len(spline.bezier_points if kind == 'BEZIER' else spline.points) == 2
print('PASS: center merge, attributes, untouched NURBS, linked datablock, undo and redo')

# Exercise Blender's real active edit point; no injected active indices.
for kind in ('BEZIER', 'POLY'):
    clean()
    obj = create_curve(kind)
    points = obj.data.splines[0].bezier_points if kind == 'BEZIER' else obj.data.splines[0].points
    for i, point in enumerate(points):
        if kind == 'BEZIER':
            point.select_control_point = i == 2
        else:
            point.select = i == 2
    obj.location = (2, 3, 4)
    obj.scale = (2, 1, 1)
    bpy.ops.object.mode_set(mode='EDIT')
    cursor = bpy.context.scene.cursor.location.copy()
    assert bpy.ops.curve.vertex_add(location=(2, 5, 4)) == {'FINISHED'}
    destination = addon.active_point_position(bpy.context)
    assert destination is not None
    bpy.ops.curve.select_all(action='SELECT')
    assert bpy.ops.curve.merge_selected_points(merge_type='ACTIVE') == {'FINISHED'}
    assert bpy.context.scene.cursor.location == cursor
    bpy.ops.object.mode_set(mode='OBJECT')
    spline = obj.data.splines[0]
    points = spline.bezier_points if kind == 'BEZIER' else spline.points
    assert len(points) == 1
    close(obj.matrix_world @ Vector(points[0].co[:3]), destination)
print('PASS: active merge uses Blender native active point and object transforms, cursor unchanged')

clean()
obj = create_curve()
for i, point in enumerate(obj.data.splines[0].bezier_points):
    point.select_control_point = i == 2
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.curve.vertex_add(location=(0, 0, 0))
bpy.ops.curve.select_all(action='SELECT')
for i, point in enumerate(obj.data.splines[0].bezier_points):
    point.co = (0, 0, 0)
    point.radius = i + 1
baseline = addon.snapshot(obj.data.splines[0])
active = addon.active_point_indices(bpy.context)
assert active is not None
assert addon.snapshot(obj.data.splines[0]) == baseline
expected_radius = baseline[active[1]]['radius']
assert bpy.ops.curve.merge_selected_points(merge_type='ACTIVE') == {'FINISHED'}
bpy.ops.object.mode_set(mode='OBJECT')
assert len(obj.data.splines[0].bezier_points) == 1
assert obj.data.splines[0].bezier_points[0].radius == expected_radius
print('PASS: overlapping points retain the actual active point attributes, active lookup preserves selection')

for kind in ('BEZIER', 'POLY'):
    clean()
    obj = create_curve(kind)
    first = obj.data.splines[0]
    points = first.bezier_points if kind == 'BEZIER' else first.points
    for i, point in enumerate(points):
        if kind == 'BEZIER':
            point.select_control_point = i == 2
        else:
            point.select = i == 2
    second = obj.data.splines.new(kind)
    points = second.bezier_points if kind == 'BEZIER' else second.points
    points.add(1)
    for i, point in enumerate(points):
        if kind == 'BEZIER':
            point.co = (2, 1 + i, 0)
            point.handle_left_type = point.handle_right_type = 'VECTOR'
            point.select_control_point = i == 0
        else:
            point.co = (2, 1 + i, 0, 1)
            point.select = i == 0
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.ops.curve.merge_selected_points(merge_type='CENTER') == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    assert len(obj.data.splines) == 1
    spline = obj.data.splines[0]
    points = spline.bezier_points if kind == 'BEZIER' else spline.points
    assert len(points) == 4
    close(points[2].co[:3], (1, 1, 0))
print('PASS: merging endpoints joins two splines into one')

clean()
obj = create_curve()
baseline = addon.snapshot_splines(obj.data)
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.merge_selected_points(merge_type='CENTER') == {'CANCELLED'}
assert bpy.ops.curve.merge_selected_points(merge_type='ACTIVE') == {'CANCELLED'}
assert bpy.context.mode == 'EDIT_CURVE'
bpy.ops.object.mode_set(mode='OBJECT')
assert addon.snapshot_splines(obj.data) == baseline
print('PASS: invalid merge selection cancels without changing geometry')

addon.unregister()
addon.register()
addon.unregister()
print('ALL BLENDER INTEGRATION TESTS PASSED')
