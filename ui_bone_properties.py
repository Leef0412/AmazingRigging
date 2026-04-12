import bpy
from bpy.types import Panel, Operator, PropertyGroup, Menu
from bpy.props import StringProperty, PointerProperty
from . import utils_bone_data


# 追踪最后同步的 bone，避免在用户编辑 UI 时覆盖
_last_synced_bone = None  # (armature_name, bone_name)

# 标志：当 armature 切换时清空 target_bone，但不触发清空 bone 数据的逻辑
_skip_bone_changed_callback = False

# 标志：当 sync_ui 正在更新 UI 时，禁止回调修改 bone 数据
_syncing_ui = False


def reset_state():
    """重置模块全局状态（文件加载或插件重新注册时调用）"""
    global _last_synced_bone, _skip_bone_changed_callback, _syncing_ui
    _last_synced_bone = None
    _skip_bone_changed_callback = False
    _syncing_ui = False


def get_active_bone_name(context, obj):
    """获取当前活跃骨骼名称（仅 Pose Mode）"""
    if not obj or obj.type != 'ARMATURE':
        return None
    if obj.mode != 'POSE':
        return None

    active_pb = getattr(context, 'active_pose_bone', None)
    if active_pb:
        return active_pb.name

    bone = getattr(context, 'bone', None)
    if bone:
        return bone.name

    selected_pbs = getattr(context, 'selected_pose_bones', [])
    if selected_pbs:
        return selected_pbs[0].name

    return None


def _get_target_pb_from_info(settings_info):
    """从 settings_info 获取主导 PoseBone 对象"""
    if not settings_info:
        return None
    arm_obj = utils_bone_data.find_armature_obj_by_uuid(settings_info['armature_uuid'])
    if not arm_obj:
        arm_data = bpy.data.armatures.get(settings_info['armature_name'])
        if arm_data:
            for obj in bpy.data.objects:
                if obj.type == 'ARMATURE' and obj.data == arm_data:
                    arm_obj = obj
                    break
    if arm_obj:
        return arm_obj.pose.bones.get(settings_info['bone_name'])
    return None


def sync_ui_to_selected_bone(scene):
    """Sync ui_state to the currently selected bone's settings.

    只在 bone 切换时同步 UI，避免覆盖用户的编辑操作。
    使用 _syncing_ui 标志防止回调在同步过程中修改 bone 数据。
    """
    import bpy
    try:
        context = bpy.context
        obj = context.active_object
    except Exception:
        return

    if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
        return

    arm_data = obj.data
    ui_state = scene.amazing_rigging_ui

    bone_name = get_active_bone_name(context, obj)

    global _last_synced_bone, _syncing_ui
    current_bone_key = (arm_data.name, bone_name) if bone_name else None

    if current_bone_key == _last_synced_bone:
        return

    _last_synced_bone = current_bone_key

    _syncing_ui = True
    try:
        if not bone_name:
            ui_state.target_armature = None
            ui_state.target_bone = ""
            return

        pose_bone = obj.pose.bones.get(bone_name)
        if not pose_bone:
            return

        settings_info = utils_bone_data.get_settings_bone_info(pose_bone)

        if settings_info:
            target_arm_obj = utils_bone_data.find_armature_obj_by_uuid(settings_info['armature_uuid'])
            if not target_arm_obj:
                for scene_obj in scene.objects:
                    if scene_obj.type == 'ARMATURE' and scene_obj.data.name == settings_info['armature_name']:
                        target_arm_obj = scene_obj
                        break

            ui_state.target_armature = target_arm_obj
            ui_state.target_bone = settings_info['bone_name']
        else:
            ui_state.target_armature = None
            ui_state.target_bone = ""
    finally:
        _syncing_ui = False


# ── Scene Properties for UI state ──

def _on_target_armature_changed(self, context):
    """When target armature changes, clear the bone selection"""
    global _syncing_ui, _skip_bone_changed_callback

    if _syncing_ui:
        return

    obj = context.active_object
    if not obj or obj.type != 'ARMATURE':
        return

    ui_state = context.scene.amazing_rigging_ui

    _skip_bone_changed_callback = True
    try:
        ui_state.target_bone = ""
    finally:
        _skip_bone_changed_callback = False

    for area in context.screen.areas:
        area.tag_redraw()


