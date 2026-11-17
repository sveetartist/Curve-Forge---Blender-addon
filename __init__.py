# SPDX-License-Identifier: GPL-3.0-or-later
"""Curve Forge: mesh-edge conversion, thickness, beveling, and point merging."""

import bpy

from .bevel import BevelSession, CURVE_OT_bevel_selected_points
from .common import snapshot, write_points, active_point_position, active_point_indices, snapshot_splines
from .edge_to_curve import MESH_OT_interactive_curve_extruder
from .merge_operators import CURVE_OT_merge_selected_points, CURVE_MT_merge_points, CURVE_OT_merge_points_menu
from .slide import CURVE_OT_grab_or_slide, CURVE_OT_slide_points
from .interaction import cancel_all
from .ui import (BevelCurvePreferences, addon_keymaps,
                 draw_menu, draw_edge_menu, draw_mesh_context_menu, draw_object_context_menu,
                 update_move_shortcut)


classes = (CURVE_OT_bevel_selected_points, CURVE_OT_merge_selected_points,
           CURVE_MT_merge_points, CURVE_OT_merge_points_menu,
           CURVE_OT_grab_or_slide, CURVE_OT_slide_points,
           MESH_OT_interactive_curve_extruder, BevelCurvePreferences)
menu_hooks = (
    (bpy.types.VIEW3D_MT_edit_curve, draw_menu),
    (bpy.types.VIEW3D_MT_edit_curve_context_menu, draw_menu),
    (bpy.types.VIEW3D_MT_edit_mesh_edges, draw_edge_menu),
    (bpy.types.VIEW3D_MT_edit_mesh_context_menu, draw_mesh_context_menu),
    (bpy.types.VIEW3D_MT_object_context_menu, draw_object_context_menu),
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for menu, callback in menu_hooks:
        menu.append(callback)
    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig is not None:
        keymap = keyconfig.keymaps.new(name='Curve', space_type='EMPTY', region_type='WINDOW')
        item = keymap.keymap_items.new(CURVE_OT_bevel_selected_points.bl_idname,
                                     type='B', value='PRESS', ctrl=True)
        addon_keymaps.append((keymap, item))

        item = keymap.keymap_items.new(CURVE_OT_merge_points_menu.bl_idname, type='M', value='PRESS')
        addon_keymaps.append((keymap, item))
        item = keymap.keymap_items.new(CURVE_OT_grab_or_slide.bl_idname, type='G', value='PRESS')
        addon_keymaps.append((keymap, item))

    entry = bpy.context.preferences.addons.get(__package__)
    if entry is not None and not entry.preferences.use_move_slide:
        update_move_shortcut(entry.preferences, bpy.context)


def unregister():
    cancel_all(bpy.context)
    for keymap, item in addon_keymaps:
        keymap.keymap_items.remove(item)
    addon_keymaps.clear()
    for menu, callback in reversed(menu_hooks):
        menu.remove(callback)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
