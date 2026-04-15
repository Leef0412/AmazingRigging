import bpy
from bpy.types import Operator

class AMAZING_RIGGING_OT_clean_deform(Operator):
    bl_idname = "armature.amazing_rigging_clean_deform"
    bl_label = "Clean Defrom"
    bl_description = "set 'DEF-' & 'Root' Bones turn on deform, all bones turn off deform"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select an armature object")
            return {'CANCELLED'}

        armature = obj.data
        bones = armature.edit_bones if obj.mode == 'EDIT' else armature.bones

        if not bones:
            self.report({'ERROR'}, "No bones found in this armature")
            return {'CANCELLED'}

        enabled_count = 0
        disabled_count = 0

        for bone in bones:
            should_deform = bone.name.startswith('DEF-') or bone.name == "Root"

            bone.use_deform = should_deform

            if should_deform:
                enabled_count += 1
            else:
                disabled_count += 1

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Clean Deform: {enabled_count} bones enabled, {disabled_count} bones disabled")

        return {'FINISHED'}

class AMAZING_RIGGING_OT_goto_weight_paint(Operator):
    bl_idname = "armature.amazing_rigging_goto_weight_paint"
    bl_label = "Weight Paint Mode"
    bl_description = "Switch to Weight Paint Mode (requires selected armature and mesh)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import ui_panel
        cached_armature = ui_panel._last_pose_armature

        if not cached_armature:
            obj = context.active_object
            if obj and obj.type == 'ARMATURE':
                cached_armature = obj
            else:
                self.report({'ERROR'}, "Please enter Pose Mode first to select an armature")
                return {'CANCELLED'}

        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_meshes:
            self.report({'ERROR'}, "Please select at least one mesh object")
            return {'CANCELLED'}

        target_mesh = selected_meshes[0]

        context.view_layer.objects.active = target_mesh

        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Switch to Weight Paint mode for '{target_mesh.name}")

        return {'FINISHED'}

class AMAZING_RIGGING_OT_goto_pose(Operator):
    bl_idname = "armature.amazing_rigging_goto_pose"
    bl_label = "Pose Mode"
    bl_description = "Current Mode must be Weight Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        active_obj = context.active_object

        if not active_obj or active_obj.mode != 'WEIGHT_PAINT':
            self.report({'ERROR'}, "Must be in Weight Paint mode")
            return {'CANCELLED'}

        armature_obj = None
        for modifier in active_obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object:
                armature_obj = modifier.object
                break

        if not armature_obj:
            for obj in context.selected_objects:
                if obj.type == 'ARMATURE':
                    armature_obj = obj
                    break
        if not armature_obj:
            self.report({'ERROR'}, "No associated armature found")
            return {'CANCELLED'}

        context.view_layer.objects.active = armature_obj

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Switch to Pose mode for '{armature_obj.name}'")

        return {'FINISHED'}

class AMAZING_RIGGING_OT_clean_transform(Operator):
    bl_idname = "armature.amazing_rigging_ot_clean_transform"
    bl_label = "Clean Transform"
    bl_description = "Clean All bones transform"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import ui_panel
        cached_armature = ui_panel._last_pose_armature

        obj = context.active_object
        target_obj = None

        if obj and obj.type == 'ARMATURE':
            target_obj = obj
        elif cached_armature:
            target_obj = cached_armature
        else:
            self.report({'ERROR'}, "Please selected an armature object or enter Pose Mode first")
            return {'CANCELLED'}

        if target_obj.mode != 'POSE':
            self.report({'ERROR'}, "Armature must be in Pose Mode")
            return {'CANCELLED'}

        pose_bones = target_obj.pose.bones

        if not pose_bones:
            self.report({'ERROR'}, "No pose bones found in this armature")
            return {'CANCELLED'}

        cleaned_count = 0

        for bone in pose_bones:
            bone.location = (0.0, 0.0, 0.0)
            bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            bone.rotation_euler = (0.0, 0.0, 0.0)
            bone.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)
            bone.scale = (1.0, 1.0, 1.0)
            cleaned_count += 1

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Clean Transform: {cleaned_count} bones cleared")

        return {'FINISHED'}

class AMAZING_RIGGING_OT_show_all_deform_bones(Operator):
    bl_idname = "armature.amazing_rigging_show_all_deform_bones"
    bl_label = "Show All Deform Bones"
    bl_description = "Show All Deform Bones"
    bl_options = {'REGISTER', 'UNDO'}

class AMAZING_RIGGING_OT_hide_all_deform_bones(Operator):
    bl_idname = "armature.amazing_rigging_hide_all_deform_bones"
    bl_label = "Hide All Deform Bones"
    bl_description = "Hide All Deform Bones"
    bl_options = {'REGISTER', 'UNDO'}

class AMAZING_RIGGING_OT_show_all_ctrl_bones(Operator):
    bl_idname = "armature.amazing_rigging_show_all_ctrl_bones"
    bl_label = "Show All Ctrl Bones"
    bl_description = "Show All Ctrl Bones"
    bl_options = {'REGISTER', 'UNDO'}

class AMAZING_RIGGING_OT_hide_all_ctrl_bones(Operator):
    bl_idname = "armature.amazing_rigging_hide_all_ctrl_bones"
    bl_label = "Hide All Ctrl Bones"
    bl_description = "Hide All Ctrl Bones"
    bl_options = {'REGISTER', 'UNDO'}

class AMAZING_RIGGING_OT_export_ue(Operator):
    bl_idname = "armature.amazing_rigging_ot_export_ue"
    bl_label = "Export to UE"
    bl_description = "Export to UE, Only save deform bones"
    bl_options = {'REGISTER', 'UNDO'}

classes = [
    AMAZING_RIGGING_OT_clean_deform,
    AMAZING_RIGGING_OT_goto_weight_paint,
    AMAZING_RIGGING_OT_goto_pose,
    AMAZING_RIGGING_OT_clean_transform,
    AMAZING_RIGGING_OT_export_ue,
]