def _on_target_bone_changed(self, context):
    """When target bone changes, apply or clear the setting"""
    global _skip_bone_changed_callback, _syncing_ui

    if _syncing_ui:
        return

    if _skip_bone_changed_callback:
        return

    obj = context.active_object
    if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
        return

    bone_name = get_active_bone_name(context, obj)
    if not bone_name:
        return

    pose_bone = obj.pose.bones.get(bone_name)
    if not pose_bone:
        return

    arm_obj = context.scene.amazing_rigging_ui.target_armature
    if not arm_obj or arm_obj.type != 'ARMATURE':
        return

    # 防止骨骼引用自身作为 settings bone
    if (obj.data == arm_obj.data and obj.name == arm_obj.name and
        bone_name == ui_state.target_bone):
        return

    ui_state = context.scene.amazing_rigging_ui

    if ui_state.target_bone:
        target_pb = arm_obj.pose.bones.get(ui_state.target_bone)
        if target_pb:
            current_info = utils_bone_data.get_settings_bone_info(pose_bone)
            if current_info:
                current_target_pb = _get_target_pb_from_info(current_info)
                utils_bone_data.clear_settings_bone(pose_bone, target_bone_info=current_info, target_pose_bone=current_target_pb)

            utils_bone_data.set_settings_bone(
                pose_bone, ui_state.target_bone, arm_obj,
                source_arm_obj=obj, source_pose_bone=pose_bone,
                target_pose_bone=target_pb
            )
            for area in context.screen.areas:
                area.tag_redraw()
    else:
        settings_info = utils_bone_data.get_settings_bone_info(pose_bone)
        if settings_info:
            target_pb = _get_target_pb_from_info(settings_info)
            utils_bone_data.clear_settings_bone(pose_bone, target_bone_info=settings_info, target_pose_bone=target_pb)
            for area in context.screen.areas:
                area.tag_redraw()


class AMAZING_RIGGING_PG_settings_bone_ui(PropertyGroup):
    """UI state for settings bone selection"""
    target_armature: PointerProperty(
        name="Target",
        description="Target armature object",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE',
        update=_on_target_armature_changed
    )
    target_bone: StringProperty(
        name="Bone",
        description="Target bone name",
        default="",
        update=_on_target_bone_changed
    )


# ── Bone Selection Menu ──

class AMAZING_RIGGING_MT_bone_selection(Menu):
    """Bone selection popup menu"""
    bl_label = "Select Bone"
    bl_idname = "AMAZING_RIGGING_MT_bone_selection"

    def draw(self, context):
        layout = self.layout
        ui_state = context.scene.amazing_rigging_ui
        arm_obj = ui_state.target_armature

        if not arm_obj or arm_obj.type != 'ARMATURE' or not arm_obj.data:
            layout.label(text="No target armature selected", icon='INFO')
            return

        # 显示 target armature 的所有骨骼，不排除任何 bone
        for bone in arm_obj.data.bones:
            op = layout.operator("amazing_rigging.select_bone", text=bone.name, icon='BONE_DATA')
            op.bone_name = bone.name


class AMAZING_RIGGING_OT_select_bone(Operator):
    """Select a bone from the popup menu"""
    bl_idname = "amazing_rigging.select_bone"
    bl_label = "Select Bone"
    bl_options = {'INTERNAL'}

    bone_name: StringProperty()

    def execute(self, context):
        context.scene.amazing_rigging_ui.target_bone = self.bone_name
        return {'FINISHED'}


# ── Clear Operators ──

class AMAZING_RIGGING_OT_clear_target(Operator):
    """Clear target armature and remove settings bone association"""
    bl_idname = "armature.amazing_rigging_clear_target"
    bl_label = ""
    bl_description = "Clear target and remove settings bone association"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'ERROR'}, "Please select an armature in Pose Mode")
            return {'CANCELLED'}

        bone_name = get_active_bone_name(context, obj)
        if not bone_name:
            return {'CANCELLED'}

        pose_bone = obj.pose.bones.get(bone_name)
        if pose_bone:
            settings_info = utils_bone_data.get_settings_bone_info(pose_bone)
            target_pb = _get_target_pb_from_info(settings_info)
            utils_bone_data.clear_settings_bone(pose_bone, target_bone_info=settings_info, target_pose_bone=target_pb)

        global _syncing_ui
        _syncing_ui = True
        try:
            ui_state = context.scene.amazing_rigging_ui
            ui_state.target_armature = None
            ui_state.target_bone = ""
        finally:
            _syncing_ui = False

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}


