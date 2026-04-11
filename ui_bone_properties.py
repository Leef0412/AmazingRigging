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


def _get_bone_for_read(obj, bone_name):
    """获取用于读取自定义属性的 bone 对象。
    在 Edit Mode 下，EditBone 拥有最新的自定义属性（arm_data.bones 是过时快照）。
    在其他模式下，使用 arm_data.bones。
    """
    if not obj or obj.type != 'ARMATURE' or not bone_name:
        return None
    arm_data = obj.data
    if obj.mode == 'EDIT':
        eb = arm_data.edit_bones.get(bone_name)
        if eb:
            return eb
    return arm_data.bones.get(bone_name)


def _get_writable_bone(obj, bone_name):
    """获取用于写入自定义属性的 bone 对象。
    在 Edit Mode 下，必须写入 EditBone（Blender 退出 Edit Mode 时同步到 Bone）。
    在其他模式下，写入 arm_data.bones。
    """
    if not obj or obj.type != 'ARMATURE' or not bone_name:
        return None
    arm_data = obj.data
    if obj.mode == 'EDIT':
        return arm_data.edit_bones.get(bone_name)
    return arm_data.bones.get(bone_name)


def _get_target_bone_for_write(arm_obj, bone_name):
    """获取目标 armature 上用于写入反向引用的 bone 对象。
    在 Edit Mode 下，如果目标 armature 也处于 Edit Mode，需要写入 EditBone。
    """
    if not arm_obj or arm_obj.type != 'ARMATURE' or not bone_name:
        return None
    arm_data = arm_obj.data
    if arm_obj.mode == 'EDIT':
        eb = arm_data.edit_bones.get(bone_name)
        if eb:
            return eb
    return arm_data.bones.get(bone_name)


