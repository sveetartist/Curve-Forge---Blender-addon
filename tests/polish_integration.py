"""Blender --background --factory-startup --python-exit-code 1 --python this_file.py."""
import importlib.util
from math import pi
from pathlib import Path
import sys

import bpy

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('curve_forge_polish_test', root / '__init__.py',
                                            submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def mesh_source():
    mesh = bpy.data.meshes.new('Polish source')
    mesh.from_pydata([(0, 0, 0), (2, 0, 0), (2, 2, 0)], [(0, 1), (1, 2)], [])
    obj = bpy.data.objects.new('Polish source', mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    return obj


clean()
source = mesh_source()
source_name = source.name
bpy.ops.ed.undo_push(message='Before thickness')
curve_count, object_count = len(bpy.data.curves), len(bpy.data.objects)
assert bpy.ops.mesh.interactive_curve_extruder(depth=0.2, resolution=3, fill_caps=True,
                                             shading='SMOOTH', tilt_offset=pi / 4) == {'FINISHED'}
result = bpy.context.object
assert result.type == 'CURVE' and result.name != source_name
assert abs(result.data.bevel_depth - 0.2) < 1e-6
assert result.data.bevel_resolution == 3 and result.data.use_fill_caps
assert all(s.use_smooth for s in result.data.splines)
assert abs(result.data.splines[0].points[0].tilt - pi / 4) < 1e-6
bpy.ops.ed.undo_push(message='After thickness')
bpy.ops.ed.undo()
assert bpy.context.mode == 'EDIT_MESH' and bpy.context.object.name == source_name
assert len(bpy.data.objects) == object_count and len(bpy.data.curves) == curve_count
bpy.ops.ed.redo()
assert bpy.context.object.type == 'CURVE'
assert abs(bpy.context.object.data.bevel_depth - 0.2) < 1e-6
bpy.ops.ed.undo()
# Same restored source that Blender supplies when changing the redo panel.
assert bpy.ops.mesh.interactive_curve_extruder(depth=0.35, resolution=1, tilt_offset=pi / 2) == {'FINISHED'}
assert len(bpy.data.objects) == object_count + 1 and len(bpy.data.curves) == curve_count + 1
assert abs(bpy.context.object.data.splines[0].points[0].tilt - pi / 2) < 1e-6
assert abs(bpy.context.object.data.bevel_depth - 0.35) < 1e-6
print('PASS: thickness execute, undo/redo, changed settings from restored mesh source, no duplicate objects or accumulated tilt')

clean()
source = mesh_source()
source_name = source.name
curve_count = len(bpy.data.curves)
bpy.ops.ed.undo_push(message='Before mesh output')
assert bpy.ops.mesh.interactive_curve_extruder(depth=0.1, convert_to_mesh=True) == {'FINISHED'}
assert bpy.context.object.type == 'MESH' and bpy.context.object.name != source_name
assert len(bpy.data.curves) == curve_count
bpy.ops.ed.undo_push(message='After mesh output')
bpy.ops.ed.undo()
assert bpy.context.mode == 'EDIT_MESH' and bpy.context.object.name == source_name
assert bpy.ops.mesh.interactive_curve_extruder(depth=0.3, convert_to_mesh=False) == {'FINISHED'}
assert bpy.context.object.type == 'CURVE'
assert len(bpy.data.curves) == curve_count + 1
print('PASS: mesh output cleans unused curve data, undo restores source, output can change back to curve')

clean()
data = bpy.data.curves.new('Mixed shading', 'CURVE')
data.bevel_depth, data.bevel_resolution = 0.12, 2
for kind, smooth in (('BEZIER', False), ('POLY', True)):
    spline = data.splines.new(kind)
    spline.use_smooth = smooth
    points = spline.bezier_points if kind == 'BEZIER' else spline.points
    points.add(1)
    for index, point in enumerate(points):
        point.co = (index, 0, 0) if kind == 'BEZIER' else (index, 0, 0, 1)
        point.tilt = 0.1 * index
obj = bpy.data.objects.new('Existing polish curve', data)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.ed.undo_push(message='Before existing thickness')
assert bpy.ops.mesh.interactive_curve_extruder(tilt_offset=pi / 4) == {'FINISHED'}
assert abs(data.bevel_depth - 0.12) < 1e-6 and data.bevel_resolution == 2
assert [s.use_smooth for s in data.splines] == [False, True]
bpy.ops.ed.undo_push(message='After existing thickness')
bpy.ops.ed.undo()
assert bpy.context.mode == 'EDIT_CURVE'
assert bpy.ops.mesh.interactive_curve_extruder(depth=0.5, tilt_offset=pi / 2) == {'FINISHED'}
data = bpy.context.object.data
for spline in data.splines:
    points = spline.bezier_points if spline.type == 'BEZIER' else spline.points
    for index, point in enumerate(points):
        assert abs(point.tilt - (0.1 * index + pi / 2)) < 1e-6
assert [s.use_smooth for s in data.splines] == [False, True]
print('PASS: existing-curve replay preserves mixed shading and unspecified settings; tilt is relative to original points')

addon.unregister()
print('ALL POLISH INTEGRATION TESTS PASSED')