class AMAZING_RIGGING_OT_clear_bone(Operator):
    """Clear bone selection and remove settings bone association"""
    bl_idname = "armature.amazing_rigging_clear_bone"
    bl_label = ""
    bl_description = "Clear bone and remove settings bone association"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'ERROR'}, "Please select an armature in Pose Mode")
            return {'CANCELLED'}

        bone_name = get_active_bone_name(context, obj)
        if not bone_name:
            return {'CANCELLED'}

        pose_bone = obj.pose.bones.get(bone_name)
        if pose_bone:
            settings_info = utils_bone_data.get_settings_bone_info(pose_bone)
            target_pb = _get_target_pb_from_info(settings_info)
            utils_bone_data.clear_settings_bone(pose_bone, target_bone_info=settings_info, target_pose_bone=target_pb)

        global _syncing_ui
        _syncing_ui = True
        try:
            ui_state = context.scene.amazing_rigging_ui
            ui_state.target_bone = ""
        finally:
            _syncing_ui = False

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}


class AMAZING_RIGGING_OT_select_related_bone(Operator):
    """Select and focus the related settings bone"""
    bl_idname = "armature.amazing_rigging_select_related_bone"
    bl_label = ""
    bl_description = "Select and focus the related settings bone"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'ERROR'}, "Please select an armature in Pose Mode")
            return {'CANCELLED'}

        bone_name = get_active_bone_name(context, obj)
        if not bone_name:
            return {'CANCELLED'}

        pose_bone = obj.pose.bones.get(bone_name)
        if not pose_bone:
            return {'CANCELLED'}

        settings_pb = utils_bone_data.get_settings_bone_object(pose_bone)
        if not settings_pb:
            self.report({'WARNING'}, "No related settings bone found")
            return {'CANCELLED'}

        info = utils_bone_data.get_settings_bone_info(pose_bone)
        settings_arm_obj = utils_bone_data.find_armature_obj_by_uuid(info['armature_uuid'])
        if not settings_arm_obj:
            self.report({'WARNING'}, "Settings armature not found in scene")
            return {'CANCELLED'}

        context.view_layer.objects.active = settings_arm_obj

        # Blender 5.0 移除了 Bone.select，通过 Edit Mode 中转实现选中
        # EditBone.select 仍然可用，且选择状态在切换回 Pose Mode 后保留
        bpy.ops.object.mode_set(mode='EDIT')
        for eb in settings_arm_obj.data.edit_bones:
            eb.select = False
            eb.select_head = False
            eb.select_tail = False
        target_eb = settings_arm_obj.data.edit_bones.get(settings_pb.name)
        if target_eb:
            target_eb.select = True
            target_eb.select_head = True
            target_eb.select_tail = True
            settings_arm_obj.data.edit_bones.active = target_eb
        bpy.ops.object.mode_set(mode='POSE')

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Selected bone: {settings_pb.name}")
        return {'FINISHED'}


class AMAZING_RIGGING_OT_clear_related_bone(Operator):
    """Clear the relationship with related settings bone"""
    bl_idname = "armature.amazing_rigging_clear_related_bone"
    bl_label = ""
    bl_description = "Remove settings bone association"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'ERROR'}, "Please select an armature in Pose Mode")
            return {'CANCELLED'}

        bone_name = get_active_bone_name(context, obj)
        if not bone_name:
            return {'CANCELLED'}

        pose_bone = obj.pose.bones.get(bone_name)
        if pose_bone:
            settings_info = utils_bone_data.get_settings_bone_info(pose_bone)
            target_pb = _get_target_pb_from_info(settings_info)
            utils_bone_data.clear_settings_bone(pose_bone, target_bone_info=settings_info, target_pose_bone=target_pb)

        global _syncing_ui
        _syncing_ui = True
        try:
            ui_state = context.scene.amazing_rigging_ui
            ui_state.target_armature = None
            ui_state.target_bone = ""
        finally:
            _syncing_ui = False

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}


