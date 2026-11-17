"""Run with Blender --background --factory-startup --python this_file.py."""
import importlib.util
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('curve_forge_slide_test', root / '__init__.py',
                                            submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()


def clean():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def curve(kind='BEZIER', cyclic=False, curved=False):
    data = bpy.data.curves.new('Slide curve', 'CURVE')
    data.dimensions = '3D'
    spline = data.splines.new(kind)
    points = spline.bezier_points if kind == 'BEZIER' else spline.points
    coordinates = [(-2, 0, 0), (0, 0, 0), (0, 2, 0)]
    if cyclic:
        coordinates = [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]
    if curved:
        coordinates[2] = (2, 0, 0)
    points.add(len(coordinates) - 1)
    for i, (point, co) in enumerate(zip(points, coordinates)):
        point.co = co if kind == 'BEZIER' else (*co, 1)
        if kind == 'BEZIER':
            point.handle_left_type = point.handle_right_type = 'FREE'
            point.handle_left = Vector(co) + Vector((-0.25, 0, 0))
            point.handle_right = Vector(co) + Vector((0.25, 0, 0))
            if not curved:
                point.handle_left_type = point.handle_right_type = 'VECTOR'
            point.select_control_point = i == (0 if cyclic else 1)
            point.select_left_handle = point.select_right_handle = False
        else:
            point.select = i == (0 if cyclic else 1)
        point.radius, point.tilt = i + 1, i * 0.1
    if curved:
        points[1].handle_right = (0, 2, 0)
        points[2].handle_left = (2, 2, 0)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new('Slide object', data)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


for kind in ('BEZIER', 'POLY'):
    for factor, expected in ((0.5, (0, 1, 0)), (-0.5, (-1, 0, 0)), (2, (0, 2, 0))):
        clean()
        obj = curve(kind)
        original = obj.data
        baseline = addon.snapshot(original.splines[0])
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.ed.undo_push(message='Before slide')
        assert bpy.ops.curve.slide_points(factor=factor) == {'FINISHED'}
        bpy.ops.ed.undo_push(message='After slide')
        assert bpy.context.mode == 'EDIT_CURVE' and obj.data == original
        values = addon.snapshot(original.splines[0])
        assert len(values) == 3 and (Vector(values[1]['co']) - Vector(expected)).length < 1e-5
        for name in ('radius', 'tilt', 'weight_softbody', 'selected', 'hide', 'co_weight'):
            assert values[1][name] == baseline[1][name]
        bpy.ops.ed.undo()
        obj = bpy.context.object
        assert addon.snapshot(obj.data.splines[0]) == baseline
        bpy.ops.ed.redo()
        obj = bpy.context.object
        assert (Vector(addon.snapshot(obj.data.splines[0])[1]['co']) - Vector(expected)).length < 1e-5
print('PASS: Bezier/poly slide in both directions, clamp, unchanged topology/attributes, undo and redo')

clean()
obj = curve(curved=True)
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.slide_points(factor=0.5) == {'FINISHED'}
assert (Vector(addon.snapshot(obj.data.splines[0])[1]['co']) - Vector((1, 1.5, 0))).length < 1e-5
print('PASS: curved Bezier follows the original cubic rather than its chord')

clean()
obj = curve('POLY', cyclic=True)
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.slide_points(factor=-0.5) == {'FINISHED'}
assert (Vector(addon.snapshot(obj.data.splines[0])[0]['co']) - Vector((0, 1, 0))).length < 1e-5
assert obj.data.splines[0].use_cyclic_u
print('PASS: cyclic slide wraps across the last-to-first segment')

clean()
first = curve('POLY')
first.scale = (2, 3, 1)
second = curve('BEZIER')
second.location = (4, 0, 0)
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.grab_or_slide(offset=(2, 3, 0)) == {'FINISHED'}
assert (Vector(addon.snapshot(first.data.splines[0])[1]['co']) - Vector((1, 1, 0))).length < 1e-5
assert (Vector(addon.snapshot(second.data.splines[0])[1]['co']) - Vector((2, 3, 0))).length < 1e-5
bpy.ops.object.mode_set(mode='OBJECT')
clean()
obj = curve('POLY')
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.slide_points(factor=2, use_clamp=False) == {'FINISHED'}
assert (Vector(addon.snapshot(obj.data.splines[0])[1]['co']) - Vector((0, 4, 0))).length < 1e-5
print('PASS: multi-object free move respects object scale; unclamped slide extends the endpoint tangent')

clean()
obj = curve()
obj.data.splines[0].bezier_points[1].select_control_point = False
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.slide_points(factor=0.5) == {'CANCELLED'}
assert bpy.context.mode == 'EDIT_CURVE'
bpy.ops.object.mode_set(mode='OBJECT')
obj.data.splines[0].bezier_points[1].select_control_point = True
obj.shape_key_add(name='Basis')
bpy.ops.object.mode_set(mode='EDIT')
assert bpy.ops.curve.slide_points(factor=0.5) == {'CANCELLED'}
assert len(obj.data.splines[0].bezier_points) == 3
print('PASS: missing selection and unsupported shape-key slide cancel safely')

addon.unregister()
addon.register()
addon.unregister()
print('ALL SLIDE INTEGRATION TESTS PASSED')
