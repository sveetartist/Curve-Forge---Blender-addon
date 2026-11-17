# SPDX-License-Identifier: GPL-3.0-or-later
"""Edge to Curve by ArtVit, integrated with Curve Forge."""

from math import pi

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty

from .interaction import ModalFeedback, close_feedback, edit_numeric, numeric_value


def curve_points(spline):
    return spline.bezier_points if spline.type == 'BEZIER' else spline.points


class MESH_OT_interactive_curve_extruder(bpy.types.Operator):
    # Keep the original operator ID for existing shortcuts.
    bl_idname = "mesh.interactive_curve_extruder"
    bl_label = "Edge to Thick Curve"
    bl_description = "Copy selected mesh edges to a curve, or adjust an existing curve's thickness"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    depth: FloatProperty(name="Depth (Local Units)", description="Profile radius in local curve units", default=0.0, min=0.0)
    resolution: IntProperty(name="Resolution", default=4, min=0, max=32)
    fill_caps: BoolProperty(name="Fill Caps", default=False)
    shading: EnumProperty(name="Shading", items=(
        ('KEEP', "Keep Original", "Preserve each spline's original shading"),
        ('SMOOTH', "Smooth", "Smooth every spline"),
        ('FLAT', "Flat", "Use flat shading on every spline")), default='KEEP')
    tilt_offset: FloatProperty(name="Tilt Offset", subtype='ANGLE', default=0.0)
    convert_to_mesh: BoolProperty(name="Convert to Mesh", default=False)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        operator = context.active_operator
        # Redo UI checks poll against the *result*, before undo restores the
        # source. Keep F9 usable after this operator has converted its result.
        mesh_result = (obj is not None and obj.type == 'MESH' and context.mode == 'OBJECT'
                       and operator is not None and operator.bl_idname == 'MESH_OT_interactive_curve_extruder')
        return obj is not None and (
            obj.type == 'MESH' and context.mode == 'EDIT_MESH'
            or obj.type == 'CURVE' and context.mode in {'OBJECT', 'EDIT_CURVE'} or mesh_result)

    def _remember_context(self, context):
        self.original_active = context.active_object
        self.original_selection = list(context.selected_objects)
        self.original_edit_objects = list(context.objects_in_mode) if context.mode != 'OBJECT' else []
        self.original_mode = context.mode
        self.curve_obj = None
        self.is_new_curve = False
        self.closed = False
        self._feedback = None
        self.initial_settings = None

    def _restore_context(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        selection = self.original_edit_objects if self.original_mode != 'OBJECT' else self.original_selection
        for obj in selection:
            obj.select_set(True)
        context.view_layer.objects.active = self.original_active
        if self.original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='EDIT')
        for obj in self.original_selection:
            obj.select_set(True)

    def _setup_from_existing_curve(self, context, obj):
        self.curve_obj = obj
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj

    def _setup_from_mesh_edges(self, context, obj):
        """Copy only edge coordinates; never edit the source mesh or modifiers."""
        bm = bmesh.from_edit_mesh(obj.data)
        edges = [edge for edge in bm.edges if edge.select and not edge.hide]
        if not edges:
            raise ValueError("Select at least one visible mesh edge")
        vertices = {}
        coordinates = []
        edge_indices = []
        for edge in edges:
            indices = []
            for vertex in edge.verts:
                if vertex not in vertices:
                    vertices[vertex] = len(coordinates)
                    coordinates.append(tuple(vertex.co))
                indices.append(vertices[vertex])
            edge_indices.append(tuple(indices))
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh = bpy.data.meshes.new(f"{obj.name} Edges")
        mesh_name = mesh.name
        try:
            mesh.from_pydata(coordinates, edge_indices, [])
            mesh.update()
            for material in obj.data.materials:
                mesh.materials.append(material)
            copied = bpy.data.objects.new(f"{obj.name} Curve", mesh)
            self.curve_obj = copied
            self.is_new_curve = True
            (obj.users_collection[0] if obj.users_collection else context.collection).objects.link(copied)
            copied.matrix_world = obj.matrix_world.copy()
            bpy.ops.object.select_all(action='DESELECT')
            copied.select_set(True)
            context.view_layer.objects.active = copied
            if bpy.ops.object.convert(target='CURVE') != {'FINISHED'}:
                raise ValueError("Selected edges could not be converted to a curve")
            self.curve_obj = context.active_object
            if self.curve_obj.type != 'CURVE':
                raise ValueError("Selected edges could not be converted to a curve")
            # Conversion of a mesh with only edges can discard material slots.
            self.curve_obj.data.materials.clear()
            for material in obj.data.materials:
                self.curve_obj.data.materials.append(material)
        finally:
            unused = bpy.data.meshes.get(mesh_name)
            if unused is not None and unused.users == 0:
                bpy.data.meshes.remove(unused)

    def _remember_curve(self):
        curve = self.curve_obj.data
        self.initial_settings = {name: getattr(curve, name) for name in (
            'dimensions', 'fill_mode', 'bevel_depth', 'bevel_resolution', 'use_fill_caps')}
        self.initial_splines = [(spline.use_smooth, [point.tilt for point in curve_points(spline)])
                                for spline in curve.splines]
        self.is_smooth = all(spline.use_smooth for spline in curve.splines)

    def _restore_curve(self):
        if self.initial_settings is None:
            return
        curve = self.curve_obj.data
        for name, value in self.initial_settings.items():
            setattr(curve, name, value)
        for spline, (smooth, tilts) in zip(curve.splines, self.initial_splines):
            spline.use_smooth = smooth
            for point, tilt in zip(curve_points(spline), tilts):
                point.tilt = tilt

    def _remove_created(self):
        if self.curve_obj is None:
            return
        data = self.curve_obj.data
        bpy.data.objects.remove(self.curve_obj, do_unlink=True)
        self.curve_obj = None
        if data.users == 0:
            if isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)
            elif isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)

    def _cleanup(self):
        close_feedback(self)

    def cancel(self, context):
        if self.closed:
            return
        try:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            if self.is_new_curve:
                self._remove_created()
            elif self.curve_obj is not None:
                self._restore_curve()
        finally:
            try:
                self._restore_context(context)
            finally:
                self.closed = True
                self._cleanup()

    def _finish(self, context, as_mesh=False):
        self.convert_to_mesh = self.convert_to_mesh or as_mesh
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        self.curve_obj.select_set(True)
        context.view_layer.objects.active = self.curve_obj
        if self.convert_to_mesh:
            curve = self.curve_obj.data
            if bpy.ops.object.convert(target='MESH') != {'FINISHED'}:
                raise ValueError("Curve could not be converted to a mesh")
            self.curve_obj = context.active_object
            if curve.users == 0:
                bpy.data.curves.remove(curve)
        self.closed = True
        self._cleanup()
        return {'FINISHED'}

    def update_status(self, context):
        curve = self.curve_obj.data
        self._workspace.status_text_set(
            "Drag: thickness | Type: local units | Shift: precision | Wheel: resolution | S: shading | F: caps | "
            "R: tilt 45 degrees | A: mesh | LMB/Enter: confirm | Esc/RMB: cancel")
        self._area.tag_redraw()
        if self._feedback is not None:
            value = self._numeric or f"{self.depth:.5g}"
            shading = 'Original shading' if self.shading == 'KEEP' else self.shading.title()
            self._area.header_text_set(
                f"Curve Thickness | Depth: {value} (local units) | Resolution: {self.resolution} | "
                f"Caps: {'On' if self.fill_caps else 'Off'} | {shading} | "
                f"Tilt: {self.tilt_offset * 180 / pi:.1f} degrees")


    def _begin(self, context, initialize=False):
        # Reacquire source RNA on every execute: undo/F9 invalidates old pointers.
        self._remember_context(context)
        if self.original_active.type == 'MESH':
            self._setup_from_mesh_edges(context, self.original_active)
        else:
            self._setup_from_existing_curve(context, self.original_active)
        self._remember_curve()
        for name, source in (('depth', 'bevel_depth'), ('resolution', 'bevel_resolution'),
                             ('fill_caps', 'use_fill_caps')):
            if initialize or not self.properties.is_property_set(name):
                setattr(self, name, self.initial_settings[source])
        if initialize:
            self.shading = 'KEEP'
            self.tilt_offset = 0.0
            self.convert_to_mesh = False
        self._last_tilt = self._last_shading = None
        self._numeric = ''
        self._apply_settings()

    def _apply_settings(self):
        curve = self.curve_obj.data
        curve.dimensions = '3D'
        curve.fill_mode = 'FULL'
        curve.bevel_depth = self.depth
        curve.bevel_resolution = self.resolution
        curve.use_fill_caps = self.fill_caps
        if self._last_tilt != self.tilt_offset or self._last_shading != self.shading:
            for spline, (smooth, tilts) in zip(curve.splines, self.initial_splines):
                spline.use_smooth = smooth if self.shading == 'KEEP' else self.shading == 'SMOOTH'
                if self._last_tilt != self.tilt_offset:
                    for point, tilt in zip(curve_points(spline), tilts):
                        point.tilt = tilt + self.tilt_offset
            self._last_tilt, self._last_shading = self.tilt_offset, self.shading
        self.is_smooth = all(spline.use_smooth for spline in curve.splines)
        curve.update_tag()

    def execute(self, context):
        if not self.poll(context):
            return {'CANCELLED'}
        if context.active_object.type == 'MESH' and context.mode != 'EDIT_MESH':
            self.report({'WARNING'}, "Select mesh edges in Edit Mode, or use F9 to adjust the last result")
            return {'CANCELLED'}
        try:
            self._begin(context)
            return self._finish(context)
        except Exception as exc:
            self.cancel(context)
            self.report({'WARNING'}, f"Curve thickness failed: {exc}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        if context.area is None or context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "Run this tool in the 3D viewport")
            return {'CANCELLED'}
        if not self.poll(context):
            return {'CANCELLED'}
        if context.active_object.type == 'MESH' and context.mode == 'OBJECT':
            bpy.ops.screen.redo_last('INVOKE_DEFAULT')
            return {'CANCELLED'}
        try:
            self._begin(context, initialize=True)
            self._area, self._workspace = context.area, context.workspace
            self.last_mouse_x = event.mouse_x
            self._feedback = ModalFeedback(context)
            self._feedback.on_cancel = self.cancel
            self.update_status(context)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        except Exception as exc:
            self.cancel(context)
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if self.closed:
            return {'CANCELLED'}
        try:
            return self._modal(context, event)
        except Exception as exc:
            self.cancel(context)
            self.report({'WARNING'}, f"Curve thickness preview failed: {exc}")
            return {'CANCELLED'}

    def _modal(self, context, event):
        if event.value == 'PRESS':
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                self.cancel(context)
                return {'CANCELLED'}
            if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'}:
                return self._finish(context)
            if event.type == 'A':
                return self._finish(context, as_mesh=True)
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            delta = event.mouse_x - self.last_mouse_x
            self.last_mouse_x = event.mouse_x
            if not self._numeric:
                self.depth = max(0.0, self.depth + delta * (0.0004 if event.shift else 0.002))
        elif event.value == 'PRESS':
            edited = edit_numeric(self._numeric, event)
            if edited is not None:
                self._numeric = edited
                if edited:
                    self.depth = numeric_value(edited)
            elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                self.resolution = max(0, min(32, self.resolution + (1 if event.type == 'WHEELUPMOUSE' else -1)))
            elif event.type == 'S':
                self.is_smooth = not self.is_smooth
                self.shading = 'SMOOTH' if self.is_smooth else 'FLAT'
            elif event.type == 'F':
                self.fill_caps = not self.fill_caps
            elif event.type == 'R':
                self.tilt_offset += pi / 4.0
            else:
                return {'RUNNING_MODAL'}
        else:
            return {'RUNNING_MODAL'}
        self._apply_settings()
        self.update_status(context)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        for name in ('depth', 'resolution', 'fill_caps', 'shading', 'tilt_offset', 'convert_to_mesh'):
            self.layout.prop(self, name)
