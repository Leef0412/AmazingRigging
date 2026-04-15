import bpy
from bpy.types import Panel, Operator
from bpy.props import StringProperty, IntProperty
from datetime import datetime
from . import utils_bone_data

_last_pose_armature = None

# Independent fold state for ui_panel (not shared with Split Bones Rules panel)
_ui_panel_rule_hidden = {}  # {armature_data_name_rule_idx: is_hidden}

# Independent fold state for pockets per rule (not shared across rules)
_ui_panel_pocket_hidden = {}  # {armature_data_name_rule_idx_pocket_row: is_hidden}

class AMAZING_RIGGING_OT_toggle_ui_panel_rule(Operator):
    bl_idname = "armature.amazing_rigging_toggle_ui_panel_rule"
    bl_label = "Toggle UI Panel Rule Visibility"
    bl_description = "Toggle rule visibility in UI panel only"
    bl_options = {'INTERNAL'}

    rule_index: IntProperty()

    def execute(self, context):
        global _ui_panel_rule_hidden
        arm_data = context.active_object.data

        rule_key = f"{arm_data.name}_{self.rule_index}"
        current_hidden = _ui_panel_rule_hidden.get(rule_key, False)
        _ui_panel_rule_hidden[rule_key] = not current_hidden

        for area in context.screen.areas:
            area.tag_redraw()

        status = "expanded" if current_hidden else "collapsed"
        self.report({'INFO'}, f"Rule {self.rule_index} {status}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_toggle_ui_panel_pocket(Operator):
    bl_idname = "armature.amazing_rigging_toggle_ui_panel_pocket"
    bl_label = "Toggle UI Panel Pocket Visibility"
    bl_description = "Toggle pocket visibility in UI panel only"
    bl_options = {'INTERNAL'}

    pocket_row: IntProperty()
    rule_index: IntProperty()

    def execute(self, context):
        global _ui_panel_pocket_hidden
        arm_data = context.active_object.data

        # Use independent fold state per rule
        pocket_key = f"{arm_data.name}_{self.rule_index}_{self.pocket_row}"
        current_hidden = _ui_panel_pocket_hidden.get(pocket_key, False)
        _ui_panel_pocket_hidden[pocket_key] = not current_hidden

        for area in context.screen.areas:
            area.tag_redraw()

        status = "expanded" if current_hidden else "collapsed"
        self.report({'INFO'}, f"Pocket {self.pocket_row} in rule {self.rule_index} {status}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_toggle_bone_collection(Operator):
    bl_idname = "armature.amazing_rigging_toggle_collection"
    bl_label = "Toggle Collection Visibility"
    bl_description = "Toggle bone collection visibility"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: StringProperty()

    def execute(self, context):
        arm_data = context.active_object.data
        b_cols = getattr(arm_data, "collections", None)

        if b_cols and self.collection_name in b_cols:
            b_col = b_cols[self.collection_name]
            b_col.is_visible = not b_col.is_visible

            for area in context.screen.areas:
                area.tag_redraw()

            status = "shown" if b_col.is_visible else "hidden"
            self.report({'INFO'}, f"'{self.collection_name}' {status}")

        return {'FINISHED'}

class AMAZING_RIGGING_OT_show_all(Operator):
    bl_idname = "armature.collection_show_all"
    bl_label = "Show All Collections"
    bl_description = "Show all bone collections"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_data = context.active_object.data
        b_cols = getattr(arm_data, "collections", None)

        if b_cols:
            for b_col in b_cols:
                b_col.is_visible = True

            for area in context.screen.areas:
                area.tag_redraw()

            self.report({'INFO'}, "All collections shown")

        return {'FINISHED'}

class AMAZING_RIGGING_OT_hide_all(Operator):
    bl_idname = "armature.collection_hide_all"
    bl_label = "Hide All Collections"
    bl_description = "Hide all bone collections"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_data = context.active_object.data
        b_cols = getattr(arm_data, "collections", None)

        if b_cols:
            for b_col in b_cols:
                b_col.is_visible = False

            for area in context.screen.areas:
                area.tag_redraw()

            self.report({'INFO'}, "All collections hidden")

        return {'FINISHED'}

def update_pose_armature_cache(context):
    global _last_pose_armature
    obj = context.active_object

    if obj and obj.type == 'ARMATURE' and obj.mode == 'POSE':
        _last_pose_armature = obj
        print(f"  - [缓存更新] _last_pose_armature = {obj.name}")
    elif obj and obj.type != 'ARMATURE':
        in_pose_mode = False
        for scene_obj in context.scene.objects:
            if scene_obj.type == 'ARMATURE' and scene_obj.mode == 'POSE':
                in_pose_mode = True
                break

        if not in_pose_mode and _last_pose_armature:
            print(f"  - [缓存清空] _last_pose_armature 从 '{_last_pose_armature.name}' 清空为 None")
            _last_pose_armature = None

def _get_target_armature(context):
    """获取目标 Armature 对象"""
    global _last_pose_armature
    obj = context.active_object

    if obj and obj.type == 'ARMATURE':
        return obj
    elif _last_pose_armature:
        return _last_pose_armature
    return None

def _draw_rule_content(layout, context, arm_data, rule_idx, rule_name):
    """绘制单个规则的 bone grid 内容（含内层折叠机制）"""
    global _ui_panel_rule_hidden, _ui_panel_pocket_hidden
    
    grid_data = getattr(arm_data, "amazing_grid_data", [])
    pockets = getattr(arm_data, "amazing_bone_pockets", [])
    b_cols = getattr(arm_data, "collections", None)

    if not grid_data or len(grid_data) == 0:
        return

    rule_key = f"{arm_data.name}_{rule_idx}"
    is_hidden = _ui_panel_rule_hidden.get(rule_key, False)

    # Filter items for this rule
    rule_items = [item for item in grid_data if item.rule_index == rule_idx]
    
    if not rule_items:
        layout.label(text="No bones match this rule", icon='INFO')
        return

    # Rule header with fold button
    row_header = layout.row()
    icon_type = 'TRIA_RIGHT' if is_hidden else 'TRIA_DOWN'

    toggle_op = row_header.operator("armature.amazing_rigging_toggle_ui_panel_rule", text=f"{rule_name} ({len(rule_items)})", icon=icon_type, emboss=False)
    toggle_op.rule_index = rule_idx

    # Rule content (when expanded)
    if not is_hidden:
        # Filter pockets for this rule (by row AND rule_index)
        rule_rows = {item.row for item in rule_items}
        rule_pockets = [p for p in pockets if p.row in rule_rows and p.rule_index == rule_idx]
        pocket_rows = {p.row for p in rule_pockets}

        # Sort items by row/col
        sorted_items = sorted(rule_items, key=lambda x: (x.row, x.col))
        rows_dict = {}
        for item in sorted_items:
            if item.row not in rows_dict:
                rows_dict[item.row] = []
            rows_dict[item.row].append(item)

        sorted_pocket_rows = sorted(pocket_rows)

        # Helper function to find which pocket affects a row
        def get_pocket_for_row(row_idx):
            for i, pocket_row in enumerate(sorted_pocket_rows):
                if pocket_row == row_idx:
                    for pocket in rule_pockets:
                        if pocket.row == pocket_row:
                            return pocket
                elif pocket_row < row_idx:
                    next_pocket_row = sorted_pocket_rows[i + 1] if i + 1 < len(sorted_pocket_rows) else None
                    if next_pocket_row is None or row_idx < next_pocket_row:
                        for pocket in rule_pockets:
                            if pocket.row == pocket_row:
                                return pocket
            return None

        def is_pocket_hidden(pocket):
            if pocket is None:
                return False
            pocket_key = f"{arm_data.name}_{rule_idx}_{pocket.row}"
            return _ui_panel_pocket_hidden.get(pocket_key, False)

        # Group items by pocket or no-pocket
        pocket_items_dict = {}
        for pocket in rule_pockets:
            pocket_items_dict[pocket.row] = []
        no_pocket_items = []
        
        for row_idx in sorted(rows_dict.keys()):
            pocket = get_pocket_for_row(row_idx)
            if pocket:
                if pocket.row not in pocket_items_dict:
                    pocket_items_dict[pocket.row] = []
                pocket_items_dict[pocket.row].extend(rows_dict[row_idx])
            else:
                no_pocket_items.extend(rows_dict[row_idx])

        # Draw pockets first (each pocket wraps its items)
        for pocket_row in sorted_pocket_rows:
            pocket = None
            for p in rule_pockets:
                if p.row == pocket_row:
                    pocket = p
                    break
            
            if not pocket:
                continue
            
            # Pocket box
            pocket_box = layout.box()
            pocket_header = pocket_box.row()
            
            # Use independent fold state per rule
            pocket_key = f"{arm_data.name}_{rule_idx}_{pocket_row}"
            is_pocket_hidden_val = _ui_panel_pocket_hidden.get(pocket_key, False)
            icon_type_pocket = 'TRIA_RIGHT' if is_pocket_hidden_val else 'TRIA_DOWN'
            
            toggle_pocket_op = pocket_header.operator("armature.amazing_rigging_toggle_ui_panel_pocket", text=pocket.name, icon=icon_type_pocket, emboss=False)
            toggle_pocket_op.pocket_row = pocket_row
            toggle_pocket_op.rule_index = rule_idx
            
            # Pocket content (when expanded)
            if not is_pocket_hidden_val:
                pocket_items = pocket_items_dict.get(pocket_row, [])
                if pocket_items:
                    # Group by row
                    pocket_rows_dict = {}
                    for item in pocket_items:
                        if item.row not in pocket_rows_dict:
                            pocket_rows_dict[item.row] = []
                        pocket_rows_dict[item.row].append(item)
                    
                    # Draw items row by row
                    for item_row in sorted(pocket_rows_dict.keys()):
                        row_items = pocket_rows_dict[item_row]
                        if row_items:
                            row_flow = pocket_box.row(align=True)
                            for item in row_items:
                                if item.is_hidden:
                                    continue
                                
                                if b_cols and item.name in b_cols:
                                    b_col = b_cols[item.name]
                                    row_flow.prop(b_col, "is_visible", text=item.note, toggle=True)
                                else:
                                    row_flow.label(text=item.note)

        # Draw items without pocket
        if no_pocket_items:
            no_pocket_rows_dict = {}
            for item in no_pocket_items:
                if item.row not in no_pocket_rows_dict:
                    no_pocket_rows_dict[item.row] = []
                no_pocket_rows_dict[item.row].append(item)
            
            for item_row in sorted(no_pocket_rows_dict.keys()):
                row_items = no_pocket_rows_dict[item_row]
                if row_items:
                    row_flow = layout.row(align=True)
                    for item in row_items:
                        if item.is_hidden:
                            continue
                        
                        if b_cols and item.name in b_cols:
                            b_col = b_cols[item.name]
                            row_flow.prop(b_col, "is_visible", text=item.note, toggle=True)
                        else:
                            row_flow.label(text=item.note)

def _draw_settings_bone_summary(layout, context, armature):
    """在侧栏显示主导骨骼（settings bone）的 Custom Properties"""
    if not armature:
        return

    obj = context.active_object
    if not obj or obj.type != 'ARMATURE':
        return

    if obj.mode != 'POSE':
        return

    # 获取当前选中骨骼（Pose Mode only）
    from . import ui_bone_properties
    bone_name = ui_bone_properties.get_active_bone_name(context, obj)
    if not bone_name:
        return

    pose_bone = obj.pose.bones.get(bone_name)
    if not pose_bone:
        return

    # 获取关联的 settings bone 信息
    settings_info = utils_bone_data.get_settings_bone_info(pose_bone)
    if not settings_info:
        return

    # 查找 settings bone 所属的 armature 对象
    settings_arm_obj = utils_bone_data.find_armature_obj_by_uuid(settings_info['armature_uuid'])
    if not settings_arm_obj:
        arm_data = bpy.data.armatures.get(settings_info['armature_name'])
        if arm_data:
            for o in bpy.data.objects:
                if o.type == 'ARMATURE' and o.data == arm_data:
                    settings_arm_obj = o
                    break
    if not settings_arm_obj:
        return

    # 获取 settings PoseBone 对象
    settings_pb = settings_arm_obj.pose.bones.get(settings_info['bone_name'])
    if not settings_pb:
        return

    # 读取 settings bone 的自定义属性（过滤内部键名）
    prop_keys = [k for k in settings_pb.keys() if k not in utils_bone_data.INTERNAL_KEYS]

    if not prop_keys:
        return

    # 显示标题（settings bone 名称）
    box = layout.box()
    box.label(text="Settings Bone: " + settings_info['bone_name'], icon='BONE_DATA')

    for key in prop_keys:
        value = settings_pb[key]
        row = box.row()

        if isinstance(value, (int, float)):
            row.prop(settings_pb, f'["{key}"]', text=key)
        elif isinstance(value, str):
            row.label(text=f"{key}: {value}")
        else:
            row.label(text=f"{key}: {str(value)}")

def _draw_custom_properties(layout, context, armature):
    """绘制 Custom Properties 面板 - 过滤内部属性"""
    if not armature:
        return

    obj = context.active_object
    if not obj or obj.type != 'ARMATURE':
        return

    # 仅 Pose Mode 显示
    if obj.mode != 'POSE':
        return

    # 获取选中的 PoseBone
    selected_pbs = context.selected_pose_bones
    if not selected_pbs:
        return

    pose_bone = selected_pbs[0]
    if not pose_bone:
        return

    # 过滤内部属性
    prop_keys = [k for k in pose_bone.keys() if k not in utils_bone_data.INTERNAL_KEYS]

    if not prop_keys:
        return

    # 显示 Custom Properties
    box = layout.box()
    box.label(text="Custom Properties", icon='PROPERTIES')

    for key in prop_keys:
        value = pose_bone[key]
        row = box.row()

        if isinstance(value, (int, float)):
            row.prop(pose_bone, f'["{key}"]', text=key)
        elif isinstance(value, str):
            row.label(text=f"{key}: {value}")
        else:
            row.label(text=f"{key}: {str(value)}")

# ============================================================================
# Panel 1: Amazing Scripts (Active Armature + Collection Options)
# ============================================================================
class AMAZING_RIGGING_PT_amazing_scripts(Panel):
    bl_label = "Amazing Scripts"
    bl_idname = "AMAZING_RIGGING_PT_amazing_scripts"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Amazing Rigging"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        update_pose_armature_cache(context)

        target_armature = _get_target_armature(context)

        if not target_armature:
            if not context.active_object:
                layout.label(text="Please select an object", icon='INFO')
            else:
                layout.label(text="No active armature found", icon='INFO')
            return

        arm_data = target_armature.data
        layout.label(text=f"Active Armature: {target_armature.name}", icon='ARMATURE_DATA')
        layout.separator()

        layout.label(text="Collection Options", icon='FILE_SCRIPT')
        row_scripts_1 = layout.row()
        row_scripts_1.operator("armature.amazing_rigging_clean_deform", text="Clean Deform", icon='BRUSH_DATA')

        active_obj = context.active_object
        current_mode = active_obj.mode if active_obj else 'OBJECT'
        if current_mode == 'WEIGHT_PAINT':
            row_scripts_1.operator("armature.amazing_rigging_goto_pose", text="Pose Mode", icon='POSE_HLT')
        else:
            row_scripts_1.operator("armature.amazing_rigging_goto_weight_paint", text="Weight Paint", icon='TPAINT_HLT')

        row_scripts_2 = layout.row()
        row_scripts_2.operator("armature.amazing_rigging_ot_clean_transform", text="Clean Transform", icon='LOOP_BACK')
        row_scripts_2.operator("armature.collection_show_all", text="Export to UE", icon='EXPORT')

# ============================================================================
# Panel 2: Rig Properties (Custom Properties + Settings Bone)
# ============================================================================
class AMAZING_RIGGING_PT_rig_properties(Panel):
    bl_label = "Rig Properties"
    bl_idname = "AMAZING_RIGGING_PT_rig_properties"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Amazing Rigging"
    bl_order = 1

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def draw(self, context):
        layout = self.layout
        target_armature = _get_target_armature(context)
        if not target_armature:
            return

        _draw_custom_properties(layout, context, target_armature)
        _draw_settings_bone_summary(layout, context, target_armature)

# ============================================================================
# Panel 3: Bone Collections (Show All / Hide All + All Rules)
# ============================================================================
class AMAZING_RIGGING_PT_bone_collections(Panel):
    bl_label = "Bone Collections"
    bl_idname = "AMAZING_RIGGING_PT_bone_collections"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Amazing Rigging"
    bl_order = 2

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            return False
        arm_data = obj.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])
        return len(grid_data) > 0

    def draw(self, context):
        layout = self.layout
        
        # Show All / Hide All 按钮
        row_ctrl = layout.row()
        row_ctrl.operator("armature.collection_show_all", text="Show All", icon='RESTRICT_VIEW_OFF')
        row_ctrl.operator("armature.collection_hide_all", text="Hide All", icon='RESTRICT_VIEW_ON')
        
        layout.separator()
        
        # 获取目标 armature
        target_armature = _get_target_armature(context)
        if not target_armature:
            return
        
        arm_data = target_armature.data
        rules = getattr(arm_data, "amazing_split_rules", [])
        
        if not rules:
            layout.label(text="No split rules defined", icon='INFO')
            return
        
        # 遍历所有 rules 并绘制（跳过空规则）
        for rule_idx, rule in enumerate(rules):
            # 检查该规则是否有匹配的骨骼
            grid_data = getattr(arm_data, "amazing_grid_data", [])
            rule_items = [item for item in grid_data if item.rule_index == rule_idx]
            
            # 如果该规则没有匹配的骨骼，跳过不绘制
            if not rule_items:
                continue
            
            # 绘制分隔线
            layout.separator()
            
            # 绘制规则内容（复用现有逻辑）
            rule_box = layout.box()
            _draw_rule_content(rule_box, context, arm_data, rule_idx, rule.name)

# Classes list for registration
classes = [
    AMAZING_RIGGING_OT_toggle_ui_panel_rule,
    AMAZING_RIGGING_OT_toggle_ui_panel_pocket,
    AMAZING_RIGGING_OT_toggle_bone_collection,
    AMAZING_RIGGING_OT_show_all,
    AMAZING_RIGGING_OT_hide_all,
    AMAZING_RIGGING_PT_amazing_scripts,
    AMAZING_RIGGING_PT_rig_properties,
    AMAZING_RIGGING_PT_bone_collections,
]
