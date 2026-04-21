import bpy
from bpy.types import Panel, Operator, PropertyGroup, Menu
from bpy.props import StringProperty, PointerProperty
from . import utils_bone_data
from . import utils_set_bone_config
from . import utils_fk_ik_chain


# 追踪最后同步的 bone，避免在用户编辑 UI 时覆盖
_last_synced_bone = None  # (armature_name, bone_name)

# 标志：当 armature 切换时清空 target_bone，但不触发清空 bone 数据的逻辑
_skip_bone_changed_callback = False

# 标志：当 sync_ui 正在更新 UI 时，禁止回调修改 bone 数据
_syncing_ui = False

# 标志：当同步 SET-骨骼配置时，防止触发 update 回调
_syncing_set_ui = False


def reset_state():
    """重置模块全局状态（文件加载或插件重新注册时调用）"""
    global _last_synced_bone, _skip_bone_changed_callback, _syncing_ui, _syncing_set_ui
    _last_synced_bone = None
    _skip_bone_changed_callback = False
    _syncing_ui = False
    _syncing_set_ui = False


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

        # 同步 SET-骨骼的 IK/FK 配置到 UI
        # 从持久化数据加载到 PropertyGroup，确保 UI 显示与实际数据一致
        if pose_bone and pose_bone.name.startswith("SET-"):
            utils_set_bone_config.sync_set_bone_ui(context, pose_bone)
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

    ui_state = context.scene.amazing_rigging_ui

    # 防止骨骼引用自身作为 settings bone
    if (obj.data == arm_obj.data and obj.name == arm_obj.name and
        bone_name == ui_state.target_bone):
        return

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


# IK/FK Bone Selection Properties

def _on_ik_fk_armature_changed(self, context):
    """当 IK/FK/IK CTRL 的 armature 改变时，清空 bone 并保存配置"""
    global _syncing_set_ui
    
    if _syncing_set_ui:
        return
    
    obj = context.active_object
    if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
        return
    
    # 获取所属的 PoseBone
    pose_bone = self.id_data
    if not hasattr(pose_bone, 'name'):
        return
    
    # 只处理 SET- 骨骼
    if not pose_bone.name.startswith("SET-"):
        return
    
    # 获取配置类型 (ik/fk/ik_ctrl)
    path = self.path_from_id()
    config_type = path.split('.')[0] if '.' in path else None
    if config_type not in ['ik', 'fk', 'ik_ctrl']:
        return
    
    # 清空 bone 字段
    _syncing_set_ui = True
    try:
        self.bone = ""
    finally:
        _syncing_set_ui = False
    
    # 保存配置 (armature 改变，bone 为空)
    utils_set_bone_config.save_set_bone_config(pose_bone, config_type, self.armature, "")
    
    for area in context.screen.areas:
        area.tag_redraw()


def _on_ik_fk_bone_changed(self, context):
    """当 IK/FK/IK CTRL 的 bone 改变时，保存配置"""
    global _syncing_set_ui
    
    if _syncing_set_ui:
        return
    
    obj = context.active_object
    if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
        return
    
    # 获取所属的 PoseBone
    pose_bone = self.id_data
    if not hasattr(pose_bone, 'name'):
        return
    
    # 只处理 SET- 骨骼
    if not pose_bone.name.startswith("SET-"):
        return
    
    # 获取配置类型 (ik/fk/ik_ctrl)
    path = self.path_from_id()
    config_type = path.split('.')[0] if '.' in path else None
    if config_type not in ['ik', 'fk', 'ik_ctrl']:
        return
    
    # 保存配置
    utils_set_bone_config.save_set_bone_config(pose_bone, config_type, self.armature, self.bone)
    
    for area in context.screen.areas:
        area.tag_redraw()


class AMAZING_RIGGING_PG_ik_fk_bone(PropertyGroup):
    """IK/FK bone selection for SET- bones"""
    armature: PointerProperty(
        name="Armature",
        description="Target armature object",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE',
        update=_on_ik_fk_armature_changed
    )
    bone: StringProperty(
        name="Bone",
        description="Target bone name",
        default="",
        update=_on_ik_fk_bone_changed
    )