class AMAZING_RIGGING_OT_select_dependent_bone(Operator):
    """Select and focus the dependent bone"""
    bl_idname = "armature.amazing_rigging_select_dependent_bone"
    bl_label = ""
    bl_description = "Select and focus the dependent bone"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty()
    armature_name: StringProperty()
    armature_uuid: StringProperty()

    def execute(self, context):
        dependent_arm_obj = None
        if self.armature_uuid:
            dependent_arm_obj = utils_bone_data.find_armature_obj_by_uuid(self.armature_uuid)
        if not dependent_arm_obj and self.armature_name:
            arm_data = bpy.data.armatures.get(self.armature_name)
            if arm_data:
                for obj in bpy.data.objects:
                    if obj.type == 'ARMATURE' and obj.data == arm_data:
                        dependent_arm_obj = obj
                        break

        if not dependent_arm_obj:
            self.report({'WARNING'}, "Dependent bone's armature not found in scene")
            return {'CANCELLED'}

        context.view_layer.objects.active = dependent_arm_obj

        # Blender 5.0 移除了 Bone.select，通过 Edit Mode 中转实现选中
        bpy.ops.object.mode_set(mode='EDIT')
        for eb in dependent_arm_obj.data.edit_bones:
            eb.select = False
            eb.select_head = False
            eb.select_tail = False
        target_eb = dependent_arm_obj.data.edit_bones.get(self.bone_name)
        if target_eb:
            target_eb.select = True
            target_eb.select_head = True
            target_eb.select_tail = True
            dependent_arm_obj.data.edit_bones.active = target_eb
        bpy.ops.object.mode_set(mode='POSE')

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Selected bone: {self.bone_name}")
        return {'FINISHED'}


class AMAZING_RIGGING_OT_clear_dependent_bone(Operator):
    """Clear the specified dependent bone association"""
    bl_idname = "armature.amazing_rigging_clear_dependent_bone"
    bl_label = ""
    bl_description = "Remove this dependent bone association"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty()
    armature_name: StringProperty()
    armature_uuid: StringProperty()

    def execute(self, context):
        dependent_arm_obj = None
        if self.armature_uuid:
            dependent_arm_obj = utils_bone_data.find_armature_obj_by_uuid(self.armature_uuid)
        if not dependent_arm_obj and self.armature_name:
            arm_data = bpy.data.armatures.get(self.armature_name)
            if arm_data:
                for obj in bpy.data.objects:
                    if obj.type == 'ARMATURE' and obj.data == arm_data:
                        dependent_arm_obj = obj
                        break

        if not dependent_arm_obj:
            self.report({'WARNING'}, "Dependent bone's armature not found")
            return {'CANCELLED'}

        dep_pb = dependent_arm_obj.pose.bones.get(self.bone_name)
        if not dep_pb:
            self.report({'WARNING'}, f"Dependent bone '{self.bone_name}' not found")
            return {'CANCELLED'}

        settings_info = utils_bone_data.get_settings_bone_info(dep_pb)
        target_pb = _get_target_pb_from_info(settings_info)
        utils_bone_data.clear_settings_bone(dep_pb, target_bone_info=settings_info, target_pose_bone=target_pb)

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Cleared association for bone: {self.bone_name}")
        return {'FINISHED'}


class AMAZING_RIGGING_OT_apply_to_all_selected(Operator):
    """Apply the current settings bone association to all selected bones"""
    bl_idname = "armature.amazing_rigging_apply_to_all_selected"
    bl_label = ""
    bl_description = "Apply settings bone to all selected bones"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'ERROR'}, "Please select an armature in Pose Mode")
            return {'CANCELLED'}

        ui_state = context.scene.amazing_rigging_ui
        arm_obj = ui_state.target_armature
        target_bone_name = ui_state.target_bone

        if not arm_obj or not target_bone_name:
            self.report({'WARNING'}, "Please set target armature and bone first")
            return {'CANCELLED'}

        target_pb = arm_obj.pose.bones.get(target_bone_name)
        if not target_pb:
            self.report({'WARNING'}, f"Target bone '{target_bone_name}' not found")
            return {'CANCELLED'}

        active_bone_name = get_active_bone_name(context, obj)
        selected_pbs = [pb for pb in context.selected_pose_bones
                        if pb.name != active_bone_name]

        if not selected_pbs:
            self.report({'INFO'}, "No other bones selected")
            return {'CANCELLED'}

        # 过滤掉与目标骨骼相同的骨骼（避免为骨骼自身设置自身）
        if obj.data == arm_obj.data and obj.name == arm_obj.name:
            selected_pbs = [pb for pb in selected_pbs if pb.name != target_bone_name]

        if not selected_pbs:
            self.report({'INFO'}, "No valid bones to apply")
            return {'CANCELLED'}

        applied_count = 0
        for pb in selected_pbs:
            current_info = utils_bone_data.get_settings_bone_info(pb)
            if current_info:
                current_target_pb = _get_target_pb_from_info(current_info)
                utils_bone_data.clear_settings_bone(pb, target_bone_info=current_info, target_pose_bone=current_target_pb)

            result = utils_bone_data.set_settings_bone(
                pb, target_bone_name, arm_obj,
                source_arm_obj=obj, source_pose_bone=pb,
                target_pose_bone=target_pb
            )
            if result:
                applied_count += 1

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Applied to {applied_count} bones")
        return {'FINISHED'}