def _target_bone_exists(arm_obj, bone_name):
    """检查目标 armature 上是否存在指定名称的骨骼。
    在 Edit Mode 下同时检查 edit_bones（新创建的骨骼可能不在 bones 快照中）。
    """
    if not arm_obj or arm_obj.type != 'ARMATURE' or not bone_name:
        return False
    arm_data = arm_obj.data
    if arm_data.bones.get(bone_name):
        return True
    # Edit Mode 下额外检查 edit_bones
    if arm_obj.mode == 'EDIT' and arm_data.edit_bones.get(bone_name):
        return True
    return False


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
    
    if not obj or obj.type != 'ARMATURE':
        return
    
    arm_data = obj.data
    ui_state = scene.amazing_rigging_ui
    
    bone_name = None
    if obj.mode == 'POSE':
        active_pose_bone = getattr(context, 'active_pose_bone', None)
        selected_pose_bones = getattr(context, 'selected_pose_bones', [])
        
        if active_pose_bone:
            bone_name = active_pose_bone.name
        elif selected_pose_bones:
            bone_name = selected_pose_bones[0].name
    elif obj.mode == 'EDIT':
        edit_bone = getattr(context, 'edit_bone', None)
        selected_editable_bones = getattr(context, 'selected_editable_bones', [])
        
        if edit_bone:
            bone_name = edit_bone.name
        elif selected_editable_bones:
            bone_name = selected_editable_bones[0].name
        else:
            for eb in arm_data.edit_bones:
                if eb.select:
                    bone_name = eb.name
                    break
    else:
        return
    
    # 关键：检查 bone 是否真的切换了
    global _last_synced_bone, _syncing_ui
    current_bone_key = (arm_data.name, bone_name) if bone_name else None
    
    if current_bone_key == _last_synced_bone:
        return  # 同一个 bone，跳过同步
    
    _last_synced_bone = current_bone_key
    
    # 使用 _syncing_ui 标志防止回调在设置 UI 时修改 bone 数据
    _syncing_ui = True
    try:
        if not bone_name:
            ui_state.target_armature = None
            ui_state.target_bone = ""
            return
        
        # 在 Edit Mode 下，从 EditBone 读取最新的自定义属性
        bone_data = _get_bone_for_read(obj, bone_name)
        if not bone_data:
            return
        
        settings_info = utils_bone_data.get_settings_bone_info(bone_data)
        
        if settings_info:
            target_arm_obj = None
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
    """When target armature changes, clear the bone selection (but NOT the existing settings)"""
    global _syncing_ui, _skip_bone_changed_callback
    
    # 如果 sync_ui 正在更新 UI，跳过回调（防止级联修改 bone 数据）
    if _syncing_ui:
        return
    
    obj = context.active_object
    if not obj or obj.type != 'ARMATURE':
        return

    ui_state = context.scene.amazing_rigging_ui
    
    # 选择 target armature 时，只清空 UI 中的 target_bone 字段
    # 不触发 _on_target_bone_changed 回调（避免错误清空 bone 数据）
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
    
    # 如果 sync_ui 正在更新 UI，跳过回调（防止级联修改 bone 数据）
    if _syncing_ui:
        return
    
    # 如果是 armature 切换导致的清空，不执行任何操作
    if _skip_bone_changed_callback:
        return
    
    obj = context.active_object
    if not obj or obj.type != 'ARMATURE':
        return

    arm_data = obj.data
    ui_state = context.scene.amazing_rigging_ui

    # Get selected bone name
    if obj.mode == 'POSE':
        selected = [pb.name for pb in context.selected_pose_bones]
    elif obj.mode == 'EDIT':
        selected = [eb.name for eb in context.selected_editable_bones]
    else:
        return

    if not selected:
        return
    
    bone_name = selected[0]
    
    # Get writable bone object based on mode
    writable_bone = _get_writable_bone(obj, bone_name)
    if not writable_bone:
        return
    
    # 在 Edit Mode 下从 EditBone 读取最新自定义属性
    bone_for_read = _get_bone_for_read(obj, bone_name)
    
    arm_obj = ui_state.target_armature
    if not arm_obj or arm_obj.type != 'ARMATURE':
        return

    # If bone is selected, apply; if empty, clear
    if ui_state.target_bone:
        # 在 Edit Mode 下同时检查 edit_bones（新创建的骨骼可能不在 bones 快照中）
        if _target_bone_exists(arm_obj, ui_state.target_bone):
            # 获取目标骨骼的可写对象（用于写入反向引用）
            target_bone_for_write = _get_target_bone_for_write(arm_obj, ui_state.target_bone)
            
            # Get current settings info before setting new one
            current_info = utils_bone_data.get_settings_bone_info(bone_for_read) if bone_for_read else None
            if current_info:
                # 获取当前关联的主导骨骼的可写对象
                current_target_for_write = None
                current_arm_obj = None
                for scene_obj in context.scene.objects:
                    if scene_obj.type == 'ARMATURE' and scene_obj.data.name == current_info['armature_name']:
                        current_arm_obj = scene_obj
                        break
                if current_arm_obj:
                    current_target_for_write = _get_target_bone_for_write(current_arm_obj, current_info['bone_name'])
                utils_bone_data.clear_settings_bone(writable_bone, target_bone_info=current_info, target_bone_for_write=current_target_for_write)
            
            utils_bone_data.set_settings_bone(
                writable_bone,
                ui_state.target_bone,
                arm_obj.data,
                source_arm_data=obj.data,
                source_bone=writable_bone,
                target_bone_for_write=target_bone_for_write
            )
            for area in context.screen.areas:
                area.tag_redraw()
    else:
        settings_info = utils_bone_data.get_settings_bone_info(bone_for_read) if bone_for_read else None
        # 获取主导骨骼的可写对象
        target_bone_for_write = None
        if settings_info:
            for scene_obj in context.scene.objects:
                if scene_obj.type == 'ARMATURE' and scene_obj.data.name == settings_info['armature_name']:
                    target_bone_for_write = _get_target_bone_for_write(scene_obj, settings_info['bone_name'])
                    break
        utils_bone_data.clear_settings_bone(writable_bone, target_bone_info=settings_info, target_bone_for_write=target_bone_for_write)
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


# ── Bone Selection Menu (mimics constraint bone dropdown) ──

class AMAZING_RIGGING_MT_bone_selection(Menu):
    """Bone selection popup menu - appears when clicking dropdown arrow"""
    bl_label = "Select Bone"
    bl_idname = "AMAZING_RIGGING_MT_bone_selection"

    def draw(self, context):
        layout = self.layout
        ui_state = context.scene.amazing_rigging_ui
        arm_obj = ui_state.target_armature

        if not arm_obj or arm_obj.type != 'ARMATURE' or not arm_obj.data:
            layout.label(text="No target armature selected", icon='INFO')
            return

        # Get current selected bone to exclude
        obj = context.active_object
        exclude_bone = None
        if obj and obj.type == 'ARMATURE':
            if obj.mode == 'POSE':
                selected = [pb.name for pb in context.selected_pose_bones]
            elif obj.mode == 'EDIT':
                selected = [eb.name for eb in context.selected_editable_bones]
            else:
                selected = []
            exclude_bone = selected[0] if selected else None

        for bone in arm_obj.data.bones:
            if exclude_bone and bone.name == exclude_bone:
                continue
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


