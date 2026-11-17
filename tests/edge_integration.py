"""Run with Blender --background --factory-startup --python this_file.py."""
import importlib.util
from math import pi
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from types import MethodType, SimpleNamespace

import bmesh
import bpy

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('curve_tools_edge_test', root / '__init__.py',
                                            submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()
operator_class = addon.MESH_OT_interactive_curve_extruder
for menu, callback in addon.menu_hooks:
    assert callback in menu.draw._draw_funcs


def clean():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def session():
    operator = SimpleNamespace()
    for name in ('_remember_context', '_restore_context', '_setup_from_existing_curve',
                 '_setup_from_mesh_edges', '_remember_curve', '_restore_curve', '_remove_created',
                 '_cleanup', '_finish', '_modal', '_apply_settings', 'update_status', 'cancel'):
        setattr(operator, name, MethodType(getattr(operator_class, name), operator))
    operator._remember_context(bpy.context)
    operator._area = SimpleNamespace(tag_redraw=lambda: None)
    operator._workspace = SimpleNamespace(status_text_set=lambda text: None)
    operator.report = lambda *args: None
    return operator


def begin(operator):
    if bpy.context.object.type == 'MESH':
        operator._setup_from_mesh_edges(bpy.context, bpy.context.object)
    else:
        operator._setup_from_existing_curve(bpy.context, bpy.context.object)
    operator._remember_curve()
    operator.curve_obj.data.dimensions = '3D'
    operator.curve_obj.data.fill_mode = 'FULL'
    operator.last_mouse_x = 100
    operator.depth = operator.curve_obj.data.bevel_depth
    operator.resolution = operator.curve_obj.data.bevel_resolution
    operator.fill_caps = operator.curve_obj.data.use_fill_caps
    operator.shading = 'KEEP'
    operator.tilt_offset = 0.0
    operator.convert_to_mesh = False
    operator._last_tilt = operator._last_shading = None
    operator._numeric = ''


def event(kind, x=100, shift=False, value='PRESS'):
    return SimpleNamespace(type=kind, value=value, mouse_x=x, shift=shift)


def mesh_source():
    mesh = bpy.data.meshes.new('Source mesh')
    mesh.from_pydata([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new('Source object', mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.location = (3, 4, 5)
    obj.scale = (2, 3, 1)
    obj.modifiers.new('Subdivision', 'SUBSURF').show_viewport = True
    obj.modifiers.new('Solidify', 'SOLIDIFY').show_viewport = False
    mesh.materials.append(bpy.data.materials.new('Curve test material'))
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.index_update()
    for face in bm.faces:
        face.select_set(False)
    for edge in bm.edges:
        edge.select_set(False)
    for vertex in bm.verts:
        vertex.select_set(False)
    for edge in bm.edges:
        if {vertex.index for vertex in edge.verts} in ({0, 1}, {1, 2}):
            edge.select_set(True)
    bmesh.update_edit_mesh(mesh)
    return obj


def mesh_snapshot(obj):
    if obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(obj.data)
        return ([tuple(vertex.co) for vertex in bm.verts],
                [(tuple(tuple(vertex.co) for vertex in edge.verts), edge.select) for edge in bm.edges],
                len(bm.faces), [(mod.name, mod.show_viewport) for mod in obj.modifiers])
    return ([tuple(vertex.co) for vertex in obj.data.vertices],
            [(tuple(tuple(obj.data.vertices[i].co) for i in edge.vertices), edge.select) for edge in obj.data.edges],
            len(obj.data.polygons), [(mod.name, mod.show_viewport) for mod in obj.modifiers])


clean()
source = mesh_source()
source_data = source.data
baseline = mesh_snapshot(source)
curve_names, mesh_names = set(bpy.data.curves.keys()), set(bpy.data.meshes.keys())
operator = session()
begin(operator)
created = operator.curve_obj
assert created.type == 'CURVE' and created != source
assert source.type == 'MESH' and source.data == source_data
assert not created.modifiers
assert created.matrix_world == source.matrix_world
assert list(created.data.materials) == list(source.data.materials)
positions = [tuple(point.co[:3]) for spline in created.data.splines for point in spline.points]
assert sorted(positions) == sorted([(0, 0, 0), (2, 0, 0), (2, 2, 0)])
assert mesh_snapshot(source) == baseline
modal = operator_class.modal
modal(operator, bpy.context, event('MOUSEMOVE', x=150, value='NOTHING'))
assert abs(created.data.bevel_depth - 0.1) < 1e-6
modal(operator, bpy.context, event('MOUSEMOVE', x=175, shift=True, value='NOTHING'))
assert abs(created.data.bevel_depth - 0.11) < 1e-6
modal(operator, bpy.context, event('MOUSEMOVE', x=0, value='NOTHING'))
assert created.data.bevel_depth == 0
modal(operator, bpy.context, event('MOUSEMOVE', x=10, value='NOTHING'))
assert abs(created.data.bevel_depth - 0.02) < 1e-6
resolution = created.data.bevel_resolution
modal(operator, bpy.context, event('WHEELUPMOUSE'))
assert created.data.bevel_resolution == resolution + 1
modal(operator, bpy.context, event('F'))
assert created.data.use_fill_caps
tilt = created.data.splines[0].points[0].tilt
modal(operator, bpy.context, event('R'))
assert abs(created.data.splines[0].points[0].tilt - tilt - pi / 4) < 1e-6
assert modal(operator, bpy.context, event('ESC')) == {'CANCELLED'}
assert bpy.context.mode == 'EDIT_MESH' and bpy.context.object == source
assert mesh_snapshot(source) == baseline
assert set(bpy.data.curves.keys()) == curve_names
assert set(bpy.data.meshes.keys()) == mesh_names
print('PASS: edge conversion copies selected edges, retains transforms/materials/source/modifiers; cancel removes all generated data')

# Confirm and conversion to mesh must act on the generated object only.
for finish_key, expected_type in (('LEFTMOUSE', 'CURVE'), ('A', 'MESH')):
    operator = session()
    begin(operator)
    modal(operator, bpy.context, event('MOUSEMOVE', x=150, value='NOTHING'))
    assert modal(operator, bpy.context, event(finish_key)) == {'FINISHED'}
    assert bpy.context.mode == 'OBJECT' and bpy.context.object.type == expected_type
    assert bpy.context.object != source
    assert source.type == 'MESH' and source.data == source_data
    assert mesh_snapshot(source) == baseline
    bpy.ops.object.select_all(action='DESELECT')
    source.select_set(True)
    bpy.context.view_layer.objects.active = source
    bpy.ops.object.mode_set(mode='EDIT')
print('PASS: confirm and convert-to-mesh preserve the source object')

# Existing curves can contain different shading and both point types.
clean()
curve = bpy.data.curves.new('Existing curve', 'CURVE')
curve.dimensions = '2D'
curve.fill_mode = 'FRONT'
curve.bevel_depth = 0.12
curve.bevel_resolution = 2
for kind, smooth in (('BEZIER', False), ('POLY', True)):
    spline = curve.splines.new(kind)
    points = spline.bezier_points if kind == 'BEZIER' else spline.points
    points.add(2)
    spline.use_smooth = smooth
    for i, point in enumerate(points):
        point.co = (i, i % 2, 0) if kind == 'BEZIER' else (i, i % 2, 0, 1)
        point.tilt = i * 0.1
obj = bpy.data.objects.new('Existing object', curve)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
baseline = addon.snapshot_splines(curve)
bpy.ops.object.mode_set(mode='EDIT')
operator = session()
begin(operator)
modal(operator, bpy.context, event('R'))
modal(operator, bpy.context, event('S'))
modal(operator, bpy.context, event('F'))
modal(operator, bpy.context, event('MOUSEMOVE', x=150, value='NOTHING'))
assert abs(curve.splines[0].bezier_points[0].tilt - pi / 4) < 1e-6
assert modal(operator, bpy.context, event('RIGHTMOUSE')) == {'CANCELLED'}
assert bpy.context.mode == 'EDIT_CURVE' and bpy.context.object == obj
bpy.ops.object.mode_set(mode='OBJECT')
assert curve.dimensions == '2D' and curve.fill_mode == 'FRONT'
assert abs(curve.bevel_depth - 0.12) < 1e-6 and curve.bevel_resolution == 2
assert not curve.use_fill_caps
assert addon.snapshot_splines(curve) == baseline
print('PASS: existing-curve cancel restores tilt, per-spline shading, dimensions, fill, thickness, caps, and edit mode')

addon.unregister()
for menu, callback in addon.menu_hooks:
    assert callback not in menu.draw._draw_funcs
addon.register()
addon.unregister()
print('ALL EDGE INTEGRATION TESTS PASSED')