# ── Panel ──

class AMAZING_RIGGING_PT_bone_settings(Panel):
    """Settings Bone configuration panel in Bone Properties tab"""
    bl_label = "Settings Bone - Amazing Rigging"
    bl_idname = "BONE_PT_amazing_rigging_settings"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "bone"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            return False
        if obj.mode != 'POSE':
            return False
        return get_active_bone_name(context, obj) is not None

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        ui_state = context.scene.amazing_rigging_ui

        bone_name = get_active_bone_name(context, obj)

        if not bone_name:
            layout.label(text="No bone selected", icon='INFO')
            return

        pose_bone = obj.pose.bones.get(bone_name)
        if not pose_bone:
            return

        settings_info = utils_bone_data.get_settings_bone_info(pose_bone)

        # ── Set Settings Bone ──
        box = layout.box()
        box.label(text="Set Settings Bone:", icon='BONE_DATA')

        row = box.row(align=True)
        row.prop(ui_state, "target_armature", text="Target")
        if ui_state.target_armature:
            row.operator("armature.amazing_rigging_clear_target", text="", icon='X')

        row = box.row(align=True)
        row.prop(ui_state, "target_bone", text="Bone", icon='BONE_DATA')
        if ui_state.target_bone:
            row.menu("AMAZING_RIGGING_MT_bone_selection", text="", icon='DOWNARROW_HLT')
            row.operator("armature.amazing_rigging_clear_bone", text="", icon='X')
        elif ui_state.target_armature:
            row.menu("AMAZING_RIGGING_MT_bone_selection", text="", icon='DOWNARROW_HLT')

        # Apply to All Selected 按钮
        if ui_state.target_armature and ui_state.target_bone:
            row = box.row()
            row.operator("armature.amazing_rigging_apply_to_all_selected",
                         text="Apply to All Selected", icon='GROUP_BONE')

        # ── Related Bone ──
        if settings_info:
            layout.separator()
            settings_pb = utils_bone_data.get_settings_bone_object(pose_bone)
            if settings_pb:
                row = layout.row(align=True)
                row.label(text="Related Bone:", icon='LINKED')
                row.label(text=settings_info['armature_name'])
                row.label(text=settings_info['bone_name'], icon='BONE_DATA')
                row.operator("armature.amazing_rigging_select_related_bone", text="", icon='FILE_PARENT')
                row.operator("armature.amazing_rigging_clear_related_bone", text="", icon='X')

        # ── Dependent Bones ──
        dependent_bones = utils_bone_data.get_dependent_bones(pose_bone)
        if dependent_bones:
            layout.separator()
            box_dep = layout.box()
            box_dep.label(text="Dependent Bones:", icon='UNLINKED')

            for dep in dependent_bones:
                row = box_dep.row(align=True)
                row.label(text=dep['bone_name'], icon='BONE_DATA')
                if dep.get('armature_name'):
                    row.label(text=f"({dep['armature_name']})")

                op = row.operator("armature.amazing_rigging_select_dependent_bone", text="", icon='FILE_PARENT')
                op.bone_name = dep['bone_name']
                op.armature_name = dep.get('armature_name', '')
                op.armature_uuid = dep.get('armature_uuid', '')

                op = row.operator("armature.amazing_rigging_clear_dependent_bone", text="", icon='X')
                op.bone_name = dep['bone_name']
                op.armature_name = dep.get('armature_name', '')
                op.armature_uuid = dep.get('armature_uuid', '')


classes = [
    AMAZING_RIGGING_PG_settings_bone_ui,
    AMAZING_RIGGING_MT_bone_selection,
    AMAZING_RIGGING_OT_select_bone,
    AMAZING_RIGGING_OT_clear_target,
    AMAZING_RIGGING_OT_clear_bone,
    AMAZING_RIGGING_OT_select_related_bone,
    AMAZING_RIGGING_OT_clear_related_bone,
    AMAZING_RIGGING_OT_select_dependent_bone,
    AMAZING_RIGGING_OT_clear_dependent_bone,
    AMAZING_RIGGING_OT_apply_to_all_selected,
    AMAZING_RIGGING_PT_bone_settings,
]


def register():
    bpy.types.Scene.amazing_rigging_ui = PointerProperty(type=AMAZING_RIGGING_PG_settings_bone_ui)


def unregister():
    del bpy.types.Scene.amazing_rigging_ui