class AMAZING_RIGGING_PG_set_bone_ui(PropertyGroup):
    """UI state for SET- bones"""
    ik: PointerProperty(type=AMAZING_RIGGING_PG_ik_fk_bone)
    fk: PointerProperty(type=AMAZING_RIGGING_PG_ik_fk_bone)
    ik_ctrl: PointerProperty(type=AMAZING_RIGGING_PG_ik_fk_bone)
    selected_dependent_bones: StringProperty(
        name="Selected Dependent Bones",
        description="Comma-separated list of selected dependent bone names",
        default=""
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

        # 按字母顺序排序骨骼列表
        sorted_bones = sorted(arm_obj.data.bones, key=lambda b: b.name)
        
        # 显示 target armature 的所有骨骼
        for bone in sorted_bones:
            op = layout.operator("amazing_rigging.select_bone", text=bone.name, icon='BONE_DATA')
            op.bone_name = bone.name


def get_sorted_bones_for_armature(arm_obj):
    """获取按字母顺序排序的骨骼列表
    
    Args:
        arm_obj: Armature object
    
    Returns:
        按字母顺序排序的骨骼列表
    """
    if not arm_obj or arm_obj.type != 'ARMATURE' or not arm_obj.data:
        return []
    return sorted(arm_obj.data.bones, key=lambda b: b.name)


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


class AMAZING_RIGGING_OT_toggle_dependent_bone_select(Operator):
    """Toggle selection state of a dependent bone"""
    bl_idname = "armature.amazing_rigging_toggle_dependent_bone_select"
    bl_label = ""
    bl_description = "Toggle dependent bone selection"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty()

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            return {'CANCELLED'}

        pose_bone = context.active_pose_bone
        if not pose_bone:
            return {'CANCELLED'}

        ui = pose_bone.amazing_set_bone_ui

        # Get current selection
        current_selected = set(ui.selected_dependent_bones.split(','))
        current_selected.discard('')

        # Toggle this bone's selection
        if self.bone_name in current_selected:
            current_selected.discard(self.bone_name)
        else:
            current_selected.add(self.bone_name)

        # Save back
        ui.selected_dependent_bones = ','.join(sorted(current_selected))

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}


class AMAZING_RIGGING_OT_toggle_select_all_dependents(Operator):
    """Toggle select/deselect all dependent bones"""
    bl_idname = "armature.amazing_rigging_toggle_select_all_dependents"
    bl_label = "Select All"
    bl_description = "Toggle select/deselect all dependent bones"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            return {'CANCELLED'}

        pose_bone = obj.pose.bones.get(obj.bone_IK if hasattr(obj, 'bone_IK') else "")
        if not pose_bone:
            pose_bone = context.active_pose_bone

        if not pose_bone:
            return {'CANCELLED'}

        ui = pose_bone.amazing_set_bone_ui
        dependent_bones = utils_bone_data.get_dependent_bones(pose_bone)

        if not dependent_bones:
            return {'CANCELLED'}

        # Get current selection
        current_selected = set(ui.selected_dependent_bones.split(','))
        current_selected.discard('')

        all_dep_names = {dep['bone_name'] for dep in dependent_bones}

        # Check if all are currently selected
        all_selected = current_selected == all_dep_names

        if all_selected:
            # Deselect all
            ui.selected_dependent_bones = ""
            self.report({'INFO'}, "Deselected all dependent bones")
        else:
            # Select all
            ui.selected_dependent_bones = ','.join(sorted(all_dep_names))
            self.report({'INFO'}, f"Selected {len(all_dep_names)} dependent bones")

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}


class AMAZING_RIGGING_OT_clear_selected_dependent_bones(Operator):
    """Clear the selected dependent bone associations"""
    bl_idname = "armature.amazing_rigging_clear_selected_dependent_bones"
    bl_label = "Delete Selected"
    bl_description = "Remove all selected dependent bone associations"
    bl_options = {'REGISTER', 'UNDO'}

    armature_name: StringProperty()
    armature_uuid: StringProperty()

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'ERROR'}, "Please select an armature in Pose Mode")
            return {'CANCELLED'}

        pose_bone = context.active_pose_bone
        if not pose_bone:
            return {'CANCELLED'}

        ui = pose_bone.amazing_set_bone_ui
        selected_names = ui.selected_dependent_bones.split(',')
        selected_names = [n.strip() for n in selected_names if n.strip()]

        if not selected_names:
            self.report({'WARNING'}, "No dependent bones selected")
            return {'CANCELLED'}

        dependent_bones = utils_bone_data.get_dependent_bones(pose_bone)
        dep_dict = {dep['bone_name']: dep for dep in dependent_bones}

        cleared_count = 0
        for bone_name in selected_names:
            dep = dep_dict.get(bone_name)
            if not dep:
                continue

            # Find armature
            dependent_arm_obj = None
            if dep.get('armature_uuid'):
                dependent_arm_obj = utils_bone_data.find_armature_obj_by_uuid(dep['armature_uuid'])
            if not dependent_arm_obj and dep.get('armature_name'):
                arm_data = bpy.data.armatures.get(dep['armature_name'])
                if arm_data:
                    for o in bpy.data.objects:
                        if o.type == 'ARMATURE' and o.data == arm_data:
                            dependent_arm_obj = o
                            break

            if not dependent_arm_obj:
                continue

            dep_pb = dependent_arm_obj.pose.bones.get(bone_name)
            if not dep_pb:
                continue

            settings_info = utils_bone_data.get_settings_bone_info(dep_pb)
            target_pb = _get_target_pb_from_info(settings_info)
            utils_bone_data.clear_settings_bone(dep_pb, target_bone_info=settings_info, target_pose_bone=target_pb)
            cleared_count += 1

        # Clear selection
        ui.selected_dependent_bones = ""

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Cleared {cleared_count} dependent bone associations")
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