# ── Helper for clear operators ──

def _get_target_bone_for_write_from_info(context, settings_info):
    """从 settings_info 获取主导骨骼的可写对象"""
    if not settings_info:
        return None
    for scene_obj in context.scene.objects:
        if scene_obj.type == 'ARMATURE' and scene_obj.data.name == settings_info['armature_name']:
            return _get_target_bone_for_write(scene_obj, settings_info['bone_name'])
    return None


# ── Clear Operators ──

class AMAZING_RIGGING_OT_clear_target(Operator):
    """Clear target armature and remove settings bone association"""
    bl_idname = "armature.amazing_rigging_clear_target"
    bl_label = ""
    bl_description = "Clear target and remove settings bone association"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select an armature object")
            return {'CANCELLED'}

        arm_data = obj.data

        # Get selected bone name
        if obj.mode == 'POSE':
            selected = [pb.name for pb in context.selected_pose_bones]
        elif obj.mode == 'EDIT':
            selected = [eb.name for eb in context.selected_editable_bones]
        else:
            self.report({'ERROR'}, "Must be in Edit or Pose mode")
            return {'CANCELLED'}
        
        if not selected:
            return {'CANCELLED'}
        
        bone_name = selected[0]
        
        # Get writable bone based on mode
        writable_bone = _get_writable_bone(obj, bone_name)
        bone_for_read = _get_bone_for_read(obj, bone_name)

        if writable_bone:
            settings_info = utils_bone_data.get_settings_bone_info(bone_for_read) if bone_for_read else None
            target_bone_for_write = _get_target_bone_for_write_from_info(context, settings_info)
            utils_bone_data.clear_settings_bone(writable_bone, target_bone_info=settings_info, target_bone_for_write=target_bone_for_write)

        # Clear UI state（使用 _syncing_ui 防止回调冗余修改数据）
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
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select an armature object")
            return {'CANCELLED'}

        arm_data = obj.data

        # Get selected bone name
        if obj.mode == 'POSE':
            selected = [pb.name for pb in context.selected_pose_bones]
        elif obj.mode == 'EDIT':
            selected = [eb.name for eb in context.selected_editable_bones]
        else:
            self.report({'ERROR'}, "Must be in Edit or Pose mode")
            return {'CANCELLED'}

        if not selected:
            return {'CANCELLED'}
        
        bone_name = selected[0]
        
        # Get writable bone based on mode
        writable_bone = _get_writable_bone(obj, bone_name)
        bone_for_read = _get_bone_for_read(obj, bone_name)

        if writable_bone:
            settings_info = utils_bone_data.get_settings_bone_info(bone_for_read) if bone_for_read else None
            target_bone_for_write = _get_target_bone_for_write_from_info(context, settings_info)
            utils_bone_data.clear_settings_bone(writable_bone, target_bone_info=settings_info, target_bone_for_write=target_bone_for_write)

        # Clear UI state（使用 _syncing_ui 防止回调冗余修改数据）
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
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select an armature object")
            return {'CANCELLED'}

        arm_data = obj.data

        # Get selected bone name
        if obj.mode == 'POSE':
            selected = [pb.name for pb in context.selected_pose_bones]
        elif obj.mode == 'EDIT':
            selected = [eb.name for eb in context.selected_editable_bones]
        else:
            self.report({'ERROR'}, "Must be in Edit or Pose mode")
            return {'CANCELLED'}

        if not selected:
            return {'CANCELLED'}
        
        bone_name = selected[0]
        
        # 在 Edit Mode 下从 EditBone 读取最新数据
        bone_data = _get_bone_for_read(obj, bone_name)

        if not bone_data:
            return {'CANCELLED'}

        # Get related settings bone
        settings_bone = utils_bone_data.get_settings_bone_object(bone_data)
        if not settings_bone:
            self.report({'WARNING'}, "No related settings bone found")
            return {'CANCELLED'}

        # Find the armature object that contains the settings bone
        info = utils_bone_data.get_settings_bone_info(bone_data)
        settings_arm_obj = None
        for scene_obj in context.scene.objects:
            if scene_obj.type == 'ARMATURE' and scene_obj.data.name == info['armature_name']:
                settings_arm_obj = scene_obj
                break

        if not settings_arm_obj:
            self.report({'WARNING'}, "Settings armature not found in scene")
            return {'CANCELLED'}

        # Switch to the settings armature object
        context.view_layer.objects.active = settings_arm_obj
        settings_arm_data = settings_arm_obj.data

        # Select the settings bone based on current mode
        if obj.mode == 'POSE':
            bpy.ops.object.mode_set(mode='POSE')
            for pb in settings_arm_obj.pose.bones:
                pb.bone.select = False
            pose_bone = settings_arm_obj.pose.bones.get(settings_bone.name)
            if pose_bone:
                pose_bone.bone.select = True
                settings_arm_data.bones.active = pose_bone.bone
        elif obj.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
            # 使用 settings_arm_obj.data.edit_bones 而非 arm_data.edit_bones
            for eb in settings_arm_data.edit_bones:
                eb.select = False
            edit_bone = settings_arm_data.edit_bones.get(settings_bone.name)
            if edit_bone:
                edit_bone.select = True
                settings_arm_data.edit_bones.active = edit_bone

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Selected bone: {settings_bone.name}")
        return {'FINISHED'}


