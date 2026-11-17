# SPDX-License-Identifier: GPL-3.0-or-later
"""Menus and shortcut preferences."""

import bpy
from bpy.props import BoolProperty

from .bevel import CURVE_OT_bevel_selected_points
from .merge_operators import CURVE_MT_merge_points
from .edge_to_curve import MESH_OT_interactive_curve_extruder
from .slide import CURVE_OT_slide_points

addon_keymaps = []
MOVE_OPERATOR = 'curve.grab_or_slide'


def effective_binding(context, operator_id):
    """Find the user override for our owned entry, including inactive entries."""
    owned = next(((km, item) for km, item in addon_keymaps if item.idname == operator_id), None)
    if owned is None:
        return None, None
    keymap, item = owned
    user = context.window_manager.keyconfigs.user
    user_keymap = user.keymaps.get(keymap.name) if user else None
    if user_keymap:
        user_item = user_keymap.keymap_items.from_id(item.id)
        if user_item is None or user_item.idname != operator_id:
            user_item = next((entry for entry in user_keymap.keymap_items if entry.idname == operator_id), None)
        if user_item:
            return user_keymap, user_item
    return keymap, item


def shortcut_label(context, operator_id):
    _, item = effective_binding(context, operator_id)
    if item is None or not item.active or item.type == 'NONE':
        return "Unassigned"
    return item.to_string()


def update_move_shortcut(self, context):
    _, effective = effective_binding(context, MOVE_OPERATOR)
    for _, item in addon_keymaps:
        if item.idname == MOVE_OPERATOR:
            item.active = self.use_move_slide
    if effective is not None:
        effective.active = self.use_move_slide
    context.window_manager.keyconfigs.update()
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {'VIEW_3D', 'PREFERENCES'}:
                area.tag_redraw()


class BevelCurvePreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    use_move_slide: BoolProperty(
        name="Use Curve Forge Move / Slide shortcut",
        description="Enable the custom move binding and repeated-key slide; disable to use Blender's native move",
        default=True, update=update_move_shortcut)

    def draw(self, context):
        import rna_keymap_ui
        layout = self.layout
        layout.prop(self, "use_move_slide")
        layout.label(text="Curve Edit Mode shortcuts")
        user = context.window_manager.keyconfigs.user
        for keymap, item in addon_keymaps:
            shown_keymap, shown_item = effective_binding(context, item.idname)
            layout.context_pointer_set("keymap", shown_keymap)
            rna_keymap_ui.draw_kmi([], user, shown_keymap, shown_item, layout, 0)
        layout.label(text="Click a shortcut to change it; expand its row for modifiers.")


def draw_menu(self, context):
    if CURVE_OT_bevel_selected_points.poll(context):
        self.layout.separator()
        self.layout.operator_context = 'INVOKE_REGION_WIN'
        self.layout.operator(CURVE_OT_bevel_selected_points.bl_idname, icon='MOD_BEVEL')
        self.layout.menu(CURVE_MT_merge_points.bl_idname)
        self.layout.operator(CURVE_OT_slide_points.bl_idname)
        self.layout.operator(MESH_OT_interactive_curve_extruder.bl_idname,
                             text="Adjust Curve Thickness", icon='CURVE_DATA')


def draw_edge_menu(self, context):
    if MESH_OT_interactive_curve_extruder.poll(context):
        self.layout.separator()
        self.layout.operator_context = 'INVOKE_DEFAULT'
        self.layout.operator(MESH_OT_interactive_curve_extruder.bl_idname, icon='CURVE_DATA')


def draw_mesh_context_menu(self, context):
    if context.tool_settings.mesh_select_mode[1]:
        draw_edge_menu(self, context)


def draw_object_context_menu(self, context):
    if context.active_object and context.active_object.type == 'CURVE' and MESH_OT_interactive_curve_extruder.poll(context):
        self.layout.separator()
        self.layout.operator_context = 'INVOKE_DEFAULT'
        self.layout.operator(MESH_OT_interactive_curve_extruder.bl_idname,
                             text="Adjust Curve Thickness", icon='CURVE_DATA')