# ── IK/FK Snap Operators ──

def _get_set_bone_for_snap(pose_bone):
    """
    获取用于 IK/FK Snap 的 SET- 骨骼
    
    逻辑:
    1. 如果当前骨骼是 SET- 骨骼,直接返回
    2. 如果当前骨骼是 dependent bone (有 settings bone),且 settings bone 是 SET- 骨骼,返回 settings bone
    3. 否则返回 None
    
    Args:
        pose_bone: PoseBone 对象
    
    Returns:
        PoseBone 或 None
    """
    # 如果当前骨骼是 SET- 骨骼,直接返回
    if pose_bone.name.startswith("SET-"):
        return pose_bone
    
    # 检查是否有 settings bone (即是否是 dependent bone)
    settings_info = utils_bone_data.get_settings_bone_info(pose_bone)
    if settings_info:
        # 获取 settings bone 对象
        target_pose_bone = utils_bone_data.get_settings_bone_object(pose_bone)
        # 如果 settings bone 是 SET- 骨骼,返回它
        if target_pose_bone and target_pose_bone.name.startswith("SET-"):
            return target_pose_bone
    
    return None


class AMAZING_RIGGING_OT_snap_fk_to_ik(Operator):
    """将 FK 骨骼捕捉到 IK 骨骼的位置 (FK 骨骼移动)"""
    bl_idname = "amazing_rigging.snap_fk_to_ik"
    bl_label = "FK -> IK"
    bl_description = "将 FK 骨骼捕捉到 IK 骨骼的位置"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'WARNING'}, "未处于姿态模式")
            return {'CANCELLED'}
        
        selected_pbs = context.selected_pose_bones
        if not selected_pbs:
            self.report({'WARNING'}, "未选择骨骼")
            return {'CANCELLED'}
        
        pose_bone = selected_pbs[0]
        set_bone = _get_set_bone_for_snap(pose_bone)
        if not set_bone:
            self.report({'WARNING'}, "不是 SET- 骨骼")
            return {'CANCELLED'}
        
        # 尝试链式发现
        pairs = utils_fk_ik_chain.discover_fk_ik_pairs(set_bone)
        
        if pairs is not None:
            # ========================================
            # 链式模式：发现 FK-/IK- 配对的 dependent bones
            # ========================================
            chain = utils_fk_ik_chain.build_fk_chain(pairs)
            result = utils_fk_ik_chain.snap_fk_chain_to_ik(chain, context)
            
            if result['success']:
                msg = f"链式对齐完成: {result['snapped_count']}/{result['total_count']} 个骨骼"
                if result['warnings']:
                    msg += f" (警告: {len(result['warnings'])})"
                if result['position_errors']:
                    err_names = [e['suffix'] for e in result['position_errors']]
                    msg += f" 位置偏差: {err_names}"
                self.report({'INFO'}, msg)
                return {'FINISHED'}
            else:
                if result['warnings']:
                    self.report({'WARNING'}, result['warnings'][0])
                else:
                    self.report({'WARNING'}, "链式对齐失败")
                return {'CANCELLED'}
        
        # ========================================
        # 单骨骼回退模式：使用 SET-骨骼的 IK/FK 配置
        # ========================================
        set_ui = set_bone.amazing_set_bone_ui
        ik_armature = set_ui.ik.armature
        ik_bone_name = set_ui.ik.bone
        fk_armature = set_ui.fk.armature
        fk_bone_name = set_ui.fk.bone
        
        if not ik_armature or not ik_bone_name or not fk_armature or not fk_bone_name:
            ik_config = utils_set_bone_config.load_set_bone_config(set_bone, 'ik')
            fk_config = utils_set_bone_config.load_set_bone_config(set_bone, 'fk')
            
            if ik_config["valid"]:
                ik_armature = ik_config["armature_obj"]
                ik_bone_name = ik_config["bone_name"]
            if fk_config["valid"]:
                fk_armature = fk_config["armature_obj"]
                fk_bone_name = fk_config["bone_name"]
        
        if not ik_armature or not ik_bone_name or not fk_armature or not fk_bone_name:
            self.report({'WARNING'}, "IK 和 FK 配置都必须设置")
            return {'CANCELLED'}
        
        try:
            ik_pb = ik_armature.pose.bones.get(ik_bone_name)
            fk_pb = fk_armature.pose.bones.get(fk_bone_name)
            
            if not ik_pb or not fk_pb:
                self.report({'ERROR'}, "IK 或 FK 骨骼未找到")
                return {'CANCELLED'}
            
            print(f"\n[DEBUG] FK -> IK Snap (单骨骼模式):")
            print(f"  IK骨骼: {ik_bone_name}, 旋转模式: {ik_pb.rotation_mode}")
            print(f"  FK骨骼: {fk_bone_name}, 旋转模式: {fk_pb.rotation_mode}")
            print(f"  IK世界位置: {ik_pb.matrix.to_translation()}")
            print(f"  FK世界位置(前): {fk_pb.matrix.to_translation()}")
            
            # 检测阻塞约束
            blocking = []
            for const in fk_pb.constraints:
                if not const.mute and const.type in utils_fk_ik_chain.BLOCKING_CONSTRAINT_TYPES:
                    blocking.append(const.name)
            
            if blocking:
                self.report({'WARNING'}, 
                    f"FK骨骼 '{fk_bone_name}' 被约束 {blocking} 控制，无法移动。请先禁用这些约束。")
                print(f"  [错误] 骨骼被约束阻止: {blocking}")
                return {'CANCELLED'}
            
            # 获取 IK 骨骼的世界矩阵
            ik_world_matrix = ik_pb.matrix.copy()
            
            # 计算 matrix_basis
            mb = utils_fk_ik_chain.compute_matrix_basis(fk_pb, fk_armature, ik_world_matrix)
            
            # 应用变换
            utils_fk_ik_chain.apply_matrix_basis_to_bone(fk_pb, mb)
            
            # 更新场景
            context.view_layer.update()
            
            # 验证结果
            print(f"  FK世界位置(后): {fk_pb.matrix.to_translation()}")
            print(f"  IK世界位置(目标): {ik_world_matrix.to_translation()}")
            
            fk_world_after = fk_pb.matrix.to_translation()
            ik_world = ik_world_matrix.to_translation()
            position_diff = (fk_world_after - ik_world).length
            
            if position_diff < 0.0001:
                print(f"  [成功] 位置匹配！差异: {position_diff:.6f}")
            else:
                print(f"  [警告] 位置差异: {position_diff:.6f}")
            
            self.report({'INFO'}, f"已将 FK '{fk_bone_name}' 快照到 IK '{ik_bone_name}'")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"快照失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class AMAZING_RIGGING_OT_snap_ik_to_fk(Operator):
    """将 IK 骨骼捕捉到 FK 骨骼的位置 (IK 骨骼移动)"""
    bl_idname = "amazing_rigging.snap_ik_to_fk"
    bl_label = "IK -> FK"
    bl_description = "将 IK 骨骼捕捉到 FK 骨骼的位置"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # 检查是否在 Pose Mode
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'WARNING'}, "未处于姿态模式")
            return {'CANCELLED'}
        
        # 检查是否有选中的骨骼
        selected_pbs = context.selected_pose_bones
        if not selected_pbs:
            self.report({'WARNING'}, "未选择骨骼")
            return {'CANCELLED'}
        
        pose_bone = selected_pbs[0]
        
        # 获取 SET- 骨骼 (可能是当前骨骼或其 settings bone)
        set_bone = _get_set_bone_for_snap(pose_bone)
        if not set_bone:
            self.report({'WARNING'}, "不是 SET- 骨骼")
            return {'CANCELLED'}
        
        # 获取 SET- 骨骼的 UI 状态
        set_ui = set_bone.amazing_set_bone_ui
        
        # 优先使用 UI 中的配置
        ik_armature = set_ui.ik.armature
        ik_bone_name = set_ui.ik.bone
        fk_armature = set_ui.fk.armature
        fk_bone_name = set_ui.fk.bone
        ik_ctrl_armature = set_ui.ik_ctrl.armature
        ik_ctrl_bone_name = set_ui.ik_ctrl.bone
        
        # 如果 UI 中没有配置,尝试从持久化配置加载
        if not ik_armature or not ik_bone_name or not fk_armature or not fk_bone_name:
            ik_config = utils_set_bone_config.load_set_bone_config(set_bone, 'ik')
            fk_config = utils_set_bone_config.load_set_bone_config(set_bone, 'fk')
            
            if ik_config["valid"]:
                ik_armature = ik_config["armature_obj"]
                ik_bone_name = ik_config["bone_name"]
            if fk_config["valid"]:
                fk_armature = fk_config["armature_obj"]
                fk_bone_name = fk_config["bone_name"]
        
        # 加载 IK CTRL 配置
        if not ik_ctrl_armature or not ik_ctrl_bone_name:
            ik_ctrl_config = utils_set_bone_config.load_set_bone_config(set_bone, 'ik_ctrl')
            if ik_ctrl_config["valid"]:
                ik_ctrl_armature = ik_ctrl_config["armature_obj"]
                ik_ctrl_bone_name = ik_ctrl_config["bone_name"]
        
        # 验证IK和FK配置
        if not ik_armature or not ik_bone_name:
            self.report({'WARNING'}, "缺失IK配置骨骼，无法执行IK->FK对齐")
            return {'CANCELLED'}
        
        if not fk_armature or not fk_bone_name:
            self.report({'WARNING'}, "IK 和 FK 配置都必须设置")
            return {'CANCELLED'}
        
        try:
            from mathutils import Vector, Matrix
            
            # 获取 IK 和 FK 骨骼
            ik_pb = ik_armature.pose.bones.get(ik_bone_name)
            fk_pb = fk_armature.pose.bones.get(fk_bone_name)
            
            if not ik_pb or not fk_pb:
                self.report({'ERROR'}, "IK 或 FK 骨骼未找到")
                return {'CANCELLED'}
            
            # 检测IK CTRL配置骨骼是否有效
            ik_ctrl_pb = None
            if ik_ctrl_armature and ik_ctrl_bone_name:
                ik_ctrl_pb = ik_ctrl_armature.pose.bones.get(ik_ctrl_bone_name)
            
            # ========================================
            # 分支逻辑：IK CTRL 有效 vs 无效
            # ========================================
            
            if ik_ctrl_pb is not None:
                # ========================================
                # IK CTRL 有效：通过移动 IK CTRL 骨骼来间接对齐 IK 骨骼
                # ========================================
                
                print(f"\n[DEBUG] IK -> FK Snap (通过IK CTRL骨骼间接对齐):")
                print(f"  IK CTRL骨骼: {ik_ctrl_bone_name}, 旋转模式: {ik_ctrl_pb.rotation_mode}")
                print(f"  IK骨骼: {ik_bone_name}, 旋转模式: {ik_pb.rotation_mode}")
                print(f"  FK骨骼: {fk_bone_name}, 旋转模式: {fk_pb.rotation_mode}")
                print(f"  FK世界位置: {fk_pb.matrix.to_translation()}")
                print(f"  IK CTRL世界位置(前): {ik_ctrl_pb.matrix.to_translation()}")
                print(f"  IK世界位置(前): {ik_pb.matrix.to_translation()}")
                
                # 步骤1: 检测IK CTRL骨骼是否有影响location/transform的约束
                blocking_constraints = []
                for const in ik_ctrl_pb.constraints:
                    if not const.mute and const.type in [
                        'COPY_LOCATION',
                        'TRANSFORM',
                        'COPY_TRANSFORMS',
                        'LIMIT_LOCATION',
                        'CLAMP_TO'
                    ]:
                        blocking_constraints.append(const.name)
                
                if blocking_constraints:
                    self.report({'WARNING'}, 
                        f"IK CTRL骨骼 '{ik_ctrl_bone_name}' 被约束 {blocking_constraints} 控制，无法移动。请先禁用这些约束。")
                    print(f"  [错误] IK CTRL骨骼被约束阻止: {blocking_constraints}")
                    return {'CANCELLED'}
                
                # 步骤2: 计算IK骨骼与IK CTRL骨骼之间的空间关系（相对变换）
                # rel_matrix = IK CTRL世界逆矩阵 @ IK世界矩阵
                # 即: IK世界 = IK CTRL世界 @ rel_matrix
                ik_ctrl_world_inv = ik_ctrl_pb.matrix.copy().inverted()
                ik_world_before = ik_pb.matrix.copy()
                rel_matrix = ik_ctrl_world_inv @ ik_world_before
                
                print(f"  IK->IK CTRL相对变换(偏移): loc={rel_matrix.to_translation()}, rot={rel_matrix.to_quaternion()}")
                
                # 步骤3: 计算IK骨骼的目标世界变换（对齐到FK骨骼）
                fk_world_matrix = fk_pb.matrix.copy()
                
                # 步骤4: 基于相对关系，计算IK CTRL骨骼的目标世界变换
                # IK CTRL目标世界 = FK世界 @ 相对变换逆矩阵
                # 因为: IK世界 = IK CTRL世界 @ rel_matrix
                # 所以: IK CTRL世界 = IK世界 @ rel_matrix.inverted()
                # 目标: IK CTRL目标世界 = FK世界 @ rel_matrix.inverted()
                ik_ctrl_target_world = fk_world_matrix @ rel_matrix.inverted()
                
                print(f"  IK CTRL目标世界位置: {ik_ctrl_target_world.to_translation()}")
                
                # 步骤5: 计算IK CTRL骨骼的matrix_basis
                if ik_ctrl_pb.parent is not None:
                    ctrl_parent_world = ik_ctrl_pb.parent.matrix.copy()
                    ctrl_bone_local_rest = ik_ctrl_pb.parent.bone.matrix_local.inverted() @ ik_ctrl_pb.bone.matrix_local
                    ctrl_matrix_basis = ctrl_bone_local_rest.inverted() @ ctrl_parent_world.inverted() @ ik_ctrl_target_world
                else:
                    ctrl_armature_world = ik_ctrl_armature.matrix_world.copy()
                    ctrl_bone_local_rest = ik_ctrl_pb.bone.matrix_local
                    ctrl_matrix_basis = ctrl_bone_local_rest.inverted() @ ctrl_armature_world.inverted() @ ik_ctrl_target_world
                
                # 步骤6: 分解并应用变换到IK CTRL骨骼
                ctrl_basis_loc, ctrl_basis_rot, ctrl_basis_scale = ctrl_matrix_basis.decompose()
                ctrl_original_rotation_mode = ik_ctrl_pb.rotation_mode
                
                ik_ctrl_pb.scale = ctrl_basis_scale
                
                if ctrl_original_rotation_mode == 'QUATERNION':
                    ik_ctrl_pb.rotation_quaternion = ctrl_basis_rot
                elif ctrl_original_rotation_mode == 'AXIS_ANGLE':
                    ik_ctrl_pb.rotation_axis_angle = ctrl_basis_rot.to_axis_angle()
                else:
                    ik_ctrl_pb.rotation_euler = ctrl_basis_rot.to_euler(ctrl_original_rotation_mode)
                
                ik_ctrl_pb.location = ctrl_basis_loc
                
                # 更新场景
                context.view_layer.update()
                
                # 步骤7: 验证结果
                print(f"  IK CTRL本地位置(后): {ik_ctrl_pb.location}")
                print(f"  IK CTRL世界位置(后): {ik_ctrl_pb.matrix.to_translation()}")
                print(f"  IK世界位置(后): {ik_pb.matrix.to_translation()}")
                print(f"  FK世界位置(目标): {fk_world_matrix.to_translation()}")
                
                # 验证IK骨骼是否对齐到FK位置
                ik_world_after = ik_pb.matrix.to_translation()
                fk_world = fk_world_matrix.to_translation()
                position_diff = (ik_world_after - fk_world).length
                
                if position_diff < 0.001:
                    print(f"  [成功] IK CTRL间接对齐成功！IK位置差异: {position_diff:.6f}")
                else:
                    print(f"  [警告] IK位置差异: {position_diff:.6f}")
                
                self.report({'INFO'}, f"已通过 IK CTRL '{ik_ctrl_bone_name}' 将 IK '{ik_bone_name}' 对齐到 FK '{fk_bone_name}'")
                
            else:
                # ========================================
                # IK CTRL 无效：直接移动 IK 骨骼到 FK 位置（原始逻辑）
                # ========================================
                
                print(f"\n[DEBUG] IK -> FK Snap (IK骨骼直接移动到FK位置):")
                print(f"  IK骨骼: {ik_bone_name}, 旋转模式: {ik_pb.rotation_mode}")
                print(f"  FK骨骼: {fk_bone_name}, 旋转模式: {fk_pb.rotation_mode}")
                print(f"  FK世界位置: {fk_pb.matrix.to_translation()}")
                print(f"  IK世界位置(前): {ik_pb.matrix.to_translation()}")
                print(f"  IK本地位置(前): {ik_pb.location}")
                
                # 检测IK骨骼是否有影响location/transform的约束
                blocking_constraints = []
                for const in ik_pb.constraints:
                    if not const.mute and const.type in [
                        'COPY_LOCATION',
                        'TRANSFORM',
                        'COPY_TRANSFORMS',
                        'LIMIT_LOCATION',
                        'CLAMP_TO'
                    ]:
                        blocking_constraints.append(const.name)
                
                if blocking_constraints:
                    self.report({'WARNING'}, 
                        f"IK骨骼 '{ik_bone_name}' 被约束 {blocking_constraints} 控制，无法移动。请先禁用这些约束。")
                    print(f"  [错误] 骨骼被约束阻止: {blocking_constraints}")
                    return {'CANCELLED'}
                
                # 获取FK骨骼的世界矩阵
                fk_world_matrix = fk_pb.matrix.copy()
                
                # 计算IK骨骼的matrix_basis
                if ik_pb.parent is not None:
                    parent_world = ik_pb.parent.matrix.copy()
                    bone_local_rest = ik_pb.parent.bone.matrix_local.inverted() @ ik_pb.bone.matrix_local
                    matrix_basis = bone_local_rest.inverted() @ parent_world.inverted() @ fk_world_matrix
                else:
                    armature_world = ik_armature.matrix_world.copy()
                    bone_local_rest = ik_pb.bone.matrix_local
                    matrix_basis = bone_local_rest.inverted() @ armature_world.inverted() @ fk_world_matrix
                
                # 分解并应用变换
                basis_loc, basis_rot, basis_scale = matrix_basis.decompose()
                original_rotation_mode = ik_pb.rotation_mode
                
                ik_pb.scale = basis_scale
                
                if original_rotation_mode == 'QUATERNION':
                    ik_pb.rotation_quaternion = basis_rot
                elif original_rotation_mode == 'AXIS_ANGLE':
                    ik_pb.rotation_axis_angle = basis_rot.to_axis_angle()
                else:
                    ik_pb.rotation_euler = basis_rot.to_euler(original_rotation_mode)
                
                ik_pb.location = basis_loc
                
                # 更新场景
                context.view_layer.update()
                
                # 验证结果
                print(f"  IK本地位置(后): {ik_pb.location}")
                print(f"  IK世界位置(后): {ik_pb.matrix.to_translation()}")
                print(f"  FK世界位置(目标): {fk_world_matrix.to_translation()}")
                
                ik_world_after = ik_pb.matrix.to_translation()
                fk_world = fk_world_matrix.to_translation()
                position_diff = (ik_world_after - fk_world).length
                
                if position_diff < 0.0001:
                    print(f"  [成功] 位置匹配！差异: {position_diff:.6f}")
                else:
                    print(f"  [警告] 位置差异: {position_diff:.6f}")
                
                self.report({'INFO'}, f"已将 IK '{ik_bone_name}' 快照到 FK '{fk_bone_name}'")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"快照失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