class AMAZING_RIGGING_OT_clear_related_bone(Operator):
    """Clear the relationship with related settings bone"""
    bl_idname = "armature.amazing_rigging_clear_related_bone"
    bl_label = ""
    bl_description = "Remove settings bone association"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select an armature object")
            return {'CANCELLED'}

        arm_data = obj.data

        # Get selected bone name
        if obj.mode == 'POSE':
            selected = [pb.name for pb in context.selected_pose_bones]
        elif obj.mode == 'EDIT':
            selected = [eb.name for eb in context.selected_editable_bones]
        else:
            self.report({'ERROR'}, "Must be in Edit or Pose mode")
            return {'CANCELLED'}

        if not selected:
            return {'CANCELLED'}
        
        bone_name = selected[0]
        
        # Get writable bone based on mode
        writable_bone = _get_writable_bone(obj, bone_name)
        bone_for_read = _get_bone_for_read(obj, bone_name)

        if writable_bone:
            settings_info = utils_bone_data.get_settings_bone_info(bone_for_read) if bone_for_read else None
            target_bone_for_write = _get_target_bone_for_write_from_info(context, settings_info)
            utils_bone_data.clear_settings_bone(writable_bone, target_bone_info=settings_info, target_bone_for_write=target_bone_for_write)

        # Clear UI state（使用 _syncing_ui 防止回调冗余修改数据）
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
        # Find the armature object
        dependent_arm_obj = None
        for scene_obj in context.scene.objects:
            if scene_obj.type == 'ARMATURE':
                if self.armature_uuid and hasattr(scene_obj.data, 'uuid') and scene_obj.data.uuid == self.armature_uuid:
                    dependent_arm_obj = scene_obj
                    break
                elif scene_obj.data.name == self.armature_name:
                    dependent_arm_obj = scene_obj
                    break

        if not dependent_arm_obj:
            self.report({'WARNING'}, "Dependent bone's armature not found in scene")
            return {'CANCELLED'}

        # Switch to the dependent armature object
        context.view_layer.objects.active = dependent_arm_obj
        dep_arm_data = dependent_arm_obj.data

        # Select the dependent bone based on current mode
        if context.active_object.mode == 'POSE':
            bpy.ops.object.mode_set(mode='POSE')
            for pb in dependent_arm_obj.pose.bones:
                pb.bone.select = False
            pose_bone = dependent_arm_obj.pose.bones.get(self.bone_name)
            if pose_bone:
                pose_bone.bone.select = True
                dep_arm_data.bones.active = pose_bone.bone
        elif context.active_object.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
            for eb in dep_arm_data.edit_bones:
                eb.select = False
            edit_bone = dep_arm_data.edit_bones.get(self.bone_name)
            if edit_bone:
                edit_bone.select = True
                dep_arm_data.edit_bones.active = edit_bone

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
        # Find the dependent bone's armature
        dependent_arm_obj = None
        for scene_obj in context.scene.objects:
            if scene_obj.type == 'ARMATURE':
                if self.armature_uuid and hasattr(scene_obj.data, 'uuid') and scene_obj.data.uuid == self.armature_uuid:
                    dependent_arm_obj = scene_obj
                    break
                elif scene_obj.data.name == self.armature_name:
                    dependent_arm_obj = scene_obj
                    break

        if not dependent_arm_obj:
            self.report({'WARNING'}, "Dependent bone's armature not found")
            return {'CANCELLED'}

        dep_arm_data = dependent_arm_obj.data

        # Get the dependent bone object（可写版本）
        if dependent_arm_obj.mode == 'EDIT':
            dependent_bone = dep_arm_data.edit_bones.get(self.bone_name)
        else:
            dependent_bone = dep_arm_data.bones.get(self.bone_name)

        if not dependent_bone:
            self.report({'WARNING'}, f"Dependent bone '{self.bone_name}' not found")
            return {'CANCELLED'}

        # 读取 settings info 并传递给 clear_settings_bone（用于清理反向引用）
        settings_info = utils_bone_data.get_settings_bone_info(dependent_bone)
        target_bone_for_write = None
        if settings_info:
            for scene_obj in context.scene.objects:
                if scene_obj.type == 'ARMATURE' and scene_obj.data.name == settings_info['armature_name']:
                    target_bone_for_write = _get_target_bone_for_write(scene_obj, settings_info['bone_name'])
                    break
        utils_bone_data.clear_settings_bone(dependent_bone, target_bone_info=settings_info, target_bone_for_write=target_bone_for_write)

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Cleared association for bone: {self.bone_name}")
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
        return obj.mode in ('EDIT', 'POSE')

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        arm_data = obj.data
        ui_state = context.scene.amazing_rigging_ui
        
        # Get current bone from context
        bone_name = None
        if obj.mode == 'POSE':
            if context.bone:
                bone_name = context.bone.name
            elif context.selected_pose_bones:
                bone_name = context.selected_pose_bones[0].name
        elif obj.mode == 'EDIT':
            if context.edit_bone:
                bone_name = context.edit_bone.name
            elif context.selected_editable_bones:
                bone_name = context.selected_editable_bones[0].name
        
        if not bone_name:
            layout.label(text="No bone selected", icon='INFO')
            return

        # 在 Edit Mode 下从 EditBone 读取最新自定义属性
        bone_data = _get_bone_for_read(obj, bone_name)

        if not bone_data:
            return

        settings_info = utils_bone_data.get_settings_bone_info(bone_data)

        # ── Set Settings Bone ──
        box = layout.box()
        box.label(text="Set Settings Bone:", icon='BONE_DATA')

        # Target armature row: object field + delete button
        row = box.row(align=True)
        row.prop(ui_state, "target_armature", text="Target")
        if ui_state.target_armature:
            row.operator("armature.amazing_rigging_clear_target", text="", icon='X')

        # Target bone row: text input + dropdown + delete button
        row = box.row(align=True)
        row.prop(ui_state, "target_bone", text="Bone", icon='BONE_DATA')
        if ui_state.target_bone:
            row.menu("AMAZING_RIGGING_MT_bone_selection", text="", icon='DOWNARROW_HLT')
            row.operator("armature.amazing_rigging_clear_bone", text="", icon='X')
        elif ui_state.target_armature:
            row.menu("AMAZING_RIGGING_MT_bone_selection", text="", icon='DOWNARROW_HLT')

        # ── Related Bone (显示已关联的 settings bone) ──
        if settings_info:
            layout.separator()
            settings_bone_obj = utils_bone_data.get_settings_bone_object(bone_data)
            if settings_bone_obj:
                row = layout.row(align=True)
                row.label(text="Related Bone:", icon='LINKED')
                row.label(text=settings_info['armature_name'])
                row.label(text=settings_info['bone_name'], icon='BONE_DATA')
                row.operator("armature.amazing_rigging_select_related_bone", text="", icon='FILE_PARENT')
                row.operator("armature.amazing_rigging_clear_related_bone", text="", icon='X')

        # ── Dependent Bones (显示关联到当前骨骼的从属骨骼) ──
        dependent_bones = utils_bone_data.get_dependent_bones(bone_data)
        if dependent_bones:
            layout.separator()
            box_dep = layout.box()
            box_dep.label(text="Dependent Bones:", icon='UNLINKED')

            for dep in dependent_bones:
                row = box_dep.row(align=True)
                row.label(text=dep['bone_name'], icon='BONE_DATA')
                if dep.get('armature_name'):
                    row.label(text=f"({dep['armature_name']})")

                # 跳转按钮
                op = row.operator("armature.amazing_rigging_select_dependent_bone", text="", icon='FILE_PARENT')
                op.bone_name = dep['bone_name']
                op.armature_name = dep.get('armature_name', '')
                op.armature_uuid = dep.get('armature_uuid', '')

                # 删除按钮
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
    AMAZING_RIGGING_PT_bone_settings,
]


def register():
    bpy.types.Scene.amazing_rigging_ui = PointerProperty(type=AMAZING_RIGGING_PG_settings_bone_ui)


def unregister():
    del bpy.types.Scene.amazing_rigging_ui