# ── SET-骨骼 IK/FK/IK CTRL 配置加载 Operator ──

class AMAZING_RIGGING_OT_load_ik_fk_config(Operator):
    """Load IK/FK/IK CTRL configuration from saved data"""
    bl_idname = "amazing_rigging.load_ik_fk_config"
    bl_label = "Load IK/FK Config"
    bl_options = {'INTERNAL'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'WARNING'}, "Not in Pose Mode")
            return {'CANCELLED'}
        
        # 获取选中的骨骼
        selected_pbs = context.selected_pose_bones
        if not selected_pbs:
            self.report({'WARNING'}, "No bone selected")
            return {'CANCELLED'}
        
        pose_bone = selected_pbs[0]
        
        # 只处理 SET- 骨骼
        if not pose_bone.name.startswith("SET-"):
            self.report({'WARNING'}, "Not a SET- bone")
            return {'CANCELLED'}
        
        # 加载配置到 UI
        if utils_set_bone_config.sync_set_bone_ui(context, pose_bone):
            for area in context.screen.areas:
                area.tag_redraw()
            self.report({'INFO'}, "Configuration loaded")
        else:
            self.report({'WARNING'}, "No saved configuration found")
        
        return {'FINISHED'}


# ── SET-骨骼 IK/FK/IK CTRL 配置清除 Operator ──

class AMAZING_RIGGING_OT_clear_ik_fk_config(Operator):
    """Clear IK/FK/IK CTRL configuration for SET- bone"""
    bl_idname = "amazing_rigging.clear_ik_fk_config"
    bl_label = "Clear IK/FK Config"
    bl_options = {'INTERNAL'}
    
    config_type: StringProperty(
        name="Config Type",
        description="Type of configuration to clear (ik, fk, or ik_ctrl)",
        default=""
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'WARNING'}, "Not in Pose Mode")
            return {'CANCELLED'}
        
        # 获取选中的骨骼
        selected_pbs = context.selected_pose_bones
        if not selected_pbs:
            self.report({'WARNING'}, "No bone selected")
            return {'CANCELLED'}
        
        pose_bone = selected_pbs[0]
        
        # 只处理 SET- 骨骼
        if not pose_bone.name.startswith("SET-"):
            self.report({'WARNING'}, "Not a SET- bone")
            return {'CANCELLED'}
        
        # 清除配置
        if utils_set_bone_config.clear_set_bone_config(pose_bone, self.config_type):
            # 清空 UI
            global _syncing_set_ui
            _syncing_set_ui = True
            try:
                set_ui = pose_bone.amazing_set_bone_ui
                if self.config_type == 'ik':
                    set_ui.ik.armature = None
                    set_ui.ik.bone = ""
                elif self.config_type == 'fk':
                    set_ui.fk.armature = None
                    set_ui.fk.bone = ""
                elif self.config_type == 'ik_ctrl':
                    set_ui.ik_ctrl.armature = None
                    set_ui.ik_ctrl.bone = ""
            finally:
                _syncing_set_ui = False
            
            for area in context.screen.areas:
                area.tag_redraw()
            
            self.report({'INFO'}, f"Cleared {self.config_type} configuration")
        else:
            self.report({'WARNING'}, "Failed to clear configuration")
        
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

            # Sync selected_dependent_bones - remove stale entries
            dep_names = {dep['bone_name'] for dep in dependent_bones}
            current_selected = pose_bone.amazing_set_bone_ui.selected_dependent_bones.split(',')
            stale_selected = [n for n in current_selected if n and n not in dep_names]
            if stale_selected:
                new_selected = [n for n in current_selected if n and n not in stale_selected]
                pose_bone.amazing_set_bone_ui.selected_dependent_bones = ','.join(new_selected)

            # Header row with Select All toggle
            header_row = box_dep.row(align=True)
            header_row.operator(
                "armature.amazing_rigging_toggle_select_all_dependents",
                text="Select All",
                icon='CHECKBOX_HLT' if len(pose_bone.amazing_set_bone_ui.selected_dependent_bones.split(',')) == len(dependent_bones) else 'CHECKBOX_DEHLT'
            )
            header_row.label(text="")  # Spacer

            # Get selected bones set
            selected_deps = set(pose_bone.amazing_set_bone_ui.selected_dependent_bones.split(','))
            selected_deps.discard('')

            for dep in dependent_bones:
                row = box_dep.row(align=True)

                # Checkbox toggle button
                is_selected = dep['bone_name'] in selected_deps
                checkbox_icon = 'CHECKBOX_HLT' if is_selected else 'CHECKBOX_DEHLT'
                toggle_op = row.operator(
                    "armature.amazing_rigging_toggle_dependent_bone_select",
                    text="",
                    icon=checkbox_icon,
                    emboss=False
                )
                toggle_op.bone_name = dep['bone_name']

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

            # Delete Selected button at bottom
            # Get current armature info for the operator
            current_arm_name = obj.name
            current_arm_uuid = obj.data.uuid if hasattr(obj.data, 'uuid') else ''

            if selected_deps:
                footer_row = box_dep.row()
                delete_op = footer_row.operator(
                    "armature.amazing_rigging_clear_selected_dependent_bones",
                    text=f"Delete Selected ({len(selected_deps)})",
                    icon='X'
                )
                delete_op.armature_name = current_arm_name
                delete_op.armature_uuid = current_arm_uuid
            else:
                footer_row = box_dep.row()
                delete_op = footer_row.operator(
                    "armature.amazing_rigging_clear_selected_dependent_bones",
                    text="Delete Selected",
                    icon='X',
                    emboss=False
                )
                delete_op.armature_name = current_arm_name
                delete_op.armature_uuid = current_arm_uuid
                footer_row.enabled = False


classes = [
    AMAZING_RIGGING_PG_ik_fk_bone,
    AMAZING_RIGGING_PG_set_bone_ui,
    AMAZING_RIGGING_PG_settings_bone_ui,
    AMAZING_RIGGING_MT_bone_selection,
    AMAZING_RIGGING_OT_select_bone,
    AMAZING_RIGGING_OT_clear_target,
    AMAZING_RIGGING_OT_clear_bone,
    AMAZING_RIGGING_OT_select_related_bone,
    AMAZING_RIGGING_OT_clear_related_bone,
    AMAZING_RIGGING_OT_select_dependent_bone,
    AMAZING_RIGGING_OT_clear_dependent_bone,
    AMAZING_RIGGING_OT_toggle_dependent_bone_select,
    AMAZING_RIGGING_OT_toggle_select_all_dependents,
    AMAZING_RIGGING_OT_clear_selected_dependent_bones,
    AMAZING_RIGGING_OT_apply_to_all_selected,
    AMAZING_RIGGING_OT_snap_fk_to_ik,
    AMAZING_RIGGING_OT_snap_ik_to_fk,
    AMAZING_RIGGING_OT_load_ik_fk_config,
    AMAZING_RIGGING_OT_clear_ik_fk_config,
    AMAZING_RIGGING_PT_bone_settings,
]


def register():
    bpy.types.Scene.amazing_rigging_ui = PointerProperty(type=AMAZING_RIGGING_PG_settings_bone_ui)
    bpy.types.PoseBone.amazing_set_bone_ui = PointerProperty(type=AMAZING_RIGGING_PG_set_bone_ui)


def unregister():
    del bpy.types.Scene.amazing_rigging_ui
    if hasattr(bpy.types.PoseBone, 'amazing_set_bone_ui'):
        del bpy.types.PoseBone.amazing_set_bone_ui
